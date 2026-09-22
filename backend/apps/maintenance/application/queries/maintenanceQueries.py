"""Maintenance queries (Phase 21)."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Query


@dataclass(frozen=True)
class ListDevicesQuery(Query):
    status: str = ""
    department: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50


@dataclass(frozen=True)
class GetDeviceQuery(Query):
    deviceId: str


@dataclass(frozen=True)
class ListDuePmQuery(Query):
    pass


@dataclass(frozen=True)
class ListWorkOrdersQuery(Query):
    deviceId: str = ""
    status: str = ""
    orderType: str = ""
    priority: str = ""
    department: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50


@dataclass(frozen=True)
class GetWorkOrderQuery(Query):
    workOrderId: str
