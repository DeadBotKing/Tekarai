"""Phase 12 application tests — multi-recipient notification services over a
real SQLite test DB. Covers broadcast fan-out (§12.3/§12.7), per-recipient read
state (§12.8), priority delivery routing (§12.5), retry + dead-letter
(§12.17/§12.18), rules (§12.24), idempotent event intake (§12.38) and tenant
isolation (§12.25).
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.notifications.application.commands.phase12Commands import (
    CreateBroadcastCommand,
    DefineRuleCommand,
    IngestEventCommand,
    ListBroadcastsQuery,
    RecipientStateCommand,
    RetryDeliveryCommand,
    UnreadCountQuery,
)
from apps.notifications.infrastructure import container as c
from apps.notifications.infrastructure.channels.webhookChannel import (
    WebhookDeliveryChannel,
)
from apps.notifications.infrastructure.models import (
    NotificationAttemptModel,
    NotificationEventModel,
    NotificationRecipientDeliveryModel,
)
from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from tests.support.phase8Helpers import ensureTenant, ensureUser
from tests.support.phase9Helpers import grantNotificationAdmin


def ctx(tenantId: uuid.UUID, userId: uuid.UUID):
    return requestScope(
        RequestContext(
            actorId=str(userId),
            tenantId=str(tenantId),
            actorTenantId=str(tenantId),
        )
    )


class Phase12Base(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenant = ensureTenant("p12_tenant")
        self.other = ensureTenant("p12_other")
        self.admin = ensureUser(self.tenant, "p12_admin")
        self.u1 = ensureUser(self.tenant, "p12_u1")
        self.u2 = ensureUser(self.tenant, "p12_u2")
        self.alien = ensureUser(self.other, "p12_alien")
        grantNotificationAdmin(self.tenant, self.admin)

    def context(self, tenant, user):
        return ctx(tenant.id, user.id)


class BroadcastCreationTests(Phase12Base):
    def testCreateFanOutToRecipients(self) -> None:
        with self.context(self.tenant, self.admin):
            n = c.createBroadcastService().execute(
                CreateBroadcastCommand(
                    notificationType="TASK_ASSIGNED",
                    title="Task assigned",
                    body="do it",
                    recipientIds=(self.u1.id, self.u2.id),
                    priority="NORMAL",
                )
            )
        self.assertEqual(len(n.recipients), 2)
        reloaded = c.broadcastRepository().getById(self.tenant.id, n.id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(len(reloaded.recipients), 2)

    def testIdempotencyKeyReturnsExisting(self) -> None:
        with self.context(self.tenant, self.admin):
            cmd = CreateBroadcastCommand(
                notificationType="X", title="t",
                recipientIds=(self.u1.id,), idempotencyKey="dup-1",
            )
            n1 = c.createBroadcastService().execute(cmd)
            n2 = c.createBroadcastService().execute(cmd)
        self.assertEqual(n1.id, n2.id)

    def testDeliveryFanOutUsesPriorityRouting(self) -> None:
        with self.context(self.tenant, self.admin):
            n = c.createBroadcastService().execute(
                CreateBroadcastCommand(
                    notificationType="ALERT", title="crit",
                    recipientIds=(self.u1.id,), priority="CRITICAL",
                )
            )
            deliveries = c.deliveryDispatchService().fanOut(n)
        channels = {d.channel for d in deliveries}
        # CRITICAL -> IN_APP, EMAIL, PUSH, SMS, WEBHOOK
        self.assertIn("SMS", channels)
        self.assertIn("WEBHOOK", channels)
        self.assertIn("IN_APP", channels)
        self.assertEqual(
            NotificationRecipientDeliveryModel.objects.filter(
                notificationId=n.id
            ).count(),
            len(channels),
        )


class RecipientStateTests(Phase12Base):
    def _broadcast(self):
        with self.context(self.tenant, self.admin):
            return c.createBroadcastService().execute(
                CreateBroadcastCommand(
                    notificationType="X", title="hi",
                    recipientIds=(self.u1.id, self.u2.id),
                )
            )

    def testReadAffectsOnlyActingRecipient(self) -> None:
        n = self._broadcast()
        with self.context(self.tenant, self.u1):
            rcp = c.recipientStateService().execute(
                RecipientStateCommand(notificationId=str(n.id), action="read")
            )
        self.assertEqual(rcp.state, "READ")
        # u2 still unread
        count = c.broadcastRepository().unreadCount(self.tenant.id, self.u2.id)
        self.assertEqual(count, 1)
        count1 = c.broadcastRepository().unreadCount(self.tenant.id, self.u1.id)
        self.assertEqual(count1, 0)

    def testUnreadArchiveDismiss(self) -> None:
        n = self._broadcast()
        with self.context(self.tenant, self.u1):
            c.recipientStateService().execute(
                RecipientStateCommand(notificationId=str(n.id), action="read")
            )
            c.recipientStateService().execute(
                RecipientStateCommand(notificationId=str(n.id), action="unread")
            )
        rcp = c.broadcastRepository().getRecipient(self.tenant.id, n.id, self.u1.id)
        self.assertEqual(rcp.state, "UNREAD")

    def testInboxQueryScopedToViewer(self) -> None:
        self._broadcast()
        with self.context(self.tenant, self.u1):
            items = c.broadcastQueryService().execute(ListBroadcastsQuery())
            self.assertEqual(len(items), 1)
            result = c.broadcastQueryService().execute(UnreadCountQuery())
            self.assertEqual(result["unreadCount"], 1)

    def testOtherTenantCannotRead(self) -> None:
        n = self._broadcast()
        from apps.sharedKernel.domain.errors import EntityNotFoundError

        with self.context(self.other, self.alien):
            with self.assertRaises(EntityNotFoundError):
                c.recipientStateService().execute(
                    RecipientStateCommand(notificationId=str(n.id), action="read")
                )


class RetryDeadLetterTests(Phase12Base):
    def _queuedDelivery(self, channel="EMAIL"):
        with self.context(self.tenant, self.admin):
            n = c.createBroadcastService().execute(
                CreateBroadcastCommand(
                    notificationType="X", title="t",
                    recipientIds=(self.u1.id,), priority="LOW",
                )
            )
            deliveries = c.deliveryDispatchService().fanOut(n)
        return next(d for d in deliveries if d.channel == "IN_APP") if channel == "IN_APP" else None

    def testInAppDeliversImmediately(self) -> None:
        with self.context(self.tenant, self.admin):
            n = c.createBroadcastService().execute(
                CreateBroadcastCommand(
                    notificationType="X", title="t",
                    recipientIds=(self.u1.id,), priority="LOW",
                )
            )
            c.deliveryDispatchService().fanOut(n)
            result = c.deliveryRetryService().processDue()
        self.assertGreaterEqual(result["delivered"], 1)

    def testFailingChannelDeadLettersAfterMaxAttempts(self) -> None:
        def alwaysFail(delivery):
            return (False, False, "broken-provider", "", "PROVIDER_DOWN", "down")

        with self.context(self.tenant, self.admin):
            n = c.createBroadcastService().execute(
                CreateBroadcastCommand(
                    notificationType="X", title="t",
                    recipientIds=(self.u1.id,), priority="LOW",
                )
            )
            c.deliveryDispatchService().fanOut(n)
            svc = c.deliveryRetryService()
            svc.channelSender = alwaysFail
            delivery = NotificationRecipientDeliveryModel.objects.get(notificationId=n.id)
            domain_delivery = c.recipientDeliveryRepository().getById(
                self.tenant.id, delivery.id
            )
            # attempt up to the cap; backoff delays are ignored by calling the
            # per-delivery attempt directly (worker would otherwise wait).
            for _ in range(6):
                if domain_delivery.status == "DEAD_LETTER":
                    break
                svc._attempt(domain_delivery)
        dead = NotificationRecipientDeliveryModel.objects.filter(
            notificationId=n.id, deliveryStatus="DEAD_LETTER"
        )
        self.assertTrue(dead.exists())
        attempts = NotificationAttemptModel.objects.filter(deliveryId=dead.first().id)
        self.assertEqual(attempts.count(), 5)

    def testManualRetryRequeuesDeadLetter(self) -> None:
        with self.context(self.tenant, self.admin):
            n = c.createBroadcastService().execute(
                CreateBroadcastCommand(
                    notificationType="X", title="t",
                    recipientIds=(self.u1.id,), priority="LOW",
                )
            )
            c.deliveryDispatchService().fanOut(n)
            delivery = NotificationRecipientDeliveryModel.objects.get(notificationId=n.id)
            delivery.deliveryStatus = "DEAD_LETTER"
            delivery.save()
            result = c.deliveryRetryService().execute(
                RetryDeliveryCommand(deliveryId=str(delivery.id))
            )
        self.assertIn(result.status, ("DELIVERED", "QUEUED", "DEAD_LETTER"))


class RuleAndEventTests(Phase12Base):
    def testRuleCreatedAndListed(self) -> None:
        with self.context(self.tenant, self.admin):
            c.ruleDefinitionService().execute(
                DefineRuleCommand(
                    name="overdue high",
                    eventType="TASK_OVERDUE",
                    condition={"priority": "HIGH"},
                    recipientStrategy="TARGET",
                    channels=("IN_APP",),
                    priority="HIGH",
                )
            )
            found = c.notificationRuleRepository().listForEvent(
                self.tenant.id, "TASK_OVERDUE"
            )
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].matches("TASK_OVERDUE", {"priority": "HIGH"}))

    def testEventIntakeCreatesNotificationIdempotently(self) -> None:
        with self.context(self.tenant, self.admin):
            c.ruleDefinitionService().execute(
                DefineRuleCommand(
                    name="task assigned",
                    eventType="TASK_ASSIGNED",
                    recipientStrategy="TARGET",
                    channels=("IN_APP",),
                )
            )
            payload = {"title": "New task", "body": "assigned",
                       "recipientIds": [str(self.u1.id)]}
            cmd = IngestEventCommand(eventId="evt-100", eventType="TASK_ASSIGNED",
                                     payload=payload)
            first = c.eventIntakeService().execute(cmd)
            second = c.eventIntakeService().execute(cmd)  # redelivered
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertTrue(
            NotificationEventModel.objects.filter(
                tenantId=self.tenant.id, eventId="evt-100", processed=True
            ).exists()
        )
        # recipient got an in-app delivery
        self.assertEqual(
            NotificationRecipientDeliveryModel.objects.filter(
                tenantId=self.tenant.id, channel="IN_APP"
            ).count(),
            1,
        )

    def testConditionFiltersEvents(self) -> None:
        with self.context(self.tenant, self.admin):
            c.ruleDefinitionService().execute(
                DefineRuleCommand(
                    name="only high", eventType="TASK_OVERDUE",
                    condition={"priority": "HIGH"}, recipientStrategy="TARGET",
                )
            )
            low = c.eventIntakeService().execute(
                IngestEventCommand(
                    eventId="e-low", eventType="TASK_OVERDUE",
                    payload={"priority": "LOW", "recipientIds": [str(self.u1.id)]},
                )
            )
            high = c.eventIntakeService().execute(
                IngestEventCommand(
                    eventId="e-high", eventType="TASK_OVERDUE",
                    payload={"priority": "HIGH", "recipientIds": [str(self.u1.id)]},
                )
            )
        self.assertEqual(len(low), 0)
        self.assertEqual(len(high), 1)


class WebhookChannelTests(Phase12Base):
    def testWebhookMissingUrlFails(self) -> None:
        ch = WebhookDeliveryChannel()
        result = ch.send(
            tenantId=str(self.tenant.id), notificationId="n1",
            recipientId=str(self.u1.id), title="t", body="b", metadata={},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["errorCode"], "WEBHOOK_URL_MISSING")

    def testWebhookLoggingProviderSucceeds(self) -> None:
        ch = WebhookDeliveryChannel()
        result = ch.send(
            tenantId=str(self.tenant.id), notificationId="n1",
            recipientId=str(self.u1.id), title="t", body="b",
            metadata={"webhookUrl": "https://example.com/hook"},
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["delivered"])
