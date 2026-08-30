"""§41 realtime — WebSocket push for connected recipients.

The DB stays the source of truth (§42); this broadcaster is an
optimization. Same loop-hopping technique as the communication
broadcaster so sync worker threads can push through Channels.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

try:  # production: channels layer present
    from channels.layers import get_channel_layer

    _CHANNELS_AVAILABLE = True
except Exception:  # pragma: no cover — channels not installed
    _CHANNELS_AVAILABLE = False


class ChannelsNotificationBroadcaster:
    """Pushes ``notification.event`` frames to ``user.{id}`` groups."""

    def __init__(self) -> None:
        self.layer = get_channel_layer() if _CHANNELS_AVAILABLE else None
        self.localLog: list[dict[str, Any]] = []  # test inspection without a layer
        self._loop: asyncio.AbstractEventLoop | None = None

    def bindLoop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def _asend(self, group: str, message: dict[str, Any]) -> None:
        await self.layer.group_send(group, message)

    def toUser(self, userId: uuid.UUID, event: dict[str, Any]) -> None:
        self._send(f"user.{userId}", event)

    def _send(self, group: str, event: dict[str, Any]) -> None:
        self.localLog.append({"group": group, "event": event})
        if self.layer is None:
            return
        message = {"type": "notification.event", "event": event}
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            self._loop = loop
            loop.create_task(self._asend(group, message))
            return
        bound = self._loop
        if bound is not None and not bound.is_closed():
            asyncio.run_coroutine_threadsafe(self._asend(group, message), bound)
            return
        from asgiref.sync import async_to_sync

        async_to_sync(self.layer.group_send)(group, message)
