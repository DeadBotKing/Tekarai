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


@dataclass(frozen=True)
class ListWorkOrderHistoryQuery(Query):
    workOrderId: str


@dataclass(frozen=True)
class DeviceMaintenanceReportQuery(Query):
    """Full maintenance history + stats for one device (Phase 23).

    ``fromDate``/``toDate`` are optional ISO dates (YYYY-MM-DD) that bound the
    work orders by creation date; empty means unbounded on that side.
    """

    deviceId: str
    fromDate: str = ""
    toDate: str = ""


@dataclass(frozen=True)
class GetDeviceTimelineQuery(Query):
    """The unified, chronological timeline for a single device.

    Merges the device's own history (registration, updates, status changes, PM
    completions) with milestones of the work orders raised against it.
    """

    deviceId: str
