"""WebSocket routing for the notification gateway (§41)."""

from __future__ import annotations

from django.urls import path

from apps.notifications.presentation.ws.notificationsConsumer import (
    NotificationsConsumer,
)

websocketUrlPatterns = [
    path("ws/notifications/", NotificationsConsumer.as_asgi()),
]
