"""Phase 9 WebSocket gateway tests (§41 realtime, §42 recovery model).

Runs the REAL ASGI application: authenticated connect, live push of
notification events to the recipient's group, heartbeat and the
unauthenticated rejection. The DB stays authoritative — the socket is
only the optimization layer.
"""

from __future__ import annotations

import uuid

from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from config.asgi import application

from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from apps.tenancy.infrastructure.models import TenantModel
from tests.support.phase6Helpers import seedPlatform
from tests.support.phase8Helpers import ensureUser
from tests.support.phase9Helpers import (
    grantNotificationAdmin,
    notificationOf,
    sessionTokenFor,
)

WS = "/ws/notifications/"


class NotificationWebsocketTests(TransactionTestCase):
    def setUp(self) -> None:
        super().setUp()
        seedPlatform()
        self.tenant = TenantModel.objects.get(code="platform")
        self.bob = ensureUser(self.tenant, "ws-ntf-bob")
        grantNotificationAdmin(self.tenant, self.bob)  # allow admin send too

    async def connectAs(self, user) -> WebsocketCommunicator:
        token = await self.arun(sessionTokenFor, user.id, self.tenant.id)
        communicator = WebsocketCommunicator(
            application,
            f"{WS}?token={token}",
            headers=[(b"origin", b"http://testserver")],
        )
        connected, _ = await communicator.connect()
        assert connected
        return communicator

    async def arun(self, func, *args):
        from asgiref.sync import async_to_sync
        from channels.db import database_sync_to_async

        return await database_sync_to_async(lambda: func(*args))()

    async def testUnauthenticatedIsRejected(self) -> None:
        communicator = WebsocketCommunicator(
            application, WS, headers=[(b"origin", b"http://testserver")]
        )
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4401)
        await communicator.disconnect()

    async def testReadyFrameOnConnect(self) -> None:
        communicator = await self.connectAs(self.bob)
        ready = await communicator.receive_json_from(timeout=5)
        self.assertEqual(ready["type"], "notification.ready")
        self.assertEqual(ready["event"]["userId"], str(self.bob.id))
        await communicator.disconnect()

    async def testLivePushReachesConnectedRecipient(self) -> None:
        from apps.notifications.infrastructure.container import container

        communicator = await self.connectAs(self.bob)
        await communicator.receive_json_from(timeout=5)  # ready frame

        def createAndDispatch():
            with requestScope(
                RequestContext(
                    actorId=str(self.bob.id),
                    tenantId=str(self.tenant.id),
                    actorTenantId=str(self.tenant.id),
                )
            ):
                outcome = container.createNotificationService().execute(
                    notificationOf(self.tenant, self.bob, eventId="ws-1")
                )
                return outcome.notifications[0].id

        notificationId = await self.arun(createAndDispatch)
        frame = await communicator.receive_json_from(timeout=5)
        self.assertEqual(frame["type"], "notification.event")
        self.assertEqual(frame["event"]["name"], "notificationDelivered")
        self.assertEqual(frame["event"]["notificationId"], notificationId)
        await communicator.disconnect()

    async def testHeartbeat(self) -> None:
        communicator = await self.connectAs(self.bob)
        await communicator.receive_json_from(timeout=5)
        await communicator.send_json_to({"type": "heartbeat"})
        reply = await communicator.receive_json_from(timeout=5)
        self.assertEqual(reply["type"], "heartbeat.ok")
        await communicator.disconnect()

    async def testReconcileHintPointsToRest(self) -> None:
        """§42 — the socket never guarantees delivery; recovery is REST."""
        communicator = await self.connectAs(self.bob)
        await communicator.receive_json_from(timeout=5)
        await communicator.send_json_to({"type": "reconcile"})
        reply = await communicator.receive_json_from(timeout=5)
        self.assertEqual(reply["type"], "reconcile.hint")
        self.assertIn("/api/v1/notifications", reply["event"]["source"])
        await communicator.disconnect()
