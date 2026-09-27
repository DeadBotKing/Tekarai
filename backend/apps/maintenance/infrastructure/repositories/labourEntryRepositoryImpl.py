"""Transactional Django repository for technician labour time entries.

Every mutation re-aggregates the work order's ``labourHours`` / ``labourCost``
denormalised columns inside the same transaction, so the report page can read
a single WorkOrder row while the entry rows keep the «who / how long / at what
rate» evidence behind the totals.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce

from apps.maintenance.domain.entities.labourEntry import LabourEntry
from apps.maintenance.infrastructure.models import (
    WorkOrderLabourEntryModel,
    WorkOrderModel,
)
from apps.sharedKernel.domain.errors import EntityNotFoundError


class LabourEntryRepositoryDjango:
    @staticmethod
    def _entry(model: WorkOrderLabourEntryModel) -> LabourEntry:
        return LabourEntry(
            id=model.id,
            tenantId=model.tenantId,
            workOrderId=model.workOrderId,
            technicianName=model.technicianName,
            hours=model.hours,
            hourlyRate=model.hourlyRate,
            workedAt=model.workedAt,
            note=model.note,
            createdAt=model.createdAt,
        )

    @staticmethod
    def _workOrderOr404(tenantId: uuid.UUID, workOrderId: uuid.UUID) -> WorkOrderModel:
        order = WorkOrderModel.objects.filter(
            id=workOrderId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        if order is None:
            raise EntityNotFoundError("WorkOrder", str(workOrderId))
        return order

    @staticmethod
    def _rollupWorkOrderLabour(tenantId: uuid.UUID, workOrderId: uuid.UUID) -> None:
        """Rewrite the work order's cached labour totals from its entries."""
        aggregates = WorkOrderLabourEntryModel.objects.filter(
            tenantId=tenantId, workOrderId=workOrderId
        ).aggregate(
            totalHours=Coalesce(Sum("hours"), Decimal("0")),
        )
        entries = WorkOrderLabourEntryModel.objects.filter(
            tenantId=tenantId, workOrderId=workOrderId
        ).values_list("hours", "hourlyRate")
        totalCost = Decimal("0")
        for hours, rate in entries:
            totalCost += hours * rate
        WorkOrderModel.objects.filter(id=workOrderId, tenantId=tenantId).update(
            labourHours=aggregates["totalHours"],
            labourCost=totalCost.quantize(Decimal("0.01")),
            updatedAt=datetime.now().astimezone(),
        )

    def log(
        self,
        tenantId: uuid.UUID,
        workOrderId: uuid.UUID,
        technicianName: str,
        hours: Decimal,
        hourlyRate: Decimal,
        workedAt: datetime,
        note: str,
    ) -> LabourEntry:
        with transaction.atomic():
            self._workOrderOr404(tenantId, workOrderId)
            model = WorkOrderLabourEntryModel.objects.create(
                tenantId=tenantId,
                workOrderId=workOrderId,
                technicianName=technicianName.strip(),
                hours=hours,
                hourlyRate=hourlyRate,
                workedAt=workedAt,
                note=note.strip(),
            )
            self._rollupWorkOrderLabour(tenantId, workOrderId)
        model.refresh_from_db()
        return self._entry(model)

    def listForWorkOrder(self, tenantId: uuid.UUID, workOrderId: uuid.UUID) -> list[LabourEntry]:
        self._workOrderOr404(tenantId, workOrderId)
        rows = WorkOrderLabourEntryModel.objects.filter(
            tenantId=tenantId, workOrderId=workOrderId
        ).order_by("-workedAt")
        return [self._entry(item) for item in rows]

    def delete(self, tenantId: uuid.UUID, entryId: uuid.UUID) -> LabourEntry:
        with transaction.atomic():
            model = (
                WorkOrderLabourEntryModel.objects.select_for_update()
                .filter(id=entryId, tenantId=tenantId)
                .first()
            )
            if model is None:
                raise EntityNotFoundError("WorkOrderLabourEntry", str(entryId))
            entry = self._entry(model)
            workOrderId = model.workOrderId
            model.delete()
            self._rollupWorkOrderLabour(tenantId, workOrderId)
        return entry
