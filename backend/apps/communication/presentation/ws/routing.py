"""WebSocket routing for the communication gateway (§8/§30)."""

from __future__ import annotations

from django.urls import path

from apps.communication.presentation.ws.communicationConsumer import (
    CommunicationConsumer,
)

websocketUrlPatterns = [
    path("ws/communication/", CommunicationConsumer.as_asgi()),
]
