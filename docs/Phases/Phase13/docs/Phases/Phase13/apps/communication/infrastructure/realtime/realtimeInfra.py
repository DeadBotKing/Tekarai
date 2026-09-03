"""Ephemeral + realtime infrastructure (Phase 08 §7, §8, §11, §12, §29).

Redis is the production backing store; a process-local fallback keeps the
platform fully functional (and testable) without a Redis server.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from apps.sharedKernel.domain.events import DomainEvent

logger = logging.getLogger(__name__)

try:  # production: Channels layer backed by Redis
    from channels.layers import get_channel_layer
    from channels_redis.core import RedisChannelLayer  # noqa: F401

    _CHANNELS_AVAILABLE = True
except Exception:  # pragma: no cover — channels not installed yet
    _CHANNELS_AVAILABLE = False


# ---------------------------------------------------------------------------
# §7 presence
# ---------------------------------------------------------------------------


class RedisPresenceRepository:
    """Presence with TTL heartbeats (§7). SQL is never the source of truth
    for online state; it only keeps audit/history."""

    def __init__(self, redisClient: Any | None = None) -> None:
        self.redis = redisClient
        self.fallback: dict[tuple[uuid.UUID, uuid.UUID], tuple[str, datetime]] = {}

    def _key(self, tenantId: uuid.UUID, userId: uuid.UUID) -> str:
        return f"tekarai:presence:{tenantId}:{userId}"

    def set(
        self,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        status: str,
        ttlSeconds: int,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(tz=timezone.utc)
        if self.redis is not None:
            self.redis.set(self._key(tenantId, userId), status, ex=ttlSeconds)
        else:
            self.fallback[(tenantId, userId)] = (
                status,
                now + timedelta(seconds=ttlSeconds),
            )

    def get(
        self, tenantId: uuid.UUID, userId: uuid.UUID
    ) -> str:
        if self.redis is not None:
            value = self.redis.get(self._key(tenantId, userId))
            if isinstance(value, bytes):
                return value.decode()
            return value or "OFFLINE"
        entry = self.fallback.get((tenantId, userId))
        if entry is None:
            return "OFFLINE"
        status, expiresAt = entry
        if datetime.now(tz=timezone.utc) > expiresAt:
            self.fallback.pop((tenantId, userId), None)
            return "OFFLINE"
        return status

    def getMany(
        self, tenantId: uuid.UUID, userIds: list[uuid.UUID]
    ) -> dict[str, str]:
        return {str(userId): self.get(tenantId, userId) for userId in userIds}


# ---------------------------------------------------------------------------
# §8/§30 realtime broadcaster
# ---------------------------------------------------------------------------


class ChannelsRealtimeBroadcaster:
    """Pushes events through the Channels layer to WS group members.

    Use cases are synchronous but often run inside worker threads
    (``database_sync_to_async``); channel layers are event-loop bound. The
    broadcaster therefore remembers the server loop (``bindLoop`` — done by
    the WS gateway on startup) and hops threads with
    ``run_coroutine_threadsafe``. In pure-WSGI processes it falls back to
    ``async_to_sync`` (works with the Redis layer).
    """

    def __init__(self) -> None:
        self.layer = get_channel_layer() if _CHANNELS_AVAILABLE else None
        self.localLog: list[dict] = []  # test inspection when no layer exists
        self._loop: asyncio.AbstractEventLoop | None = None

    def bindLoop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def _asend(self, group: str, message: dict) -> None:
        await self.layer.group_send(group, message)

    def _send(self, group: str, event: dict) -> None:
        self.localLog.append({"group": group, **event})
        if self.layer is None:
            return
        # the channel-layer control key must not clash with the payload's
        # own "type" (e.g. typing.started) — nest the event explicitly.
        message = {"type": "communication.event", "event": event}
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

    def toUser(self, userId: uuid.UUID, event: dict) -> None:
        self._send(f"user.{userId}", event)

    def toConversation(self, conversationId: uuid.UUID, event: dict) -> None:
        self._send(f"conversation.{conversationId}", event)

    def toMeeting(self, meetingId: uuid.UUID, event: dict) -> None:
        self._send(f"meeting.{meetingId}", event)

    def toCall(self, callId: uuid.UUID, event: dict) -> None:
        self._send(f"call.{callId}", event)


# ---------------------------------------------------------------------------
# §12 media router (SFU adapter)
# ---------------------------------------------------------------------------


class NoopMediaRouter:
    """Peer-to-peer default. In production this adapter provisions an SFU
    room (e.g. LiveKit/mediasoup); the domain stays vendor-free (§12)."""

    def __init__(self, sfuClient: Any | None = None) -> None:
        self.sfu = sfuClient

    def openSession(self, callId: str, mediaType: str) -> str:
        if self.sfu is not None and hasattr(self.sfu, "createRoom"):
            return str(self.sfu.createRoom(callId, mediaType))
        return ""  # empty = direct peer-to-peer, no routing needed

    def joinSession(self, sessionRef: str, userId: str) -> None:
        if self.sfu is not None and sessionRef:
            self.sfu.addParticipant(sessionRef, userId)

    def leaveSession(self, sessionRef: str, userId: str) -> None:
        if self.sfu is not None and sessionRef:
            self.sfu.removeParticipant(sessionRef, userId)


# ---------------------------------------------------------------------------
# §29 outbox dispatcher
# ---------------------------------------------------------------------------


class OutboxDispatcher:
    """Publishes pending integration events after commit (§28/§29).

    A failing dispatcher leaves rows PENDING — they are retried on the next
    tick; nothing is ever published before its transaction commits."""

    def __init__(self, outboxRepository: Any, eventDispatcher: Any, clock: Any) -> None:
        self.outboxRepository = outboxRepository
        self.eventDispatcher = eventDispatcher
        self.clock = clock

    def dispatchDue(self, *, limit: int = 100) -> dict[str, int]:
        published, failed = 0, 0
        from apps.communication.infrastructure.metrics.communicationMetrics import (
            communicationMetrics,
        )

        metrics = communicationMetrics()
        for row in self.outboxRepository.pending(limit=limit):
            startedAt = datetime.now(tz=timezone.utc)
            try:
                self.eventDispatcher.dispatch(
                    DomainEvent(
                        name=row.eventType,
                        occurredAt=row.occurredAt,
                        tenantId=row.tenantId,
                        payload=row.payload,
                    )
                )
                self.outboxRepository.markPublished(row.id, self.clock.nowUtc())
                metrics.observeEventProcessing(
                    (datetime.now(tz=timezone.utc) - startedAt).total_seconds()
                )  # §39 eventProcessingLatency
                published += 1
            except Exception:  # noqa: BLE001 — §38 keep row pending on failure
                logger.exception("Outbox dispatch failed for %s", row.id)
                failed += 1
        return {"published": published, "failed": failed}
