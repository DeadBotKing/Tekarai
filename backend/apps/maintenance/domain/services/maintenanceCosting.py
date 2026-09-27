"""Maintenance cost aggregation — pure computation over dated rows (time & cost).

Same philosophy as ``maintenanceAnalytics``: totals are *derived* from the
individual labour entries and part-usage rows, never trusted from a
hand-maintained counter. Given the per-work-order readings the repository
loads, the functions here produce the summary and the device / department /
technician breakdowns the maintenance cost report renders.

The module is intentionally free of Django so the rules can be unit-tested
without a database.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class WorkOrderCostReading:
    """One work order's cost facts, with its device attached for grouping."""

    workOrderId: str
    title: str
    orderType: str
    status: str
    department: str
    deviceId: str
    deviceCode: str
    deviceName: str
    assignedToName: str
    labourHours: Decimal
    labourCost: Decimal
    partsCost: Decimal
    createdAtIso: str
    closedAtIso: str = ""

    @property
    def totalCost(self) -> Decimal:
        return (self.labourCost + self.partsCost).quantize(CENT)


@dataclass(frozen=True)
class LabourCostReading:
    """One technician labour entry flattened for technician-level rollups."""

    workOrderId: str
    technicianName: str
    hours: Decimal
    cost: Decimal


@dataclass(frozen=True)
class CostTotals:
    workOrderCount: int = 0
    labourHours: Decimal = ZERO
    labourCost: Decimal = ZERO
    partsCost: Decimal = ZERO
    totalCost: Decimal = ZERO


@dataclass(frozen=True)
class CostGroup:
    """One bucket of a breakdown (a device, a department, …)."""

    key: str
    label: str
    workOrderCount: int = 0
    labourHours: Decimal = ZERO
    labourCost: Decimal = ZERO
    partsCost: Decimal = ZERO
    totalCost: Decimal = ZERO


@dataclass(frozen=True)
class TechnicianLabourGroup:
    """Technician productivity: hours worked and their labour cost."""

    technicianName: str
    entryCount: int = 0
    hours: Decimal = ZERO
    cost: Decimal = ZERO


@dataclass
class CostRowBucket:
    """Mutable accumulator used only inside the grouping pass."""

    label: str = ""
    orderIds: set[str] = field(default_factory=set)
    labourHours: Decimal = ZERO
    labourCost: Decimal = ZERO
    partsCost: Decimal = ZERO


def totalCosts(readings: list[WorkOrderCostReading]) -> CostTotals:
    """Grand totals across the report window."""
    labourHours = sum((row.labourHours for row in readings), ZERO)
    labourCost = sum((row.labourCost for row in readings), ZERO)
    partsCost = sum((row.partsCost for row in readings), ZERO)
    return CostTotals(
        workOrderCount=len(readings),
        labourHours=labourHours.quantize(CENT),
        labourCost=labourCost.quantize(CENT),
        partsCost=partsCost.quantize(CENT),
        totalCost=(labourCost + partsCost).quantize(CENT),
    )


def groupCosts(
    readings: list[WorkOrderCostReading],
    keyOf: Callable[[WorkOrderCostReading], str],
    labelOf: Callable[[WorkOrderCostReading], str],
) -> list[CostGroup]:
    """Break the readings into buckets, most expensive first."""
    buckets: dict[str, CostRowBucket] = OrderedDict()
    for row in readings:
        key = keyOf(row) or "—"
        bucket = buckets.setdefault(key, CostRowBucket(label=labelOf(row) or key))
        bucket.orderIds.add(row.workOrderId)
        bucket.labourHours += row.labourHours
        bucket.labourCost += row.labourCost
        bucket.partsCost += row.partsCost

    groups = [
        CostGroup(
            key=key,
            label=bucket.label,
            workOrderCount=len(bucket.orderIds),
            labourHours=bucket.labourHours.quantize(CENT),
            labourCost=bucket.labourCost.quantize(CENT),
            partsCost=bucket.partsCost.quantize(CENT),
            totalCost=(bucket.labourCost + bucket.partsCost).quantize(CENT),
        )
        for key, bucket in buckets.items()
    ]
    groups.sort(key=lambda group: group.totalCost, reverse=True)
    return groups


@dataclass
class LabourRowBucket:
    entryCount: int = 0
    hours: Decimal = ZERO
    cost: Decimal = ZERO


def groupLabourByTechnician(
    entries: list[LabourCostReading],
) -> list[TechnicianLabourGroup]:
    """Roll individual labour entries up per technician, most hours first."""
    buckets: dict[str, LabourRowBucket] = OrderedDict()
    for entry in entries:
        key = entry.technicianName.strip() or "—"
        bucket = buckets.setdefault(key, LabourRowBucket())
        bucket.entryCount += 1
        bucket.hours += entry.hours
        bucket.cost += entry.cost

    groups = [
        TechnicianLabourGroup(
            technicianName=key,
            entryCount=bucket.entryCount,
            hours=bucket.hours.quantize(CENT),
            cost=bucket.cost.quantize(CENT),
        )
        for key, bucket in buckets.items()
    ]
    groups.sort(key=lambda group: group.hours, reverse=True)
    return groups
