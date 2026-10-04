"""Maintenance routes — mounted under /api/v1/maintenance/."""

from __future__ import annotations

from django.urls import path

from apps.maintenance.presentation.api.views import openapiRegistration  # noqa: F401
from apps.maintenance.presentation.api.views.workCalendarViews import (
    CalendarHolidayDetailView,
    CalendarHolidayView,
    CapacityPlanView,
    ShiftAssignmentDetailView,
    ShiftAssignmentView,
    WorkCalendarDetailView,
    WorkCalendarListView,
    WorkingDayView,
    WorkShiftDetailView,
    WorkShiftView,
)
from apps.maintenance.presentation.api.views.assetHierarchyViews import (
    AssetAncestryView,
    AssetMovementListView,
    AssetRetirementView,
    AssetTreeView,
)
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
from apps.maintenance.presentation.api.views.meterViews import (
    DeviceMeterPointListView,
    DeviceMeterReadingView,
    MeterPmStatusView,
    MeterPointDetailView,
    MeterPointListView,
    MeterPointReadingView,
    MeterPointSummaryView,
    MeterReadingCorrectionView,
    MeterReadingListView,
    SensorIngestView,
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
    PmScheduleView,
    WorkOrderClosureView,
)
from apps.maintenance.presentation.api.views.sparePartViews import (
    PartTransactionsView,
    SparePartDetailView,
    SparePartListView,
    WorkOrderPartUsageView,
)
from apps.maintenance.presentation.api.views.teamSyncViews import (
    TeamInspectionRecordListView,
    TeamInspectionTemplateCommitView,
    TeamInspectionTemplateDetailView,
    TeamInspectionTemplateListView,
    TeamReservationDetailView,
    TeamReservationListView,
)
from apps.maintenance.presentation.api.views.fieldOpsViews import (
    MyRunningTimersView,
    OfflineSyncView,
    ScanResolveView,
    SyncHistoryView,
    WorkOrderTimerListView,
    WorkOrderTimerStartView,
    WorkOrderTimerStopView,
    WorkTimerDetailView,
)
from apps.maintenance.presentation.api.views.timeCostViews import (
    LabourEntryDetailView,
    MaintenanceCostReportView,
    WorkOrderCostSummaryView,
    WorkOrderLabourEntryView,
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
    # -- Meter readings (ثبت قرائت دستی و سنسوری) --------------------------------
    # Static ingest path precedes the reading uuid capture, otherwise
    # "ingest" would be parsed as a reading id.
    path(
        "meter-readings/ingest",
        SensorIngestView.as_view(),
        name="meterReadingIngest",
    ),
    path("meter-readings", MeterReadingListView.as_view(), name="meterReadingList"),
    path(
        "meter-readings/<uuid:readingId>/correct",
        MeterReadingCorrectionView.as_view(),
        name="meterReadingCorrect",
    ),
    path("meter-points", MeterPointListView.as_view(), name="meterPointList"),
    path(
        "meter-points/<uuid:meterPointId>",
        MeterPointDetailView.as_view(),
        name="meterPointDetail",
    ),
    path(
        "meter-points/<uuid:meterPointId>/readings",
        MeterPointReadingView.as_view(),
        name="meterPointReadings",
    ),
    path(
        "meter-points/<uuid:meterPointId>/summary",
        MeterPointSummaryView.as_view(),
        name="meterPointSummary",
    ),
    path(
        "devices/<uuid:deviceId>/meter-points",
        DeviceMeterPointListView.as_view(),
        name="deviceMeterPoints",
    ),
    path(
        "devices/<uuid:deviceId>/meter-readings",
        DeviceMeterReadingView.as_view(),
        name="deviceMeterReadings",
    ),
    path("meter-pm-status", MeterPmStatusView.as_view(), name="meterPmStatus"),
    path("pm-schedule", PmScheduleView.as_view(), name="pmSchedule"),
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
    # -- Work calendar, shifts, capacity (Phase 28) ------------------------------
    # Static segments are declared before the <uuid:> ones so "holidays" and
    # "shifts" are never swallowed by the detail route.
    path("work-calendars", WorkCalendarListView.as_view(), name="workCalendars"),
    path(
        "work-calendars/holidays",
        CalendarHolidayView.as_view(),
        name="calendarHolidays",
    ),
    path(
        "work-calendars/holidays/<uuid:holidayId>",
        CalendarHolidayDetailView.as_view(),
        name="calendarHolidayDetail",
    ),
    path("work-calendars/shifts", WorkShiftView.as_view(), name="workShifts"),
    path(
        "work-calendars/shifts/<uuid:shiftId>",
        WorkShiftDetailView.as_view(),
        name="workShiftDetail",
    ),
    path(
        "work-calendars/assignments",
        ShiftAssignmentView.as_view(),
        name="shiftAssignments",
    ),
    path(
        "work-calendars/assignments/<uuid:assignmentId>",
        ShiftAssignmentDetailView.as_view(),
        name="shiftAssignmentDetail",
    ),
    path("work-calendars/capacity", CapacityPlanView.as_view(), name="capacityPlan"),
    path(
        "work-calendars/working-day", WorkingDayView.as_view(), name="workingDay"
    ),
    path(
        "work-calendars/<uuid:calendarId>",
        WorkCalendarDetailView.as_view(),
        name="workCalendarDetail",
    ),
    # -- Asset hierarchy (Phase 27) ---------------------------------------------
    path("assets/tree", AssetTreeView.as_view(), name="assetTree"),
    path(
        "devices/<uuid:deviceId>/ancestry",
        AssetAncestryView.as_view(),
        name="assetAncestry",
    ),
    path(
        "devices/<uuid:deviceId>/movements",
        AssetMovementListView.as_view(),
        name="assetMovements",
    ),
    path(
        "devices/<uuid:deviceId>/retirement",
        AssetRetirementView.as_view(),
        name="assetRetirement",
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
    path(
        "spare-parts/<uuid:partId>/transactions",
        PartTransactionsView.as_view(),
        name="partTransactions",
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
    path(
        "work-orders/<uuid:workOrderId>/parts",
        WorkOrderPartUsageView.as_view(),
        name="workOrderPartUsage",
    ),
    # Time & cost tracking (ثبت زمان و هزینه).
    path(
        "work-orders/<uuid:workOrderId>/labour",
        WorkOrderLabourEntryView.as_view(),
        name="workOrderLabourEntries",
    ),
    path(
        "work-orders/<uuid:workOrderId>/cost-summary",
        WorkOrderCostSummaryView.as_view(),
        name="workOrderCostSummary",
    ),
    path(
        "labour-entries/<uuid:entryId>",
        LabourEntryDetailView.as_view(),
        name="labourEntryDetail",
    ),
    path(
        "reports/maintenance-costs",
        MaintenanceCostReportView.as_view(),
        name="maintenanceCostReport",
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
    # Team sync (موج دوم) — رزرو قطعات و چک‌لیست‌های تیمی
    path("team/reservations", TeamReservationListView.as_view(), name="teamReservationList"),
    path(
        "team/reservations/<str:reservationId>",
        TeamReservationDetailView.as_view(),
        name="teamReservationDetail",
    ),
    path(
        "team/inspection-templates",
        TeamInspectionTemplateListView.as_view(),
        name="teamInspectionTemplateList",
    ),
    path(
        "team/inspection-templates/<str:templateId>",
        TeamInspectionTemplateDetailView.as_view(),
        name="teamInspectionTemplateDetail",
    ),
    path(
        "team/inspection-templates/<str:templateId>/commit",
        TeamInspectionTemplateCommitView.as_view(),
        name="teamInspectionTemplateCommit",
    ),
    # -- Field operations: timers, scanning, offline sync -------------------------
    path(
        "work-orders/<uuid:workOrderId>/timer/start",
        WorkOrderTimerStartView.as_view(),
        name="workOrderTimerStart",
    ),
    path(
        "work-orders/<uuid:workOrderId>/timer/stop",
        WorkOrderTimerStopView.as_view(),
        name="workOrderTimerStop",
    ),
    path(
        "work-orders/<uuid:workOrderId>/timers",
        WorkOrderTimerListView.as_view(),
        name="workOrderTimerList",
    ),
    path("work-timers/active", MyRunningTimersView.as_view(), name="workTimerActive"),
    path(
        "work-timers/<uuid:timerId>",
        WorkTimerDetailView.as_view(),
        name="workTimerDetail",
    ),
    path("scan", ScanResolveView.as_view(), name="scanResolve"),
    path("sync", OfflineSyncView.as_view(), name="offlineSync"),
    path("sync/history", SyncHistoryView.as_view(), name="offlineSyncHistory"),
    path("team/inspection-records", TeamInspectionRecordListView.as_view(), name="teamInspectionRecordList"),
]
