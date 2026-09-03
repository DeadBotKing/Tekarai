"""Notification WebSocket gateway (Phase 09 §41/§42).

Thin consumer: authenticate → join the user's group → push
``notification.event`` frames. The DB remains the source of truth; a
reconnecting client recovers via REST (§42), so nothing here is queued.
"""

from __future__ import annotations

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class NotificationsConsumer(AsyncJsonWebsocketConsumer):
    """One socket per connected user; frames pushed to ``user.{id}``."""

    async def connect(self) -> None:
        principal = await self.authenticate()
        if principal is None:
            await self.close(code=4401)  # unauthenticated
            return
        self.userId = principal.userId
        self.tenantId = principal.tenantId
        await self.accept()
        await self.channel_layer.group_add(f"user.{self.userId}", self.channel_name)
        from apps.notifications.infrastructure.metrics.notificationMetrics import (
            notificationMetrics,
        )
        from apps.notifications.infrastructure.realtime.notificationRealtime import (
            ChannelsNotificationBroadcaster,
        )
        import asyncio

        broadcasterSingleton = notificationRealtimeSingleton()
        if isinstance(broadcasterSingleton, ChannelsNotificationBroadcaster):
            broadcasterSingleton.bindLoop(asyncio.get_running_loop())
        notificationMetrics().increment("activeNotificationConnections")
        await self.send_json(
            {
                "type": "notification.ready",
                "event": {"userId": str(self.userId), "heartbeatSeconds": 30},
            }
        )

    async def disconnect(self, code: int) -> None:
        try:
            await self.channel_layer.group_discard(
                f"user.{self.userId}", self.channel_name
            )
        except AttributeError:
            pass  # connect() never completed
        from apps.notifications.infrastructure.metrics.notificationMetrics import (
            notificationMetrics,
        )

        notificationMetrics().increment("activeNotificationConnections", -1)

    async def authenticate(self):
        token = ""
        for key, value in self.scope.get("headers", []):
            if key == b"authorization":
                token = value.decode().removeprefix("Bearer ").strip()
        if not token and "token=" in self.scope.get("query_string", b"").decode():
            token = self.scope["query_string"].decode().split("token=")[-1].split("&")[0]
        if not token:
            return None

        from apps.identity.application.services import principalDirectory

        @database_sync_to_async
        def _verify():
            return principalDirectory.verifySessionToken(token)

        return await _verify()

    # -- group_send handler (matches the broadcaster envelope) ----------------

    async def notification_event(self, message: dict) -> None:
        await self.send_json(
            {"type": "notification.event", "event": message.get("event", {})}
        )

    async def receive_json(self, content: dict, **kwargs) -> None:
        """Minimal client→server surface: heartbeat + reconcile hint."""
        action = str(content.get("type", "") or "")
        if action == "heartbeat":
            await self.send_json({"type": "heartbeat.ok"})
            return
        if action == "reconcile":
            unread = await self._unreadCount()
            await self.send_json(
                {"type": "reconcile.hint", "event": {"unreadCount": unread,
                                                     "source": "rest:/api/v1/notifications"}}
            )
            return
        await self.send_json(
            {
                "type": "error",
                "code": "SYS_VALIDATION_FAILED",
                "message": f"Unknown action '{action}'.",
            }
        )

    async def _unreadCount(self) -> int:
        from apps.notifications.infrastructure.container import container

        @database_sync_to_async
        def _count() -> int:
            return container.notificationRepository().unreadCount(
                self.tenantId, self.userId
            )

        return await _count()


def notificationRealtimeSingleton():
    from apps.notifications.infrastructure.realtime.notificationRealtime import (
        ChannelsNotificationBroadcaster,
    )

    return _singleton()


_singletonInstance = None


def _singleton():
    global _singletonInstance
    if _singletonInstance is None:
        from apps.notifications.infrastructure.container import realtime

        _singletonInstance = realtime()
    return _singletonInstance
