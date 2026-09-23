"""WorkOrderHistory — an immutable record of one work-order transition.

Part of the Phase 22 workflow feature. Each lifecycle action (submit, route,
assign, status change, approval decision) appends one entry, giving every work
order a full, ordered timeline of who did what and when.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

# History action codes — stable reference data; Persian labels live in the
# frontend localization layer, never here.
HISTORY_SUBMITTED = "submitted"
HISTORY_ROUTED = "routed"
HISTORY_ASSIGNED = "assigned"
HISTORY_STATUS_CHANGED = "statusChanged"
HISTORY_SUBMITTED_FOR_APPROVAL = "submittedForApproval"
HISTORY_APPROVED = "approved"
HISTORY_REJECTED = "rejected"


@dataclass(frozen=True)
class WorkOrderHistoryEntry:
    id: uuid.UUID
    tenantId: uuid.UUID
    workOrderId: uuid.UUID
    action: str
    fromStatus: str
    toStatus: str
    fromDepartment: str
    toDepartment: str
    actorName: str
    note: str
    createdAt: datetime

    @staticmethod
    def create(
        *,
        tenantId: uuid.UUID,
        workOrderId: uuid.UUID,
        action: str,
        now: datetime,
        fromStatus: str = "",
        toStatus: str = "",
        fromDepartment: str = "",
        toDepartment: str = "",
        actorName: str = "",
        note: str = "",
    ) -> WorkOrderHistoryEntry:
        return WorkOrderHistoryEntry(
            id=uuid.uuid4(),
            tenantId=tenantId,
            workOrderId=workOrderId,
            action=action,
            fromStatus=fromStatus,
            toStatus=toStatus,
            fromDepartment=fromDepartment,
            toDepartment=toDepartment,
            actorName=actorName,
            note=note,
            createdAt=now,
        )
