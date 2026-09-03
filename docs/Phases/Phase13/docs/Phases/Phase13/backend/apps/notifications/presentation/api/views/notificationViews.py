"""Notification REST views (Phase 09 §40).

Own notifications need authentication only; administration surfaces
(templates/policies/channels/tenant rules/schedules) require the
``notification.manage`` action; the send/schedule surface requires
``notification.send``. Views stay thin: serialize → command → service →
envelope.
"""

from __future__ import annotations

import uuid

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.application.commands.notificationCommands import (
    AcknowledgeNotificationCommand,
    ArchiveNotificationCommand,
    CancelNotificationCommand,
    CancelScheduleCommand,
    CreateNotificationCommand,
    DeleteTenantRuleCommand,
    DeactivateTemplateCommand,
    DeletePolicyCommand,
    MarkNotificationReadCommand,
    MarkNotificationsReadCommand,
    MarkNotificationUnreadCommand,
    RegisterDeviceCommand,
    RevokeDeviceCommand,
    SavePolicyCommand,
    SaveTemplateCommand,
    SaveTenantRuleCommand,
    ScheduleNotificationCommand,
    UpdatePreferencesCommand,
)
from apps.notifications.application.dto.notificationDtos import dtoAsDict
from apps.notifications.application.queries.notificationQueries import (
    GetNotificationQuery,
    GetPreferencesQuery,
    ListDevicesQuery,
    ListNotificationsQuery,
    ListPoliciesQuery,
    ListSchedulesQuery,
    ListTemplateVersionsQuery,
    ListTemplatesQuery,
    ListTenantRulesQuery,
    UnreadCountQuery,
)
from apps.notifications.infrastructure.container import container
from apps.sharedKernel.presentation.api.authentication import (
    BearerSessionAuthentication,
)
from apps.sharedKernel.presentation.api.openapi import (
    EndpointSpec,
    registerEndpoint,
)
from apps.sharedKernel.presentation.api.permissions import (
    IsAuthenticated,
    actionPermission,
)
from apps.sharedKernel.presentation.api.response import successEnvelope

NOTIFICATION_ERRORS = [
    "SYS_VALIDATION_FAILED",
    "SYS_RECORD_NOT_FOUND",
    "PERM_PERMISSION_DENIED",
    "SYS_CONCURRENCY_CONFLICT",
]


def _actorIds(request: Request) -> tuple[uuid.UUID, uuid.UUID]:
    """§34 — identity strictly from the authenticated context."""
    from apps.sharedKernel.application.requestContext import currentContext
    from apps.sharedKernel.domain.errors import AuthenticationRequiredError

    context = currentContext()
    if not context.actorId or not context.tenantId:
        raise AuthenticationRequiredError()
    return uuid.UUID(context.actorId), uuid.UUID(context.tenantId)


def _actorTenantId(request: Request) -> uuid.UUID:
    return _actorIds(request)[1]


def _actorUserId(request: Request) -> uuid.UUID:
    return _actorIds(request)[0]


def _correlationId() -> str:
    from apps.sharedKernel.application.requestContext import currentContext

    return currentContext().correlationIdOrNew()


# -- own notifications (§40) --------------------------------------------------------


class NotificationListView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        query = ListNotificationsQuery(
            tenantId=_actorTenantId(request),
            recipientId=_actorUserId(request),
            unreadOnly=str(request.query_params.get("unread", "")).lower()
            in ("1", "true", "yes"),
            category=str(request.query_params.get("category", "") or ""),
            priority=str(request.query_params.get("priority", "") or ""),
            beforeId=(
                uuid.UUID(request.query_params["before"])
                if request.query_params.get("before")
                else None
            ),
            limit=min(int(request.query_params.get("limit", 50) or 50), 200),
            includeArchived=str(request.query_params.get("archived", "")).lower()
            in ("1", "true", "yes"),
        )
        page = container.listNotificationsUseCase().execute(query)
        return Response(
            successEnvelope(
                [dtoAsDict(item) for item in page.items],
                meta={
                    "unreadCount": page.unreadCount,
                    "hasNext": page.hasNext,
                },
            )
        )


class NotificationDetailView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, notificationId: str) -> Response:
        dto = container.getNotificationUseCase().execute(
            GetNotificationQuery(
                notificationId=uuid.UUID(notificationId),
                recipientId=_actorUserId(request),
            )
        )
        return Response(successEnvelope(dtoAsDict(dto)))


class NotificationReadView(APIView):
    """POST mark-read; DELETE mark-unread (§26 read ≠ acknowledged)."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, notificationId: str) -> Response:
        result = container.markNotificationReadService().execute(
            MarkNotificationReadCommand(
                notificationId=uuid.UUID(notificationId),
                recipientId=_actorUserId(request),
            )
        )
        return Response(successEnvelope(result))

    def delete(self, request: Request, notificationId: str) -> Response:
        result = container.markNotificationUnreadService().execute(
            MarkNotificationUnreadCommand(
                notificationId=uuid.UUID(notificationId),
                recipientId=_actorUserId(request),
            )
        )
        return Response(successEnvelope(result))


class NotificationReadBulkView(APIView):
    """§42 — client reconciliation after reconnect."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        ids = request.data.get("notificationIds", []) or []
        result = container.markNotificationReadService().execute(
            MarkNotificationsReadCommand(
                recipientId=_actorUserId(request),
                notificationIds=tuple(uuid.UUID(str(item)) for item in ids),
            )
        )
        return Response(successEnvelope(result))


class NotificationAcknowledgeView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, notificationId: str) -> Response:
        result = container.acknowledgeNotificationService().execute(
            AcknowledgeNotificationCommand(
                notificationId=uuid.UUID(notificationId),
                recipientId=_actorUserId(request),
            )
        )
        return Response(successEnvelope(result))


class NotificationArchiveView(APIView):
    """§40 Delete/Archive where allowed — soft delete."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, notificationId: str) -> Response:
        result = container.archiveNotificationService().execute(
            ArchiveNotificationCommand(
                notificationId=uuid.UUID(notificationId),
                recipientId=_actorUserId(request),
            )
        )
        return Response(successEnvelope(result))


class NotificationUnreadCountView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        result = container.unreadCountUseCase().execute(
            UnreadCountQuery(
                tenantId=_actorTenantId(request), recipientId=_actorUserId(request)
            )
        )
        return Response(successEnvelope(result))


class NotificationCancelView(APIView):
    """§40 admin cancel (pre-delivery only)."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("notification.send")]

    def post(self, request: Request, notificationId: str) -> Response:
        result = container.cancelNotificationService().execute(
            CancelNotificationCommand(
                notificationId=uuid.UUID(notificationId),
                actorId=_actorUserId(request),
            )
        )
        return Response(successEnvelope(result))


# -- preferences (§10/§40) -------------------------------------------------------------


class PreferenceListView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        result = container.getPreferencesService().execute(
            GetPreferencesQuery(
                tenantId=_actorTenantId(request), userId=_actorUserId(request)
            )
        )
        return Response(
            successEnvelope(
                {
                    "preferences": [dtoAsDict(item) for item in result["preferences"]],
                    "levels": result["levels"],
                    "channels": result["channels"],
                }
            )
        )

    def put(self, request: Request) -> Response:
        preferences = request.data.get("preferences", []) or []
        rows = [
            {
                "level": str(row.get("level", "")),
                "channel": str(row.get("channel", "")),
                "category": str(row.get("category", "") or ""),
                "notificationType": str(row.get("notificationType", "") or ""),
                "enabled": bool(row.get("enabled", True)),
                "quietHoursStart": str(row.get("quietHoursStart", "") or ""),
                "quietHoursEnd": str(row.get("quietHoursEnd", "") or ""),
            }
            for row in preferences
        ]
        result = container.updatePreferencesService().execute(
            UpdatePreferencesCommand(
                tenantId=_actorTenantId(request),
                userId=_actorUserId(request),
                preferences=tuple(rows),
            )
        )
        return Response(successEnvelope([dtoAsDict(item) for item in result]))


# -- devices (§15/§40) -------------------------------------------------------------------


class DeviceListView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        result = container.listDevicesService().execute(
            ListDevicesQuery(
                tenantId=_actorTenantId(request),
                userId=_actorUserId(request),
                activeOnly=str(request.query_params.get("active", "")).lower()
                in ("1", "true", "yes"),
            )
        )
        return Response(successEnvelope([dtoAsDict(item) for item in result]))

    def post(self, request: Request) -> Response:
        dto = container.registerDeviceService().execute(
            RegisterDeviceCommand(
                tenantId=_actorTenantId(request),
                userId=_actorUserId(request),
                platform=str(request.data.get("platform", "")),
                deviceIdentifier=str(request.data.get("deviceIdentifier", "")),
                pushToken=str(request.data.get("pushToken", "")),
                provider=str(request.data.get("provider", "FCM") or "FCM"),
            )
        )
        return Response(successEnvelope(dtoAsDict(dto)), status=201)


class DeviceDetailView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, deviceId: str) -> Response:
        result = container.revokeDeviceService().execute(
            RevokeDeviceCommand(
                deviceId=uuid.UUID(deviceId), userId=_actorUserId(request)
            )
        )
        return Response(successEnvelope(result))


# -- administration (§40 admin APIs) ------------------------------------------------------


class AdminSendView(APIView):
    """§40 send surface for systems/integrations (§7 event flow preferred)."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("notification.send")]

    def post(self, request: Request) -> Response:
        from apps.notifications.presentation.api.serializers import (
            notificationSerializers,
        )

        serializer = notificationSerializers.CreateNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        recipientValue = data.get("recipientValue") or []
        if not isinstance(recipientValue, (list, tuple)):
            recipientValue = [recipientValue]
        command = CreateNotificationCommand(
            tenantId=_actorTenantId(request),
            recipientSpec={"type": data["recipientType"], "value": recipientValue},
            eventType="api.send",
            eventId=str(data.get("eventId", "") or f"api:{uuid.uuid4()}"),
            notificationType=data["notificationType"],
            category=data["category"],
            priority=data["priority"],
            title=data["title"],
            body=data.get("body", ""),
            sourceType=data.get("sourceType", "") or "API",
            sourceId=data.get("sourceId", ""),
            data=dict(data.get("data") or {}, actionUrl=data.get("actionUrl", "")),
            templateKey=data.get("templateKey", ""),
            actionUrl=data.get("actionUrl", ""),
            ackRequired=bool(data.get("ackRequired", False)),
            channels=tuple(data.get("channels") or ()),
            expiresAt=data.get("expiresAt"),
            correlationId=_correlationId(),
            actorId=_actorUserId(request),
        )
        outcome = container.createNotificationService().execute(command)
        return Response(
            successEnvelope(
                {
                    "notifications": [dtoAsDict(item) for item in outcome.notifications],
                    "duplicates": outcome.duplicates,
                    "aggregatedToDigest": outcome.aggregatedToDigest,
                }
            ),
            status=201,
        )


class AdminScheduleListView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("notification.send")]

    def get(self, request: Request) -> Response:
        items = container.listSchedulesService().execute(
            ListSchedulesQuery(tenantId=_actorTenantId(request))
        )
        return Response(successEnvelope([dtoAsDict(item) for item in items]))

    def post(self, request: Request) -> Response:
        from apps.notifications.presentation.api.serializers import (
            notificationSerializers,
        )

        serializer = notificationSerializers.ScheduleNotificationSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        recipientValue = data.get("recipientValue") or []
        if not isinstance(recipientValue, (list, tuple)):
            recipientValue = [recipientValue]
        dto = container.scheduleNotificationService().execute(
            ScheduleNotificationCommand(
                tenantId=_actorTenantId(request),
                kind=data["kind"],
                recipientSpec={"type": data["recipientType"], "value": recipientValue},
                notificationType=data["notificationType"],
                category=data["category"],
                priority=data["priority"],
                title=data["title"],
                body=data.get("body", ""),
                scheduledAt=data.get("scheduledAt"),
                recurEverySeconds=int(data.get("recurEverySeconds", 0) or 0),
                delaySeconds=int(data.get("delaySeconds", 0) or 0),
                payload=dict(data.get("payload") or {}),
                correlationId=_correlationId(),
                actorId=_actorUserId(request),
            )
        )
        return Response(successEnvelope(dtoAsDict(dto)), status=201)


class AdminScheduleDetailView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("notification.send")]

    def delete(self, request: Request, scheduleId: str) -> Response:
        result = container.cancelScheduleService().execute(
            CancelScheduleCommand(scheduleId=uuid.UUID(scheduleId))
        )
        return Response(successEnvelope(result))


class AdminTemplateListView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("notification.manage")]

    def get(self, request: Request) -> Response:
        if request.query_params.get("templateKey"):
            items = container.listTemplatesService().execute(
                ListTemplateVersionsQuery(
                    tenantId=_actorTenantId(request),
                    templateKey=str(request.query_params["templateKey"]),
                    language=str(request.query_params.get("language", "")),
                    channel=str(request.query_params.get("channel", "")),
                )
            )
        else:
            items = container.listTemplatesService().execute(
                ListTemplatesQuery(tenantId=_actorTenantId(request))
            )
        return Response(successEnvelope([dtoAsDict(item) for item in items]))

    def post(self, request: Request) -> Response:
        from apps.notifications.presentation.api.serializers import (
            notificationSerializers,
        )

        serializer = notificationSerializers.SaveTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.saveTemplateService().execute(
            SaveTemplateCommand(
                tenantId=_actorTenantId(request),
                templateKey=data["templateKey"],
                language=data["language"],
                channel=data["channel"],
                titleTemplate=data["title"],
                subjectTemplate=data.get("subject", ""),
                bodyTemplate=data.get("body", ""),
                actorId=_actorUserId(request),
            )
        )
        return Response(successEnvelope(dtoAsDict(dto)), status=201)


class AdminTemplateDetailView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("notification.manage")]

    def delete(self, request: Request, templateId: str) -> Response:
        result = container.deactivateTemplateService().execute(
            DeactivateTemplateCommand(templateId=uuid.UUID(templateId))
        )
        return Response(successEnvelope(result))


class AdminPolicyListView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("notification.manage")]

    def get(self, request: Request) -> Response:
        items = container.listPoliciesService().execute(
            ListPoliciesQuery(tenantId=_actorTenantId(request))
        )
        return Response(successEnvelope([dtoAsDict(item) for item in items]))

    def post(self, request: Request) -> Response:
        from apps.notifications.presentation.api.serializers import (
            notificationSerializers,
        )

        serializer = notificationSerializers.SavePolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.savePolicyService().execute(
            SavePolicyCommand(
                tenantId=_actorTenantId(request),
                policyKey=data["policyKey"],
                matchType=data["matchType"],
                matchValue=data["matchValue"],
                channels=tuple(data.get("channels") or ()),
                priority=data.get("priority", "NORMAL"),
                templateKey=data.get("templateKey", ""),
                maxRetries=int(data.get("maxRetries", 3) or 3),
                cooldownSeconds=int(data.get("cooldownSeconds", 60) or 60),
                digestKind=data.get("digestKind", ""),
                allowPreferenceBypass=bool(data.get("allowPreferenceBypass", False)),
                escalationStages=tuple(data.get("escalationStages") or ()),
                actorId=_actorUserId(request),
            )
        )
        return Response(successEnvelope(dtoAsDict(dto)), status=201)


class AdminPolicyDetailView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("notification.manage")]

    def delete(self, request: Request, policyId: str) -> Response:
        result = container.deletePolicyService().execute(
            DeletePolicyCommand(policyId=uuid.UUID(policyId))
        )
        return Response(successEnvelope(result))


class AdminChannelListView(APIView):
    """§40 'Manage Channels' — catalog + provider failover status (§48)."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("notification.manage")]

    def get(self, request: Request) -> Response:
        registry = container.channelRegistry()
        return Response(
            successEnvelope(
                {
                    "channels": registry.channelStatus(),
                    "available": registry.availableChannels(),
                }
            )
        )


class AdminTenantRuleListView(APIView):
    """§40 tenant notification configuration (§11 FORCED/DENIED rules)."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("notification.manage")]

    def get(self, request: Request) -> Response:
        items = container.listTenantRulesService().execute(
            ListTenantRulesQuery(tenantId=_actorTenantId(request))
        )
        return Response(successEnvelope([dtoAsDict(item) for item in items]))

    def post(self, request: Request) -> Response:
        from apps.notifications.presentation.api.serializers import (
            notificationSerializers,
        )

        serializer = notificationSerializers.SaveTenantRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.saveTenantRuleService().execute(
            SaveTenantRuleCommand(
                tenantId=_actorTenantId(request),
                effect=data["effect"],
                channel=data["channel"],
                category=data.get("category", ""),
                notificationType=data.get("notificationType", ""),
                actorId=_actorUserId(request),
            )
        )
        return Response(successEnvelope(dtoAsDict(dto)), status=201)


class AdminTenantRuleDetailView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("notification.manage")]

    def delete(self, request: Request, ruleId: str) -> Response:
        result = container.deleteTenantRuleService().execute(
            DeleteTenantRuleCommand(ruleId=uuid.UUID(ruleId))
        )
        return Response(successEnvelope(result))


class NotificationMetricsView(APIView):
    """§44 analytics feed for the future Analytics platform."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("notification.manage")]

    def get(self, request: Request) -> Response:
        from apps.notifications.infrastructure.container import container as roots
        from apps.notifications.infrastructure.metrics.notificationMetrics import (
            notificationMetrics,
        )

        totals = roots.notificationRepository().readAndAckCounts(
            _actorTenantId(request), _actorUserId(request)
        )
        channelUsage = roots.deliveryRepository().channelUsageCounts(
            _actorTenantId(request)
        )
        return Response(
            successEnvelope(
                notificationMetrics().snapshot(
                    totals=totals, channelUsage=channelUsage
                )
            )
        )


# -- OpenAPI registration (§24 platform docs) ---------------------------------------------


def registerNotificationEndpoints() -> None:
    specs = [
        EndpointSpec(
            method="GET",
            path="api/v1/notifications",
            summary="List the caller's notifications (§42 recovery read).",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/notifications/{notificationId}",
            summary="Notification detail with per-channel deliveries.",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/notifications/{notificationId}/read",
            summary="Mark one notification read (§26 read ≠ acknowledged).",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="DELETE",
            path="api/v1/notifications/{notificationId}/read",
            summary="Mark unread (blocked after acknowledgement).",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/notifications/read-bulk",
            summary="Bulk mark-read for client reconciliation.",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/notifications/{notificationId}/acknowledge",
            summary="Acknowledge (only when required).",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/notifications/{notificationId}/archive",
            summary="Archive (soft delete) own notification.",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/notifications/unread-count",
            summary="Unread badge count.",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/notifications/{notificationId}/cancel",
            summary="Cancel before delivery (§40 admin).",
            permission="notification.send",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/notifications/preferences",
            summary="Own notification preferences (§10).",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="PUT",
            path="api/v1/notifications/preferences",
            summary="Replace own preference set.",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/notifications/devices",
            summary="List registered push devices (§15).",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/notifications/devices",
            summary="Register/refresh a push device.",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="DELETE",
            path="api/v1/notifications/devices/{deviceId}",
            summary="Revoke a push device (immediate stop).",
            permission="authenticated",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/notifications/admin/send",
            summary="Create notifications for systems/integrations.",
            permission="notification.send",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/notifications/admin/schedules",
            summary="List schedules (§22).",
            permission="notification.send",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/notifications/admin/schedules",
            summary="Create schedule (IMMEDIATE/SCHEDULED/RECURRING/DELAYED/DIGEST).",
            permission="notification.send",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="DELETE",
            path="api/v1/notifications/admin/schedules/{scheduleId}",
            summary="Cancel a schedule.",
            permission="notification.send",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/notifications/admin/templates",
            summary="List templates/versions (§19).",
            permission="notification.manage",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/notifications/admin/templates",
            summary="Save template — next version (§18/§19).",
            permission="notification.manage",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="DELETE",
            path="api/v1/notifications/admin/templates/{templateId}",
            summary="Deactivate a template.",
            permission="notification.manage",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/notifications/admin/policies",
            summary="List policies (§8).",
            permission="notification.manage",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/notifications/admin/policies",
            summary="Upsert policy (config-driven behaviour).",
            permission="notification.manage",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="DELETE",
            path="api/v1/notifications/admin/policies/{policyId}",
            summary="Delete a policy.",
            permission="notification.manage",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/notifications/admin/channels",
            summary="Channel catalog + provider status (§12/§48).",
            permission="notification.manage",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/notifications/admin/tenant-rules",
            summary="Tenant FORCED/DENIED rules (§11).",
            permission="notification.manage",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/notifications/admin/tenant-rules",
            summary="Save a tenant rule (never weakens security).",
            permission="notification.manage",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="DELETE",
            path="api/v1/notifications/admin/tenant-rules/{ruleId}",
            summary="Delete a tenant rule.",
            permission="notification.manage",
            errorCodes=NOTIFICATION_ERRORS,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/notifications/admin/metrics",
            summary="Notification analytics snapshot (§44).",
            permission="notification.manage",
            errorCodes=NOTIFICATION_ERRORS,
        ),
    ]
    for spec in specs:
        registerEndpoint(spec)


registerNotificationEndpoints()
