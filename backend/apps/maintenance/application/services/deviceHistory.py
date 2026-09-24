"""Helpers that turn device lifecycle events into history entries.

Keeps device-history recording in one place so every device use case appends a
consistent, actor-attributed timeline entry (device timeline feature).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from apps.maintenance.domain.entities.device import Device
from apps.maintenance.domain.entities.deviceHistory import (
    DEVICE_HISTORY_PM_COMPLETED,
    DEVICE_HISTORY_REGISTERED,
    DEVICE_HISTORY_STATUS_CHANGED,
    DEVICE_HISTORY_UPDATED,
    DeviceHistoryEntry,
)
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    DeviceHistoryRepository,
)
from apps.sharedKernel.application.requestContext import currentContext


def actorName() -> str:
    """Display name of the current actor, falling back to a system label."""
    return currentContext().actorName or "سامانه"


def recordDeviceHistory(
    historyRepository: DeviceHistoryRepository,
    device: Device,
    action: str,
    now: datetime,
    *,
    fromStatus: str = "",
    toStatus: str = "",
    note: str = "",
    actor: str = "",
) -> None:
    historyRepository.append(
        DeviceHistoryEntry.create(
            tenantId=device.tenantId,
            deviceId=device.id,
            action=action,
            now=now,
            fromStatus=fromStatus,
            toStatus=toStatus,
            note=note,
            actorName=actor or actorName(),
        )
    )


__all__ = [
    "DEVICE_HISTORY_PM_COMPLETED",
    "DEVICE_HISTORY_REGISTERED",
    "DEVICE_HISTORY_STATUS_CHANGED",
    "DEVICE_HISTORY_UPDATED",
    "actorName",
    "recordDeviceHistory",
    "uuid",
]
