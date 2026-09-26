"""ORM implementation of DeviceRepository (Phase 21)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

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
            manufacturer=model.manufacturer,
            modelNumber=model.modelNumber,
            serialNumber=model.serialNumber,
            equipmentType=model.assetType,
            criticality=model.criticality or "medium",
            locationId=model.locationId,
            locationPath=model.locationPath,
            parentDeviceId=model.parentDeviceId,
            operatorUnit=model.operatorUnit,
            runningHours=float(model.runningHours or 0),
        )

    # -- Phase 26 asset registry -----------------------------------------------------
    #: Registry columns a device carries beyond its maintenance basics. Kept as a
    #: whitelist so a client can never write an arbitrary column through the API.
    NAMEPLATE_FIELDS = (
        "manufacturer",
        "modelNumber",
        "serialNumber",
        "assetType",
        "manufactureYear",
        "capacity",
        "powerRating",
        "electricalSpec",
        "criticality",
        "operatorUnit",
        "supplier",
        "notes",
    )
    NAMEPLATE_DATE_FIELDS = ("purchasedOn", "installedOn", "commissionedOn", "warrantyUntil")
    NAMEPLATE_DECIMAL_FIELDS = ("purchaseCost", "runningHours")

    def updateNameplate(
        self,
        tenantId: uuid.UUID,
        deviceId: uuid.UUID,
        values: dict,
        locationPath: str,
        now: datetime,
    ) -> None:
        """Write the optional registry attributes of one device."""
        model = DeviceModel.objects.filter(
            id=deviceId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        if model is None:
            return
        for field in self.NAMEPLATE_FIELDS:
            if field in values:
                setattr(model, field, values[field] or "")
        for field in self.NAMEPLATE_DATE_FIELDS:
            if field in values:
                setattr(model, field, values[field] or None)
        for field in self.NAMEPLATE_DECIMAL_FIELDS:
            if field in values:
                raw = values[field]
                setattr(model, field, Decimal(str(raw)) if str(raw or "").strip() else Decimal("0"))
        if "locationId" in values:
            model.locationId = values["locationId"] or None
            model.locationPath = locationPath
        if "parentDeviceId" in values:
            parent = values["parentDeviceId"] or None
            model.parentDeviceId = None if parent == deviceId else parent
        model.updatedAt = now
        model.save()

    def readNameplate(self, tenantId: uuid.UUID, deviceId: uuid.UUID) -> dict:
        """Registry attributes as a plain dict for the profile/report payloads."""
        model = DeviceModel.objects.filter(
            id=deviceId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        if model is None:
            return {}
        payload: dict = {field: getattr(model, field) for field in self.NAMEPLATE_FIELDS}
        for field in self.NAMEPLATE_DATE_FIELDS:
            value = getattr(model, field)
            payload[field] = value.isoformat() if value else ""
        for field in self.NAMEPLATE_DECIMAL_FIELDS:
            payload[field] = str(getattr(model, field))
        payload["locationId"] = str(model.locationId) if model.locationId else ""
        payload["locationPath"] = model.locationPath
        payload["parentDeviceId"] = str(model.parentDeviceId) if model.parentDeviceId else ""
        return payload

    def listChildren(self, tenantId: uuid.UUID, deviceId: uuid.UUID) -> list[Device]:
        """Sub-assemblies whose parent is this device (motor, gearbox, panel…)."""
        return [
            self.toDomain(model)
            for model in DeviceModel.objects.filter(
                tenantId=tenantId, parentDeviceId=deviceId, deletedAt__isnull=True
            )
        ]

    def recordClosureDetails(
        self, tenantId: uuid.UUID, workOrderId: uuid.UUID, values: dict, now: datetime
    ) -> bool:
        """Persist the failure / downtime / cost facts of one closed work order."""
        from apps.maintenance.infrastructure.models import WorkOrderModel

        model = WorkOrderModel.objects.filter(
            id=workOrderId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        if model is None:
            return False
        for field in (
            "failureType",
            "failedComponent",
            "failureSymptom",
            "rootCause",
            "actionTaken",
        ):
            if field in values:
                setattr(model, field, values[field] or "")
        if "repeatFailure" in values:
            model.repeatFailure = bool(values["repeatFailure"])
        for field in (
            "failureReportedAt",
            "repairStartedAt",
            "repairFinishedAt",
            "returnedToServiceAt",
        ):
            if field in values:
                setattr(model, field, values[field] or None)
        if "downtimeMinutes" in values:
            model.downtimeMinutes = int(values["downtimeMinutes"] or 0)
        for field in ("labourHours", "labourCost", "partsCost"):
            if field in values:
                raw = values[field]
                setattr(model, field, Decimal(str(raw)) if str(raw or "").strip() else Decimal("0"))
        model.updatedAt = now
        model.save()
        return True
