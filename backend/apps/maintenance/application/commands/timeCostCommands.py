from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Command, Query


@dataclass(frozen=True)
class LogLabourEntryCommand(Command):
    workOrderId: str
    technicianName: str
    hours: str
    hourlyRate: str = "0"
    workedAt: str = ""  # ISO datetime; empty → now
    note: str = ""


@dataclass(frozen=True)
class DeleteLabourEntryCommand(Command):
    entryId: str


@dataclass(frozen=True)
class ListLabourEntriesQuery(Query):
    workOrderId: str


@dataclass(frozen=True)
class WorkOrderCostSummaryQuery(Query):
    workOrderId: str


@dataclass(frozen=True)
class MaintenanceCostReportQuery(Query):
    fromDate: str = ""  # YYYY-MM-DD, inclusive lower bound on work-order creation
    toDate: str = ""  # YYYY-MM-DD, inclusive upper bound on work-order creation
    deviceId: str = ""
    department: str = ""
