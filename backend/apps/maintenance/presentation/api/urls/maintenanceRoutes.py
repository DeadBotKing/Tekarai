"""Maintenance routes — mounted under /api/v1/maintenance/."""

from __future__ import annotations

from django.urls import path

from apps.maintenance.presentation.api.views import openapiRegistration  # noqa: F401
from apps.maintenance.presentation.api.views.deviceViews import (
    DeviceDetailView,
    DeviceListView,
    DevicePmView,
    DeviceStatusView,
    DuePmListView,
)
from apps.maintenance.presentation.api.views.workOrderViews import (
    DeviceMaintenanceReportView,
    WorkOrderApproveView,
    WorkOrderAssignView,
    WorkOrderDetailView,
    WorkOrderGeneratePmView,
    WorkOrderHistoryView,
    WorkOrderListView,
    WorkOrderRejectView,
    WorkOrderRouteView,
    WorkOrderStatusView,
)

urlpatterns = [
    # Devices — order matters: the static "due-pm" path precedes the uuid capture.
    path("devices", DeviceListView.as_view(), name="deviceList"),
    path("devices/due-pm", DuePmListView.as_view(), name="devicesDuePm"),
    path("devices/<uuid:deviceId>", DeviceDetailView.as_view(), name="deviceDetail"),
    path("devices/<uuid:deviceId>/status", DeviceStatusView.as_view(), name="deviceStatus"),
    path("devices/<uuid:deviceId>/pm", DevicePmView.as_view(), name="devicePm"),
    path(
        "devices/<uuid:deviceId>/report",
        DeviceMaintenanceReportView.as_view(),
        name="deviceMaintenanceReport",
    ),
    # Work orders — static "generate-pm" path precedes the uuid capture.
    path("work-orders", WorkOrderListView.as_view(), name="workOrderList"),
    path(
        "work-orders/generate-pm",
        WorkOrderGeneratePmView.as_view(),
        name="workOrderGeneratePm",
    ),
    path(
        "work-orders/<uuid:workOrderId>",
        WorkOrderDetailView.as_view(),
        name="workOrderDetail",
    ),
    path(
        "work-orders/<uuid:workOrderId>/route",
        WorkOrderRouteView.as_view(),
        name="workOrderRoute",
    ),
    path(
        "work-orders/<uuid:workOrderId>/assign",
        WorkOrderAssignView.as_view(),
        name="workOrderAssign",
    ),
    path(
        "work-orders/<uuid:workOrderId>/status",
        WorkOrderStatusView.as_view(),
        name="workOrderStatus",
    ),
    path(
        "work-orders/<uuid:workOrderId>/approve",
        WorkOrderApproveView.as_view(),
        name="workOrderApprove",
    ),
    path(
        "work-orders/<uuid:workOrderId>/reject",
        WorkOrderRejectView.as_view(),
        name="workOrderReject",
    ),
    path(
        "work-orders/<uuid:workOrderId>/history",
        WorkOrderHistoryView.as_view(),
        name="workOrderHistory",
    ),
]
