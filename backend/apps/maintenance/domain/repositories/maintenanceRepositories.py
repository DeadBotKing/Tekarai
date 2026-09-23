"""Maintenance repository contracts (Phase 21).

Devices and WorkOrders are separate aggregates in the same bounded context.
Each has its own repository protocol; both stay tenant-scoped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 — used in dataclass field annotations
from typing import Protocol, runtime_checkable

from apps.maintenance.domain.entities.device import Device
from apps.maintenance.domain.entities.workOrder import WorkOrder
from apps.maintenance.domain.entities.workOrderHistory import WorkOrderHistoryEntry


@dataclass(frozen=True)
class DeviceFilters:
    tenantId: uuid.UUID
    status: str = ""
    department: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50


@dataclass(frozen=True)
class DevicePage:
    items: list[Device]
    totalCount: int


@dataclass(frozen=True)
class WorkOrderFilters:
    tenantId: uuid.UUID
    deviceId: str = ""
    status: str = ""
    orderType: str = ""
    priority: str = ""
    department: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50
    # Optional inclusive creation-date bounds (aware datetimes); Phase 23.
    createdFrom: "datetime | None" = None
    createdTo: "datetime | None" = None


@dataclass(frozen=True)
class WorkOrderPage:
    items: list[WorkOrder]
    totalCount: int


@runtime_checkable
class DeviceRepository(Protocol):
    def create(self, device: Device) -> None: ...

    def update(self, device: Device) -> None: ...

    def getById(self, tenantId: uuid.UUID, deviceId: uuid.UUID) -> Device | None: ...

    def getByCode(self, tenantId: uuid.UUID, code: str) -> Device | None: ...

    def countByTenant(self, tenantId: uuid.UUID) -> int: ...

    def listDueForPm(self, tenantId: uuid.UUID) -> list[Device]: ...

    def list(self, filters: DeviceFilters) -> DevicePage: ...


@runtime_checkable
class WorkOrderRepository(Protocol):
    def create(self, order: WorkOrder) -> None: ...

    def update(self, order: WorkOrder) -> None: ...

    def getById(self, tenantId: uuid.UUID, orderId: uuid.UUID) -> WorkOrder | None: ...

    def countByTenant(self, tenantId: uuid.UUID) -> int: ...

    def countOpenByTenant(self, tenantId: uuid.UUID) -> int: ...

    def hasOpenPreventiveOrder(self, tenantId: uuid.UUID, deviceId: uuid.UUID) -> bool: ...

    def countOpenByAssignee(self, tenantId: uuid.UUID, department: str) -> dict[str, int]: ...

    def list(self, filters: WorkOrderFilters) -> WorkOrderPage: ...


@runtime_checkable
class WorkOrderHistoryRepository(Protocol):
    def append(self, entry: WorkOrderHistoryEntry) -> None: ...

    def listForOrder(
        self, tenantId: uuid.UUID, workOrderId: uuid.UUID
    ) -> list[WorkOrderHistoryEntry]: ...
