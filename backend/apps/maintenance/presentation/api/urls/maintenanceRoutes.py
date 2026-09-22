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
    WorkOrderAssignView,
    WorkOrderDetailView,
    WorkOrderListView,
    WorkOrderStatusView,
)

urlpatterns = [
    # Devices — order matters: the static "due-pm" path precedes the uuid capture.
    path("devices", DeviceListView.as_view(), name="deviceList"),
    path("devices/due-pm", DuePmListView.as_view(), name="devicesDuePm"),
    path("devices/<uuid:deviceId>", DeviceDetailView.as_view(), name="deviceDetail"),
    path("devices/<uuid:deviceId>/status", DeviceStatusView.as_view(), name="deviceStatus"),
    path("devices/<uuid:deviceId>/pm", DevicePmView.as_view(), name="devicePm"),
    # Work orders
    path("work-orders", WorkOrderListView.as_view(), name="workOrderList"),
    path(
        "work-orders/<uuid:workOrderId>",
        WorkOrderDetailView.as_view(),
        name="workOrderDetail",
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
]
