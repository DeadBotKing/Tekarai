"""Phase 12 REST views — multi-recipient broadcast notifications.

Thin transport (§12.29): authenticate → validate input → application service →
envelope. No business logic / ORM here (§12.43/§12.51). Surfaces:

* POST   /broadcasts                      create a multi-recipient notification
* GET    /broadcasts                      inbox for the calling user
* GET    /broadcasts/unread-count         unread count for the calling user
* POST   /broadcasts/{id}/read|unread|archive|dismiss   recipient read state
* GET    /deliveries                      operations: deliveries / dead-letter
* POST   /deliveries/{id}/retry           operations: manual retry
* POST   /rules                           define a WHEN/IF/THEN rule
* POST   /events                          idempotent event intake
"""

from __future__ import annotations

from rest_framework import serializers as drf_serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.application.commands.phase12Commands import (
    CreateBroadcastCommand,
    DefineRuleCommand,
    IngestEventCommand,
    ListBroadcastsQuery,
    ListDeliveriesQuery,
    RecipientStateCommand,
    RetryDeliveryCommand,
    UnreadCountQuery,
)
from apps.notifications.infrastructure import container as c
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


def _notificationDto(n: object) -> dict:
    from apps.notifications.application.services.phase12Services import _actor  # noqa: PLC0415

    viewerId, _tenant = _actor()
    recipient = n.recipientFor(viewerId)
    return {
        "id": str(n.id),
        "type": n.notificationType,
        "title": n.title,
        "body": n.body,
        "priority": n.priority,
        "severity": n.severity,
        "sourceType": n.sourceType,
        "sourceId": n.sourceId,
        "deepLink": n.deepLink,
        "state": recipient.state if recipient else "UNREAD",
        "createdAt": n.createdAt.isoformat() if n.createdAt else None,
    }


# -- serializers (input validation only, §12.49) ------------------------------


class CreateBroadcastSerializer(drf_serializers.Serializer):
    notificationType = drf_serializers.CharField(max_length=120)
    title = drf_serializers.CharField(max_length=300)
    body = drf_serializers.CharField(required=False, allow_blank=True, default="")
    recipientIds = drf_serializers.ListField(
        child=drf_serializers.CharField(), allow_empty=False
    )
    priority = drf_serializers.ChoiceField(
        choices=["LOW", "NORMAL", "HIGH", "URGENT", "CRITICAL"], default="NORMAL"
    )
    severity = drf_serializers.ChoiceField(
        choices=["INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO"
    )
    sourceType = drf_serializers.CharField(required=False, allow_blank=True, default="")
    sourceId = drf_serializers.CharField(required=False, allow_blank=True, default="")
    deepLink = drf_serializers.CharField(required=False, allow_blank=True, default="")
    language = drf_serializers.CharField(required=False, allow_blank=True, default="")
    metadata = drf_serializers.DictField(required=False, default=dict)
    idempotencyKey = drf_serializers.CharField(required=False, allow_blank=True, default="")
    correlationId = drf_serializers.CharField(required=False, allow_blank=True, default="")


class DefineRuleSerializer(drf_serializers.Serializer):
    name = drf_serializers.CharField(max_length=160)
    eventType = drf_serializers.CharField(max_length=120)
    condition = drf_serializers.DictField(required=False, default=dict)
    recipientStrategy = drf_serializers.ChoiceField(
        choices=["TARGET", "ASSIGNEE", "MANAGER", "ROLE"], default="TARGET"
    )
    channels = drf_serializers.ListField(
        child=drf_serializers.CharField(), required=False, default=list
    )
    priority = drf_serializers.ChoiceField(
        choices=["LOW", "NORMAL", "HIGH", "URGENT", "CRITICAL"], default="NORMAL"
    )
    templateKey = drf_serializers.CharField(required=False, allow_blank=True, default="")


class IngestEventSerializer(drf_serializers.Serializer):
    eventId = drf_serializers.CharField(max_length=80)
    eventType = drf_serializers.CharField(max_length=120)
    payload = drf_serializers.DictField(required=False, default=dict)


# -- broadcast (§12.3/§12.7/§12.8) --------------------------------------------


class BroadcastListView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = CreateBroadcastSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        notification = c.createBroadcastService().execute(
            CreateBroadcastCommand(
                notificationType=data["notificationType"],
                title=data["title"],
                recipientIds=tuple(data["recipientIds"]),
                body=data.get("body", ""),
                priority=data.get("priority", "NORMAL"),
                severity=data.get("severity", "INFO"),
                sourceType=data.get("sourceType", ""),
                sourceId=data.get("sourceId", ""),
                deepLink=data.get("deepLink", ""),
                language=data.get("language", ""),
                metadata=data.get("metadata", {}),
                idempotencyKey=data.get("idempotencyKey", ""),
                correlationId=data.get("correlationId", ""),
            )
        )
        # fan out channel deliveries (§12.40 — QUEUED, non-blocking)
        c.deliveryDispatchService().fanOut(notification)
        return Response(successEnvelope(_notificationDto(notification)), status=201)

    def get(self, request: Request) -> Response:
        unreadOnly = str(request.query_params.get("unreadOnly", "")).lower() in ("1", "true")
        limit = int(request.query_params.get("limit", "50"))
        dtos = c.broadcastQueryService().execute(
            ListBroadcastsQuery(unreadOnly=unreadOnly, limit=limit)
        )
        return Response(successEnvelope(dtos))


class BroadcastUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        result = c.broadcastQueryService().execute(UnreadCountQuery())
        return Response(successEnvelope(result))


class RecipientStateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, notificationId: str, action: str) -> Response:
        recipient = c.recipientStateService().execute(
            RecipientStateCommand(notificationId=notificationId, action=action)
        )
        return Response(
            successEnvelope(
                {"notificationId": notificationId, "state": recipient.state}
            )
        )


# -- deliveries / dead-letter (§12.14-§12.18) ---------------------------------


class DeliveryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        deadLetterOnly = str(
            request.query_params.get("deadLetterOnly", "")
        ).lower() in ("1", "true")
        notificationId = request.query_params.get("notificationId", "")
        dtos = c.deliveryQueryService().execute(
            ListDeliveriesQuery(
                notificationId=notificationId,
                deadLetterOnly=deadLetterOnly,
                limit=int(request.query_params.get("limit", "100")),
            )
        )
        return Response(successEnvelope(dtos))


class DeliveryRetryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, deliveryId: str) -> Response:
        delivery = c.deliveryRetryService().execute(
            RetryDeliveryCommand(deliveryId=deliveryId)
        )
        return Response(
            successEnvelope(
                {"deliveryId": str(delivery.id), "status": delivery.status}
            )
        )


# -- rules (§12.24) -----------------------------------------------------------


class RuleListView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = DefineRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        rule = c.ruleDefinitionService().execute(
            DefineRuleCommand(
                name=data["name"],
                eventType=data["eventType"],
                condition=data.get("condition", {}),
                recipientStrategy=data.get("recipientStrategy", "TARGET"),
                channels=tuple(data.get("channels", [])),
                priority=data.get("priority", "NORMAL"),
                templateKey=data.get("templateKey", ""),
            )
        )
        return Response(
            successEnvelope(
                {
                    "id": str(rule.id),
                    "name": rule.name,
                    "eventType": rule.eventType,
                    "channels": list(rule.channels),
                    "priority": rule.priority,
                    "isActive": rule.isActive,
                }
            ),
            status=201,
        )


# -- event intake (§12.23/§12.38) ---------------------------------------------


class EventIntakeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = IngestEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        created = c.eventIntakeService().execute(
            IngestEventCommand(
                eventId=data["eventId"],
                eventType=data["eventType"],
                payload=data.get("payload", {}),
            )
        )
        return Response(
            successEnvelope(
                {"created": len(created),
                 "notificationIds": [str(n.id) for n in created]}
            ),
            status=201,
        )
