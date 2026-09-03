"""Phase 8 WebSocket gateway tests (§8 thin consumer, §30 live transport).

Runs the REAL ASGI application (Channels communicator + InMemory layer):
connect (auth), subscribe (membership check), typing relay, read receipts,
message send, signaling relay and the unauthenticated rejection.
"""

from __future__ import annotations

import uuid

from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from config.asgi import application

from apps.identity.infrastructure.models import SessionModel, UserModel
from apps.communication.infrastructure.models import ConversationModel, MessageModel
from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from apps.tenancy.infrastructure.models import TenantModel
from apps.communication.application.commands.communicationCommands import (
    CreateGroupConversationCommand,
    SendMessageCommand,
)
from apps.communication.application.useCases.conversationUseCases import (
    CreateGroupConversationUseCase,
)
from apps.communication.infrastructure import container
from tests.support.phase8Helpers import ensureUser, grantCommAdmin
from tests.support.phase6Helpers import seedPlatform

WS = "/ws/communication/"


def _sessionTokenFor(userId, tenantId) -> str:
    """Mint a session + access token exactly like a login would (§7)."""
    from datetime import UTC, datetime, timedelta

    from apps.identity.infrastructure.services.jwtService import defaultJwtService

    sessionId = uuid.uuid4()
    SessionModel.objects.create(
        id=sessionId,
        userId=userId,
        tenantId=tenantId,
        refreshTokenHash=uuid.uuid4().hex,
        expiresAt=datetime.now(UTC) + timedelta(hours=1),
    )
    token, _ttl = defaultJwtService().issueAccessToken(
        userId=userId, tenantId=tenantId, sessionId=sessionId
    )
    return token


class WebsocketGatewayTests(TransactionTestCase):
    def setUp(self) -> None:
        super().setUp()
        seedPlatform()
        self.tenant = TenantModel.objects.get(code="platform")
        self.alice = ensureUser(self.tenant, "ws-alice")
        self.bob = ensureUser(self.tenant, "ws-bob")
        grantCommAdmin(self.tenant, self.alice)
        with requestScope(
            RequestContext(
                actorId=str(self.alice.id),
                tenantId=str(self.tenant.id),
                actorTenantId=str(self.tenant.id),
            )
        ):
            self.conversation = CreateGroupConversationUseCase(
                conversationRepository=container.conversationRepository(),
                participantRepository=container.participantRepository(),
                userDirectory=container.userDirectory(),
                **container.commPorts(),
            ).execute(
                CreateGroupConversationCommand(
                    name="اتاق WS", memberIds=[str(self.bob.id)]
                )
            )
            self.message = container.sendMessageUseCase().execute(
                SendMessageCommand(
                    conversationId=str(self.conversation.id), body="پیام پایه"
                )
            )

    async def connect(self, user) -> WebsocketCommunicator:
        token = await self.arun(_sessionTokenFor, user.id, self.tenant.id)
        # browsers always send Origin; Channels' origin validator requires it
        communicator = WebsocketCommunicator(
            application,
            f"{WS}?token={token}",
            headers=[(b"origin", b"http://testserver")],
        )
        connected, _ = await communicator.connect()
        assert connected
        return communicator

    @staticmethod
    async def arun(fn, *args):
        from asgiref.sync import sync_to_async

        return await sync_to_async(fn)(*args)

    @staticmethod
    async def receiveUntil(communicator, expectedType: str, tries: int = 10) -> dict:
        """Subscribed sockets also receive group broadcasts; wait for one
        specific frame type."""
        import asyncio

        for _ in range(tries):
            frame = await asyncio.wait_for(
                communicator.receive_json_from(), timeout=5
            )
            if frame.get("type") == expectedType:
                return frame
        raise AssertionError(f"never received {expectedType}")

    async def testUnauthenticatedConnectionRejected(self) -> None:
        communicator = WebsocketCommunicator(
            application, WS, headers=[(b"origin", b"http://testserver")]
        )
        connected, _ = await communicator.connect()
        self.assertFalse(connected)  # §17 — no anonymous sockets
        await communicator.disconnect()

    async def testSubscribeTypingReadAndSend(self) -> None:
        communicator = await self.connect(self.bob)
        try:
            # subscribe (member → allowed)
            await communicator.send_json_to(
                {"type": "subscribe", "payload": {"conversationId": str(self.conversation.id)}}
            )
            ack = await communicator.receive_json_from()
            self.assertEqual(ack["type"], "subscribed")

            # typing relay is ephemeral (§31) — nothing persisted
            await communicator.send_json_to(
                {
                    "type": "typing",
                    "payload": {"conversationId": str(self.conversation.id), "isTyping": True},
                }
            )
            typing = await communicator.receive_json_from()
            self.assertEqual(typing["type"], "typing.started")

            # read receipt (§32)
            await communicator.send_json_to(
                {
                    "type": "read",
                    "payload": {
                        "conversationId": str(self.conversation.id),
                        "uptoMessageId": str(self.message.id),
                    },
                }
            )
            read = await self.receiveUntil(communicator, "read.ack")

            # live send (§30)
            await communicator.send_json_to(
                {
                    "type": "message.send",
                    "payload": {
                        "conversationId": str(self.conversation.id),
                        "body": "سلام از سوکت",
                        "clientRequestId": f"ws-{uuid.uuid4()}",
                    },
                }
            )
            sent = await self.receiveUntil(communicator, "message.sent")
            self.assertEqual(sent["message"]["body"], "سلام از سوکت")
        finally:
            await communicator.disconnect()

    async def testSubscribeRefusedForNonMember(self) -> None:
        outsider = await self.arun(ensureUser, self.tenant, "ws-outsider")
        communicator = await self.connect(outsider)
        try:
            await communicator.send_json_to(
                {"type": "subscribe", "payload": {"conversationId": str(self.conversation.id)}}
            )
            refusal = await communicator.receive_json_from()
            self.assertEqual(refusal["code"], "PERM_PERMISSION_DENIED")
        finally:
            await communicator.disconnect()

    async def testUnknownActionReturnsTransportError(self) -> None:
        communicator = await self.connect(self.alice)
        try:
            await communicator.send_json_to({"type": "nonsense", "payload": {}})
            error = await communicator.receive_json_from()
            self.assertEqual(error["code"], "SYS_VALIDATION_FAILED")
        finally:
            await communicator.disconnect()

    async def testSignalingRelayRoundTrip(self) -> None:
        from apps.communication.domain.services.communicationRules import SignalingProtocol

        with requestScope(
            RequestContext(
                actorId=str(self.alice.id),
                tenantId=str(self.tenant.id),
                actorTenantId=str(self.tenant.id),
            )
        ):
            call = await self.arun(
                lambda: container.startCallUseCase().execute(
                    __import__(
                        "apps.communication.application.commands.communicationCommands",
                        fromlist=["StartCallCommand"],
                    ).StartCallCommand(
                        conversationId=str(self.conversation.id), mediaType="AUDIO"
                    )
                )
            )
        communicator = await self.connect(self.alice)
        try:
            envelope = SignalingProtocol.envelope(
                "OFFER", callId=call.id, fromUser="ignored", payload={"sdp": "v=0"}
            )
            await communicator.send_json_to(
                {"type": "signal", "payload": {"envelope": envelope}}
            )
            ack = await self.receiveUntil(communicator, "signal.ack")
            self.assertTrue(ack["result"]["relayed"])
        finally:
            await communicator.disconnect()
