"""Maintenance analytics — pure metric computation (Phase 26 reporting).

Every number the reporting layer shows is *derived here from dated rows*, never
read from a counter kept on the device. That is deliberate: a stored
"repairCount" drifts the moment an order is edited or deleted, while a
recomputed one can always be traced back to the exact work orders behind it —
which is what makes drill-down possible.

The module is intentionally free of Django and of the application layer: it
takes plain readings and returns plain results, so the rules can be unit-tested
without a database.

Definitions used here
---------------------
* **Repair (corrective) count** — work orders of type ``corrective`` in range.
* **Downtime** — recorded ``downtimeMinutes``; when absent it is derived from
  ``failureReportedAt`` → ``returnedToServiceAt``.
* **MTTR** — mean time to repair: mean of (repair finished − repair started)
  over completed corrective orders, in hours.
* **MTBF** — mean time between failures: operating time in the window divided
  by the number of failures, in hours; operating time excludes downtime.
* **Availability** — operating time ÷ calendar time in the window.
* **PM compliance** — PM executions completed on time ÷ all PM executions due.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

MINUTES_PER_HOUR = 60.0
HOURS_PER_DAY = 24.0

#: Work-order types that count as a *failure* of the asset. A preventive or
#: inspection order is planned work, so it must never inflate the failure count.
FAILURE_ORDER_TYPES = ("corrective",)


@dataclass(frozen=True)
class WorkOrderReading:
    """The subset of a work order the analytics engine needs."""

    id: str
    title: str = ""
    orderType: str = "corrective"
    status: str = "submitted"
    priority: str = "normal"
    department: str = "general"
    assignedToName: str = ""
    failureType: str = ""
    failedComponent: str = ""
    rootCause: str = ""
    repeatFailure: bool = False
    createdAt: datetime | None = None
    closedAt: datetime | None = None
    failureReportedAt: datetime | None = None
    repairStartedAt: datetime | None = None
    repairFinishedAt: datetime | None = None
    returnedToServiceAt: datetime | None = None
    downtimeMinutes: int = 0
    labourHours: Decimal = Decimal("0")
    labourCost: Decimal = Decimal("0")
    partsCost: Decimal = Decimal("0")

    @property
    def isFailure(self) -> bool:
        return self.orderType in FAILURE_ORDER_TYPES

    @property
    def isClosed(self) -> bool:
        return self.status in ("completed", "cancelled") or self.closedAt is not None

    def downtimeHours(self) -> float:
        """Recorded downtime, falling back to reported → back-in-service."""
        if self.downtimeMinutes:
            return self.downtimeMinutes / MINUTES_PER_HOUR
        start = self.failureReportedAt or self.repairStartedAt or self.createdAt
        end = self.returnedToServiceAt or self.repairFinishedAt or self.closedAt
        if start and end and end > start:
            return (end - start).total_seconds() / 3600.0
        return 0.0

    def repairHours(self) -> float | None:
        """Wrench time: repair start → repair finish; None when not recorded."""
        start = self.repairStartedAt
        end = self.repairFinishedAt or self.closedAt
        if start and end and end >= start:
            return (end - start).total_seconds() / 3600.0
        if self.createdAt and self.closedAt and self.closedAt >= self.createdAt:
            return (self.closedAt - self.createdAt).total_seconds() / 3600.0
        return None

    def totalCost(self) -> Decimal:
        return Decimal(self.labourCost or 0) + Decimal(self.partsCost or 0)


@dataclass(frozen=True)
class PartUsageReading:
    """One issue of a spare part against a work order."""

    partId: str
    partCode: str
    partName: str
    unit: str
    quantity: Decimal
    consumedAt: datetime | None = None
    workOrderId: str = ""
    deviceId: str = ""
    deviceCode: str = ""
    deviceName: str = ""
    unitCost: Decimal = Decimal("0")


@dataclass(frozen=True)
class PmExecutionReading:
    """One completed PM run."""

    planId: str
    discipline: str
    performedOn: date
    dueOn: date | None = None
    onTime: bool = True
    durationMinutes: int = 0


@dataclass(frozen=True)
class PartConsumptionStat:
    """How much of one part a device (or the plant) has consumed.

    ``usageCount`` and ``totalQuantity`` are deliberately separate: three
    bearings fitted in a single repair is *one* usage of three units, and
    conflating the two hides how often a part actually fails.
    """

    partId: str
    partCode: str
    partName: str
    unit: str
    usageCount: int = 0
    totalQuantity: Decimal = Decimal("0")
    totalCost: Decimal = Decimal("0")
    lastUsedAt: str = ""
    deviceCount: int = 0


@dataclass(frozen=True)
class FailureModeStat:
    label: str
    count: int = 0


@dataclass(frozen=True)
class TechnicianStat:
    name: str
    totalOrders: int = 0
    correctiveOrders: int = 0
    preventiveOrders: int = 0
    completedOrders: int = 0
    openOrders: int = 0
    labourHours: float = 0.0
    averageRepairHours: float | None = None


@dataclass(frozen=True)
class PeriodBucket:
    """One month of the trend series."""

    label: str
    failures: int = 0
    preventive: int = 0
    downtimeHours: float = 0.0
    cost: Decimal = Decimal("0")


@dataclass(frozen=True)
class DeviceAnalytics:
    """The full statistical picture of one device over a window."""

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

    labourCost: Decimal = Decimal("0")
    partsCost: Decimal = Decimal("0")
    totalCost: Decimal = Decimal("0")
    labourHours: float = 0.0

    partsUsedCount: int = 0
    partsUsedQuantity: Decimal = Decimal("0")

    lastFailureAt: str = ""
    lastRepairAt: str = ""

    byFailureType: list[FailureModeStat] = field(default_factory=list)
    byFailedComponent: list[FailureModeStat] = field(default_factory=list)
    byRootCause: list[FailureModeStat] = field(default_factory=list)
    byDepartment: list[FailureModeStat] = field(default_factory=list)
    byStatus: dict[str, int] = field(default_factory=dict)
    byType: dict[str, int] = field(default_factory=dict)
    byPriority: dict[str, int] = field(default_factory=dict)
    partConsumption: list[PartConsumptionStat] = field(default_factory=list)
    technicians: list[TechnicianStat] = field(default_factory=list)
    trend: list[PeriodBucket] = field(default_factory=list)


def _round(value: float, digits: int = 2) -> float:
    return float(round(value, digits))


def _rankCounts(counter: dict[str, int], limit: int = 12) -> list[FailureModeStat]:
    ranked = sorted(counter.items(), key=lambda pair: (-pair[1], pair[0]))
    return [FailureModeStat(label=label, count=count) for label, count in ranked[:limit] if label]


def monthKey(moment: datetime | date) -> str:
    return f"{moment.year:04d}-{moment.month:02d}"


def summarisePartUsage(
    usages: list[PartUsageReading],
) -> list[PartConsumptionStat]:
    """Aggregate raw part issues into per-part consumption statistics."""
    grouped: dict[str, list[PartUsageReading]] = defaultdict(list)
    for usage in usages:
        grouped[usage.partId].append(usage)

    stats: list[PartConsumptionStat] = []
    for partId, rows in grouped.items():
        quantity = sum((Decimal(row.quantity or 0) for row in rows), Decimal("0"))
        cost = sum(
            (Decimal(row.quantity or 0) * Decimal(row.unitCost or 0) for row in rows),
            Decimal("0"),
        )
        moments = [row.consumedAt for row in rows if row.consumedAt is not None]
        devices = {row.deviceId for row in rows if row.deviceId}
        first = rows[0]
        stats.append(
            PartConsumptionStat(
                partId=partId,
                partCode=first.partCode,
                partName=first.partName,
                unit=first.unit,
                usageCount=len(rows),
                totalQuantity=quantity,
                totalCost=cost,
                lastUsedAt=max(moments).isoformat() if moments else "",
                deviceCount=len(devices),
            )
        )
    stats.sort(key=lambda stat: (-stat.usageCount, -float(stat.totalQuantity), stat.partCode))
    return stats


def summariseTechnicians(orders: list[WorkOrderReading]) -> list[TechnicianStat]:
    grouped: dict[str, list[WorkOrderReading]] = defaultdict(list)
    for order in orders:
        if order.assignedToName:
            grouped[order.assignedToName].append(order)

    stats: list[TechnicianStat] = []
    for name, rows in grouped.items():
        repairDurations = [hours for hours in (row.repairHours() for row in rows) if hours]
        stats.append(
            TechnicianStat(
                name=name,
                totalOrders=len(rows),
                correctiveOrders=sum(1 for row in rows if row.orderType == "corrective"),
                preventiveOrders=sum(1 for row in rows if row.orderType == "preventive"),
                completedOrders=sum(1 for row in rows if row.status == "completed"),
                openOrders=sum(1 for row in rows if not row.isClosed),
                labourHours=_round(sum(float(row.labourHours or 0) for row in rows)),
                averageRepairHours=(
                    _round(sum(repairDurations) / len(repairDurations))
                    if repairDurations
                    else None
                ),
            )
        )
    stats.sort(key=lambda stat: (-stat.totalOrders, stat.name))
    return stats


def buildTrend(
    orders: list[WorkOrderReading],
    fromDate: date,
    toDate: date,
) -> list[PeriodBucket]:
    """Monthly buckets across the window, including months with no activity."""
    failures: dict[str, int] = defaultdict(int)
    preventive: dict[str, int] = defaultdict(int)
    downtime: dict[str, float] = defaultdict(float)
    cost: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for order in orders:
        moment = order.failureReportedAt or order.createdAt
        if moment is None:
            continue
        key = monthKey(moment)
        if order.isFailure:
            failures[key] += 1
        elif order.orderType == "preventive":
            preventive[key] += 1
        downtime[key] += order.downtimeHours()
        cost[key] += order.totalCost()

    buckets: list[PeriodBucket] = []
    cursor = date(fromDate.year, fromDate.month, 1)
    guard = 0
    while cursor <= toDate and guard < 120:
        key = f"{cursor.year:04d}-{cursor.month:02d}"
        buckets.append(
            PeriodBucket(
                label=key,
                failures=failures.get(key, 0),
                preventive=preventive.get(key, 0),
                downtimeHours=_round(downtime.get(key, 0.0)),
                cost=cost.get(key, Decimal("0")),
            )
        )
        cursor = date(cursor.year + 1, 1, 1) if cursor.month == 12 else date(
            cursor.year, cursor.month + 1, 1
        )
        guard += 1
    return buckets


def computeDeviceAnalytics(
    deviceId: str,
    orders: list[WorkOrderReading],
    partUsages: list[PartUsageReading],
    pmExecutions: list[PmExecutionReading],
    pmPlansDue: int,
    pmPlansOverdue: int,
    fromDate: date,
    toDate: date,
) -> DeviceAnalytics:
    """Derive every headline metric for one device from its dated rows."""
    windowDays = max((toDate - fromDate).days + 1, 1)
    calendarHours = windowDays * HOURS_PER_DAY

    failures = [order for order in orders if order.isFailure]
    preventiveOrders = [order for order in orders if order.orderType == "preventive"]
    inspections = [order for order in orders if order.orderType == "inspection"]

    downtimeHours = sum(order.downtimeHours() for order in orders)
    operatingHours = max(calendarHours - downtimeHours, 0.0)

    repairDurations = [
        hours for hours in (order.repairHours() for order in failures) if hours is not None
    ]
    mttr = _round(sum(repairDurations) / len(repairDurations)) if repairDurations else None
    mtbf = _round(operatingHours / len(failures)) if failures else None
    availability = _round(operatingHours / calendarHours * 100.0) if calendarHours else None

    pmOnTime = sum(1 for run in pmExecutions if run.onTime)
    pmCompleted = len(pmExecutions)
    pmScheduled = max(pmPlansDue, pmCompleted)
    compliance = _round(pmOnTime / pmScheduled * 100.0) if pmScheduled else None

    labourCost = sum((Decimal(order.labourCost or 0) for order in orders), Decimal("0"))
    partsCost = sum((Decimal(order.partsCost or 0) for order in orders), Decimal("0"))
    usageStats = summarisePartUsage(partUsages)

    failureTypes: dict[str, int] = defaultdict(int)
    components: dict[str, int] = defaultdict(int)
    rootCauses: dict[str, int] = defaultdict(int)
    departments: dict[str, int] = defaultdict(int)
    statuses: dict[str, int] = defaultdict(int)
    types: dict[str, int] = defaultdict(int)
    priorities: dict[str, int] = defaultdict(int)

    for order in orders:
        statuses[order.status] += 1
        types[order.orderType] += 1
        priorities[order.priority] += 1
        departments[order.department] += 1
        if order.isFailure:
            if order.failureType:
                failureTypes[order.failureType] += 1
            if order.failedComponent:
                components[order.failedComponent.strip()] += 1
            if order.rootCause:
                rootCauses[order.rootCause.strip()[:120]] += 1

    failureMoments = [
        order.failureReportedAt or order.createdAt
        for order in failures
        if (order.failureReportedAt or order.createdAt)
    ]
    repairMoments = [
        order.repairFinishedAt or order.closedAt
        for order in orders
        if (order.repairFinishedAt or order.closedAt)
    ]

    return DeviceAnalytics(
        deviceId=deviceId,
        fromDate=fromDate.isoformat(),
        toDate=toDate.isoformat(),
        windowDays=windowDays,
        totalOrders=len(orders),
        repairCount=len(failures),
        preventiveCount=len(preventiveOrders),
        inspectionCount=len(inspections),
        openOrders=sum(1 for order in orders if not order.isClosed),
        completedOrders=sum(1 for order in orders if order.status == "completed"),
        repeatFailures=sum(1 for order in failures if order.repeatFailure),
        totalDowntimeHours=_round(downtimeHours),
        operatingHours=_round(operatingHours),
        mtbfHours=mtbf,
        mttrHours=mttr,
        availabilityPercent=availability,
        pmScheduled=pmScheduled,
        pmCompleted=pmCompleted,
        pmOnTime=pmOnTime,
        pmOverdue=pmPlansOverdue,
        pmCompliancePercent=compliance,
        labourCost=labourCost,
        partsCost=partsCost,
        totalCost=labourCost + partsCost,
        labourHours=_round(sum(float(order.labourHours or 0) for order in orders)),
        partsUsedCount=sum(stat.usageCount for stat in usageStats),
        partsUsedQuantity=sum((stat.totalQuantity for stat in usageStats), Decimal("0")),
        lastFailureAt=max(failureMoments).isoformat() if failureMoments else "",
        lastRepairAt=max(repairMoments).isoformat() if repairMoments else "",
        byFailureType=_rankCounts(failureTypes),
        byFailedComponent=_rankCounts(components),
        byRootCause=_rankCounts(rootCauses),
        byDepartment=_rankCounts(departments),
        byStatus=dict(statuses),
        byType=dict(types),
        byPriority=dict(priorities),
        partConsumption=usageStats,
        technicians=summariseTechnicians(orders),
        trend=buildTrend(orders, fromDate, toDate),
    )


def defaultWindow(today: date, months: int = 12) -> tuple[date, date]:
    """A sensible reporting window ending today — the last ``months`` months."""
    start = today - timedelta(days=30 * max(1, months))
    return start, today
