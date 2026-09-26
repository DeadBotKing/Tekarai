"""ORM implementations for the asset registry and analytics (Phase 26)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from django.db.models import Q

from apps.maintenance.domain.entities.assetRegistry import (
    DeviceAssignment,
    DeviceBomItem,
    DeviceSpecification,
    MaintenanceLocation,
    MaintenancePersonnel,
    PmExecution,
    PmPlan,
)
from apps.maintenance.domain.services.maintenanceAnalytics import (
    PartUsageReading,
    PmExecutionReading,
    WorkOrderReading,
)
from apps.maintenance.infrastructure.models import (
    DeviceAssignmentModel,
    DeviceBomModel,
    DeviceModel,
    DeviceSpecificationModel,
    MaintenanceLocationModel,
    MaintenancePersonnelModel,
    PmExecutionModel,
    PmPlanModel,
    SparePartModel,
    WorkOrderModel,
    WorkOrderPartUsageModel,
)
from apps.sharedKernel.domain.errors import EntityNotFoundError

MAX_LOCATION_DEPTH = 12


def _splitLines(value: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in (value or "").splitlines() if line.strip())


def _joinLines(values: list[str] | tuple[str, ...]) -> str:
    return "\n".join(item.strip() for item in values if item and item.strip())


# =====================================================================================
# Locations
# =====================================================================================
class LocationRepositoryDjango:
    """Hierarchical location tree; ``path`` is recomputed on every write."""

    def create(
        self,
        tenantId: uuid.UUID,
        code: str,
        name: str,
        kind: str,
        parentId: uuid.UUID | None,
        note: str,
        now: datetime,
    ) -> MaintenanceLocation:
        model = MaintenanceLocationModel.objects.create(
            tenantId=tenantId,
            code=code.strip(),
            name=name.strip(),
            kind=kind,
            parentId=parentId,
            path=self._buildPath(tenantId, parentId, name.strip()),
            note=note,
            createdAt=now,
        )
        return self.toDomain(model)

    def update(
        self,
        tenantId: uuid.UUID,
        locationId: uuid.UUID,
        name: str,
        kind: str,
        parentId: uuid.UUID | None,
        note: str,
        now: datetime,
    ) -> MaintenanceLocation:
        model = self._get(tenantId, locationId)
        if parentId and self._wouldCycle(tenantId, locationId, parentId):
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "A location cannot be placed inside itself.",
                fieldErrors={"parentId": "cycle"},
            )
        model.name = name.strip()
        model.kind = kind
        model.parentId = parentId
        model.note = note
        model.path = self._buildPath(tenantId, parentId, model.name)
        model.updatedAt = now
        model.save(update_fields=["name", "kind", "parentId", "note", "path", "updatedAt"])
        self._refreshDescendants(tenantId, model.id, model.path)
        return self.toDomain(model)

    def delete(self, tenantId: uuid.UUID, locationId: uuid.UUID, now: datetime) -> None:
        model = self._get(tenantId, locationId)
        model.deletedAt = now
        model.save(update_fields=["deletedAt"])

    def getById(self, tenantId: uuid.UUID, locationId: uuid.UUID) -> MaintenanceLocation | None:
        model = MaintenanceLocationModel.objects.filter(
            id=locationId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        return self.toDomain(model) if model else None

    def getByCode(self, tenantId: uuid.UUID, code: str) -> MaintenanceLocation | None:
        model = MaintenanceLocationModel.objects.filter(
            tenantId=tenantId, code=code, deletedAt__isnull=True
        ).first()
        return self.toDomain(model) if model else None

    def list(self, tenantId: uuid.UUID, search: str = "") -> list[MaintenanceLocation]:
        queryset = MaintenanceLocationModel.objects.filter(
            tenantId=tenantId, deletedAt__isnull=True
        )
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(code__icontains=search) | Q(path__icontains=search)
            )
        return [self.toDomain(model) for model in queryset]

    def countDevices(self, tenantId: uuid.UUID) -> dict[str, int]:
        counts: dict[str, int] = {}
        rows = DeviceModel.objects.filter(
            tenantId=tenantId, deletedAt__isnull=True, locationId__isnull=False
        ).values_list("locationId", flat=True)
        for locationId in rows:
            key = str(locationId)
            counts[key] = counts.get(key, 0) + 1
        return counts

    # -- helpers ------------------------------------------------------------------
    def _get(self, tenantId: uuid.UUID, locationId: uuid.UUID) -> MaintenanceLocationModel:
        model = MaintenanceLocationModel.objects.filter(
            id=locationId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        if model is None:
            raise EntityNotFoundError("Location not found.")
        return model

    def _buildPath(self, tenantId: uuid.UUID, parentId: uuid.UUID | None, name: str) -> str:
        if parentId is None:
            return name
        parent = MaintenanceLocationModel.objects.filter(
            id=parentId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        return f"{parent.path} / {name}" if parent else name

    def _wouldCycle(
        self, tenantId: uuid.UUID, locationId: uuid.UUID, parentId: uuid.UUID
    ) -> bool:
        cursor: uuid.UUID | None = parentId
        for _ in range(MAX_LOCATION_DEPTH):
            if cursor is None:
                return False
            if cursor == locationId:
                return True
            parent = MaintenanceLocationModel.objects.filter(
                id=cursor, tenantId=tenantId
            ).values_list("parentId", flat=True).first()
            cursor = parent
        return False

    def _refreshDescendants(self, tenantId: uuid.UUID, parentId: uuid.UUID, path: str) -> None:
        children = MaintenanceLocationModel.objects.filter(
            tenantId=tenantId, parentId=parentId, deletedAt__isnull=True
        )
        for child in children:
            child.path = f"{path} / {child.name}"
            child.save(update_fields=["path"])
            self._refreshDescendants(tenantId, child.id, child.path)

    @staticmethod
    def toDomain(model: MaintenanceLocationModel) -> MaintenanceLocation:
        return MaintenanceLocation(
            id=model.id,
            tenantId=model.tenantId,
            code=model.code,
            name=model.name,
            kind=model.kind,
            parentId=model.parentId,
            path=model.path,
            note=model.note,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
        )


# =====================================================================================
# Personnel
# =====================================================================================
class PersonnelRepositoryDjango:
    def create(
        self,
        tenantId: uuid.UUID,
        personnelCode: str,
        fullName: str,
        specialty: str,
        unit: str,
        phone: str,
        shift: str,
        skills: list[str],
        certifications: list[str],
        active: bool,
        now: datetime,
    ) -> MaintenancePersonnel:
        model = MaintenancePersonnelModel.objects.create(
            tenantId=tenantId,
            personnelCode=personnelCode.strip(),
            fullName=fullName.strip(),
            specialty=specialty,
            unit=unit,
            phone=phone,
            shift=shift,
            skills=_joinLines(skills),
            certifications=_joinLines(certifications),
            active=active,
            createdAt=now,
        )
        return self.toDomain(model)

    def update(
        self,
        tenantId: uuid.UUID,
        personnelId: uuid.UUID,
        fullName: str,
        specialty: str,
        unit: str,
        phone: str,
        shift: str,
        skills: list[str],
        certifications: list[str],
        active: bool,
        now: datetime,
    ) -> MaintenancePersonnel:
        model = self._get(tenantId, personnelId)
        model.fullName = fullName.strip()
        model.specialty = specialty
        model.unit = unit
        model.phone = phone
        model.shift = shift
        model.skills = _joinLines(skills)
        model.certifications = _joinLines(certifications)
        model.active = active
        model.updatedAt = now
        model.save()
        return self.toDomain(model)

    def delete(self, tenantId: uuid.UUID, personnelId: uuid.UUID, now: datetime) -> None:
        model = self._get(tenantId, personnelId)
        model.deletedAt = now
        model.save(update_fields=["deletedAt"])

    def getById(self, tenantId: uuid.UUID, personnelId: uuid.UUID) -> MaintenancePersonnel | None:
        model = MaintenancePersonnelModel.objects.filter(
            id=personnelId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        return self.toDomain(model) if model else None

    def getByCode(self, tenantId: uuid.UUID, code: str) -> MaintenancePersonnel | None:
        model = MaintenancePersonnelModel.objects.filter(
            tenantId=tenantId, personnelCode=code, deletedAt__isnull=True
        ).first()
        return self.toDomain(model) if model else None

    def list(
        self, tenantId: uuid.UUID, search: str = "", specialty: str = ""
    ) -> list[MaintenancePersonnel]:
        queryset = MaintenancePersonnelModel.objects.filter(
            tenantId=tenantId, deletedAt__isnull=True
        )
        if specialty:
            queryset = queryset.filter(specialty=specialty)
        if search:
            queryset = queryset.filter(
                Q(fullName__icontains=search)
                | Q(personnelCode__icontains=search)
                | Q(unit__icontains=search)
                | Q(skills__icontains=search)
            )
        return [self.toDomain(model) for model in queryset]

    def _get(self, tenantId: uuid.UUID, personnelId: uuid.UUID) -> MaintenancePersonnelModel:
        model = MaintenancePersonnelModel.objects.filter(
            id=personnelId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        if model is None:
            raise EntityNotFoundError("Personnel record not found.")
        return model

    @staticmethod
    def toDomain(model: MaintenancePersonnelModel) -> MaintenancePersonnel:
        return MaintenancePersonnel(
            id=model.id,
            tenantId=model.tenantId,
            personnelCode=model.personnelCode,
            fullName=model.fullName,
            specialty=model.specialty,
            unit=model.unit,
            phone=model.phone,
            shift=model.shift,
            skills=_splitLines(model.skills),
            certifications=_splitLines(model.certifications),
            active=model.active,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
        )


# =====================================================================================
# Device registry parts — specifications, PM plans, BOM, assignments
# =====================================================================================
class DeviceRegistryRepositoryDjango:
    # -- specifications ------------------------------------------------------------
    def replaceSpecifications(
        self,
        tenantId: uuid.UUID,
        deviceId: uuid.UUID,
        rows: list[dict[str, object]],
        now: datetime,
    ) -> list[DeviceSpecification]:
        DeviceSpecificationModel.objects.filter(tenantId=tenantId, deviceId=deviceId).delete()
        created = [
            DeviceSpecificationModel(
                tenantId=tenantId,
                deviceId=deviceId,
                label=str(row.get("label", "")).strip(),
                value=str(row.get("value", "")).strip(),
                unit=str(row.get("unit", "")).strip(),
                sortOrder=int(row.get("sortOrder", index) or index),
                createdAt=now,
            )
            for index, row in enumerate(rows)
            if str(row.get("label", "")).strip()
        ]
        DeviceSpecificationModel.objects.bulk_create(created)
        return self.listSpecifications(tenantId, deviceId)

    def listSpecifications(
        self, tenantId: uuid.UUID, deviceId: uuid.UUID
    ) -> list[DeviceSpecification]:
        return [
            DeviceSpecification(
                id=model.id,
                tenantId=model.tenantId,
                deviceId=model.deviceId,
                label=model.label,
                value=model.value,
                unit=model.unit,
                sortOrder=model.sortOrder,
            )
            for model in DeviceSpecificationModel.objects.filter(
                tenantId=tenantId, deviceId=deviceId
            )
        ]

    # -- PM plans ------------------------------------------------------------------
    def createPlan(
        self, tenantId: uuid.UUID, deviceId: uuid.UUID, payload: dict[str, object], now: datetime
    ) -> PmPlan:
        model = PmPlanModel.objects.create(
            tenantId=tenantId,
            deviceId=deviceId,
            title=str(payload.get("title", "")).strip(),
            discipline=str(payload.get("discipline", "general")),
            description=str(payload.get("description", "")),
            checklist=_joinLines(list(payload.get("checklist", []) or [])),
            frequencyEvery=int(payload.get("frequencyEvery", 1) or 1),
            frequencyUnit=str(payload.get("frequencyUnit", "month")),
            estimatedMinutes=int(payload.get("estimatedMinutes", 0) or 0),
            responsibleName=str(payload.get("responsibleName", "")),
            lastExecutedOn=payload.get("lastExecutedOn") or None,
            active=bool(payload.get("active", True)),
            createdAt=now,
        )
        return self.toPlan(model)

    def updatePlan(
        self, tenantId: uuid.UUID, planId: uuid.UUID, payload: dict[str, object], now: datetime
    ) -> PmPlan:
        model = PmPlanModel.objects.filter(
            id=planId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        if model is None:
            raise EntityNotFoundError("PM plan not found.")
        model.title = str(payload.get("title", model.title)).strip()
        model.discipline = str(payload.get("discipline", model.discipline))
        model.description = str(payload.get("description", model.description))
        model.checklist = _joinLines(list(payload.get("checklist", []) or []))
        model.frequencyEvery = int(payload.get("frequencyEvery", model.frequencyEvery) or 1)
        model.frequencyUnit = str(payload.get("frequencyUnit", model.frequencyUnit))
        model.estimatedMinutes = int(payload.get("estimatedMinutes", model.estimatedMinutes) or 0)
        model.responsibleName = str(payload.get("responsibleName", model.responsibleName))
        model.active = bool(payload.get("active", model.active))
        model.updatedAt = now
        model.save()
        return self.toPlan(model)

    def deletePlan(self, tenantId: uuid.UUID, planId: uuid.UUID, now: datetime) -> None:
        PmPlanModel.objects.filter(id=planId, tenantId=tenantId).update(deletedAt=now)

    def getPlan(self, tenantId: uuid.UUID, planId: uuid.UUID) -> PmPlan | None:
        model = PmPlanModel.objects.filter(
            id=planId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        return self.toPlan(model) if model else None

    def listPlans(
        self, tenantId: uuid.UUID, deviceId: uuid.UUID | None = None, discipline: str = ""
    ) -> list[PmPlan]:
        queryset = PmPlanModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
        if deviceId is not None:
            queryset = queryset.filter(deviceId=deviceId)
        if discipline:
            queryset = queryset.filter(discipline=discipline)
        return [self.toPlan(model) for model in queryset]

    def recordExecution(
        self,
        tenantId: uuid.UUID,
        planId: uuid.UUID,
        payload: dict[str, object],
        now: datetime,
    ) -> PmExecution:
        plan = PmPlanModel.objects.filter(
            id=planId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        if plan is None:
            raise EntityNotFoundError("PM plan not found.")
        performedOn: date = payload.get("performedOn") or now.date()  # type: ignore[assignment]
        dueOn = self.toPlan(plan).nextDueOn()
        model = PmExecutionModel.objects.create(
            tenantId=tenantId,
            planId=planId,
            deviceId=plan.deviceId,
            discipline=plan.discipline,
            performedOn=performedOn,
            dueOn=dueOn,
            onTime=bool(dueOn is None or performedOn <= dueOn),
            performedByName=str(payload.get("performedByName", "")),
            durationMinutes=int(payload.get("durationMinutes", 0) or 0),
            findings=str(payload.get("findings", "")),
            createdAt=now,
        )
        plan.lastExecutedOn = performedOn
        plan.updatedAt = now
        plan.save(update_fields=["lastExecutedOn", "updatedAt"])
        return self.toExecution(model)

    def listExecutions(
        self,
        tenantId: uuid.UUID,
        deviceId: uuid.UUID | None = None,
        fromDate: date | None = None,
        toDate: date | None = None,
    ) -> list[PmExecution]:
        queryset = PmExecutionModel.objects.filter(tenantId=tenantId)
        if deviceId is not None:
            queryset = queryset.filter(deviceId=deviceId)
        if fromDate is not None:
            queryset = queryset.filter(performedOn__gte=fromDate)
        if toDate is not None:
            queryset = queryset.filter(performedOn__lte=toDate)
        return [self.toExecution(model) for model in queryset]

    # -- bill of materials ----------------------------------------------------------
    def addBomItem(
        self,
        tenantId: uuid.UUID,
        deviceId: uuid.UUID,
        partId: uuid.UUID,
        position: str,
        standardQuantity: Decimal,
        note: str,
        now: datetime,
    ) -> DeviceBomItem:
        part = SparePartModel.objects.filter(
            id=partId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        if part is None:
            raise EntityNotFoundError("Spare part not found.")
        model, _created = DeviceBomModel.objects.update_or_create(
            tenantId=tenantId,
            deviceId=deviceId,
            partId=partId,
            defaults={
                "position": position,
                "standardQuantity": standardQuantity,
                "note": note,
                "createdAt": now,
            },
        )
        return self._toBomItem(model, part)

    def removeBomItem(self, tenantId: uuid.UUID, deviceId: uuid.UUID, partId: uuid.UUID) -> None:
        DeviceBomModel.objects.filter(
            tenantId=tenantId, deviceId=deviceId, partId=partId
        ).delete()

    def listBom(self, tenantId: uuid.UUID, deviceId: uuid.UUID) -> list[DeviceBomItem]:
        rows = list(DeviceBomModel.objects.filter(tenantId=tenantId, deviceId=deviceId))
        parts = {
            part.id: part
            for part in SparePartModel.objects.filter(
                tenantId=tenantId, id__in=[row.partId for row in rows]
            )
        }
        return [self._toBomItem(row, parts.get(row.partId)) for row in rows]

    def listDevicesForPart(self, tenantId: uuid.UUID, partId: uuid.UUID) -> list[uuid.UUID]:
        return list(
            DeviceBomModel.objects.filter(tenantId=tenantId, partId=partId).values_list(
                "deviceId", flat=True
            )
        )

    # -- assignments -----------------------------------------------------------------
    def replaceAssignments(
        self,
        tenantId: uuid.UUID,
        deviceId: uuid.UUID,
        rows: list[dict[str, object]],
        now: datetime,
    ) -> list[DeviceAssignment]:
        DeviceAssignmentModel.objects.filter(tenantId=tenantId, deviceId=deviceId).delete()
        created = []
        for row in rows:
            name = str(row.get("personnelName", "")).strip()
            personnelId = row.get("personnelId") or None
            if personnelId:
                person = MaintenancePersonnelModel.objects.filter(
                    id=personnelId, tenantId=tenantId, deletedAt__isnull=True
                ).first()
                if person is not None:
                    name = name or person.fullName
            if not name:
                continue
            created.append(
                DeviceAssignmentModel(
                    tenantId=tenantId,
                    deviceId=deviceId,
                    personnelId=personnelId,
                    personnelName=name,
                    role=str(row.get("role", "technician")),
                    unit=str(row.get("unit", "")),
                    fromDate=row.get("fromDate") or None,
                    toDate=row.get("toDate") or None,
                    createdAt=now,
                )
            )
        DeviceAssignmentModel.objects.bulk_create(created)
        return self.listAssignments(tenantId, deviceId)

    def listAssignments(self, tenantId: uuid.UUID, deviceId: uuid.UUID) -> list[DeviceAssignment]:
        return [
            DeviceAssignment(
                id=model.id,
                tenantId=model.tenantId,
                deviceId=model.deviceId,
                role=model.role,
                personnelId=model.personnelId,
                personnelName=model.personnelName,
                unit=model.unit,
                fromDate=model.fromDate,
                toDate=model.toDate,
            )
            for model in DeviceAssignmentModel.objects.filter(
                tenantId=tenantId, deviceId=deviceId
            )
        ]

    # -- mapping ----------------------------------------------------------------------
    @staticmethod
    def toPlan(model: PmPlanModel) -> PmPlan:
        return PmPlan(
            id=model.id,
            tenantId=model.tenantId,
            deviceId=model.deviceId,
            title=model.title,
            discipline=model.discipline,
            description=model.description,
            checklist=_splitLines(model.checklist),
            frequencyEvery=model.frequencyEvery,
            frequencyUnit=model.frequencyUnit,
            estimatedMinutes=model.estimatedMinutes,
            responsibleName=model.responsibleName,
            lastExecutedOn=model.lastExecutedOn,
            active=model.active,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
        )

    @staticmethod
    def toExecution(model: PmExecutionModel) -> PmExecution:
        return PmExecution(
            id=model.id,
            tenantId=model.tenantId,
            planId=model.planId,
            deviceId=model.deviceId,
            discipline=model.discipline,
            performedOn=model.performedOn,
            dueOn=model.dueOn,
            onTime=model.onTime,
            performedByName=model.performedByName,
            durationMinutes=model.durationMinutes,
            findings=model.findings,
            workOrderId=model.workOrderId,
            createdAt=model.createdAt,
        )

    @staticmethod
    def _toBomItem(model: DeviceBomModel, part: SparePartModel | None) -> DeviceBomItem:
        return DeviceBomItem(
            id=model.id,
            tenantId=model.tenantId,
            deviceId=model.deviceId,
            partId=model.partId,
            partCode=part.code if part else "",
            partName=part.name if part else "",
            unit=part.unit if part else "",
            position=model.position,
            standardQuantity=model.standardQuantity,
            note=model.note,
            quantityOnHand=part.quantityOnHand if part else Decimal("0"),
            minimumStock=part.minimumStock if part else Decimal("0"),
        )


# =====================================================================================
# Analytics readings
# =====================================================================================
class MaintenanceAnalyticsRepositoryDjango:
    """Reads the dated rows the analytics engine turns into metrics."""

    def readWorkOrders(
        self,
        tenantId: uuid.UUID,
        deviceId: uuid.UUID | None,
        fromDate: date,
        toDate: date,
    ) -> list[WorkOrderReading]:
        queryset = WorkOrderModel.objects.filter(
            tenantId=tenantId,
            deletedAt__isnull=True,
            createdAt__gte=self._startOfDay(fromDate),
            createdAt__lte=self._endOfDay(toDate),
        )
        if deviceId is not None:
            queryset = queryset.filter(deviceId=deviceId)
        return [self._toOrderReading(model) for model in queryset]

    def readPartUsage(
        self,
        tenantId: uuid.UUID,
        deviceId: uuid.UUID | None,
        fromDate: date,
        toDate: date,
    ) -> list[PartUsageReading]:
        orders = WorkOrderModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
        if deviceId is not None:
            orders = orders.filter(deviceId=deviceId)
        orderMap = {
            str(row["id"]): str(row["deviceId"]) for row in orders.values("id", "deviceId")
        }
        usages = WorkOrderPartUsageModel.objects.filter(
            tenantId=tenantId,
            workOrderId__in=[uuid.UUID(key) for key in orderMap],
            consumedAt__gte=self._startOfDay(fromDate),
            consumedAt__lte=self._endOfDay(toDate),
        )
        deviceIds = {uuid.UUID(value) for value in orderMap.values()}
        devices = {
            str(device.id): device
            for device in DeviceModel.objects.filter(tenantId=tenantId, id__in=deviceIds)
        }
        readings: list[PartUsageReading] = []
        for usage in usages:
            ownerDeviceId = orderMap.get(str(usage.workOrderId), "")
            device = devices.get(ownerDeviceId)
            readings.append(
                PartUsageReading(
                    partId=str(usage.partId),
                    partCode=usage.partCode,
                    partName=usage.partName,
                    unit=usage.unit,
                    quantity=usage.quantity,
                    consumedAt=usage.consumedAt,
                    workOrderId=str(usage.workOrderId),
                    deviceId=ownerDeviceId,
                    deviceCode=device.code if device else "",
                    deviceName=device.name if device else "",
                )
            )
        return readings

    def readPmExecutions(
        self,
        tenantId: uuid.UUID,
        deviceId: uuid.UUID | None,
        fromDate: date,
        toDate: date,
    ) -> list[PmExecutionReading]:
        queryset = PmExecutionModel.objects.filter(
            tenantId=tenantId, performedOn__gte=fromDate, performedOn__lte=toDate
        )
        if deviceId is not None:
            queryset = queryset.filter(deviceId=deviceId)
        return [
            PmExecutionReading(
                planId=str(model.planId),
                discipline=model.discipline,
                performedOn=model.performedOn,
                dueOn=model.dueOn,
                onTime=model.onTime,
                durationMinutes=model.durationMinutes,
            )
            for model in queryset
        ]

    @staticmethod
    def _startOfDay(value: date) -> datetime:
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)

    @staticmethod
    def _endOfDay(value: date) -> datetime:
        return datetime(value.year, value.month, value.day, 23, 59, 59, tzinfo=timezone.utc)

    @staticmethod
    def _toOrderReading(model: WorkOrderModel) -> WorkOrderReading:
        return WorkOrderReading(
            id=str(model.id),
            title=model.title,
            orderType=model.orderType,
            status=model.status,
            priority=model.priority,
            department=model.department,
            assignedToName=model.assignedToName,
            failureType=model.failureType,
            failedComponent=model.failedComponent,
            rootCause=model.rootCause,
            repeatFailure=model.repeatFailure,
            createdAt=model.createdAt,
            closedAt=model.closedAt,
            failureReportedAt=model.failureReportedAt,
            repairStartedAt=model.repairStartedAt,
            repairFinishedAt=model.repairFinishedAt,
            returnedToServiceAt=model.returnedToServiceAt,
            downtimeMinutes=model.downtimeMinutes,
            labourHours=model.labourHours,
            labourCost=model.labourCost,
            partsCost=model.partsCost,
        )
