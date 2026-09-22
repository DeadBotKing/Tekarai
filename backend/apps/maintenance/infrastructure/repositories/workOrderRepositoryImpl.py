"""ORM implementation of WorkOrderRepository (Phase 21)."""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db.models import Q

from apps.maintenance.domain.entities.workOrder import WorkOrder
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    WorkOrderFilters,
    WorkOrderPage,
)
from apps.maintenance.domain.valueObjects.maintenanceState import (
    WO_CANCELLED,
    WO_COMPLETED,
    MaintenanceDepartment,
    WorkOrderPriority,
    WorkOrderStatus,
    WorkOrderType,
)
from apps.maintenance.infrastructure.models import WorkOrderModel
from apps.sharedKernel.domain.errors import ValidationFailedError

SORTABLE_COLUMNS = {
    "createdAt": "createdAt",
    "title": "title",
    "status": "status",
    "priority": "priority",
}

CLOSED_STATUSES = (WO_COMPLETED, WO_CANCELLED)


class WorkOrderRepositoryDjango:
    def create(self, order: WorkOrder) -> None:
        WorkOrderModel.objects.create(
            id=order.id,
            tenantId=order.tenantId,
            deviceId=order.deviceId,
            title=order.title,
            description=order.description,
            orderType=str(order.orderType),
            priority=str(order.priority),
            status=str(order.status),
            department=str(order.department),
            requestedByName=order.requestedByName,
            assignedToName=order.assignedToName,
            resolutionNote=order.resolutionNote,
            createdAt=order.createdAt,
        )

    def update(self, order: WorkOrder) -> None:
        WorkOrderModel.objects.filter(id=order.id).update(
            title=order.title,
            description=order.description,
            priority=str(order.priority),
            status=str(order.status),
            department=str(order.department),
            assignedToName=order.assignedToName,
            resolutionNote=order.resolutionNote,
            updatedAt=order.updatedAt or datetime.now(tz=None),
            closedAt=order.closedAt,
        )

    def getById(self, tenantId: uuid.UUID, orderId: uuid.UUID) -> WorkOrder | None:
        model = WorkOrderModel.objects.filter(
            id=orderId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        return self.toDomain(model) if model else None

    def countByTenant(self, tenantId: uuid.UUID) -> int:
        return WorkOrderModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True).count()

    def countOpenByTenant(self, tenantId: uuid.UUID) -> int:
        return (
            WorkOrderModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
            .exclude(status__in=CLOSED_STATUSES)
            .count()
        )

    def hasOpenPreventiveOrder(self, tenantId: uuid.UUID, deviceId: uuid.UUID) -> bool:
        """True when the device already has an unfinished preventive work order.

        Prevents the PM auto-generator from raising duplicate orders on every run.
        """
        return (
            WorkOrderModel.objects.filter(
                tenantId=tenantId,
                deviceId=deviceId,
                orderType="preventive",
                deletedAt__isnull=True,
            )
            .exclude(status__in=CLOSED_STATUSES)
            .exists()
        )

    def list(self, filters: WorkOrderFilters) -> WorkOrderPage:
        queryset = WorkOrderModel.objects.filter(tenantId=filters.tenantId, deletedAt__isnull=True)
        if filters.deviceId:
            queryset = queryset.filter(deviceId=filters.deviceId)
        if filters.status:
            queryset = queryset.filter(status=filters.status)
        if filters.orderType:
            queryset = queryset.filter(orderType=filters.orderType)
        if filters.priority:
            queryset = queryset.filter(priority=filters.priority)
        if filters.department:
            queryset = queryset.filter(department=filters.department)
        if filters.search:
            queryset = queryset.filter(
                Q(title__icontains=filters.search)
                | Q(requestedByName__icontains=filters.search)
                | Q(assignedToName__icontains=filters.search)
            )
        requestedField = filters.ordering.lstrip("-").split(",")[0].strip()
        if requestedField and requestedField not in SORTABLE_COLUMNS:
            raise ValidationFailedError(
                "Field is not sortable.", fieldErrors={"ordering": requestedField}
            )
        orderingColumn = SORTABLE_COLUMNS.get(requestedField, "createdAt")
        orderBy = f"-{orderingColumn}" if filters.ordering.startswith("-") else orderingColumn
        totalCount = queryset.count()
        pageSize = min(100, max(1, filters.pageSize))
        items = [
            self.toDomain(model)
            for model in queryset.order_by(orderBy)[
                (max(1, filters.page) - 1) * pageSize : max(1, filters.page) * pageSize
            ]
        ]
        return WorkOrderPage(items=items, totalCount=totalCount)

    @staticmethod
    def toDomain(model: WorkOrderModel) -> WorkOrder:
        return WorkOrder(
            id=model.id,
            tenantId=model.tenantId,
            deviceId=model.deviceId,
            title=model.title,
            description=model.description,
            orderType=WorkOrderType(model.orderType),
            priority=WorkOrderPriority(model.priority),
            status=WorkOrderStatus(model.status),
            department=MaintenanceDepartment(model.department),
            requestedByName=model.requestedByName,
            assignedToName=model.assignedToName,
            resolutionNote=model.resolutionNote,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
            closedAt=model.closedAt,
            deletedAt=model.deletedAt,
        )
