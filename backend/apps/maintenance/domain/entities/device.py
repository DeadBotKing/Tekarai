"""Device aggregate root — a maintainable piece of equipment (Phase 21).

A Device carries its own preventive-maintenance (PM) schedule: an interval in
days plus the date of the last completed PM. ``nextDueDate`` is derived so the
application layer can flag machines that are due or overdue without duplicating
the rule. Each device also names the maintenance *department* that owns it, so
work orders (and auto-generated PM orders) are routed to the right unit.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from apps.maintenance.domain.valueObjects.maintenanceState import (
    DEVICE_OPERATIONAL,
    DeviceStatus,
    MaintenanceDepartment,
)
from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.sharedKernel.domain.events import DomainEvent


class Device(AggregateRoot):
    """A tenant-scoped device tracked for maintenance."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        code: str,
        name: str,
        location: str,
        status: DeviceStatus,
        department: MaintenanceDepartment,
        pmIntervalDays: int,
        lastPmDate: date | None,
        createdAt: datetime,
        updatedAt: datetime | None = None,
        deletedAt: datetime | None = None,
        *,
        # -- Phase 26 registry attributes -------------------------------------------
        # Optional master data that the registry writes through a dedicated
        # nameplate command. They are descriptive only: no maintenance rule
        # depends on them, so every pre-Phase-26 device stays valid.
        manufacturer: str = "",
        modelNumber: str = "",
        serialNumber: str = "",
        equipmentType: str = "",
        criticality: str = "medium",
        locationId: uuid.UUID | None = None,
        locationPath: str = "",
        parentDeviceId: uuid.UUID | None = None,
        operatorUnit: str = "",
        runningHours: float = 0.0,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.code = code
        self.name = name
        self.location = location
        self.status = status
        self.department = department
        self.pmIntervalDays = pmIntervalDays
        self.lastPmDate = lastPmDate
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.deletedAt = deletedAt
        self.manufacturer = manufacturer
        self.modelNumber = modelNumber
        self.serialNumber = serialNumber
        self.equipmentType = equipmentType
        self.criticality = criticality
        self.locationId = locationId
        self.locationPath = locationPath
        self.parentDeviceId = parentDeviceId
        self.operatorUnit = operatorUnit
        self.runningHours = runningHours

    @staticmethod
    def create(
        tenantId: uuid.UUID,
        code: str,
        name: str,
        location: str,
        department: MaintenanceDepartment,
        pmIntervalDays: int,
        now: datetime,
    ) -> Device:
        if not code.strip():
            raise ValidationFailedError(
                "Device code is required.", fieldErrors={"code": "required"}
            )
        if not name.strip():
            raise ValidationFailedError(
                "Device name is required.", fieldErrors={"name": "required"}
            )
        if pmIntervalDays < 0:
            raise ValidationFailedError(
                "PM interval must be zero or positive.",
                fieldErrors={"pmIntervalDays": "invalid"},
            )
        device = Device(
            id=newId(),
            tenantId=tenantId,
            code=code.strip(),
            name=name.strip(),
            location=location.strip(),
            status=DeviceStatus(DEVICE_OPERATIONAL),
            department=department,
            pmIntervalDays=pmIntervalDays,
            lastPmDate=None,
            createdAt=now,
        )
        device.recordEvent(
            DomainEvent(
                name="deviceRegistered",
                occurredAt=now,
                tenantId=tenantId,
                payload={
                    "deviceId": str(device.id),
                    "code": device.code,
                    "department": str(device.department),
                },
            )
        )
        return device

    def updateDetails(
        self,
        name: str,
        location: str,
        department: MaintenanceDepartment,
        pmIntervalDays: int,
        now: datetime,
    ) -> None:
        if not name.strip():
            raise ValidationFailedError(
                "Device name is required.", fieldErrors={"name": "required"}
            )
        if pmIntervalDays < 0:
            raise ValidationFailedError(
                "PM interval must be zero or positive.",
                fieldErrors={"pmIntervalDays": "invalid"},
            )
        self.name = name.strip()
        self.location = location.strip()
        self.department = department
        self.pmIntervalDays = pmIntervalDays
        self.updatedAt = now

    def changeStatus(self, target: str, now: datetime) -> None:
        previous = str(self.status)
        self.status = DeviceStatus(target)
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="deviceStatusChanged",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"deviceId": str(self.id), "from": previous, "to": target},
            )
        )

    def recordPreventiveMaintenance(self, performedOn: date, now: datetime) -> None:
        """Mark a PM cycle as completed; resets the schedule clock."""
        self.lastPmDate = performedOn
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="devicePmCompleted",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"deviceId": str(self.id), "performedOn": performedOn.isoformat()},
            )
        )

    def nextDueDate(self) -> date | None:
        """Derived next PM date, or None when no interval / no baseline."""
        if self.pmIntervalDays <= 0 or self.lastPmDate is None:
            return None
        return self.lastPmDate + timedelta(days=self.pmIntervalDays)

    def isPmDue(self, asOf: date) -> bool:
        """True when a PM cycle is scheduled and the next date has arrived."""
        due = self.nextDueDate()
        return due is not None and asOf >= due

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "tenantId": str(self.tenantId),
            "code": self.code,
            "name": self.name,
            "status": str(self.status),
            "department": str(self.department),
            "pmIntervalDays": self.pmIntervalDays,
        }
