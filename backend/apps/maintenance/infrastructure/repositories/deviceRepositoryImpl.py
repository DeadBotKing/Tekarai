"""ORM implementation of DeviceRepository (Phase 21)."""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db.models import Q

from apps.maintenance.domain.entities.device import Device
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    DeviceFilters,
    DevicePage,
)
from apps.maintenance.domain.valueObjects.maintenanceState import (
    DeviceStatus,
    MaintenanceDepartment,
)
from apps.maintenance.infrastructure.models import DeviceModel
from apps.sharedKernel.domain.errors import ValidationFailedError

SORTABLE_COLUMNS = {
    "createdAt": "createdAt",
    "code": "code",
    "name": "name",
    "status": "status",
}


class DeviceRepositoryDjango:
    def create(self, device: Device) -> None:
        DeviceModel.objects.create(
            id=device.id,
            tenantId=device.tenantId,
            code=device.code,
            name=device.name,
            location=device.location,
            status=str(device.status),
            department=str(device.department),
            pmIntervalDays=device.pmIntervalDays,
            lastPmDate=device.lastPmDate,
            createdAt=device.createdAt,
        )

    def update(self, device: Device) -> None:
        DeviceModel.objects.filter(id=device.id).update(
            name=device.name,
            location=device.location,
            status=str(device.status),
            department=str(device.department),
            pmIntervalDays=device.pmIntervalDays,
            lastPmDate=device.lastPmDate,
            updatedAt=device.updatedAt or datetime.now(tz=None),
        )

    def getById(self, tenantId: uuid.UUID, deviceId: uuid.UUID) -> Device | None:
        model = DeviceModel.objects.filter(
            id=deviceId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        return self.toDomain(model) if model else None

    def getByCode(self, tenantId: uuid.UUID, code: str) -> Device | None:
        model = DeviceModel.objects.filter(
            tenantId=tenantId, code=code, deletedAt__isnull=True
        ).first()
        return self.toDomain(model) if model else None

    def countByTenant(self, tenantId: uuid.UUID) -> int:
        return DeviceModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True).count()

    def listDueForPm(self, tenantId: uuid.UUID) -> list[Device]:
        queryset = DeviceModel.objects.filter(
            tenantId=tenantId,
            deletedAt__isnull=True,
            lastPmDate__isnull=False,
            pmIntervalDays__gt=0,
        )
        return [self.toDomain(model) for model in queryset.order_by("lastPmDate")]

    def list(self, filters: DeviceFilters) -> DevicePage:
        queryset = DeviceModel.objects.filter(tenantId=filters.tenantId, deletedAt__isnull=True)
        if filters.status:
            queryset = queryset.filter(status=filters.status)
        if filters.department:
            queryset = queryset.filter(department=filters.department)
        if filters.search:
            queryset = queryset.filter(
                Q(name__icontains=filters.search)
                | Q(code__icontains=filters.search)
                | Q(location__icontains=filters.search)
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
        return DevicePage(items=items, totalCount=totalCount)

    @staticmethod
    def toDomain(model: DeviceModel) -> Device:
        return Device(
            id=model.id,
            tenantId=model.tenantId,
            code=model.code,
            name=model.name,
            location=model.location,
            status=DeviceStatus(model.status),
            department=MaintenanceDepartment(model.department),
            pmIntervalDays=model.pmIntervalDays,
            lastPmDate=model.lastPmDate,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
            deletedAt=model.deletedAt,
        )
