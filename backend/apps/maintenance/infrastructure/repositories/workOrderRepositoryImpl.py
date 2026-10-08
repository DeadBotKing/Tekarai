"""ORM implementation of WorkOrderRepository (Phase 21)."""

from __future__ import annotations

import builtins
import uuid
from datetime import datetime

from django.db.models import Q

from apps.maintenance.domain.entities.workOrder import WorkOrder
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    WorkOrderAlertRow,
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
            orgDepartmentId=order.orgDepartmentId,
            requestedByUserId=order.requestedByUserId,
            assignedToUserId=order.assignedToUserId,
        )

    def update(self, order: WorkOrder) -> None:
        WorkOrderModel.objects.filter(id=order.id).update(
            title=order.title,
            description=order.description,
            priority=str(order.priority),
            status=str(order.status),
            department=str(order.department),
            assignedToName=order.assignedToName,
            assignedToUserId=order.assignedToUserId,
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

    def countOpenByAssignee(self, tenantId: uuid.UUID, department: str) -> dict[str, int]:
        """Open work-order counts per technician within a department.

        Feeds the auto-assign rule (least-loaded technician). Only non-terminal
        orders that already have an assignee are counted.
        """
        rows = (
            WorkOrderModel.objects.filter(
                tenantId=tenantId,
                department=department,
                deletedAt__isnull=True,
            )
            .exclude(status__in=CLOSED_STATUSES)
            .exclude(assignedToName="")
            .values_list("assignedToName", flat=True)
        )
        counts: dict[str, int] = {}
        for name in rows:
            counts[name] = counts.get(name, 0) + 1
        return counts

    def list(self, filters: WorkOrderFilters) -> WorkOrderPage:
        queryset = WorkOrderModel.objects.filter(tenantId=filters.tenantId, deletedAt__isnull=True)
        # Organisation scope (Phase 28). Applied FIRST, before any caller
        # filter, so no query parameter can widen it. `scopeDenied` means
        # the user holds no grant at all — an empty page, never an
        # unfiltered one.
        if filters.scopeDenied:
            return WorkOrderPage(items=[], totalCount=0)
        if filters.scopeDepartmentIds is not None:
            queryset = queryset.filter(orgDepartmentId__in=filters.scopeDepartmentIds)
        if filters.scopeUserIds is not None:
            queryset = queryset.filter(
                Q(requestedByUserId__in=filters.scopeUserIds)
                | Q(assignedToUserId__in=filters.scopeUserIds)
            )
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
        if filters.createdFrom is not None:
            queryset = queryset.filter(createdAt__gte=filters.createdFrom)
        if filters.createdTo is not None:
            queryset = queryset.filter(createdAt__lte=filters.createdTo)
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
            orgDepartmentId=model.orgDepartmentId,
            requestedByUserId=model.requestedByUserId,
            assignedToUserId=model.assignedToUserId,
            assignedToName=model.assignedToName,
            resolutionNote=model.resolutionNote,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
            closedAt=model.closedAt,
            deletedAt=model.deletedAt,
            failureType=model.failureType,
            failedComponent=model.failedComponent,
            failureSymptom=model.failureSymptom,
            rootCause=model.rootCause,
            actionTaken=model.actionTaken,
            repeatFailure=model.repeatFailure,
            failureReportedAt=model.failureReportedAt,
            repairStartedAt=model.repairStartedAt,
            repairFinishedAt=model.repairFinishedAt,
            returnedToServiceAt=model.returnedToServiceAt,
            downtimeMinutes=model.downtimeMinutes,
            labourHours=model.labourHours,
            labourCost=model.labourCost,
            partsCost=model.partsCost,
        )

    def listAlertRows(self, tenantId: uuid.UUID) -> builtins.list[WorkOrderAlertRow]:
        rows = WorkOrderModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True).order_by(
            "-createdAt"
        )[:500]
        return [
            WorkOrderAlertRow(
                id=model.id,
                deviceId=model.deviceId,
                tenantId=model.tenantId,
                title=model.title,
                status=model.status,
                priority=model.priority,
                department=model.department,
                createdAt=model.createdAt,
            )
            for model in rows
        ]
