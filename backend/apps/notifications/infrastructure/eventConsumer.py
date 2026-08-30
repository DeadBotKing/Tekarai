"""§30 outbox integration — the notification consumer.

Integration events published by other contexts (Phase 08 outbox →
InProcessEventDispatcher) reach the notification engine here. The route
table below is CONFIGURATION (§8): adding a source event needs no code
change in the engine, only a new row in ``NOTIFICATION_EVENT_ROUTES``
(overridable via settings).
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from apps.sharedKernel.domain.events import DomainEvent
from apps.sharedKernel.infrastructure.wiring import defaultEventDispatcher

logger = logging.getLogger(__name__)

#: §30/§8 — event → notification shape. recipientSpec.type may reference
#: a payload field with ``$payload.<field>`` indirection.
DEFAULT_EVENT_ROUTES: dict[str, dict[str, Any]] = {
    "CommunicationMeetingCreatedV1": {
        "notificationType": "meeting.invitation",
        "category": "MEETING",
        "priority": "HIGH",
        "templateKey": "meeting.invitation",
        "recipientSpec": {"type": "MEETING", "value": "$payload.meetingId"},
        "titleData": {"meetingId": "$payload.meetingId"},
        "sourceType": "COMMUNICATION",
    },
    "CommunicationMeetingStartedV1": {
        "notificationType": "meeting.started",
        "category": "MEETING",
        "priority": "NORMAL",
        "templateKey": "meeting.started",
        "recipientSpec": {"type": "MEETING", "value": "$payload.meetingId"},
        "sourceType": "COMMUNICATION",
    },
    "CommunicationMeetingCancelledV1": {
        "notificationType": "meeting.cancelled",
        "category": "MEETING",
        "priority": "NORMAL",
        "templateKey": "meeting.cancelled",
        "recipientSpec": {"type": "MEETING", "value": "$payload.meetingId"},
        "sourceType": "COMMUNICATION",
    },
    "CommunicationCallStartedV1": {
        "notificationType": "call.incoming",
        "category": "COMMUNICATION",
        "priority": "URGENT",
        "templateKey": "call.incoming",
        "recipientSpec": {"type": "CALL", "value": "$payload.callId"},
        "sourceType": "COMMUNICATION",
    },
    "CommunicationMessageCreatedV1": {
        "notificationType": "message.received",
        "category": "COMMUNICATION",
        "priority": "LOW",
        "templateKey": "message.received",
        "digestible": True,
        "recipientSpec": {"type": "CONVERSATION", "value": "$payload.conversationId"},
        "sourceType": "COMMUNICATION",
    },
    "CommunicationLetterCreatedV1": {
        "notificationType": "letter.created",
        "category": "DOCUMENT",
        "priority": "NORMAL",
        "templateKey": "letter.created",
        "recipientSpec": {"type": "TENANT_ADMIN"},
        "sourceType": "COMMUNICATION",
    },
    "CommunicationRecordingStartedV1": {
        "notificationType": "recording.started",
        "category": "MEETING",
        "priority": "LOW",
        "templateKey": "recording.started",
        "recipientSpec": {"type": "MEETING", "value": "$payload.meetingId"},
        "sourceType": "COMMUNICATION",
    },
    "CommunicationAISummaryGeneratedV1": {
        "notificationType": "ai.summary",
        "category": "AI",
        "priority": "LOW",
        "templateKey": "ai.summary",
        "recipientSpec": {"type": "MEETING", "value": "$payload.meetingId"},
        "sourceType": "COMMUNICATION",
    },
}


def _resolveToken(token: Any, payload: dict[str, Any]) -> Any:
    """``$payload.<field>`` indirection — routes stay data-only."""
    if isinstance(token, str) and token.startswith("$payload."):
        return payload.get(token.split("$payload.", 1)[1], "")
    return token


def _resolveSpec(spec: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    resolved = {}
    for key, value in spec.items():
        if isinstance(value, (list, tuple)):
            resolved[key] = [_resolveToken(item, payload) for item in value]
        else:
            resolved[key] = _resolveToken(value, payload)
    return resolved


def makeNotificationHandler(route: dict[str, Any]) -> Callable[[DomainEvent], None]:
    """Builds the §30 consumer for one routed event."""

    def handleNotificationEvent(event: DomainEvent) -> None:
        from apps.notifications.application.commands.notificationCommands import (
            CreateNotificationCommand,
        )
        from apps.notifications.infrastructure.container import container

        payload = dict(event.payload or {})
        command = CreateNotificationCommand(
            tenantId=event.tenantId,
            recipientSpec=_resolveSpec(route.get("recipientSpec", {}), payload),
            eventType=event.name,
            eventId=str(
                payload.get("eventId")
                or payload.get("messageId")
                or payload.get("meetingId")
                or payload.get("callId")
                or payload.get("letterId")
                or payload.get("recordingId")
                or f"{event.name}:{event.occurredAt.isoformat()}"
            ),
            notificationType=route["notificationType"],
            category=route["category"],
            priority=route.get("priority", "NORMAL"),
            title=route.get("title", route["notificationType"]),
            body=route.get("body", ""),
            sourceType=route.get("sourceType", event.name),
            sourceId=str(
                payload.get("sourceId")
                or payload.get("meetingId")
                or payload.get("callId")
                or payload.get("messageId")
                or payload.get("letterId")
                or ""
            ),
            data={
                "templateKey": route.get("templateKey", ""),
                "actionUrl": route.get("actionUrl", ""),
                **{key: value for key, value in payload.items()
                   if isinstance(value, (str, int, float, bool))},
            },
            templateKey=route.get("templateKey", ""),
            correlationId=event.correlationId,
            causationId=event.name,  # §46 tracing chain
        )
        try:
            container.createNotificationService().execute(command)
        except Exception:  # noqa: BLE001 — consumer must never break the dispatcher
            logger.exception(
                "Notification consumer failed",
                extra={"eventName": event.name, "tenantId": str(event.tenantId)},
            )

    return handleNotificationEvent


def notificationEventRoutes() -> dict[str, dict[str, Any]]:
    from django.conf import settings

    configured = getattr(settings, "NOTIFICATION_EVENT_ROUTES", None)
    if configured is not None:
        return dict(configured)
    return dict(DEFAULT_EVENT_ROUTES)


def registerNotificationSubscriptions() -> int:
    """Idempotent §30 wiring on the shared dispatcher."""
    dispatcher = defaultEventDispatcher()
    registered = 0
    for eventName, route in notificationEventRoutes().items():
        handler = makeNotificationHandler(route)
        handlerName = f"notifications.{eventName}"
        existing = dispatcher.handlers.get(eventName, [])
        if any(getattr(item, "__name__", "") == handlerName for item in existing):
            continue
        handler.__name__ = handlerName
        dispatcher.subscribe(eventName, handler)
        registered += 1
    return registered
