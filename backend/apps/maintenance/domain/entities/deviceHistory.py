"""DeviceHistory — an immutable record of one device lifecycle event.

Part of the device timeline feature. Each device action (registration, detail
update, status change, preventive-maintenance completion) appends one entry,
giving every device a full, ordered history of who did what and when. Combined
with the device's related work orders, this powers the device timeline the
frontend renders on the device detail page.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

# History action codes — stable reference data; Persian labels live in the
# frontend localization layer, never here.
DEVICE_HISTORY_REGISTERED = "registered"
DEVICE_HISTORY_UPDATED = "updated"
DEVICE_HISTORY_STATUS_CHANGED = "statusChanged"
DEVICE_HISTORY_PM_COMPLETED = "pmCompleted"


@dataclass(frozen=True)
class DeviceHistoryEntry:
    id: uuid.UUID
    tenantId: uuid.UUID
    deviceId: uuid.UUID
    action: str
    fromStatus: str
    toStatus: str
    note: str
    actorName: str
    createdAt: datetime

    @staticmethod
    def create(
        *,
        tenantId: uuid.UUID,
        deviceId: uuid.UUID,
        action: str,
        now: datetime,
        fromStatus: str = "",
        toStatus: str = "",
        note: str = "",
        actorName: str = "",
    ) -> DeviceHistoryEntry:
        return DeviceHistoryEntry(
            id=uuid.uuid4(),
            tenantId=tenantId,
            deviceId=deviceId,
            action=action,
            fromStatus=fromStatus,
            toStatus=toStatus,
            note=note,
            actorName=actorName,
            createdAt=now,
        )
