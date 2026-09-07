"""Thin Phase 15 Notification Platform REST transport."""

from __future__ import annotations

import json

from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.application.commands.phase15Commands import (
    ProcessProviderWebhookCommand,
    RegisterPushSubscriptionCommand,
    RevokePushSubscriptionCommand,
    RunNotificationCleanupCommand,
    SaveProviderConfigurationCommand,
    SearchNotificationsQuery,
)
from apps.notifications.infrastructure import container
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated, actionPermission
from apps.sharedKernel.presentation.api.rateLimiting import enforceRateLimit
from apps.sharedKernel.presentation.api.response import successEnvelope


class SearchSerializer(serializers.Serializer):
    q = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    notificationType = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )
    status = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    readState = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    channel = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    dateFrom = serializers.DateTimeField(required=False, allow_null=True, default=None)
    dateTo = serializers.DateTimeField(required=False, allow_null=True, default=None)
    beforeId = serializers.UUIDField(required=False, allow_null=True, default=None)
    limit = serializers.IntegerField(min_value=1, max_value=200, default=50)


class PushSubscriptionSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=2000)
    publicKey = serializers.CharField(max_length=512)
    authSecret = serializers.CharField(max_length=512, write_only=True)
    expiresAt = serializers.DateTimeField(required=False, allow_null=True, default=None)


class ProviderConfigurationSerializer(serializers.Serializer):
    channel = serializers.CharField(max_length=16)
    provider = serializers.CharField(max_length=48)
    credentialRef = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    configuration = serializers.DictField(required=False, default=dict)
    isActive = serializers.BooleanField(default=True)


class ProviderWebhookSerializer(serializers.Serializer):
    eventId = serializers.CharField(max_length=120)
    providerMessageId = serializers.CharField(max_length=120)
    status = serializers.CharField(max_length=16)
    errorCode = serializers.CharField(max_length=48, required=False, allow_blank=True, default="")
    metadata = serializers.DictField(required=False, default=dict)


class CleanupSerializer(serializers.Serializer):
    retentionDays = serializers.IntegerField(min_value=1, max_value=36500, required=False)
    dryRun = serializers.BooleanField(default=True)


class NotificationSearchView(APIView):
    permission_classes = [IsAuthenticated]

    @enforceRateLimit("notification:search")
    def get(self, request: Request) -> Response:
        serializer = SearchSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.phase15SearchService().execute(
            SearchNotificationsQuery(
                query=data["q"],
                notificationType=data["notificationType"],
                status=data["status"],
                readState=data["readState"],
                channel=data["channel"],
                dateFrom=data["dateFrom"],
                dateTo=data["dateTo"],
                beforeId=str(data["beforeId"]) if data["beforeId"] else "",
                limit=data["limit"],
            )
        )
        return Response(successEnvelope({"items": list(result), "count": len(result)}))


class PushSubscriptionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        result = container.phase15PushSubscriptionService().execute(None)
        return Response(successEnvelope(list(result)))

    @enforceRateLimit("notification:device")
    def post(self, request: Request) -> Response:
        serializer = PushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.phase15PushSubscriptionService().execute(
            RegisterPushSubscriptionCommand(**serializer.validated_data)
        )
        return Response(successEnvelope(result), status=201)


class PushSubscriptionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, subscriptionId: str) -> Response:
        result = container.phase15PushSubscriptionService().execute(
            RevokePushSubscriptionCommand(subscriptionId=subscriptionId)
        )
        return Response(successEnvelope(result))


class ProviderWebhookView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @enforceRateLimit("notification:webhook")
    def post(self, request: Request, tenantId: str, provider: str) -> Response:
        rawBody = request.body
        try:
            parsed = json.loads(rawBody.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = None
        serializer = ProviderWebhookSerializer(data=parsed)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.phase15ProviderWebhookService().execute(
            ProcessProviderWebhookCommand(
                tenantId=tenantId,
                provider=provider,
                providerEventId=data["eventId"],
                providerMessageId=data["providerMessageId"],
                status=data["status"],
                timestamp=request.headers.get("X-Webhook-Timestamp", ""),
                signature=request.headers.get("X-Webhook-Signature", ""),
                rawBody=rawBody,
                errorCode=data["errorCode"],
                metadata=data["metadata"],
            )
        )
        return Response(successEnvelope(result))


class ProviderConfigurationView(APIView):
    permission_classes = [actionPermission("notification.manage")]

    def get(self, request: Request) -> Response:
        result = container.phase15ProviderConfigurationService().execute(None)
        return Response(successEnvelope(list(result)))

    @enforceRateLimit("notification:admin")
    def post(self, request: Request) -> Response:
        serializer = ProviderConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.phase15ProviderConfigurationService().execute(
            SaveProviderConfigurationCommand(**serializer.validated_data)
        )
        return Response(successEnvelope(result), status=201)


class NotificationCleanupView(APIView):
    permission_classes = [actionPermission("notification.manage")]

    @enforceRateLimit("notification:admin")
    def post(self, request: Request) -> Response:
        serializer = CleanupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.phase15CleanupService().execute(
            RunNotificationCleanupCommand(**serializer.validated_data)
        )
        return Response(successEnvelope(result))


__all__ = [
    "NotificationCleanupView",
    "NotificationSearchView",
    "ProviderConfigurationView",
    "ProviderWebhookView",
    "PushSubscriptionDetailView",
    "PushSubscriptionListView",
]
