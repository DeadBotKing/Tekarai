"""ORM implementation of DeviceHistoryRepository (device timeline)."""

from __future__ import annotations

import uuid

from apps.maintenance.domain.entities.deviceHistory import DeviceHistoryEntry
from apps.maintenance.infrastructure.models import DeviceHistoryModel


class DeviceHistoryRepositoryDjango:
    def append(self, entry: DeviceHistoryEntry) -> None:
        DeviceHistoryModel.objects.create(
            id=entry.id,
            tenantId=entry.tenantId,
            deviceId=entry.deviceId,
            action=entry.action,
            fromStatus=entry.fromStatus,
            toStatus=entry.toStatus,
            note=entry.note,
            actorName=entry.actorName,
            createdAt=entry.createdAt,
        )

    def listForDevice(
        self, tenantId: uuid.UUID, deviceId: uuid.UUID
    ) -> list[DeviceHistoryEntry]:
        rows = DeviceHistoryModel.objects.filter(
            tenantId=tenantId, deviceId=deviceId
        ).order_by("createdAt")
        return [self.toDomain(row) for row in rows]

    @staticmethod
    def toDomain(model: DeviceHistoryModel) -> DeviceHistoryEntry:
        return DeviceHistoryEntry(
            id=model.id,
            tenantId=model.tenantId,
            deviceId=model.deviceId,
            action=model.action,
            fromStatus=model.fromStatus,
            toStatus=model.toStatus,
            note=model.note,
            actorName=model.actorName,
            createdAt=model.createdAt,
        )
