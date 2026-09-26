"""Equipment-registry and analytics DTOs (Phase 26)."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.maintenance.domain.entities.assetRegistry import (
    DeviceAssignment,
    DeviceBomItem,
    DeviceSpecification,
    MaintenanceLocation,
    MaintenancePersonnel,
    PmExecution,
    PmPlan,
)
from apps.maintenance.domain.services.maintenanceAnalytics import DeviceAnalytics


@dataclass(frozen=True)
class LocationDto:
    id: str
    code: str
    name: str
    kind: str
    parentId: str = ""
    path: str = ""
    note: str = ""
    deviceCount: int = 0


@dataclass(frozen=True)
class LocationListDto:
    items: list[LocationDto] = field(default_factory=list)

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": len(self.items)}


@dataclass(frozen=True)
class PersonnelDto:
    id: str
    personnelCode: str
    fullName: str
    specialty: str
    unit: str = ""
    phone: str = ""
    shift: str = ""
    skills: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    active: bool = True


@dataclass(frozen=True)
class PersonnelListDto:
    items: list[PersonnelDto] = field(default_factory=list)

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": len(self.items)}


@dataclass(frozen=True)
class SpecificationDto:
    id: str
    label: str
    value: str = ""
    unit: str = ""
    sortOrder: int = 0


@dataclass(frozen=True)
class PmPlanDto:
    id: str
    deviceId: str
    title: str
    discipline: str
    description: str = ""
    checklist: list[str] = field(default_factory=list)
    frequencyEvery: int = 1
    frequencyUnit: str = "month"
    periodDays: int = 0
    estimatedMinutes: int = 0
    responsibleName: str = ""
    lastExecutedOn: str = ""
    nextDueOn: str = ""
    overdue: bool = False
    active: bool = True


@dataclass(frozen=True)
class PmExecutionDto:
    id: str
    planId: str
    deviceId: str
    discipline: str
    performedOn: str
    dueOn: str = ""
    onTime: bool = True
    performedByName: str = ""
    durationMinutes: int = 0
    findings: str = ""


@dataclass(frozen=True)
class BomItemDto:
    id: str
    partId: str
    partCode: str
    partName: str
    unit: str = ""
    position: str = ""
    standardQuantity: str = "0"
    note: str = ""
    quantityOnHand: str = "0"
    minimumStock: str = "0"
    lowStock: bool = False
    usageCount: int = 0
    usedQuantity: str = "0"
    lastUsedAt: str = ""


@dataclass(frozen=True)
class AssignmentDto:
    id: str
    role: str
    personnelId: str = ""
    personnelName: str = ""
    unit: str = ""
    fromDate: str = ""
    toDate: str = ""
    current: bool = True


@dataclass(frozen=True)
class FailureModeDto:
    label: str
    count: int


@dataclass(frozen=True)
class PartConsumptionDto:
    partId: str
    partCode: str
    partName: str
    unit: str
    usageCount: int
    totalQuantity: str
    totalCost: str
    lastUsedAt: str = ""
    deviceCount: int = 0


@dataclass(frozen=True)
class TechnicianStatDto:
    name: str
    totalOrders: int
    correctiveOrders: int
    preventiveOrders: int
    completedOrders: int
    openOrders: int
    labourHours: float
    averageRepairHours: float | None = None


@dataclass(frozen=True)
class TrendBucketDto:
    label: str
    failures: int
    preventive: int
    downtimeHours: float
    cost: str


@dataclass(frozen=True)
class DeviceAnalyticsDto:
    """Everything the device report page renders, in one shape."""

    deviceId: str = ""
    fromDate: str = ""
    toDate: str = ""
    windowDays: int = 0
    totalOrders: int = 0
    repairCount: int = 0
    preventiveCount: int = 0
    inspectionCount: int = 0
    openOrders: int = 0
    completedOrders: int = 0
    repeatFailures: int = 0
    totalDowntimeHours: float = 0.0
    operatingHours: float = 0.0
    mtbfHours: float | None = None
    mttrHours: float | None = None
    availabilityPercent: float | None = None
    pmScheduled: int = 0
    pmCompleted: int = 0
    pmOnTime: int = 0
    pmOverdue: int = 0
    pmCompliancePercent: float | None = None
    labourCost: str = "0"
    partsCost: str = "0"
    totalCost: str = "0"
    labourHours: float = 0.0
    partsUsedCount: int = 0
    partsUsedQuantity: str = "0"
    lastFailureAt: str = ""
    lastRepairAt: str = ""
    byFailureType: list[FailureModeDto] = field(default_factory=list)
    byFailedComponent: list[FailureModeDto] = field(default_factory=list)
    byRootCause: list[FailureModeDto] = field(default_factory=list)
    byDepartment: list[FailureModeDto] = field(default_factory=list)
    byStatus: dict[str, int] = field(default_factory=dict)
    byType: dict[str, int] = field(default_factory=dict)
    byPriority: dict[str, int] = field(default_factory=dict)
    partConsumption: list[PartConsumptionDto] = field(default_factory=list)
    technicians: list[TechnicianStatDto] = field(default_factory=list)
    trend: list[TrendBucketDto] = field(default_factory=list)

    def asMeta(self) -> dict[str, object]:
        return {
            "repairCount": self.repairCount,
            "fromDate": self.fromDate,
            "toDate": self.toDate,
        }


@dataclass(frozen=True)
class DeviceProfileDto:
    """The complete equipment file — master data plus every linked registry list."""

    device: object
    nameplate: dict = field(default_factory=dict)
    specifications: list[SpecificationDto] = field(default_factory=list)
    pmPlans: list[PmPlanDto] = field(default_factory=list)
    pmExecutions: list[PmExecutionDto] = field(default_factory=list)
    bom: list[BomItemDto] = field(default_factory=list)
    assignments: list[AssignmentDto] = field(default_factory=list)
    location: LocationDto | None = None
    locationPath: str = ""
    children: list[dict[str, str]] = field(default_factory=list)
    analytics: DeviceAnalyticsDto | None = None
    generatedAt: str = ""

    def asMeta(self) -> dict[str, object]:
        return {
            "pmPlanCount": len(self.pmPlans),
            "bomCount": len(self.bom),
            "assignmentCount": len(self.assignments),
            "generatedAt": self.generatedAt,
        }


@dataclass(frozen=True)
class PartUsageReportRowDto:
    """One device that consumed a part — the part-centric report."""

    deviceId: str
    deviceCode: str
    deviceName: str
    usageCount: int
    totalQuantity: str
    lastUsedAt: str = ""


@dataclass(frozen=True)
class PartUsageReportDto:
    partId: str = ""
    partCode: str = ""
    partName: str = ""
    unit: str = ""
    fromDate: str = ""
    toDate: str = ""
    totalUsageCount: int = 0
    totalQuantity: str = "0"
    devices: list[PartUsageReportRowDto] = field(default_factory=list)

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": len(self.devices), "totalUsageCount": self.totalUsageCount}


@dataclass(frozen=True)
class FleetAnalyticsRowDto:
    """One device line of the plant-wide comparison table."""

    deviceId: str
    code: str
    name: str
    department: str
    criticality: str
    locationPath: str
    status: str
    repairCount: int = 0
    preventiveCount: int = 0
    repeatFailures: int = 0
    downtimeHours: float = 0.0
    mtbfHours: float | None = None
    mttrHours: float | None = None
    availabilityPercent: float | None = None
    pmCompliancePercent: float | None = None
    partsUsedQuantity: str = "0"
    totalCost: str = "0"


@dataclass(frozen=True)
class FleetAnalyticsDto:
    fromDate: str = ""
    toDate: str = ""
    generatedAt: str = ""
    deviceCount: int = 0
    totalRepairs: int = 0
    totalPreventive: int = 0
    totalDowntimeHours: float = 0.0
    totalCost: str = "0"
    fleetMtbfHours: float | None = None
    fleetMttrHours: float | None = None
    fleetAvailabilityPercent: float | None = None
    pmCompliancePercent: float | None = None
    rows: list[FleetAnalyticsRowDto] = field(default_factory=list)
    topParts: list[PartConsumptionDto] = field(default_factory=list)
    topFailureTypes: list[FailureModeDto] = field(default_factory=list)
    technicians: list[TechnicianStatDto] = field(default_factory=list)
    trend: list[TrendBucketDto] = field(default_factory=list)

    def asMeta(self) -> dict[str, object]:
        return {
            "totalCount": len(self.rows),
            "fromDate": self.fromDate,
            "toDate": self.toDate,
            "generatedAt": self.generatedAt,
        }


# -- mappers ------------------------------------------------------------------------
def locationDto(location: MaintenanceLocation, deviceCount: int = 0) -> LocationDto:
    return LocationDto(
        id=str(location.id),
        code=location.code,
        name=location.name,
        kind=location.kind,
        parentId=str(location.parentId) if location.parentId else "",
        path=location.displayPath(),
        note=location.note,
        deviceCount=deviceCount,
    )


def personnelDto(person: MaintenancePersonnel) -> PersonnelDto:
    return PersonnelDto(
        id=str(person.id),
        personnelCode=person.personnelCode,
        fullName=person.fullName,
        specialty=person.specialty,
        unit=person.unit,
        phone=person.phone,
        shift=person.shift,
        skills=list(person.skills),
        certifications=list(person.certifications),
        active=person.active,
    )


def specificationDto(spec: DeviceSpecification) -> SpecificationDto:
    return SpecificationDto(
        id=str(spec.id),
        label=spec.label,
        value=spec.value,
        unit=spec.unit,
        sortOrder=spec.sortOrder,
    )


def pmPlanDto(plan: PmPlan, asOf) -> PmPlanDto:  # noqa: ANN001 — date
    nextDue = plan.nextDueOn()
    return PmPlanDto(
        id=str(plan.id),
        deviceId=str(plan.deviceId),
        title=plan.title,
        discipline=plan.discipline,
        description=plan.description,
        checklist=list(plan.checklist),
        frequencyEvery=plan.frequencyEvery,
        frequencyUnit=plan.frequencyUnit,
        periodDays=plan.periodDays() or 0,
        estimatedMinutes=plan.estimatedMinutes,
        responsibleName=plan.responsibleName,
        lastExecutedOn=plan.lastExecutedOn.isoformat() if plan.lastExecutedOn else "",
        nextDueOn=nextDue.isoformat() if nextDue else "",
        overdue=plan.isOverdue(asOf),
        active=plan.active,
    )


def pmExecutionDto(run: PmExecution) -> PmExecutionDto:
    return PmExecutionDto(
        id=str(run.id),
        planId=str(run.planId),
        deviceId=str(run.deviceId),
        discipline=run.discipline,
        performedOn=run.performedOn.isoformat(),
        dueOn=run.dueOn.isoformat() if run.dueOn else "",
        onTime=run.onTime,
        performedByName=run.performedByName,
        durationMinutes=run.durationMinutes,
        findings=run.findings,
    )


def bomItemDto(
    item: DeviceBomItem,
    usageCount: int = 0,
    usedQuantity: str = "0",
    lastUsedAt: str = "",
) -> BomItemDto:
    return BomItemDto(
        id=str(item.id),
        partId=str(item.partId),
        partCode=item.partCode,
        partName=item.partName,
        unit=item.unit,
        position=item.position,
        standardQuantity=str(item.standardQuantity),
        note=item.note,
        quantityOnHand=str(item.quantityOnHand),
        minimumStock=str(item.minimumStock),
        lowStock=item.lowStock,
        usageCount=usageCount,
        usedQuantity=usedQuantity,
        lastUsedAt=lastUsedAt,
    )


def assignmentDto(assignment: DeviceAssignment, asOf) -> AssignmentDto:  # noqa: ANN001 — date
    return AssignmentDto(
        id=str(assignment.id),
        role=assignment.role,
        personnelId=str(assignment.personnelId) if assignment.personnelId else "",
        personnelName=assignment.personnelName,
        unit=assignment.unit,
        fromDate=assignment.fromDate.isoformat() if assignment.fromDate else "",
        toDate=assignment.toDate.isoformat() if assignment.toDate else "",
        current=assignment.isCurrent(asOf),
    )


def analyticsDto(analytics: DeviceAnalytics) -> DeviceAnalyticsDto:
    return DeviceAnalyticsDto(
        deviceId=analytics.deviceId,
        fromDate=analytics.fromDate,
        toDate=analytics.toDate,
        windowDays=analytics.windowDays,
        totalOrders=analytics.totalOrders,
        repairCount=analytics.repairCount,
        preventiveCount=analytics.preventiveCount,
        inspectionCount=analytics.inspectionCount,
        openOrders=analytics.openOrders,
        completedOrders=analytics.completedOrders,
        repeatFailures=analytics.repeatFailures,
        totalDowntimeHours=analytics.totalDowntimeHours,
        operatingHours=analytics.operatingHours,
        mtbfHours=analytics.mtbfHours,
        mttrHours=analytics.mttrHours,
        availabilityPercent=analytics.availabilityPercent,
        pmScheduled=analytics.pmScheduled,
        pmCompleted=analytics.pmCompleted,
        pmOnTime=analytics.pmOnTime,
        pmOverdue=analytics.pmOverdue,
        pmCompliancePercent=analytics.pmCompliancePercent,
        labourCost=str(analytics.labourCost),
        partsCost=str(analytics.partsCost),
        totalCost=str(analytics.totalCost),
        labourHours=analytics.labourHours,
        partsUsedCount=analytics.partsUsedCount,
        partsUsedQuantity=str(analytics.partsUsedQuantity),
        lastFailureAt=analytics.lastFailureAt,
        lastRepairAt=analytics.lastRepairAt,
        byFailureType=[FailureModeDto(item.label, item.count) for item in analytics.byFailureType],
        byFailedComponent=[
            FailureModeDto(item.label, item.count) for item in analytics.byFailedComponent
        ],
        byRootCause=[FailureModeDto(item.label, item.count) for item in analytics.byRootCause],
        byDepartment=[FailureModeDto(item.label, item.count) for item in analytics.byDepartment],
        byStatus=analytics.byStatus,
        byType=analytics.byType,
        byPriority=analytics.byPriority,
        partConsumption=[
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
            for stat in analytics.partConsumption
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
            for stat in analytics.technicians
        ],
        trend=[
            TrendBucketDto(
                label=bucket.label,
                failures=bucket.failures,
                preventive=bucket.preventive,
                downtimeHours=bucket.downtimeHours,
                cost=str(bucket.cost),
            )
            for bucket in analytics.trend
        ],
    )
