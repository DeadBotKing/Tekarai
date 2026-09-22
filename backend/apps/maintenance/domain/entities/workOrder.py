"""WorkOrder aggregate root — a maintenance request and its lifecycle (Phase 21).

Anyone can submit a work order against a device. The workflow is two-step:
first a manager *routes* the order to a maintenance department (e.g. electrical),
then a technician of that department is *assigned* and works it through progress
states to completion. Transitions are guarded by ``WORK_ORDER_TRANSITIONS`` so
the workflow stays predictable (BR-WO-001).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.maintenance.domain.valueObjects.maintenanceState import (
    WO_ASSIGNED,
    WO_ROUTED,
    WO_SUBMITTED,
    MaintenanceDepartment,
    WorkOrderPriority,
    WorkOrderStatus,
    WorkOrderType,
)
from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.errors import (
    InvalidStateTransitionError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.events import DomainEvent


class WorkOrder(AggregateRoot):
    """A tenant-scoped maintenance request tied to a device."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        deviceId: uuid.UUID,
        title: str,
        description: str,
        orderType: WorkOrderType,
        priority: WorkOrderPriority,
        status: WorkOrderStatus,
        department: MaintenanceDepartment,
        requestedByName: str,
        assignedToName: str,
        resolutionNote: str,
        createdAt: datetime,
        updatedAt: datetime | None = None,
        closedAt: datetime | None = None,
        deletedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.deviceId = deviceId
        self.title = title
        self.description = description
        self.orderType = orderType
        self.priority = priority
        self.status = status
        self.department = department
        self.requestedByName = requestedByName
        self.assignedToName = assignedToName
        self.resolutionNote = resolutionNote
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.closedAt = closedAt
        self.deletedAt = deletedAt

    @staticmethod
    def submit(
        tenantId: uuid.UUID,
        deviceId: uuid.UUID,
        title: str,
        description: str,
        orderType: WorkOrderType,
        priority: WorkOrderPriority,
        department: MaintenanceDepartment,
        requestedByName: str,
        now: datetime,
    ) -> WorkOrder:
        if not title.strip():
            raise ValidationFailedError(
                "Work order title is required.", fieldErrors={"title": "required"}
            )
        order = WorkOrder(
            id=newId(),
            tenantId=tenantId,
            deviceId=deviceId,
            title=title.strip(),
            description=description.strip(),
            orderType=orderType,
            priority=priority,
            status=WorkOrderStatus(WO_SUBMITTED),
            department=department,
            requestedByName=requestedByName.strip(),
            assignedToName="",
            resolutionNote="",
            createdAt=now,
        )
        order.recordEvent(
            DomainEvent(
                name="workOrderSubmitted",
                occurredAt=now,
                tenantId=tenantId,
                payload={
                    "workOrderId": str(order.id),
                    "deviceId": str(deviceId),
                    "orderType": str(orderType),
                    "department": str(department),
                },
            )
        )
        return order

    def updateDetails(
        self,
        title: str,
        description: str,
        priority: WorkOrderPriority,
        now: datetime,
    ) -> None:
        if not title.strip():
            raise ValidationFailedError(
                "Work order title is required.", fieldErrors={"title": "required"}
            )
        self.title = title.strip()
        self.description = description.strip()
        self.priority = priority
        self.updatedAt = now

    def routeToDepartment(self, department: MaintenanceDepartment, now: datetime) -> None:
        """Step 1 of dispatch — a manager routes the order to a department.

        Allowed from ``submitted`` (initial routing) and from ``routed``/``assigned``
        (re-routing to a different department before work starts).
        """
        if not self.status.canTransitionTo(WO_ROUTED) and str(self.status) != WO_ROUTED:
            raise InvalidStateTransitionError(
                f"Cannot route a work order in state '{self.status}'."
            )
        previous = str(self.status)
        previousDepartment = str(self.department)
        self.department = department
        # Re-routing an already-assigned order clears the individual assignee.
        self.assignedToName = ""
        self.status = WorkOrderStatus(WO_ROUTED)
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="workOrderRouted",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={
                    "workOrderId": str(self.id),
                    "from": previous,
                    "fromDepartment": previousDepartment,
                    "toDepartment": str(department),
                },
            )
        )

    def assign(self, technicianName: str, now: datetime) -> None:
        if not technicianName.strip():
            raise ValidationFailedError(
                "A technician name is required to assign.",
                fieldErrors={"assignedToName": "required"},
            )
        if not self.status.canTransitionTo(WO_ASSIGNED) and str(self.status) != WO_ASSIGNED:
            raise InvalidStateTransitionError(
                f"Cannot assign a work order in state '{self.status}'."
            )
        previous = str(self.status)
        self.assignedToName = technicianName.strip()
        self.status = WorkOrderStatus(WO_ASSIGNED)
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="workOrderAssigned",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={
                    "workOrderId": str(self.id),
                    "from": previous,
                    "department": str(self.department),
                    "assignedTo": self.assignedToName,
                },
            )
        )

    def changeStatus(self, target: str, resolutionNote: str, now: datetime) -> None:
        if not self.status.canTransitionTo(target):
            raise InvalidStateTransitionError(
                f"Cannot move a work order from '{self.status}' to '{target}'."
            )
        previous = str(self.status)
        self.status = WorkOrderStatus(target)
        self.updatedAt = now
        if target in ("completed", "cancelled"):
            self.closedAt = now
            if resolutionNote.strip():
                self.resolutionNote = resolutionNote.strip()
        self.recordEvent(
            DomainEvent(
                name="workOrderStatusChanged",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"workOrderId": str(self.id), "from": previous, "to": target},
            )
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "tenantId": str(self.tenantId),
            "deviceId": str(self.deviceId),
            "title": self.title,
            "orderType": str(self.orderType),
            "priority": str(self.priority),
            "status": str(self.status),
            "department": str(self.department),
            "assignedToName": self.assignedToName,
        }
