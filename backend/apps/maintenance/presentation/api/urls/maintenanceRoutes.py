"""Maintenance routes — mounted under /api/v1/maintenance/."""

from __future__ import annotations

from django.urls import path

from apps.maintenance.presentation.api.views import openapiRegistration  # noqa: F401
from apps.maintenance.presentation.api.views.deviceViews import (
    DeviceDetailView,
    DeviceListView,
    DevicePmRemindersView,
    DevicePmView,
    DeviceStatusView,
    DeviceTimelineView,
    DuePmListView,
)
from apps.maintenance.presentation.api.views.maintenanceAttachmentViews import (
    DeviceAttachmentView,
    MaintenanceAttachmentDetailView,
    MaintenanceAttachmentDownloadView,
    WorkOrderAttachmentView,
)
from apps.maintenance.presentation.api.views.registryViews import (
    DeviceAnalyticsView,
    DeviceAssignmentsView,
    DeviceBomItemView,
    DeviceBomView,
    DeviceNameplateView,
    DevicePmPlanListView,
    DeviceProfileView,
    DeviceSpecificationsView,
    FleetAnalyticsView,
    LocationDetailView,
    LocationListView,
    PartUsageReportView,
    PersonnelDetailView,
    PersonnelListView,
    PmPlanDetailView,
    PmPlanExecutionView,
    WorkOrderClosureView,
)
from apps.maintenance.presentation.api.views.sparePartViews import (
    SparePartDetailView,
    SparePartListView,
    WorkOrderPartUsageView,
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
    path(
        "devices/pm-reminders",
        DevicePmRemindersView.as_view(),
        name="devicesPmReminders",
    ),
    path("devices/<uuid:deviceId>", DeviceDetailView.as_view(), name="deviceDetail"),
    path("devices/<uuid:deviceId>/status", DeviceStatusView.as_view(), name="deviceStatus"),
    path("devices/<uuid:deviceId>/pm", DevicePmView.as_view(), name="devicePm"),
    path(
        "devices/<uuid:deviceId>/attachments",
        DeviceAttachmentView.as_view(),
        name="deviceAttachments",
    ),
    path(
        "devices/<uuid:deviceId>/report",
        DeviceMaintenanceReportView.as_view(),
        name="deviceMaintenanceReport",
    ),
    path(
        "devices/<uuid:deviceId>/timeline",
        DeviceTimelineView.as_view(),
        name="deviceTimeline",
    ),
    # -- Phase 26 asset registry -------------------------------------------------
    # Static registry paths precede the device uuid capture above them only where
    # they do not collide; device-scoped registry paths live under the uuid.
    path("locations", LocationListView.as_view(), name="maintenanceLocationList"),
    path(
        "locations/<uuid:locationId>",
        LocationDetailView.as_view(),
        name="maintenanceLocationDetail",
    ),
    path("personnel", PersonnelListView.as_view(), name="maintenancePersonnelList"),
    path(
        "personnel/<uuid:personnelId>",
        PersonnelDetailView.as_view(),
        name="maintenancePersonnelDetail",
    ),
    path(
        "devices/<uuid:deviceId>/profile",
        DeviceProfileView.as_view(),
        name="deviceProfile",
    ),
    path(
        "devices/<uuid:deviceId>/nameplate",
        DeviceNameplateView.as_view(),
        name="deviceNameplate",
    ),
    path(
        "devices/<uuid:deviceId>/specifications",
        DeviceSpecificationsView.as_view(),
        name="deviceSpecifications",
    ),
    path(
        "devices/<uuid:deviceId>/pm-plans",
        DevicePmPlanListView.as_view(),
        name="devicePmPlans",
    ),
    path("pm-plans/<uuid:planId>", PmPlanDetailView.as_view(), name="pmPlanDetail"),
    path(
        "pm-plans/<uuid:planId>/executions",
        PmPlanExecutionView.as_view(),
        name="pmPlanExecutions",
    ),
    path("devices/<uuid:deviceId>/bom", DeviceBomView.as_view(), name="deviceBom"),
    path(
        "devices/<uuid:deviceId>/bom/<uuid:partId>",
        DeviceBomItemView.as_view(),
        name="deviceBomItem",
    ),
    path(
        "devices/<uuid:deviceId>/assignments",
        DeviceAssignmentsView.as_view(),
        name="deviceAssignments",
    ),
    path(
        "devices/<uuid:deviceId>/analytics",
        DeviceAnalyticsView.as_view(),
        name="deviceAnalytics",
    ),
    path("analytics/fleet", FleetAnalyticsView.as_view(), name="fleetAnalytics"),
    path(
        "analytics/parts/<uuid:partId>",
        PartUsageReportView.as_view(),
        name="partUsageReport",
    ),
    path(
        "work-orders/<uuid:workOrderId>/closure",
        WorkOrderClosureView.as_view(),
        name="workOrderClosure",
    ),
    # Spare-parts warehouse.
    path("spare-parts", SparePartListView.as_view(), name="sparePartList"),
    path("spare-parts/<uuid:partId>", SparePartDetailView.as_view(), name="sparePartDetail"),
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
    path(
        "work-orders/<uuid:workOrderId>/parts",
        WorkOrderPartUsageView.as_view(),
        name="workOrderPartUsage",
    ),
    path(
        "work-orders/<uuid:workOrderId>/attachments",
        WorkOrderAttachmentView.as_view(),
        name="workOrderAttachments",
    ),
    path(
        "attachments/<uuid:attachmentId>/download",
        MaintenanceAttachmentDownloadView.as_view(),
        name="maintenanceAttachmentDownload",
    ),
    path(
        "attachments/<uuid:attachmentId>",
        MaintenanceAttachmentDetailView.as_view(),
        name="maintenanceAttachmentDetail",
    ),
]
