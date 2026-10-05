"""Equipment-registry and analytics use cases (Phase 26).

Two groups live here:

* **Registry CRUD** — locations, personnel, device specifications, PM plans,
  bill of materials and personnel assignments. Each is an independent record
  linked to a device, so the same part or person is never duplicated.
* **Analytics** — per-device and fleet-wide statistics. Nothing is cached on
  the device row: every figure is recomputed from work orders, part issues and
  PM executions, which is what allows the UI to drill from any number down to
  the exact records behind it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date
from decimal import Decimal

from apps.maintenance.application.dto.maintenanceDtos import deviceDtoFromDomain
from apps.maintenance.application.dto.registryDtos import (
    AssignmentDto,
    BomItemDto,
    DeviceAnalyticsDto,
    DeviceProfileDto,
    FailureModeDto,
    FleetAnalyticsDto,
    FleetAnalyticsRowDto,
    LocationDto,
    LocationListDto,
    PartConsumptionDto,
    PartUsageReportDto,
    PartUsageReportRowDto,
    PersonnelDto,
    PersonnelListDto,
    PmExecutionDto,
    PmPlanDto,
    TechnicianStatDto,
    TrendBucketDto,
    analyticsDto,
    assignmentDto,
    bomItemDto,
    locationDto,
    personnelDto,
    pmExecutionDto,
    pmPlanDto,
    specificationDto,
)
from apps.maintenance.application.services.tenantResolver import (
    parseDateOrNone,
    resolveTenantId,
)
from apps.maintenance.domain.services.assetHierarchyRules import (
    assertDepthWithinLimit,
    assertLocationNesting,
    assertNoCycle,
    resolveChildLevel,
)
from apps.maintenance.domain.services.maintenanceAnalytics import (
    computeDeviceAnalytics,
    defaultWindow,
    summarisePartUsage,
    summariseTechnicians,
)
from apps.maintenance.domain.valueObjects.maintenanceState import FREQUENCY_RUNNING_HOUR
from apps.maintenance.domain.valueObjects.meterTypes import (
    TRIGGER_CALENDAR,
    TRIGGER_CONDITION,
    TRIGGER_METER,
    MeterValue,
    ensureThresholdOperator,
    ensureTriggerType,
    normalizeMeterCode,
    normalizeSensorKey,
)
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_DELETE, AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import (
    DuplicateBusinessCodeError,
    EntityNotFoundError,
    ValidationFailedError,
)

PERMISSION_REGISTRY_VIEW = "maintenance.device.view"
PERMISSION_REGISTRY_MANAGE = "maintenance.device.manage"
PERMISSION_REGISTRY_LIST = "maintenance.device.list"


def planDecimal(raw: str, fieldName: str) -> Decimal | None:
    """Parse an optional decimal field of a PM plan."""
    text = str(raw or "").strip()
    if not text:
        return None
    return MeterValue.parse(text, fieldName=fieldName).amount


def resolveTriggerType(requested: str, frequencyUnit: str) -> str:
    """Decide which trigger governs a plan.

    ``frequencyUnit='runningHour'`` is the pre-existing way the UI expressed
    "every N running hours". It is treated as a meter trigger so plans saved
    through the old form start working instead of staying inert.
    """
    trigger = str(requested or "").strip() or TRIGGER_CALENDAR
    if trigger == TRIGGER_CALENDAR and frequencyUnit == FREQUENCY_RUNNING_HOUR:
        return TRIGGER_METER
    return trigger


# =====================================================================================
# Commands / queries
# =====================================================================================
@dataclass(frozen=True)
class SaveLocationCommand:
    locationId: str = ""
    code: str = ""
    name: str = ""
    kind: str = "site"
    parentId: str = ""
    note: str = ""


@dataclass(frozen=True)
class DeleteLocationCommand:
    locationId: str


@dataclass(frozen=True)
class ListLocationsQuery:
    search: str = ""


@dataclass(frozen=True)
class SavePersonnelCommand:
    personnelId: str = ""
    personnelCode: str = ""
    fullName: str = ""
    specialty: str = "general"
    unit: str = ""
    phone: str = ""
    shift: str = ""
    skills: tuple[str, ...] = ()
    certifications: tuple[str, ...] = ()
    active: bool = True


@dataclass(frozen=True)
class DeletePersonnelCommand:
    personnelId: str


@dataclass(frozen=True)
class ListPersonnelQuery:
    search: str = ""
    specialty: str = ""


@dataclass(frozen=True)
class SaveSpecificationsCommand:
    deviceId: str
    rows: tuple[dict, ...] = ()


@dataclass(frozen=True)
class SavePmPlanCommand:
    deviceId: str = ""
    planId: str = ""
    title: str = ""
    discipline: str = "general"
    description: str = ""
    checklist: tuple[str, ...] = ()
    frequencyEvery: int = 1
    frequencyUnit: str = "month"
    estimatedMinutes: int = 0
    responsibleName: str = ""
    active: bool = True
    # -- Meter / condition trigger ------------------------------------------------
    triggerType: str = "calendar"
    metricType: str = ""
    metricInterval: str = ""
    thresholdOperator: str = ">="
    thresholdValue: str = ""
    warningValue: str = ""
    metricUnit: str = ""
    sensorKey: str = ""


@dataclass(frozen=True)
class DeletePmPlanCommand:
    planId: str


@dataclass(frozen=True)
class RecordPmExecutionCommand:
    planId: str
    performedOn: str = ""
    performedByName: str = ""
    durationMinutes: int = 0
    findings: str = ""
    #: Meter value observed at execution. Blank lets the repository read the
    #: bound meter point's current value.
    meterValue: str = ""


@dataclass(frozen=True)
class SaveBomItemCommand:
    deviceId: str
    partId: str
    position: str = ""
    standardQuantity: str = "1"
    note: str = ""


@dataclass(frozen=True)
class RemoveBomItemCommand:
    deviceId: str
    partId: str


@dataclass(frozen=True)
class SaveAssignmentsCommand:
    deviceId: str
    rows: tuple[dict, ...] = ()


@dataclass(frozen=True)
class GetDeviceProfileQuery:
    deviceId: str
    fromDate: str = ""
    toDate: str = ""


@dataclass(frozen=True)
class GetDeviceAnalyticsQuery:
    deviceId: str
    fromDate: str = ""
    toDate: str = ""


@dataclass(frozen=True)
class GetFleetAnalyticsQuery:
    fromDate: str = ""
    toDate: str = ""
    department: str = ""
    criticality: str = ""
    locationId: str = ""


@dataclass(frozen=True)
class GetPartUsageReportQuery:
    partId: str
    fromDate: str = ""
    toDate: str = ""


# =====================================================================================
# Base
# =====================================================================================
class RegistryUseCaseBase(UseCase):
    """Shared wiring for every registry use case."""

    def __init__(
        self,
        *,
        deviceRepository,  # noqa: ANN001 — protocol, injected by the container
        registryRepository,  # noqa: ANN001
        locationRepository,  # noqa: ANN001
        personnelRepository,  # noqa: ANN001
        analyticsRepository,  # noqa: ANN001
        unitOfWork,  # noqa: ANN001
        auditRecorder,  # noqa: ANN001
        eventDispatcher,  # noqa: ANN001
        permissionGate,  # noqa: ANN001
        clock,  # noqa: ANN001
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.deviceRepository = deviceRepository
        self.registryRepository = registryRepository
        self.locationRepository = locationRepository
        self.personnelRepository = personnelRepository
        self.analyticsRepository = analyticsRepository

    def resolveWindow(self, fromDate: str, toDate: str, today: date) -> tuple[date, date]:
        start = parseDateOrNone(fromDate)
        end = parseDateOrNone(toDate)
        if start is None or end is None:
            defaultStart, defaultEnd = defaultWindow(today)
            start = start or defaultStart
            end = end or defaultEnd
        if start > end:
            start, end = end, start
        return start, end

    def requireDevice(self, tenantId: uuid.UUID, deviceId: str):  # noqa: ANN201
        device = self.deviceRepository.getById(tenantId, uuid.UUID(deviceId))
        if device is None:
            raise EntityNotFoundError("Device not found.")
        return device


# =====================================================================================
# Locations
# =====================================================================================
class SaveLocationUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_MANAGE

    def validateCommand(self, command: SaveLocationCommand) -> None:
        if not command.name.strip():
            raise ValidationFailedError(
                "Location name is required.", fieldErrors={"name": "required"}
            )
        if not command.locationId and not command.code.strip():
            raise ValidationFailedError(
                "Location code is required.", fieldErrors={"code": "required"}
            )

    def perform(self, command: SaveLocationCommand) -> LocationDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        parentId = uuid.UUID(command.parentId) if command.parentId else None
        if parentId is not None:
            parent = self.locationRepository.getById(tenantId, parentId)
            if parent is None:
                raise EntityNotFoundError("Parent location not found.")
            # Catalogued kinds carry a rank, so a site filed under a production
            # line is refused. A plant's own word («سوله») has no rank and is
            # always allowed — the vocabulary stays open on purpose.
            assertLocationNesting(parent.kind, parent.name, command.kind)
        if command.locationId:
            location = self.locationRepository.update(
                tenantId,
                uuid.UUID(command.locationId),
                command.name,
                command.kind,
                parentId,
                command.note,
                now,
            )
            action = AUDIT_UPDATE
        else:
            if self.locationRepository.getByCode(tenantId, command.code.strip()) is not None:
                raise DuplicateBusinessCodeError(
                    f"A location with code '{command.code}' already exists."
                )
            location = self.locationRepository.create(
                tenantId, command.code, command.name, command.kind, parentId, command.note, now
            )
            action = AUDIT_CREATE
        self.audit(
            action,
            resourceType="MaintenanceLocation",
            resourceId=str(location.id),
            tenantId=tenantId,
            after={"code": location.code, "path": location.path},
        )
        return locationDto(location)


class DeleteLocationUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: DeleteLocationCommand) -> dict[str, str]:
        tenantId = resolveTenantId("")
        self.locationRepository.delete(tenantId, uuid.UUID(command.locationId), self.clock.nowUtc())
        self.audit(
            AUDIT_DELETE,
            resourceType="MaintenanceLocation",
            resourceId=command.locationId,
            tenantId=tenantId,
        )
        return {"id": command.locationId}


class ListLocationsUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_LIST

    def perform(self, query: ListLocationsQuery) -> LocationListDto:
        tenantId = resolveTenantId("")
        counts = self.locationRepository.countDevices(tenantId)
        items = [
            locationDto(location, counts.get(str(location.id), 0))
            for location in self.locationRepository.list(tenantId, query.search)
        ]
        return LocationListDto(items=items)


# =====================================================================================
# Personnel
# =====================================================================================
class SavePersonnelUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_MANAGE

    def validateCommand(self, command: SavePersonnelCommand) -> None:
        if not command.fullName.strip():
            raise ValidationFailedError(
                "Personnel name is required.", fieldErrors={"fullName": "required"}
            )
        if not command.personnelId and not command.personnelCode.strip():
            raise ValidationFailedError(
                "Personnel code is required.", fieldErrors={"personnelCode": "required"}
            )

    def perform(self, command: SavePersonnelCommand) -> PersonnelDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        if command.personnelId:
            person = self.personnelRepository.update(
                tenantId,
                uuid.UUID(command.personnelId),
                command.fullName,
                command.specialty,
                command.unit,
                command.phone,
                command.shift,
                list(command.skills),
                list(command.certifications),
                command.active,
                now,
            )
            action = AUDIT_UPDATE
        else:
            existing = self.personnelRepository.getByCode(tenantId, command.personnelCode.strip())
            if existing is not None:
                raise DuplicateBusinessCodeError(
                    f"Personnel code '{command.personnelCode}' already exists."
                )
            person = self.personnelRepository.create(
                tenantId,
                command.personnelCode,
                command.fullName,
                command.specialty,
                command.unit,
                command.phone,
                command.shift,
                list(command.skills),
                list(command.certifications),
                command.active,
                now,
            )
            action = AUDIT_CREATE
        self.audit(
            action,
            resourceType="MaintenancePersonnel",
            resourceId=str(person.id),
            tenantId=tenantId,
            after={"code": person.personnelCode, "specialty": person.specialty},
        )
        return personnelDto(person)


class DeletePersonnelUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: DeletePersonnelCommand) -> dict[str, str]:
        tenantId = resolveTenantId("")
        self.personnelRepository.delete(
            tenantId, uuid.UUID(command.personnelId), self.clock.nowUtc()
        )
        self.audit(
            AUDIT_DELETE,
            resourceType="MaintenancePersonnel",
            resourceId=command.personnelId,
            tenantId=tenantId,
        )
        return {"id": command.personnelId}


class ListPersonnelUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_LIST

    def perform(self, query: ListPersonnelQuery) -> PersonnelListDto:
        tenantId = resolveTenantId("")
        return PersonnelListDto(
            items=[
                personnelDto(person)
                for person in self.personnelRepository.list(tenantId, query.search, query.specialty)
            ]
        )


# =====================================================================================
# Device specifications / PM plans / BOM / assignments
# =====================================================================================
class SaveSpecificationsUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: SaveSpecificationsCommand) -> list:
        tenantId = resolveTenantId("")
        self.requireDevice(tenantId, command.deviceId)
        specs = self.registryRepository.replaceSpecifications(
            tenantId, uuid.UUID(command.deviceId), list(command.rows), self.clock.nowUtc()
        )
        self.audit(
            AUDIT_UPDATE,
            resourceType="DeviceSpecification",
            resourceId=command.deviceId,
            tenantId=tenantId,
            after={"count": len(specs)},
        )
        return [specificationDto(spec) for spec in specs]


class SavePmPlanUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_MANAGE

    def validateCommand(self, command: SavePmPlanCommand) -> None:
        if not command.title.strip():
            raise ValidationFailedError(
                "PM plan title is required.", fieldErrors={"title": "required"}
            )
        triggerType = resolveTriggerType(command.triggerType, command.frequencyUnit)
        ensureTriggerType(triggerType)
        ensureThresholdOperator(command.thresholdOperator or ">=")
        if triggerType == TRIGGER_CALENDAR:
            return

        # A meter-driven plan that names no meter can never be evaluated; a
        # database constraint also enforces this, but failing here produces a
        # field-level message instead of an opaque integrity error.
        if not str(command.metricType or "").strip():
            raise ValidationFailedError(
                "A meter-driven plan must name the meter it watches.",
                fieldErrors={"metricType": "required"},
            )
        if triggerType == TRIGGER_METER:
            interval = planDecimal(command.metricInterval, "metricInterval")
            if interval is None:
                interval = Decimal(str(max(1, command.frequencyEvery)))
            if interval <= 0:
                raise ValidationFailedError(
                    "Meter interval must be positive.",
                    fieldErrors={"metricInterval": "notPositive"},
                )
        if triggerType == TRIGGER_CONDITION:
            if planDecimal(command.thresholdValue, "thresholdValue") is None:
                raise ValidationFailedError(
                    "A condition trigger needs a threshold value.",
                    fieldErrors={"thresholdValue": "required"},
                )

    def perform(self, command: SavePmPlanCommand) -> PmPlanDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        triggerType = resolveTriggerType(command.triggerType, command.frequencyUnit)
        metricType = normalizeMeterCode(command.metricType) if command.metricType else ""
        interval = planDecimal(command.metricInterval, "metricInterval")
        if triggerType == TRIGGER_METER and interval is None:
            # "Every 500 running hours" typed into the calendar fields is the
            # same intent; carry it over instead of demanding re-entry.
            interval = Decimal(str(max(1, command.frequencyEvery)))
        payload = {
            "title": command.title,
            "discipline": command.discipline,
            "description": command.description,
            "checklist": list(command.checklist),
            "frequencyEvery": command.frequencyEvery,
            "frequencyUnit": command.frequencyUnit,
            "estimatedMinutes": command.estimatedMinutes,
            "responsibleName": command.responsibleName,
            "active": command.active,
            "triggerType": triggerType,
            "metricType": metricType,
            "metricInterval": interval if interval is not None else Decimal("0"),
            "thresholdOperator": command.thresholdOperator or ">=",
            "thresholdValue": planDecimal(command.thresholdValue, "thresholdValue") or Decimal("0"),
            "warningValue": planDecimal(command.warningValue, "warningValue") or Decimal("0"),
            "metricUnit": command.metricUnit.strip(),
            "sensorKey": normalizeSensorKey(command.sensorKey),
        }
        if command.planId:
            plan = self.registryRepository.updatePlan(
                tenantId, uuid.UUID(command.planId), payload, now
            )
            action = AUDIT_UPDATE
        else:
            self.requireDevice(tenantId, command.deviceId)
            plan = self.registryRepository.createPlan(
                tenantId, uuid.UUID(command.deviceId), payload, now
            )
            action = AUDIT_CREATE
        self.audit(
            action,
            resourceType="PmPlan",
            resourceId=str(plan.id),
            tenantId=tenantId,
            after={"discipline": plan.discipline, "title": plan.title},
        )
        return pmPlanDto(plan, now.date())


class DeletePmPlanUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: DeletePmPlanCommand) -> dict[str, str]:
        tenantId = resolveTenantId("")
        self.registryRepository.deletePlan(tenantId, uuid.UUID(command.planId), self.clock.nowUtc())
        self.audit(
            AUDIT_DELETE, resourceType="PmPlan", resourceId=command.planId, tenantId=tenantId
        )
        return {"id": command.planId}


class ListPmPlansUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: GetDeviceProfileQuery) -> list[PmPlanDto]:
        tenantId = resolveTenantId("")
        asOf = self.clock.nowUtc().date()
        return [
            pmPlanDto(plan, asOf)
            for plan in self.registryRepository.listPlans(tenantId, uuid.UUID(query.deviceId))
        ]


class RecordPmExecutionUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: RecordPmExecutionCommand) -> PmExecutionDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        run = self.registryRepository.recordExecution(
            tenantId,
            uuid.UUID(command.planId),
            {
                "performedOn": parseDateOrNone(command.performedOn) or now.date(),
                "performedByName": command.performedByName,
                "durationMinutes": command.durationMinutes,
                "findings": command.findings,
                "meterValue": planDecimal(command.meterValue, "meterValue"),
            },
            now,
        )
        self.audit(
            AUDIT_CREATE,
            resourceType="PmExecution",
            resourceId=str(run.id),
            tenantId=tenantId,
            after={"planId": str(run.planId), "performedOn": run.performedOn.isoformat()},
        )
        return pmExecutionDto(run)


class SaveBomItemUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: SaveBomItemCommand) -> BomItemDto:
        tenantId = resolveTenantId("")
        self.requireDevice(tenantId, command.deviceId)
        quantity = Decimal(str(command.standardQuantity or "1"))
        if quantity <= 0:
            raise ValidationFailedError(
                "Standard quantity must be positive.",
                fieldErrors={"standardQuantity": "invalid"},
            )
        item = self.registryRepository.addBomItem(
            tenantId,
            uuid.UUID(command.deviceId),
            uuid.UUID(command.partId),
            command.position,
            quantity,
            command.note,
            self.clock.nowUtc(),
        )
        self.audit(
            AUDIT_UPDATE,
            resourceType="DeviceBom",
            resourceId=str(item.id),
            tenantId=tenantId,
            after={"deviceId": command.deviceId, "partId": command.partId},
        )
        return bomItemDto(item)


class RemoveBomItemUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: RemoveBomItemCommand) -> dict[str, str]:
        tenantId = resolveTenantId("")
        self.registryRepository.removeBomItem(
            tenantId, uuid.UUID(command.deviceId), uuid.UUID(command.partId)
        )
        self.audit(
            AUDIT_DELETE,
            resourceType="DeviceBom",
            resourceId=f"{command.deviceId}:{command.partId}",
            tenantId=tenantId,
        )
        return {"deviceId": command.deviceId, "partId": command.partId}


class SaveAssignmentsUseCase(RegistryUseCaseBase):
    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: SaveAssignmentsCommand) -> list[AssignmentDto]:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        self.requireDevice(tenantId, command.deviceId)
        rows = [
            {
                "personnelId": uuid.UUID(str(row["personnelId"]))
                if row.get("personnelId")
                else None,
                "personnelName": row.get("personnelName", ""),
                "role": row.get("role", "technician"),
                "unit": row.get("unit", ""),
                "fromDate": parseDateOrNone(str(row.get("fromDate", ""))),
                "toDate": parseDateOrNone(str(row.get("toDate", ""))),
            }
            for row in command.rows
        ]
        assignments = self.registryRepository.replaceAssignments(
            tenantId, uuid.UUID(command.deviceId), rows, now
        )
        self.audit(
            AUDIT_UPDATE,
            resourceType="DeviceAssignment",
            resourceId=command.deviceId,
            tenantId=tenantId,
            after={"count": len(assignments)},
        )
        return [assignmentDto(item, now.date()) for item in assignments]


# =====================================================================================
# Analytics
# =====================================================================================
class DeviceAnalyticsComputation(RegistryUseCaseBase):
    """Shared device-metric computation for the analytics and profile use cases.

    These helpers used to live on `GetDeviceAnalyticsUseCase`, and
    `GetDeviceProfileUseCase` subclassed it purely to reuse them. That made
    the profile use case a non-substitutable subtype -- it accepts a
    different query and returns a different DTO -- so any caller holding a
    `GetDeviceAnalyticsUseCase` could be handed an object that breaks the
    declared contract. The reusable part now sits in its own base class and
    the two use cases are siblings.
    """

    def _compute(self, tenantId, deviceId, fromDate, toDate, asOf):  # noqa: ANN001, ANN202
        orders = self.analyticsRepository.readWorkOrders(tenantId, deviceId, fromDate, toDate)
        usage = self.analyticsRepository.readPartUsage(tenantId, deviceId, fromDate, toDate)
        executions = self.analyticsRepository.readPmExecutions(tenantId, deviceId, fromDate, toDate)
        plans = self.registryRepository.listPlans(tenantId, deviceId)
        scheduled = self._expectedPmRuns(plans, fromDate, toDate)
        overdue = sum(1 for plan in plans if plan.isOverdue(asOf))
        return computeDeviceAnalytics(
            deviceId=str(deviceId),
            orders=orders,
            partUsages=usage,
            pmExecutions=executions,
            pmPlansDue=scheduled,
            pmPlansOverdue=overdue,
            fromDate=fromDate,
            toDate=toDate,
        )

    @staticmethod
    def _expectedPmRuns(plans, fromDate: date, toDate: date) -> int:  # noqa: ANN001
        """How many PM runs *should* have happened in the window."""
        windowDays = max((toDate - fromDate).days + 1, 1)
        expected = 0
        for plan in plans:
            if not plan.active:
                continue
            period = plan.periodDays()
            if not period:
                continue
            expected += max(int(windowDays // period), 0)
        return expected


class GetDeviceAnalyticsUseCase(DeviceAnalyticsComputation):
    """Recompute every metric for one device from its dated rows."""

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: GetDeviceAnalyticsQuery) -> DeviceAnalyticsDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        fromDate, toDate = self.resolveWindow(query.fromDate, query.toDate, now.date())
        deviceId = uuid.UUID(query.deviceId)
        self.requireDevice(tenantId, query.deviceId)
        return analyticsDto(self._compute(tenantId, deviceId, fromDate, toDate, now.date()))


class GetDeviceProfileUseCase(DeviceAnalyticsComputation):
    """The complete equipment file: master data + registry lists + analytics."""

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: GetDeviceProfileQuery) -> DeviceProfileDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        asOf = now.date()
        fromDate, toDate = self.resolveWindow(query.fromDate, query.toDate, asOf)
        deviceId = uuid.UUID(query.deviceId)
        device = self.requireDevice(tenantId, query.deviceId)

        analytics = self._compute(tenantId, deviceId, fromDate, toDate, asOf)
        usageByPart = {stat.partId: stat for stat in analytics.partConsumption}

        bom = [
            bomItemDto(
                item,
                usageCount=usageByPart[str(item.partId)].usageCount
                if str(item.partId) in usageByPart
                else 0,
                usedQuantity=str(usageByPart[str(item.partId)].totalQuantity)
                if str(item.partId) in usageByPart
                else "0",
                lastUsedAt=usageByPart[str(item.partId)].lastUsedAt
                if str(item.partId) in usageByPart
                else "",
            )
            for item in self.registryRepository.listBom(tenantId, deviceId)
        ]

        # Registry attributes live on the device row but outside the maintenance
        # aggregate, so they are read through the repository rather than the entity.
        nameplate = self.deviceRepository.readNameplate(tenantId, deviceId)

        location = None
        locationPath = str(nameplate.get("locationPath", ""))
        rawLocationId = nameplate.get("locationId", "")
        if rawLocationId:
            found = self.locationRepository.getById(tenantId, uuid.UUID(str(rawLocationId)))
            if found is not None:
                location = locationDto(found)
                locationPath = found.displayPath()

        return DeviceProfileDto(
            device=deviceDtoFromDomain(device, asOf),
            nameplate=nameplate,
            specifications=[
                specificationDto(spec)
                for spec in self.registryRepository.listSpecifications(tenantId, deviceId)
            ],
            pmPlans=[
                pmPlanDto(plan, asOf)
                for plan in self.registryRepository.listPlans(tenantId, deviceId)
            ],
            pmExecutions=[
                pmExecutionDto(run)
                for run in self.registryRepository.listExecutions(tenantId, deviceId)
            ],
            bom=bom,
            assignments=[
                assignmentDto(item, asOf)
                for item in self.registryRepository.listAssignments(tenantId, deviceId)
            ],
            location=location,
            locationPath=locationPath or device.location,
            children=self._children(tenantId, deviceId),
            analytics=analyticsDto(analytics),
            generatedAt=now.isoformat(),
        )

    def _children(self, tenantId, deviceId) -> list[dict[str, str]]:  # noqa: ANN001
        lister = getattr(self.deviceRepository, "listChildren", None)
        if lister is None:
            return []
        return [
            {"id": str(child.id), "code": child.code, "name": child.name}
            for child in lister(tenantId, deviceId)
        ]


class GetFleetAnalyticsUseCase(RegistryUseCaseBase):
    """Plant-wide comparison across every device, plus the aggregate KPIs."""

    requiredAction = PERMISSION_REGISTRY_LIST

    def perform(self, query: GetFleetAnalyticsQuery) -> FleetAnalyticsDto:
        from apps.maintenance.domain.repositories.maintenanceRepositories import DeviceFilters

        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        asOf = now.date()
        fromDate, toDate = self.resolveWindow(query.fromDate, query.toDate, asOf)

        devices = self.deviceRepository.list(
            DeviceFilters(tenantId=tenantId, department=query.department, page=1, pageSize=100)
        ).items

        allOrders = self.analyticsRepository.readWorkOrders(tenantId, None, fromDate, toDate)
        allUsage = self.analyticsRepository.readPartUsage(tenantId, None, fromDate, toDate)

        rows: list[FleetAnalyticsRowDto] = []
        totalRepairs = totalPreventive = 0
        totalDowntime = 0.0
        totalCost = Decimal("0")
        mtbfValues: list[float] = []
        mttrValues: list[float] = []
        availabilityValues: list[float] = []
        complianceValues: list[float] = []

        for device in devices:
            if query.criticality and getattr(device, "criticality", "") != query.criticality:
                continue
            if query.locationId and str(getattr(device, "locationId", "")) != query.locationId:
                continue
            deviceId = device.id
            orders = self.analyticsRepository.readWorkOrders(tenantId, deviceId, fromDate, toDate)
            usage = self.analyticsRepository.readPartUsage(tenantId, deviceId, fromDate, toDate)
            executions = self.analyticsRepository.readPmExecutions(
                tenantId, deviceId, fromDate, toDate
            )
            plans = self.registryRepository.listPlans(tenantId, deviceId)
            analytics = computeDeviceAnalytics(
                deviceId=str(deviceId),
                orders=orders,
                partUsages=usage,
                pmExecutions=executions,
                pmPlansDue=GetDeviceAnalyticsUseCase._expectedPmRuns(plans, fromDate, toDate),
                pmPlansOverdue=sum(1 for plan in plans if plan.isOverdue(asOf)),
                fromDate=fromDate,
                toDate=toDate,
            )
            totalRepairs += analytics.repairCount
            totalPreventive += analytics.preventiveCount
            totalDowntime += analytics.totalDowntimeHours
            totalCost += analytics.totalCost
            if analytics.mtbfHours is not None:
                mtbfValues.append(analytics.mtbfHours)
            if analytics.mttrHours is not None:
                mttrValues.append(analytics.mttrHours)
            if analytics.availabilityPercent is not None:
                availabilityValues.append(analytics.availabilityPercent)
            if analytics.pmCompliancePercent is not None:
                complianceValues.append(analytics.pmCompliancePercent)

            rows.append(
                FleetAnalyticsRowDto(
                    deviceId=str(deviceId),
                    code=device.code,
                    name=device.name,
                    department=str(device.department),
                    criticality=getattr(device, "criticality", "medium"),
                    locationPath=getattr(device, "locationPath", "") or device.location,
                    status=str(device.status),
                    repairCount=analytics.repairCount,
                    preventiveCount=analytics.preventiveCount,
                    repeatFailures=analytics.repeatFailures,
                    downtimeHours=analytics.totalDowntimeHours,
                    mtbfHours=analytics.mtbfHours,
                    mttrHours=analytics.mttrHours,
                    availabilityPercent=analytics.availabilityPercent,
                    pmCompliancePercent=analytics.pmCompliancePercent,
                    partsUsedQuantity=str(analytics.partsUsedQuantity),
                    totalCost=str(analytics.totalCost),
                )
            )

        rows.sort(key=lambda row: (-row.repairCount, -row.downtimeHours, row.code))
        topParts = summarisePartUsage(allUsage)[:15]
        failureTypes: dict[str, int] = {}
        for order in allOrders:
            if order.isFailure and order.failureType:
                failureTypes[order.failureType] = failureTypes.get(order.failureType, 0) + 1

        from apps.maintenance.domain.services.maintenanceAnalytics import buildTrend

        return FleetAnalyticsDto(
            fromDate=fromDate.isoformat(),
            toDate=toDate.isoformat(),
            generatedAt=now.isoformat(),
            deviceCount=len(rows),
            totalRepairs=totalRepairs,
            totalPreventive=totalPreventive,
            totalDowntimeHours=float(round(totalDowntime, 2)),
            totalCost=str(totalCost),
            fleetMtbfHours=self._mean(mtbfValues),
            fleetMttrHours=self._mean(mttrValues),
            fleetAvailabilityPercent=self._mean(availabilityValues),
            pmCompliancePercent=self._mean(complianceValues),
            rows=rows,
            topParts=[
                PartConsumptionDto(
                    partId=stat.partId,
                    partCode=stat.partCode,
                    partName=stat.partName,
                    unit=stat.unit,
                    usageCount=stat.usageCount,
                    totalQuantity=str(stat.totalQuantity),
                    totalCost=str(stat.totalCost),
                    lastUsedAt=stat.lastUsedAt,
                    deviceCount=stat.deviceCount,
                )
                for stat in topParts
            ],
            topFailureTypes=[
                FailureModeDto(label=label, count=count)
                for label, count in sorted(
                    failureTypes.items(), key=lambda pair: (-pair[1], pair[0])
                )[:10]
            ],
            technicians=[
                TechnicianStatDto(
                    name=stat.name,
                    totalOrders=stat.totalOrders,
                    correctiveOrders=stat.correctiveOrders,
                    preventiveOrders=stat.preventiveOrders,
                    completedOrders=stat.completedOrders,
                    openOrders=stat.openOrders,
                    labourHours=stat.labourHours,
                    averageRepairHours=stat.averageRepairHours,
                )
                for stat in summariseTechnicians(allOrders)[:20]
            ],
            trend=[
                TrendBucketDto(
                    label=bucket.label,
                    failures=bucket.failures,
                    preventive=bucket.preventive,
                    downtimeHours=bucket.downtimeHours,
                    cost=str(bucket.cost),
                )
                for bucket in buildTrend(allOrders, fromDate, toDate)
            ],
        )

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        return float(round(sum(values) / len(values), 2)) if values else None


class GetPartUsageReportUseCase(RegistryUseCaseBase):
    """Part-centric view: which devices consumed this part, and how often."""

    requiredAction = PERMISSION_REGISTRY_LIST

    def perform(self, query: GetPartUsageReportQuery) -> PartUsageReportDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        fromDate, toDate = self.resolveWindow(query.fromDate, query.toDate, now.date())
        usages = [
            usage
            for usage in self.analyticsRepository.readPartUsage(tenantId, None, fromDate, toDate)
            if usage.partId == query.partId
        ]
        grouped: dict[str, list] = {}
        for usage in usages:
            grouped.setdefault(usage.deviceId, []).append(usage)

        rows = []
        for deviceId, deviceUsages in grouped.items():
            quantity = sum((Decimal(item.quantity or 0) for item in deviceUsages), Decimal("0"))
            moments = [item.consumedAt for item in deviceUsages if item.consumedAt]
            rows.append(
                PartUsageReportRowDto(
                    deviceId=deviceId,
                    deviceCode=deviceUsages[0].deviceCode,
                    deviceName=deviceUsages[0].deviceName,
                    usageCount=len(deviceUsages),
                    totalQuantity=str(quantity),
                    lastUsedAt=max(moments).isoformat() if moments else "",
                )
            )
        rows.sort(key=lambda row: (-row.usageCount, row.deviceCode))
        first = usages[0] if usages else None
        return PartUsageReportDto(
            partId=query.partId,
            partCode=first.partCode if first else "",
            partName=first.partName if first else "",
            unit=first.unit if first else "",
            fromDate=fromDate.isoformat(),
            toDate=toDate.isoformat(),
            totalUsageCount=len(usages),
            totalQuantity=str(sum((Decimal(item.quantity or 0) for item in usages), Decimal("0"))),
            devices=rows,
        )


# =====================================================================================
# Device nameplate + work-order closure facts
# =====================================================================================
@dataclass(frozen=True)
class UpdateNameplateCommand:
    deviceId: str
    values: dict


@dataclass(frozen=True)
class RecordClosureDetailsCommand:
    workOrderId: str
    values: dict


class UpdateDeviceNameplateUseCase(RegistryUseCaseBase):
    """Write the optional registry attributes of a device (manufacturer, model,
    serial, criticality, parent asset, location…)."""

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: UpdateNameplateCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        deviceId = uuid.UUID(command.deviceId)
        self.requireDevice(tenantId, command.deviceId)

        values = dict(command.values)
        for key in ("purchasedOn", "installedOn", "commissionedOn", "warrantyUntil"):
            if key in values:
                values[key] = parseDateOrNone(str(values[key] or ""))
        locationPath = ""
        if values.get("locationId"):
            location = self.locationRepository.getById(
                tenantId, uuid.UUID(str(values["locationId"]))
            )
            if location is None:
                raise EntityNotFoundError("Location not found.")
            values["locationId"] = location.id
            locationPath = location.displayPath()
        elif "locationId" in values:
            values["locationId"] = None
        if values.get("parentDeviceId"):
            parentId = str(values["parentDeviceId"])
            parent = self.deviceRepository.getById(tenantId, uuid.UUID(parentId))
            if parent is None:
                raise EntityNotFoundError("Parent device not found.")
            # Before Phase 27 the repository silently dropped a device that was
            # made its own parent and did nothing at all about longer loops, so
            # A→B→A was writable and every ancestry walk after it hung. The
            # guards below refuse the write and say why.
            index = {row["id"]: row for row in self.deviceRepository.hierarchyRows(tenantId)}
            parents = {key: (row["parentDeviceId"] or None) for key, row in index.items()}
            assertNoCycle(command.deviceId, parentId, parents)
            assertDepthWithinLimit(parentId, parents)
            stated = "assetLevel" in values
            childLevel = str(
                values.get("assetLevel") or index.get(command.deviceId, {}).get("assetLevel") or ""
            )
            # An unstated default level is derived from the new parent rather
            # than refused, so filing a machine under a line keeps working and
            # classifies the machine at the same time.
            values["assetLevel"] = resolveChildLevel(
                index.get(parentId, {}).get("assetLevel", ""),
                index.get(parentId, {}).get("name", ""),
                childLevel,
                stated=stated,
            )
            values["parentDeviceId"] = parent.id
        elif "parentDeviceId" in values:
            values["parentDeviceId"] = None

        self.deviceRepository.updateNameplate(tenantId, deviceId, values, locationPath, now)
        self.audit(
            AUDIT_UPDATE,
            resourceType="DeviceNameplate",
            resourceId=command.deviceId,
            tenantId=tenantId,
            after={"locationPath": locationPath},
        )
        return self.deviceRepository.readNameplate(tenantId, deviceId)


class RecordClosureDetailsUseCase(RegistryUseCaseBase):
    """Capture failure, downtime and cost when a repair order is closed.

    Without these rows the report page can only count orders; with them it can
    report MTTR, availability, repeat failures and cost per asset.
    """

    requiredAction = "maintenance.workorder.update"

    def perform(self, command: RecordClosureDetailsCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        values = dict(command.values)
        for key in (
            "failureReportedAt",
            "repairStartedAt",
            "repairFinishedAt",
            "returnedToServiceAt",
        ):
            if key in values:
                values[key] = _parseMoment(str(values[key] or ""))
        updated = self.deviceRepository.recordClosureDetails(
            tenantId, uuid.UUID(command.workOrderId), values, now
        )
        if not updated:
            raise EntityNotFoundError("Work order not found.")
        self.audit(
            AUDIT_UPDATE,
            resourceType="WorkOrderClosure",
            resourceId=command.workOrderId,
            tenantId=tenantId,
            after={"downtimeMinutes": values.get("downtimeMinutes", 0)},
        )
        return {"workOrderId": command.workOrderId}


def _parseMoment(value: str):  # noqa: ANN202 — datetime | None
    """Accept an ISO datetime or a bare ISO date; anything else becomes None."""
    from datetime import datetime as _datetime

    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = _datetime.fromisoformat(text)
    except ValueError:
        parsedDate = parseDateOrNone(value)
        if parsedDate is None:
            return None
        return _datetime(parsedDate.year, parsedDate.month, parsedDate.day, tzinfo=UTC)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
