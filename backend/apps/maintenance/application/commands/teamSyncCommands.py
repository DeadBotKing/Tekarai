"""Commands/queries — هم‌گام‌سازی تیمی رزروها و چک‌لیست‌های بازرسی."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.sharedKernel.application.messaging import Command, Query


@dataclass(frozen=True)
class ListReservationsQuery(Query):
    workOrderId: str = ""


@dataclass(frozen=True)
class SaveReservationCommand(Command):
    id: str
    workOrderId: str
    partCode: str
    quantity: str
    status: str = "active"
    reservedByName: str = ""


@dataclass(frozen=True)
class CloseReservationCommand(Command):
    reservationId: str
    status: str  # consumed / released


@dataclass(frozen=True)
class ListInspectionTemplatesQuery(Query):
    pass


@dataclass(frozen=True)
class SaveInspectionTemplateCommand(Command):
    id: str
    name: str
    description: str = ""
    deviceCode: str = ""
    checks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommitInspectionTemplateCommand(Command):
    templateId: str


@dataclass(frozen=True)
class ListInspectionRecordsQuery(Query):
    workOrderId: str = ""


@dataclass(frozen=True)
class SaveInspectionRecordCommand(Command):
    id: str
    templateId: str
    workOrderId: str
    deviceId: str
    passedChecks: list[str] = field(default_factory=list)
    failedChecks: list[str] = field(default_factory=list)
    performedByName: str = ""


@dataclass(frozen=True)
class DeleteInspectionTemplateCommand(Command):
    templateId: str
