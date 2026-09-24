"""Maintenance commands (Phase 21)."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Command


# -- Device commands --------------------------------------------------------------
@dataclass(frozen=True)
class RegisterDeviceCommand(Command):
    tenantId: str = ""
    code: str = ""
    name: str = ""
    location: str = ""
    department: str = "general"
    pmIntervalDays: int = 0


@dataclass(frozen=True)
class UpdateDeviceCommand(Command):
    deviceId: str
    name: str
    location: str = ""
    department: str = "general"
    pmIntervalDays: int = 0


@dataclass(frozen=True)
class ChangeDeviceStatusCommand(Command):
    deviceId: str
    target: str


@dataclass(frozen=True)
class RecordDevicePmCommand(Command):
    deviceId: str
    performedOn: str = ""


@dataclass(frozen=True)
class SendPmRemindersCommand(Command):
    """Scan the PM schedule and emit due-soon / overdue reminder events.

    ``leadDays`` is the look-ahead window: devices whose next PM date falls
    within the next ``leadDays`` days raise ``devicePmDueSoon``; devices whose
    date has already passed raise ``devicePmOverdue``.
    """

    tenantId: str = ""
    leadDays: int = 3


# -- Work order commands ----------------------------------------------------------
@dataclass(frozen=True)
class SubmitWorkOrderCommand(Command):
    tenantId: str = ""
    deviceId: str = ""
    title: str = ""
    description: str = ""
    orderType: str = "corrective"
    priority: str = "normal"
    department: str = ""
    requestedByName: str = ""


@dataclass(frozen=True)
class UpdateWorkOrderCommand(Command):
    workOrderId: str
    title: str
    description: str = ""
    priority: str = "normal"


@dataclass(frozen=True)
class RouteWorkOrderCommand(Command):
    workOrderId: str
    department: str


@dataclass(frozen=True)
class GeneratePmWorkOrdersCommand(Command):
    """Trigger auto-creation of preventive work orders for due devices."""

    tenantId: str = ""


@dataclass(frozen=True)
class AssignWorkOrderCommand(Command):
    workOrderId: str
    assignedToName: str


@dataclass(frozen=True)
class ChangeWorkOrderStatusCommand(Command):
    workOrderId: str
    target: str
    resolutionNote: str = ""


@dataclass(frozen=True)
class ApproveWorkOrderCommand(Command):
    workOrderId: str
    note: str = ""


@dataclass(frozen=True)
class RejectWorkOrderCommand(Command):
    workOrderId: str
    note: str = ""
