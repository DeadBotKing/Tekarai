"""Maintenance DTOs (Phase 21)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from apps.maintenance.domain.entities.device import Device
from apps.maintenance.domain.entities.workOrder import WorkOrder


@dataclass(frozen=True)
class DeviceDto:
    id: str
    tenantId: str
    code: str
    name: str
    location: str
    status: str
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
    requestedByName: str
    assignedToName: str
    resolutionNote: str
    createdAt: str
    updatedAt: str = ""
    closedAt: str = ""


@dataclass(frozen=True)
class WorkOrderListDto:
    items: list[WorkOrderDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


def deviceDtoFromDomain(device: Device, asOf: date) -> DeviceDto:
    nextDue = device.nextDueDate()
    return DeviceDto(
        id=str(device.id),
        tenantId=str(device.tenantId),
        code=device.code,
        name=device.name,
        location=device.location,
        status=str(device.status),
        pmIntervalDays=device.pmIntervalDays,
        lastPmDate=device.lastPmDate.isoformat() if device.lastPmDate else "",
        nextDueDate=nextDue.isoformat() if nextDue else "",
        pmDue=device.isPmDue(asOf),
        createdAt=device.createdAt.isoformat(),
        updatedAt=device.updatedAt.isoformat() if device.updatedAt else "",
    )


def workOrderDtoFromDomain(order: WorkOrder) -> WorkOrderDto:
    return WorkOrderDto(
        id=str(order.id),
        tenantId=str(order.tenantId),
        deviceId=str(order.deviceId),
        title=order.title,
        description=order.description,
        orderType=str(order.orderType),
        priority=str(order.priority),
        status=str(order.status),
        requestedByName=order.requestedByName,
        assignedToName=order.assignedToName,
        resolutionNote=order.resolutionNote,
        createdAt=order.createdAt.isoformat(),
        updatedAt=order.updatedAt.isoformat() if order.updatedAt else "",
        closedAt=order.closedAt.isoformat() if order.closedAt else "",
    )
