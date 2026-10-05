"""Work timer use cases — «ثبت زمان شروع و پایان کار».

Before this slice the system could only record a *duration* a technician
typed in afterwards ("۲ ساعت کار کردم"). That number is a memory, not a
measurement: it is rounded up, it is entered at the end of a shift for five
orders at once, and it cannot answer «کی روی این دستگاه بود؟».

A timer records the two moments instead, and derives the duration. Stopping
a span mints a normal :class:`LabourEntry`, so every existing cost report,
export and dashboard keeps working untouched — the timer is a *better input
device* for labour entries, not a parallel universe of truth.

Design decisions worth keeping:

* **The labour entry is the single source of truth for cost.** The timer row
  links to it (``labourEntryId``) but no report reads the timer table, so the
  two can never disagree about money.
* **Starting a timer moves the order to ``inProgress``** when the lifecycle
  allows it, because a technician who pressed "start" has, by definition,
  started. If the transition is illegal (the order is completed or
  cancelled), the start is refused — a timer on a closed order is a mistake
  that would later inject cost into a settled job.
* **Stopping is forgiving, starting is strict.** Stop accepts an explicit
  ``endedAt`` so a queued offline stop keeps the moment it really happened;
  start refuses a future moment outright.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.domain.entities.workTimer import WorkTimer
from apps.maintenance.domain.exceptions.fieldOpsErrors import (
    TimerNotRunningError,
    TimerSpanInvalidError,
)
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    LabourEntryRepository,
    WorkOrderRepository,
    WorkTimerRepository,
)
from apps.maintenance.domain.valueObjects.maintenanceState import (
    WO_ASSIGNED,
    WO_IN_PROGRESS,
    WO_ON_HOLD,
)
from apps.sharedKernel.application.messaging import Command, Query
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import EntityNotFoundError, ValidationFailedError
from apps.sharedKernel.domain.events import DomainEvent

#: Statuses from which pressing «شروع کار» is meaningful.
#:
#: ``submitted``/``routed`` are deliberately excluded. The lifecycle
#: (BR-WO-001) has no edge from either of them to ``inProgress``: an order
#: must be *assigned* to someone before work begins. Letting a timer start
#: there would either leave the board lying (status says "routed", a
#: stopwatch says "in progress") or force an illegal transition.
STARTABLE_STATUSES = (WO_ASSIGNED, WO_IN_PROGRESS, WO_ON_HOLD)

MAX_HOURLY_RATE = Decimal("100000000")


# ---------------------------------------------------------------------------
# Commands / queries
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StartWorkTimerCommand(Command):
    workOrderId: str
    technicianName: str = ""
    startedAt: str = ""
    hourlyRate: str = "0"
    note: str = ""
    capturedOffline: bool = False


@dataclass(frozen=True)
class StopWorkTimerCommand(Command):
    workOrderId: str = ""
    timerId: str = ""
    technicianName: str = ""
    endedAt: str = ""
    note: str = ""
    pausedSeconds: int = 0
    capturedOffline: bool = False


@dataclass(frozen=True)
class CancelWorkTimerCommand(Command):
    timerId: str


@dataclass(frozen=True)
class ListWorkTimersQuery(Query):
    workOrderId: str = ""
    technicianName: str = ""
    runningOnly: bool = False


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WorkTimerDto:
    id: str
    workOrderId: str
    technicianName: str
    startedAt: str
    endedAt: str
    running: bool
    elapsedSeconds: int
    billableHours: str
    hourlyRate: str
    startNote: str
    endNote: str
    labourEntryId: str
    capturedOffline: bool
    startedVia: str


@dataclass(frozen=True)
class StoppedTimerDto:
    timer: WorkTimerDto
    labourEntryId: str
    hours: str
    labourCost: str


def timerDto(timer: WorkTimer, asOf: datetime) -> WorkTimerDto:
    return WorkTimerDto(
        id=str(timer.id),
        workOrderId=str(timer.workOrderId),
        technicianName=timer.technicianName,
        startedAt=timer.startedAt.isoformat(),
        endedAt=timer.endedAt.isoformat() if timer.endedAt else "",
        running=timer.isRunning,
        elapsedSeconds=timer.elapsedSeconds(asOf),
        billableHours=str(timer.billableHours(asOf)),
        hourlyRate=str(timer.hourlyRate),
        startNote=timer.startNote,
        endNote=timer.endNote,
        labourEntryId=str(timer.labourEntryId) if timer.labourEntryId else "",
        capturedOffline=timer.capturedOffline,
        startedVia=timer.startedVia,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parseMoment(text: str, fallback: datetime, field: str) -> datetime:
    """ISO-8601 → aware UTC datetime. Naive input is read as UTC.

    The phone sends ``new Date().toISOString()`` which is always UTC with a
    ``Z``; hand-written values from integration tests are often naive. Both
    must land on the same instant or an offline stop would silently shift by
    the server's timezone offset.
    """
    raw = (text or "").strip()
    if not raw:
        return fallback
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValidationFailedError(
            "Invalid date/time value.", fieldErrors={field: "invalid"}
        ) from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parseRate(text: str) -> Decimal:
    raw = (text or "0").strip() or "0"
    try:
        value = Decimal(raw)
    except InvalidOperation as error:
        raise ValidationFailedError(
            "Invalid hourly rate.", fieldErrors={"hourlyRate": "invalid"}
        ) from error
    if value < 0 or value > MAX_HOURLY_RATE:
        raise ValidationFailedError(
            "Hourly rate out of range.", fieldErrors={"hourlyRate": "range"}
        )
    return value.quantize(Decimal("0.01"))


def resolveTechnicianName(explicit: str) -> str:
    """Whose stopwatch is this? The caller's name unless stated otherwise.

    A manager logging time *for* a technician passes the name explicitly;
    the technician's own phone sends nothing and inherits the session name.
    """
    name = (explicit or "").strip()
    if name:
        return name[:160]
    contextName = (currentContext().actorName or "").strip()
    if not contextName:
        raise ValidationFailedError(
            "Technician name is required.", fieldErrors={"technicianName": "required"}
        )
    return contextName[:160]


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------
class WorkTimerUseCaseBase(UseCase):
    def __init__(
        self,
        timerRepository: WorkTimerRepository,
        workOrderRepository: WorkOrderRepository,
        labourEntryRepository: LabourEntryRepository,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.timerRepository = timerRepository
        self.workOrderRepository = workOrderRepository
        self.labourEntryRepository = labourEntryRepository

    def requireOrder(self, tenantId: uuid.UUID, workOrderId: str):
        try:
            identifier = uuid.UUID(str(workOrderId))
        except (ValueError, AttributeError, TypeError) as error:
            raise ValidationFailedError(
                "Invalid work order id.", fieldErrors={"workOrderId": "invalid"}
            ) from error
        order = self.workOrderRepository.getById(tenantId, identifier)
        if order is None:
            raise EntityNotFoundError("WorkOrder", str(workOrderId))
        return order


class StartWorkTimerUseCase(WorkTimerUseCaseBase):
    """«شروع کار» — open a measured span on a work order."""

    requiredAction = "maintenance.workorder.logTime"

    def perform(self, command: StartWorkTimerCommand) -> WorkTimerDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        order = self.requireOrder(tenantId, command.workOrderId)
        status = str(order.status)
        if status not in STARTABLE_STATUSES:
            raise ValidationFailedError(
                "Work can only be started on an assigned, in-progress or "
                "on-hold order; assign this order first.",
                fieldErrors={"status": status},
            )
        technicianName = resolveTechnicianName(command.technicianName)
        startedAt = parseMoment(command.startedAt, now, "startedAt")
        context = currentContext()
        timer = WorkTimer.start(
            tenantId=tenantId,
            workOrderId=order.id,
            technicianName=technicianName,
            startedAt=startedAt,
            now=now,
            hourlyRate=parseRate(command.hourlyRate),
            note=command.note,
            capturedOffline=bool(command.capturedOffline),
            technicianUserId=uuid.UUID(context.actorId) if context.actorId else None,
        )
        stored = self.timerRepository.startExclusive(timer)

        # Pressing start *is* starting the work. Moving the order keeps the
        # board honest without a second tap, but never fights the lifecycle:
        # the transition is attempted only when the state machine allows it.
        if status != WO_IN_PROGRESS and order.status.canTransitionTo(WO_IN_PROGRESS):
            order.changeStatus(WO_IN_PROGRESS, "", now)
            self.workOrderRepository.update(order)
            self.collectEventsFrom(order)

        self.audit(
            AUDIT_CREATE,
            "WorkTimer",
            str(stored.id),
            tenantId,
            after=stored.snapshot(),
        )
        for name, payload in timer.events:
            self._pendingEvents.append(
                DomainEvent(name=name, occurredAt=now, tenantId=tenantId, payload=payload)
            )
        return timerDto(stored, now)


class StopWorkTimerUseCase(WorkTimerUseCaseBase):
    """«پایان کار» — close the span and mint the labour entry it earned."""

    requiredAction = "maintenance.workorder.logTime"

    def _locate(self, tenantId: uuid.UUID, command: StopWorkTimerCommand) -> WorkTimer:
        if command.timerId.strip():
            try:
                identifier = uuid.UUID(command.timerId.strip())
            except ValueError as error:
                raise ValidationFailedError(
                    "Invalid timer id.", fieldErrors={"timerId": "invalid"}
                ) from error
            timer = self.timerRepository.getById(tenantId, identifier)
            if timer is None:
                raise EntityNotFoundError("WorkTimer", command.timerId)
            return timer
        order = self.requireOrder(tenantId, command.workOrderId)
        technicianName = resolveTechnicianName(command.technicianName)
        timer = self.timerRepository.runningFor(tenantId, order.id, technicianName)
        if timer is None:
            # Nothing is running for this technician on this order. That is
            # «already stopped», not «never existed» — the distinction matters
            # to a replaying offline queue, which must treat it as a duplicate
            # and drop the item instead of retrying it forever.
            raise TimerNotRunningError(
                "No running timer for this technician on this work order.",
                fieldErrors={"workOrderId": str(command.workOrderId)},
            )
        return timer

    def perform(self, command: StopWorkTimerCommand) -> StoppedTimerDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        timer = self._locate(tenantId, command)
        endedAt = parseMoment(command.endedAt, now, "endedAt")
        if int(command.pausedSeconds) < 0:
            raise TimerSpanInvalidError(
                "Paused seconds cannot be negative.",
                fieldErrors={"pausedSeconds": "negative"},
            )
        timer.pausedSeconds = int(command.pausedSeconds)
        hours = timer.stop(endedAt, now, command.note)

        # The labour entry is written first: if minting it fails, the timer
        # stays running and the technician can retry, rather than losing the
        # span to a half-applied stop.
        entry = self.labourEntryRepository.log(
            tenantId,
            timer.workOrderId,
            timer.technicianName,
            hours,
            timer.hourlyRate,
            timer.startedAt,
            (command.note or timer.startNote or "").strip()[:500],
        )
        timer.attachLabourEntry(entry.id)
        stored = self.timerRepository.stop(timer)

        self.audit(
            AUDIT_UPDATE,
            "WorkTimer",
            str(stored.id),
            tenantId,
            after=stored.snapshot(),
        )
        for name, payload in timer.events:
            self._pendingEvents.append(
                DomainEvent(
                    name=name,
                    occurredAt=now,
                    tenantId=tenantId,
                    payload={**payload, "labourEntryId": str(entry.id)},
                )
            )
        return StoppedTimerDto(
            timer=timerDto(stored, now),
            labourEntryId=str(entry.id),
            hours=str(hours),
            labourCost=str(entry.totalCost),
        )


class CancelWorkTimerUseCase(WorkTimerUseCaseBase):
    """Discard a mis-tapped span. No labour entry, no cost, no trace of work."""

    requiredAction = "maintenance.workorder.logTime"

    def perform(self, command: CancelWorkTimerCommand) -> WorkTimerDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        try:
            identifier = uuid.UUID(command.timerId.strip())
        except (ValueError, AttributeError) as error:
            raise ValidationFailedError(
                "Invalid timer id.", fieldErrors={"timerId": "invalid"}
            ) from error
        timer = self.timerRepository.discard(tenantId, identifier)
        self.audit(AUDIT_UPDATE, "WorkTimer", str(timer.id), tenantId, before=timer.snapshot())
        return timerDto(timer, now)


class ListWorkTimersUseCase(WorkTimerUseCaseBase):
    requiredAction = "maintenance.workorder.view"

    def perform(self, query: ListWorkTimersQuery) -> list[WorkTimerDto]:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        if query.workOrderId.strip():
            order = self.requireOrder(tenantId, query.workOrderId)
            timers = self.timerRepository.listForWorkOrder(tenantId, order.id)
            if query.runningOnly:
                timers = [item for item in timers if item.isRunning]
        else:
            timers = self.timerRepository.listRunning(
                tenantId, (query.technicianName or "").strip()
            )
        return [timerDto(item, now) for item in timers]


class GetMyRunningTimersUseCase(WorkTimerUseCaseBase):
    """What is still ticking for the signed-in technician (app resume)."""

    requiredAction = "maintenance.workorder.view"

    def perform(self, query: ListWorkTimersQuery) -> list[WorkTimerDto]:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        name = (query.technicianName or currentContext().actorName or "").strip()
        if not name:
            return []
        return [timerDto(item, now) for item in self.timerRepository.listRunning(tenantId, name)]
