"""Notification routes — mounted under /api/v1/notifications/ (§40)."""

from __future__ import annotations

from django.urls import path

from apps.notifications.presentation.api.views.notificationViews import (
    AdminChannelListView,
    AdminPolicyDetailView,
    AdminPolicyListView,
    AdminScheduleDetailView,
    AdminScheduleListView,
    AdminSendView,
    AdminTemplateDetailView,
    AdminTemplateListView,
    AdminTenantRuleDetailView,
    AdminTenantRuleListView,
    DeviceDetailView,
    DeviceListView,
    NotificationAcknowledgeView,
    NotificationArchiveView,
    NotificationCancelView,
    NotificationDetailView,
    NotificationListView,
    NotificationMetricsView,
    NotificationReadBulkView,
    NotificationReadView,
    NotificationUnreadCountView,
    PreferenceListView,
)

urlpatterns = [
    # literal segments MUST precede <str:notificationId> (Django matches in order)
    path("", NotificationListView.as_view(), name="ntfList"),
    path("read-bulk", NotificationReadBulkView.as_view(), name="ntfReadBulk"),
    path("unread-count", NotificationUnreadCountView.as_view(), name="ntfUnreadCount"),
    path("preferences", PreferenceListView.as_view(), name="ntfPreferences"),
    path("devices", DeviceListView.as_view(), name="ntfDevices"),
    path(
        "devices/<str:deviceId>",
        DeviceDetailView.as_view(),
        name="ntfDeviceDetail",
    ),
    path("admin/send", AdminSendView.as_view(), name="ntfAdminSend"),
    path("admin/schedules", AdminScheduleListView.as_view(), name="ntfAdminSchedules"),
    path(
        "admin/schedules/<str:scheduleId>",
        AdminScheduleDetailView.as_view(),
        name="ntfAdminScheduleDetail",
    ),
    path("admin/templates", AdminTemplateListView.as_view(), name="ntfAdminTemplates"),
    path(
        "admin/templates/<str:templateId>",
        AdminTemplateDetailView.as_view(),
        name="ntfAdminTemplateDetail",
    ),
    path("admin/policies", AdminPolicyListView.as_view(), name="ntfAdminPolicies"),
    path(
        "admin/policies/<str:policyId>",
        AdminPolicyDetailView.as_view(),
        name="ntfAdminPolicyDetail",
    ),
    path("admin/channels", AdminChannelListView.as_view(), name="ntfAdminChannels"),
    path(
        "admin/tenant-rules",
        AdminTenantRuleListView.as_view(),
        name="ntfAdminTenantRules",
    ),
    path(
        "admin/tenant-rules/<str:ruleId>",
        AdminTenantRuleDetailView.as_view(),
        name="ntfAdminTenantRuleDetail",
    ),
    path("admin/metrics", NotificationMetricsView.as_view(), name="ntfAdminMetrics"),
    # per-notification routes last
    path(
        "<str:notificationId>",
        NotificationDetailView.as_view(),
        name="ntfDetail",
    ),
    path(
        "<str:notificationId>/read",
        NotificationReadView.as_view(),
        name="ntfRead",
    ),
    path(
        "<str:notificationId>/acknowledge",
        NotificationAcknowledgeView.as_view(),
        name="ntfAcknowledge",
    ),
    path(
        "<str:notificationId>/archive",
        NotificationArchiveView.as_view(),
        name="ntfArchive",
    ),
    path(
        "<str:notificationId>/cancel",
        NotificationCancelView.as_view(),
        name="ntfCancel",
    ),
]
