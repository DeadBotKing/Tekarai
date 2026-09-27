"""Time & cost tracking use cases (ثبت زمان و هزینه).

Technician labour hours are logged per work order with the hourly rate in
effect at the time; spare-part consumption snapshots the part price. Together
they feed two read models:

* per-order cost summary — the entries and usages behind one request's cost;
* maintenance cost report — tenant-wide totals with device / department /
  technician breakdowns, the basis of «گزارش هزینه‌ی نگهداری».
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from apps.maintenance.application.commands.timeCostCommands import (
    DeleteLabourEntryCommand,
    ListLabourEntriesQuery,
    LogLabourEntryCommand,
    MaintenanceCostReportQuery,
    WorkOrderCostSummaryQuery,
)
from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.domain.entities.labourEntry import LabourEntry
from apps.maintenance.domain.entities.sparePart import WorkOrderPartUsage
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    LabourEntryRepository,
    MaintenanceCostRepository,
    SparePartRepository,
    WorkOrderRepository,
)
from apps.maintenance.domain.services import maintenanceCosting
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_DELETE, UseCase
from apps.sharedKernel.domain.errors import EntityNotFoundError, ValidationFailedError

MAX_HOURS_PER_ENTRY = Decimal("1000")
MAX_HOURLY_RATE = Decimal("100000000")


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LabourEntryDto:
    id: str
    workOrderId: str
    technicianName: str
    hours: str
    hourlyRate: str
    totalCost: str
    workedAt: str
    note: str
    createdAt: str


@dataclass(frozen=True)
class LabourEntryListDto:
    items: list[LabourEntryDto] = field(default_factory=list)
    totalCount: int = 0
    totalHours: str = "0"
    totalLabourCost: str = "0"

    def asMeta(self) -> dict[str, object]:
        return {
            "totalCount": self.totalCount,
            "totalHours": self.totalHours,
            "totalLabourCost": self.totalLabourCost,
        }


@dataclass(frozen=True)
class PartUsageLineDto:
    id: str
    partId: str
    partCode: str
    partName: str
    unit: str
    quantity: str
    unitCost: str
    totalCost: str
    note: str
    consumedAt: str


@dataclass(frozen=True)
class WorkOrderCostSummaryDto:
    workOrderId: str
    title: str
    status: str
    deviceId: str
    assignedToName: str
    labourHours: str
    labourCost: str
    partsCost: str
    totalCost: str
    labourEntries: list[LabourEntryDto] = field(default_factory=list)
    partUsages: list[PartUsageLineDto] = field(default_factory=list)


@dataclass(frozen=True)
class CostReportRowDto:
    workOrderId: str
    title: str
    orderType: str
    status: str
    department: str
    deviceCode: str
    deviceName: str
    assignedToName: str
    labourHours: str
    labourCost: str
    partsCost: str
    totalCost: str
    createdAt: str
    closedAt: str


@dataclass(frozen=True)
class CostGroupDto:
    key: str
    label: str
    workOrderCount: int
    labourHours: str
    labourCost: str
    partsCost: str
    totalCost: str


@dataclass(frozen=True)
class TechnicianLabourGroupDto:
    technicianName: str
    entryCount: int
    hours: str
    cost: str


@dataclass(frozen=True)
class MaintenanceCostReportDto:
    fromDate: str
    toDate: str
    generatedAt: str
    workOrderCount: int
    totalLabourHours: str
    totalLabourCost: str
    totalPartsCost: str
    totalCost: str
    items: list[CostReportRowDto] = field(default_factory=list)
    byDevice: list[CostGroupDto] = field(default_factory=list)
    byDepartment: list[CostGroupDto] = field(default_factory=list)
    byTechnician: list[TechnicianLabourGroupDto] = field(default_factory=list)

    def asMeta(self) -> dict[str, object]:
        return {"workOrderCount": self.workOrderCount, "totalCost": self.totalCost}


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------
def labourEntryDto(entry: LabourEntry) -> LabourEntryDto:
    return LabourEntryDto(
        id=str(entry.id),
        workOrderId=str(entry.workOrderId),
        technicianName=entry.technicianName,
        hours=str(entry.hours),
        hourlyRate=str(entry.hourlyRate),
        totalCost=str(entry.totalCost),
        workedAt=entry.workedAt.isoformat(),
        note=entry.note,
        createdAt=entry.createdAt.isoformat(),
    )


def _partUsageLine(usage: WorkOrderPartUsage) -> PartUsageLineDto:
    return PartUsageLineDto(
        id=str(usage.id),
        partId=str(usage.partId),
        partCode=usage.partCode,
        partName=usage.partName,
        unit=usage.unit,
        quantity=str(usage.quantity),
        unitCost=str(usage.unitCost),
        totalCost=str(usage.totalCost),
        note=usage.note,
        consumedAt=usage.consumedAt.isoformat(),
    )


def _money(
    value: str, field: str, *, positive: bool, minimum: Decimal, maximum: Decimal
) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValidationFailedError(
            "Invalid numeric value.", fieldErrors={field: "invalid"}
        ) from error
    if positive and parsed <= 0:
        raise ValidationFailedError(
            "Value must be greater than zero.", fieldErrors={field: "invalid"}
        )
    if parsed < minimum or parsed > maximum:
        raise ValidationFailedError(
            "Value is outside the allowed range.", fieldErrors={field: "invalid"}
        )
    exponent = parsed.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValidationFailedError(
            "At most two decimal places are allowed.", fieldErrors={field: "precision"}
        )
    return parsed


def _parseWorkedAt(value: str, now: datetime) -> datetime:
    if not value.strip():
        return now
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValidationFailedError(
            "Invalid date/time value.", fieldErrors={"workedAt": "invalid"}
        ) from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------
class TimeCostUseCaseBase(UseCase):
    def __init__(self, labourEntryRepository: LabourEntryRepository, **kwargs) -> None:
        super().__init__(**kwargs)
        self.labourEntryRepository = labourEntryRepository


class LogLabourEntryUseCase(TimeCostUseCaseBase):
    """Log one chunk of technician work on a work order."""

    requiredAction = "maintenance.workorder.logTime"

    def perform(self, command: LogLabourEntryCommand) -> LabourEntryDto:
        if not command.technicianName.strip():
            raise ValidationFailedError(
                "Technician name is required.", fieldErrors={"technicianName": "required"}
            )
        hours = _money(
            command.hours,
            "hours",
            positive=True,
            minimum=Decimal("0"),
            maximum=MAX_HOURS_PER_ENTRY,
        )
        hourlyRate = _money(
            command.hourlyRate,
            "hourlyRate",
            positive=False,
            minimum=Decimal("0"),
            maximum=MAX_HOURLY_RATE,
        )
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        entry = self.labourEntryRepository.log(
            tenantId,
            uuid.UUID(command.workOrderId),
            command.technicianName,
            hours,
            hourlyRate,
            _parseWorkedAt(command.workedAt, now),
            command.note,
        )
        dto = labourEntryDto(entry)
        self.audit(
            AUDIT_CREATE,
            "WorkOrderLabourEntry",
            str(entry.id),
            tenantId,
            after=dto.__dict__,
        )
        return dto


class ListLabourEntriesUseCase(TimeCostUseCaseBase):
    requiredAction = "maintenance.workorder.view"

    def perform(self, query: ListLabourEntriesQuery) -> LabourEntryListDto:
        tenantId = resolveTenantId("")
        entries = self.labourEntryRepository.listForWorkOrder(
            tenantId, uuid.UUID(query.workOrderId)
        )
        totalHours = sum((entry.hours for entry in entries), Decimal("0"))
        totalCost = sum((entry.totalCost for entry in entries), Decimal("0"))
        return LabourEntryListDto(
            items=[labourEntryDto(entry) for entry in entries],
            totalCount=len(entries),
            totalHours=str(totalHours.quantize(Decimal("0.01"))),
            totalLabourCost=str(totalCost.quantize(Decimal("0.01"))),
        )


class DeleteLabourEntryUseCase(TimeCostUseCaseBase):
    requiredAction = "maintenance.workorder.logTime"

    def perform(self, command: DeleteLabourEntryCommand) -> LabourEntryDto:
        tenantId = resolveTenantId("")
        entry = self.labourEntryRepository.delete(tenantId, uuid.UUID(command.entryId))
        dto = labourEntryDto(entry)
        self.audit(
            AUDIT_DELETE,
            "WorkOrderLabourEntry",
            str(entry.id),
            tenantId,
            before=dto.__dict__,
        )
        return dto


class GetWorkOrderCostSummaryUseCase(TimeCostUseCaseBase):
    """Evidence behind one request's cost: entries + usages + the total."""

    requiredAction = "maintenance.costs.view"

    def __init__(
        self,
        workOrderRepository: WorkOrderRepository,
        sparePartRepository: SparePartRepository,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.workOrderRepository = workOrderRepository
        self.sparePartRepository = sparePartRepository

    def perform(self, query: WorkOrderCostSummaryQuery) -> WorkOrderCostSummaryDto:
        tenantId = resolveTenantId("")
        workOrderId = uuid.UUID(query.workOrderId)
        order = self.workOrderRepository.getById(tenantId, workOrderId)
        if order is None:
            raise EntityNotFoundError("WorkOrder", query.workOrderId)
        entries = self.labourEntryRepository.listForWorkOrder(tenantId, workOrderId)
        usages: list[WorkOrderPartUsage] = self.sparePartRepository.listUsage(tenantId, workOrderId)
        labourHours = sum((entry.hours for entry in entries), Decimal("0"))
        labourCost = sum((entry.totalCost for entry in entries), Decimal("0"))
        partsCost = sum((usage.totalCost for usage in usages), Decimal("0"))
        return WorkOrderCostSummaryDto(
            workOrderId=str(order.id),
            title=order.title,
            status=str(order.status),
            deviceId=str(order.deviceId),
            assignedToName=order.assignedToName,
            labourHours=str(labourHours.quantize(Decimal("0.01"))),
            labourCost=str(labourCost),
            partsCost=str(partsCost),
            totalCost=str(labourCost + partsCost),
            labourEntries=[labourEntryDto(entry) for entry in entries],
            partUsages=[_partUsageLine(usage) for usage in usages],
        )


class GetMaintenanceCostReportUseCase(UseCase):
    """گزارش هزینه‌ی نگهداری — totals + device/department/technician breakdowns."""

    requiredAction = "maintenance.costs.view"

    def __init__(self, costRepository: MaintenanceCostRepository, **kwargs) -> None:
        super().__init__(**kwargs)
        self.costRepository = costRepository

    def perform(self, query: MaintenanceCostReportQuery) -> MaintenanceCostReportDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        fromDay = _parseDay(query.fromDate) or (now - timedelta(days=30)).date()
        toDay = _parseDay(query.toDate) or now.date()
        if fromDay > toDay:
            raise ValidationFailedError(
                "The date range is invalid.",
                fieldErrors={"fromDate": "afterToDate"},
            )
        fromMoment = datetime(fromDay.year, fromDay.month, fromDay.day, tzinfo=UTC)
        toMoment = datetime(toDay.year, toDay.month, toDay.day, 23, 59, 59, tzinfo=UTC)
        deviceId = uuid.UUID(query.deviceId) if query.deviceId.strip() else None

        rows = self.costRepository.readWorkOrderCosts(
            tenantId, fromMoment, toMoment, deviceId, query.department
        )
        labourRows = self.costRepository.readLabourCosts(
            tenantId, fromMoment, toMoment, deviceId, query.department
        )
        totals = maintenanceCosting.totalCosts(rows)
        byDevice = maintenanceCosting.groupCosts(
            rows,
            keyOf=lambda row: row.deviceId,
            labelOf=lambda row: f"{row.deviceCode} — {row.deviceName}".strip(" —"),
        )
        byDepartment = maintenanceCosting.groupCosts(
            rows,
            keyOf=lambda row: row.department,
            labelOf=lambda row: row.department,
        )
        byTechnician = maintenanceCosting.groupLabourByTechnician(labourRows)
        rows = sorted(rows, key=lambda row: row.totalCost, reverse=True)

        return MaintenanceCostReportDto(
            fromDate=fromDay.isoformat(),
            toDate=toDay.isoformat(),
            generatedAt=now.isoformat(),
            workOrderCount=totals.workOrderCount,
            totalLabourHours=str(totals.labourHours),
            totalLabourCost=str(totals.labourCost),
            totalPartsCost=str(totals.partsCost),
            totalCost=str(totals.totalCost),
            items=[
                CostReportRowDto(
                    workOrderId=row.workOrderId,
                    title=row.title,
                    orderType=row.orderType,
                    status=row.status,
                    department=row.department,
                    deviceCode=row.deviceCode,
                    deviceName=row.deviceName,
                    assignedToName=row.assignedToName,
                    labourHours=str(row.labourHours),
                    labourCost=str(row.labourCost),
                    partsCost=str(row.partsCost),
                    totalCost=str(row.totalCost),
                    createdAt=row.createdAtIso,
                    closedAt=row.closedAtIso,
                )
                for row in rows
            ],
            byDevice=[
                CostGroupDto(
                    key=group.key,
                    label=group.label,
                    workOrderCount=group.workOrderCount,
                    labourHours=str(group.labourHours),
                    labourCost=str(group.labourCost),
                    partsCost=str(group.partsCost),
                    totalCost=str(group.totalCost),
                )
                for group in byDevice
            ],
            byDepartment=[
                CostGroupDto(
                    key=group.key,
                    label=group.label,
                    workOrderCount=group.workOrderCount,
                    labourHours=str(group.labourHours),
                    labourCost=str(group.labourCost),
                    partsCost=str(group.partsCost),
                    totalCost=str(group.totalCost),
                )
                for group in byDepartment
            ],
            byTechnician=[
                TechnicianLabourGroupDto(
                    technicianName=group.technicianName,
                    entryCount=group.entryCount,
                    hours=str(group.hours),
                    cost=str(group.cost),
                )
                for group in byTechnician
            ],
        )


def _parseDay(value: str):  # noqa: ANN202 — datetime.date | None
    if not value.strip():
        return None
    from datetime import date

    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None
