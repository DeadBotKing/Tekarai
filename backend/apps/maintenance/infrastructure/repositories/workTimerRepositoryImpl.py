"""Django repository for technician work timers.

The only genuinely hard part is *starting*: "is a timer already running?"
followed by "insert one" is a read-then-write race. Two taps a few hundred
milliseconds apart — or a queued offline start arriving while the technician
presses start again online — would both see "nothing running" and insert two
spans, and the work order would be billed twice for the same hour.

Two guards, deliberately belt-and-braces:

* the insert happens inside ``transaction.atomic`` after locking the work
  order row, which serialises concurrent starts on the same order;
* the table carries a filtered unique constraint
  (``uq_work_timer_one_running_per_tech``), so even a racing *other process*
  that skipped this code path cannot produce two running spans.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db import IntegrityError, transaction

from apps.maintenance.domain.entities.workTimer import WorkTimer
from apps.maintenance.domain.exceptions.fieldOpsErrors import (
    TimerAlreadyRunningError,
    TimerNotRunningError,
)
from apps.maintenance.infrastructure.models import WorkOrderModel, WorkTimerModel
from apps.sharedKernel.domain.errors import EntityNotFoundError


class WorkTimerRepositoryDjango:
    # -- mapping ---------------------------------------------------------------
    @staticmethod
    def _entity(model: WorkTimerModel) -> WorkTimer:
        return WorkTimer(
            id=model.id,
            tenantId=model.tenantId,
            workOrderId=model.workOrderId,
            technicianName=model.technicianName,
            startedAt=model.startedAt,
            endedAt=model.endedAt,
            pausedSeconds=int(model.pausedSeconds),
            hourlyRate=model.hourlyRate,
            startNote=model.startNote,
            endNote=model.endNote,
            labourEntryId=model.labourEntryId,
            capturedOffline=bool(model.capturedOffline),
            startedVia=model.startedVia,
            technicianUserId=model.technicianUserId,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
        )

    @staticmethod
    def _workOrderOr404(tenantId: uuid.UUID, workOrderId: uuid.UUID) -> WorkOrderModel:
        order = WorkOrderModel.objects.filter(
            id=workOrderId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        if order is None:
            raise EntityNotFoundError("WorkOrder", str(workOrderId))
        return order

    # -- commands --------------------------------------------------------------
    def startExclusive(self, timer: WorkTimer) -> WorkTimer:
        with transaction.atomic():
            # Lock the order, not the timer table: the thing we are protecting
            # is "one running span per technician *on this order*".
            WorkOrderModel.objects.select_for_update().filter(
                id=timer.workOrderId, tenantId=timer.tenantId, deletedAt__isnull=True
            ).first()
            self._workOrderOr404(timer.tenantId, timer.workOrderId)
            running = (
                WorkTimerModel.objects.filter(
                    tenantId=timer.tenantId,
                    workOrderId=timer.workOrderId,
                    technicianName=timer.technicianName.strip(),
                    endedAt__isnull=True,
                )
                .order_by("-startedAt")
                .first()
            )
            if running is not None:
                raise TimerAlreadyRunningError(
                    "A timer is already running for this technician on this order.",
                    fieldErrors={"timerId": str(running.id)},
                )
            try:
                model = WorkTimerModel.objects.create(
                    id=timer.id,
                    tenantId=timer.tenantId,
                    workOrderId=timer.workOrderId,
                    technicianName=timer.technicianName.strip(),
                    technicianUserId=timer.technicianUserId,
                    startedAt=timer.startedAt,
                    hourlyRate=timer.hourlyRate,
                    startNote=timer.startNote,
                    capturedOffline=timer.capturedOffline,
                    startedVia=timer.startedVia,
                )
            except IntegrityError as error:  # pragma: no cover — DB-level race
                raise TimerAlreadyRunningError(
                    "A timer is already running for this technician on this order."
                ) from error
        model.refresh_from_db()
        return self._entity(model)

    def stop(self, timer: WorkTimer) -> WorkTimer:
        with transaction.atomic():
            model = (
                WorkTimerModel.objects.select_for_update()
                .filter(id=timer.id, tenantId=timer.tenantId)
                .first()
            )
            if model is None:
                raise EntityNotFoundError("WorkTimer", str(timer.id))
            if model.endedAt is not None:
                raise TimerNotRunningError(
                    "This timer has already been stopped.",
                    fieldErrors={"timerId": str(timer.id)},
                )
            model.endedAt = timer.endedAt
            model.endNote = timer.endNote
            model.pausedSeconds = int(timer.pausedSeconds)
            model.labourEntryId = timer.labourEntryId
            model.updatedAt = timer.updatedAt
            model.save(
                update_fields=[
                    "endedAt",
                    "endNote",
                    "pausedSeconds",
                    "labourEntryId",
                    "updatedAt",
                ]
            )
        model.refresh_from_db()
        return self._entity(model)

    def discard(self, tenantId: uuid.UUID, timerId: uuid.UUID) -> WorkTimer:
        """Cancel a running span (mis-tap) without minting a labour entry."""
        with transaction.atomic():
            model = (
                WorkTimerModel.objects.select_for_update()
                .filter(id=timerId, tenantId=tenantId)
                .first()
            )
            if model is None:
                raise EntityNotFoundError("WorkTimer", str(timerId))
            if model.endedAt is not None:
                raise TimerNotRunningError(
                    "This timer has already been stopped.",
                    fieldErrors={"timerId": str(timerId)},
                )
            entity = self._entity(model)
            model.delete()
        return entity

    # -- queries ---------------------------------------------------------------
    def getById(self, tenantId: uuid.UUID, timerId: uuid.UUID) -> WorkTimer | None:
        model = WorkTimerModel.objects.filter(id=timerId, tenantId=tenantId).first()
        return None if model is None else self._entity(model)

    def runningFor(
        self, tenantId: uuid.UUID, workOrderId: uuid.UUID, technicianName: str
    ) -> WorkTimer | None:
        model = (
            WorkTimerModel.objects.filter(
                tenantId=tenantId,
                workOrderId=workOrderId,
                technicianName=technicianName.strip(),
                endedAt__isnull=True,
            )
            .order_by("-startedAt")
            .first()
        )
        return None if model is None else self._entity(model)

    def listRunning(self, tenantId: uuid.UUID, technicianName: str = "") -> list[WorkTimer]:
        rows = WorkTimerModel.objects.filter(tenantId=tenantId, endedAt__isnull=True)
        if technicianName.strip():
            rows = rows.filter(technicianName=technicianName.strip())
        return [self._entity(item) for item in rows.order_by("-startedAt")]

    def listForWorkOrder(self, tenantId: uuid.UUID, workOrderId: uuid.UUID) -> list[WorkTimer]:
        self._workOrderOr404(tenantId, workOrderId)
        rows = WorkTimerModel.objects.filter(tenantId=tenantId, workOrderId=workOrderId).order_by(
            "-startedAt"
        )
        return [self._entity(item) for item in rows]

    def lastStoppedFor(
        self, tenantId: uuid.UUID, workOrderId: uuid.UUID, technicianName: str, startedAt: datetime
    ) -> WorkTimer | None:
        """Used by the sync path to recognise an already-replayed stop."""
        model = (
            WorkTimerModel.objects.filter(
                tenantId=tenantId,
                workOrderId=workOrderId,
                technicianName=technicianName.strip(),
                startedAt=startedAt,
            )
            .order_by("-startedAt")
            .first()
        )
        return None if model is None else self._entity(model)
