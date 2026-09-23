"""Helpers that turn work-order lifecycle events into history entries.

Keeps history recording in one place so every work-order use case appends a
consistent, actor-attributed timeline entry (Phase 22 workflow).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from apps.maintenance.domain.entities.workOrder import WorkOrder
from apps.maintenance.domain.entities.workOrderHistory import (
    HISTORY_APPROVED,
    HISTORY_ASSIGNED,
    HISTORY_REJECTED,
    HISTORY_ROUTED,
    HISTORY_STATUS_CHANGED,
    HISTORY_SUBMITTED,
    HISTORY_SUBMITTED_FOR_APPROVAL,
    WorkOrderHistoryEntry,
)
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    WorkOrderHistoryRepository,
)
from apps.sharedKernel.application.requestContext import currentContext


def actorName() -> str:
    """Display name of the current actor, falling back to a system label."""
    return currentContext().actorName or "سامانه"


def recordHistory(
    historyRepository: WorkOrderHistoryRepository,
    order: WorkOrder,
    action: str,
    now: datetime,
    *,
    fromStatus: str = "",
    toStatus: str = "",
    fromDepartment: str = "",
    toDepartment: str = "",
    note: str = "",
    actor: str = "",
) -> None:
    historyRepository.append(
        WorkOrderHistoryEntry.create(
            tenantId=order.tenantId,
            workOrderId=order.id,
            action=action,
            now=now,
            fromStatus=fromStatus,
            toStatus=toStatus,
            fromDepartment=fromDepartment,
            toDepartment=toDepartment,
            actorName=actor or actorName(),
            note=note,
        )
    )


__all__ = [
    "HISTORY_APPROVED",
    "HISTORY_ASSIGNED",
    "HISTORY_REJECTED",
    "HISTORY_ROUTED",
    "HISTORY_STATUS_CHANGED",
    "HISTORY_SUBMITTED",
    "HISTORY_SUBMITTED_FOR_APPROVAL",
    "actorName",
    "recordHistory",
    "uuid",
]
