"""ORM implementation of WorkOrderHistoryRepository (Phase 22 workflow)."""

from __future__ import annotations

import uuid

from apps.maintenance.domain.entities.workOrderHistory import WorkOrderHistoryEntry
from apps.maintenance.infrastructure.models import WorkOrderHistoryModel


class WorkOrderHistoryRepositoryDjango:
    def append(self, entry: WorkOrderHistoryEntry) -> None:
        WorkOrderHistoryModel.objects.create(
            id=entry.id,
            tenantId=entry.tenantId,
            workOrderId=entry.workOrderId,
            action=entry.action,
            fromStatus=entry.fromStatus,
            toStatus=entry.toStatus,
            fromDepartment=entry.fromDepartment,
            toDepartment=entry.toDepartment,
            actorName=entry.actorName,
            note=entry.note,
            createdAt=entry.createdAt,
        )

    def listForOrder(
        self, tenantId: uuid.UUID, workOrderId: uuid.UUID
    ) -> list[WorkOrderHistoryEntry]:
        rows = WorkOrderHistoryModel.objects.filter(
            tenantId=tenantId, workOrderId=workOrderId
        ).order_by("createdAt")
        return [self.toDomain(row) for row in rows]

    @staticmethod
    def toDomain(model: WorkOrderHistoryModel) -> WorkOrderHistoryEntry:
        return WorkOrderHistoryEntry(
            id=model.id,
            tenantId=model.tenantId,
            workOrderId=model.workOrderId,
            action=model.action,
            fromStatus=model.fromStatus,
            toStatus=model.toStatus,
            fromDepartment=model.fromDepartment,
            toDepartment=model.toDepartment,
            actorName=model.actorName,
            note=model.note,
            createdAt=model.createdAt,
        )
