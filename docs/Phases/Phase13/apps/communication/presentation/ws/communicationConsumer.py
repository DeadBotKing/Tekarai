"""Communication WebSocket gateway (Phase 08 §8, §30).

The consumer is deliberately THIN (§8): authenticate → resolve tenant →
validate transport envelope → call an application service → respond.
Zero business rules live here.

Live traffic on this socket (§30): messages, typing, presence, signaling,
read receipts, live meeting events. Everything else stays REST.
"""

from __future__ import annotations

import logging
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.sharedKernel.application.requestContext import (
    RequestContext,
    bindContext,
    resetContext,
)

logger = logging.getLogger(__name__)


class CommunicationConsumer(AsyncJsonWebsocketConsumer):
    """One socket per connected user; group membership per subscription."""

    async def connect(self) -> None:
        principal = await self.authenticate()
        if principal is None:
            await self.close(code=4401)  # unauthenticated
            return
        self.userId = principal.userId
        self.tenantId = principal.tenantId
        self.sessionId = principal.sessionId
        self.groups: set[str] = set()
        await self.accept()
        import asyncio as _asyncio

        from apps.communication.infrastructure.metrics.communicationMetrics import (
            communicationMetrics,
        )
        from apps.communication.infrastructure.realtime.realtimeInfra import (
            ChannelsRealtimeBroadcaster,
        )

        if isinstance(self.realtimeBroadcastersSingleton(), ChannelsRealtimeBroadcaster):
            self.realtimeBroadcastersSingleton().bindLoop(_asyncio.get_running_loop())
        communicationMetrics().increment("activeConnections")  # §39
        await self.channel_layer.group_add(f"user.{self.userId}", self.channel_name)
        self.groups.add(f"user.{self.userId}")
        # §7 — first heartbeat marks the user online
        relay = await self.relay()
        relay.markOnline(self.tenantId, self.userId, await self.nowUtc())

    async def disconnect(self, code: int) -> None:
        from apps.communication.infrastructure.metrics.communicationMetrics import (
            communicationMetrics,
        )

        communicationMetrics().decrement("activeConnections")  # §39
        relay = await self.relay()
        relay.markOffline(getattr(self, "tenantId", uuid.UUID(int=0)),
                          getattr(self, "userId", uuid.UUID(int=0)),
                          await self.nowUtc())
        for group in getattr(self, "groups", set()):
            try:
                await self.channel_layer.group_discard(group, self.channel_name)
            except TypeError:  # pragma: no cover — layer without discard
                pass

    # -- §8: authentication only ------------------------------------------------

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

    # -- §8: transport validation + delegation ----------------------------------

    async def receive_json(self, content: dict, **kwargs) -> None:
        action = str(content.get("type", "") or "")
        payload = content.get("payload") or {}
        context = RequestContext(
            actorId=str(self.userId),
            actorTenantId=str(self.tenantId),
            tenantId=str(self.tenantId),
            sessionId=str(self.sessionId) if self.sessionId else "",
        )
        token = bindContext(context)
        try:
            handler = self.HANDLERS.get(action)
            if handler is None:
                await self.send_json(
                    {"type": "error", "code": "SYS_VALIDATION_FAILED",
                     "message": f"Unknown action '{action}'."}
                )
                return
            await handler(self, payload)
        except Exception as exc:  # noqa: BLE001 — transport error, never a crash
            logger.exception("WS handler failed for %s", action)
            from apps.communication.infrastructure.metrics.communicationMetrics import (
                communicationMetrics,
            )

            communicationMetrics().increment("websocketErrors")  # §39
            await self.send_json(
                {"type": "error", "code": "SYS_INTERNAL_ERROR", "message": str(exc)}
            )
        finally:
            resetContext(token)

    # -- handlers: each maps 1:1 to an application service (§8) ------------------

    async def handleSubscribe(self, payload: dict) -> None:
        """Join the live group of a conversation (membership-checked)."""
        conversationId = uuid.UUID(str(payload.get("conversationId", "")))
        relay = await self.relay()
        member = await database_sync_to_async(relay.activeMembership)(
            conversationId, self.userId
        )
        if not member:
            await self.send_json(
                {"type": "error", "code": "PERM_PERMISSION_DENIED",
                 "message": "Not a participant of this conversation."}
            )
            return
        group = f"conversation.{conversationId}"
        await self.channel_layer.group_add(group, self.channel_name)
        self.groups.add(group)
        await self.send_json({"type": "subscribed", "conversationId": str(conversationId)})

    async def handleUnsubscribe(self, payload: dict) -> None:
        conversationId = str(payload.get("conversationId", ""))
        group = f"conversation.{conversationId}"
        await self.channel_layer.group_discard(group, self.channel_name)
        self.groups.discard(group)
        await self.send_json({"type": "unsubscribed", "conversationId": conversationId})

    async def handleTyping(self, payload: dict) -> None:
        """§31 — ephemeral relay, no SQL writes at all."""
        conversationId = uuid.UUID(str(payload.get("conversationId", "")))
        relay = await self.relay()
        ok = await database_sync_to_async(relay.relayTyping)(
            tenantId=self.tenantId,
            userId=self.userId,
            conversationId=conversationId,
            isTyping=bool(payload.get("isTyping", True)),
        )
        if not ok:
            await self.send_json(
                {"type": "error", "code": "PERM_PERMISSION_DENIED",
                 "message": "Not a participant of this conversation."}
            )

    async def handlePresence(self, payload: dict) -> None:
        """§7 — presence heartbeat (status change)."""
        from apps.communication.application.commands.communicationCommands import (
            UpdatePresenceCommand,
        )
        from apps.communication.infrastructure import container

        status = str(payload.get("status", "ONLINE"))
        useCase = await self._useCase(container.updatePresenceUseCase)
        result = await useCase(UpdatePresenceCommand(status=status))
        await self.send_json({"type": "presence.ack", "result": result})

    async def handleSignal(self, payload: dict) -> None:
        """§11 — versioned signaling relay through the application layer."""
        from apps.communication.application.commands.communicationCommands import (
            RelaySignalCommand,
        )
        from apps.communication.infrastructure import container

        envelope = payload.get("envelope") or {}
        command = RelaySignalCommand(
            envelope=envelope,
            targetUserId=str(payload.get("targetUserId", "") or ""),
        )
        useCase = await self._useCase(container.relaySignalUseCase)
        result = await useCase(command)
        await self.send_json({"type": "signal.ack", "result": result})

    async def handleRead(self, payload: dict) -> None:
        """§32 — read receipts over the socket (bulk behind the scenes)."""
        from apps.communication.application.commands.communicationCommands import (
            MarkConversationReadCommand,
        )
        from apps.communication.infrastructure import container

        command = MarkConversationReadCommand(
            conversationId=str(payload.get("conversationId", "")),
            uptoMessageId=str(payload.get("uptoMessageId", "")),
        )
        useCase = await self._useCase(container.markConversationReadUseCase)
        result = await useCase(command)
        await self.send_json({"type": "read.ack", "result": result})

    async def handleSendMessage(self, payload: dict) -> None:
        """§30 — live message send (same use case as REST, §24 idempotent)."""
        from apps.communication.application.commands.communicationCommands import (
            SendMessageCommand,
        )
        from apps.communication.infrastructure import container

        command = SendMessageCommand(
            conversationId=str(payload.get("conversationId", "")),
            body=str(payload.get("body", "")),
            messageType=str(payload.get("messageType", "TEXT")),
            replyToId=str(payload.get("replyToId", "") or ""),
            clientRequestId=str(payload.get("clientRequestId", "") or ""),
            attachments=list(payload.get("attachments") or []),
        )
        useCase = await self._useCase(container.sendMessageUseCase)
        dto = await useCase(command)
        await self.send_json({"type": "message.sent", "message": dto})

    async def _useCase(self, factory):
        import dataclasses

        @database_sync_to_async
        def _run(command):
            result = factory().execute(command)
            if dataclasses.is_dataclass(result) and not isinstance(result, type):
                return dataclasses.asdict(result)
            return result

        async def runner(command):
            return await _run(command)

        return runner

    async def communication_event(self, event: dict) -> None:
        """Broadcast fan-out from ChannelsRealtimeBroadcaster."""
        await self.send_json(event.get("event", {}))

    # -- helpers -------------------------------------------------------------------

    async def relay(self):
        from apps.communication.infrastructure import container

        @database_sync_to_async
        def _build():
            return container.realtimeRelayService()

        return await _build()

    async def nowUtc(self):
        from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider

        @database_sync_to_async
        def _now():
            return sharedKernelProvider("clock")().nowUtc()

        return await _now()

    def realtimeBroadcastersSingleton(self):
        from apps.communication.infrastructure import container

        return container.broadcaster()

    HANDLERS = {
        "subscribe": handleSubscribe,
        "unsubscribe": handleUnsubscribe,
        "typing": handleTyping,
        "presence": handlePresence,
        "signal": handleSignal,
        "read": handleRead,
        "message.send": handleSendMessage,
    }
