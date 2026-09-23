"""Maintenance DTOs (Phase 21)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from apps.maintenance.domain.entities.device import Device
from apps.maintenance.domain.entities.workOrder import WorkOrder
from apps.maintenance.domain.entities.workOrderHistory import WorkOrderHistoryEntry


@dataclass(frozen=True)
class DeviceDto:
    id: str
    tenantId: str
    code: str
    name: str
    location: str
    status: str
    department: str
    pmIntervalDays: int
    lastPmDate: str
    nextDueDate: str
    pmDue: bool
    createdAt: str
    updatedAt: str = ""


@dataclass(frozen=True)
class DeviceListDto:
    items: list[DeviceDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


@dataclass(frozen=True)
class WorkOrderDto:
    id: str
    tenantId: str
    deviceId: str
    title: str
    description: str
    orderType: str
    priority: str
    status: str
    department: str
    requestedByName: str
    assignedToName: str
    resolutionNote: str
    createdAt: str
    updatedAt: str = ""
    closedAt: str = ""
    slaDueAt: str = ""
    overdue: bool = False


@dataclass(frozen=True)
class WorkOrderListDto:
    items: list[WorkOrderDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


@dataclass(frozen=True)
class WorkOrderHistoryDto:
    id: str
    workOrderId: str
    action: str
    fromStatus: str
    toStatus: str
    fromDepartment: str
    toDepartment: str
    actorName: str
    note: str
    createdAt: str


@dataclass(frozen=True)
class WorkOrderHistoryListDto:
    items: list[WorkOrderHistoryDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


def historyDtoFromDomain(entry: WorkOrderHistoryEntry) -> WorkOrderHistoryDto:
    return WorkOrderHistoryDto(
        id=str(entry.id),
        workOrderId=str(entry.workOrderId),
        action=entry.action,
        fromStatus=entry.fromStatus,
        toStatus=entry.toStatus,
        fromDepartment=entry.fromDepartment,
        toDepartment=entry.toDepartment,
        actorName=entry.actorName,
        note=entry.note,
        createdAt=entry.createdAt.isoformat(),
    )


@dataclass(frozen=True)
class DeviceMaintenanceReportDto:
    """Full maintenance history of a single device (Phase 23 reporting).

    Bundles the device card, every work order raised against it (newest
    first), and a pre-computed statistical summary so the API, Excel/CSV
    exporters and the printable report page all read from one shape.
    """

    device: DeviceDto
    workOrders: list[WorkOrderDto] = field(default_factory=list)
    summary: "DeviceReportSummaryDto | None" = None
    generatedAt: str = ""
    fromDate: str = ""
    toDate: str = ""

    def asMeta(self) -> dict[str, object]:
        return {
            "totalCount": len(self.workOrders),
            "generatedAt": self.generatedAt,
            "fromDate": self.fromDate,
            "toDate": self.toDate,
        }


@dataclass(frozen=True)
class DeviceReportSummaryDto:
    totalOrders: int = 0
    openOrders: int = 0
    completedOrders: int = 0
    overdueOrders: int = 0
    byStatus: dict[str, int] = field(default_factory=dict)
    byType: dict[str, int] = field(default_factory=dict)
    byPriority: dict[str, int] = field(default_factory=dict)
    # Mean time to repair, in hours, over completed orders (None if none).
    mttrHours: float | None = None


def deviceDtoFromDomain(device: Device, asOf: date) -> DeviceDto:
    nextDue = device.nextDueDate()
    return DeviceDto(
        id=str(device.id),
        tenantId=str(device.tenantId),
        code=device.code,
        name=device.name,
        location=device.location,
        status=str(device.status),
        department=str(device.department),
        pmIntervalDays=device.pmIntervalDays,
        lastPmDate=device.lastPmDate.isoformat() if device.lastPmDate else "",
        nextDueDate=nextDue.isoformat() if nextDue else "",
        pmDue=device.isPmDue(asOf),
        createdAt=device.createdAt.isoformat(),
        updatedAt=device.updatedAt.isoformat() if device.updatedAt else "",
    )


def workOrderDtoFromDomain(order: WorkOrder, now: datetime | None = None) -> WorkOrderDto:
    referenceNow = now or datetime.now(tz=timezone.utc)
    dueAt = order.slaDueAt()
    return WorkOrderDto(
        id=str(order.id),
        tenantId=str(order.tenantId),
        deviceId=str(order.deviceId),
        title=order.title,
        description=order.description,
        orderType=str(order.orderType),
        priority=str(order.priority),
        status=str(order.status),
        department=str(order.department),
        requestedByName=order.requestedByName,
        assignedToName=order.assignedToName,
        resolutionNote=order.resolutionNote,
        createdAt=order.createdAt.isoformat(),
        updatedAt=order.updatedAt.isoformat() if order.updatedAt else "",
        closedAt=order.closedAt.isoformat() if order.closedAt else "",
        slaDueAt=dueAt.isoformat() if dueAt else "",
        overdue=order.isOverdue(referenceNow),
    )
