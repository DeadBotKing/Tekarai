"""Phase 12 domain unit tests (docs/Phases/Phase12.md).

Framework-free tests of the multi-recipient notification model: broadcast
fan-out (§12.3/§12.7), recipient read state lives on the recipient never on the
notification (§12.8), delivery state machine + SENT vs DELIVERED (§12.15),
attempts (§12.16), exponential retry + dead-letter (§12.17/§12.18), severity
(§12.6), quiet hours (§12.21), priority routing (§12.5), rules (§12.24) and
idempotent events (§12.38).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from django.test import SimpleTestCase

from apps.notifications.domain.entities import phase12Records as r
from apps.notifications.domain.valueObjects import phase12Types as t
from apps.sharedKernel.domain.errors import ConflictError, ValidationFailedError


def _now() -> datetime:
    return datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


class BroadcastTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.users = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

    def testOneNotificationManyRecipients(self) -> None:
        n = r.BroadcastNotification.create(
            self.tenant, "TASK_ASSIGNED", "Task", "body", self.users, _now()
        )
        self.assertEqual(len(n.recipients), 3)
        self.assertTrue(all(rc.state == t.RECIPIENT_UNREAD for rc in n.recipients))

    def testDuplicateRecipientsDeduplicated(self) -> None:
        n = r.BroadcastNotification.create(
            self.tenant, "X", "t", "b", [self.users[0], self.users[0]], _now()
        )
        self.assertEqual(len(n.recipients), 1)

    def testAtLeastOneRecipientRequired(self) -> None:
        with self.assertRaises(ValidationFailedError):
            r.BroadcastNotification.create(self.tenant, "X", "t", "b", [], _now())

    def testReadStatePerRecipientIndependent(self) -> None:
        n = r.BroadcastNotification.create(
            self.tenant, "X", "t", "b", self.users, _now()
        )
        n.recipients[0].markRead(_now())
        # recipient A READ, recipient B UNREAD — notification itself has no flag
        self.assertEqual(n.recipients[0].state, t.RECIPIENT_READ)
        self.assertEqual(n.recipients[1].state, t.RECIPIENT_UNREAD)
        self.assertFalse(hasattr(n, "isRead"))
        self.assertTrue(n.isUnreadFor(self.users[1]))
        self.assertFalse(n.isUnreadFor(self.users[0]))

    def testInvalidSeverityRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            r.BroadcastNotification.create(
                self.tenant, "X", "t", "b", self.users, _now(), severity="BOGUS"
            )


class RecipientStateTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.user = uuid.uuid4()
        self.n = r.BroadcastNotification.create(
            self.tenant, "X", "t", "b", [self.user], _now()
        )
        self.rcp = self.n.recipients[0]

    def testReadUnreadArchiveDismiss(self) -> None:
        self.rcp.markRead(_now())
        self.assertEqual(self.rcp.state, t.RECIPIENT_READ)
        self.assertIsNotNone(self.rcp.readAt)
        self.rcp.markUnread(_now())
        self.assertEqual(self.rcp.state, t.RECIPIENT_UNREAD)
        self.assertIsNone(self.rcp.readAt)
        self.rcp.archive(_now())
        self.assertEqual(self.rcp.state, t.RECIPIENT_ARCHIVED)
        # dismiss directly from unread
        n2 = r.BroadcastNotification.create(
            self.tenant, "Y", "t", "b", [self.user], _now()
        )
        n2.recipients[0].dismiss(_now())
        self.assertEqual(n2.recipients[0].state, t.RECIPIENT_DISMISSED)
        self.assertIsNotNone(n2.recipients[0].dismissedAt)

    def testIllegalTransitionRaises(self) -> None:
        # UNREAD -> (archive then) trying to re-archive
        self.rcp.archive(_now())
        with self.assertRaises(ConflictError):
            self.rcp.archive(_now())


class DeliveryStateTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.user = uuid.uuid4()
        self.policy = t.RetryPolicy(maxAttempts=3, initialDelaySeconds=10)

    def _delivery(self) -> r.RecipientDelivery:
        n = r.BroadcastNotification.create(
            self.tenant, "X", "t", "b", [self.user], _now()
        )
        return r.RecipientDelivery.queue(
            self.tenant, n.id, self.user, "EMAIL", _now()
        )

    def testQueueThenProcessThenDelivered(self) -> None:
        d = self._delivery()
        self.assertEqual(d.status, t.DLV_QUEUED)
        d.markProcessing(_now())
        d.recordAttempt(_now(), succeeded=True, delivered=True, retryPolicy=self.policy)
        self.assertEqual(d.status, t.DLV_DELIVERED)
        self.assertIsNotNone(d.deliveredAt)

    def testSentThenDeliveredDistinct(self) -> None:
        d = self._delivery()
        d.markProcessing(_now())
        d.recordAttempt(_now(), succeeded=True, delivered=False, retryPolicy=self.policy)
        self.assertEqual(d.status, t.DLV_SENT)
        d.recordAttempt(_now(), succeeded=True, delivered=True, retryPolicy=self.policy)
        self.assertEqual(d.status, t.DLV_DELIVERED)

    def testRetryBackoffThenDeadLetter(self) -> None:
        d = self._delivery()
        for _ in range(3):
            d.markProcessing(_now())
            d.recordAttempt(
                _now(), succeeded=False, delivered=False, retryPolicy=self.policy,
                errorCode="BOUNCE",
            )
        self.assertEqual(d.status, t.DLV_DEAD_LETTER)
        self.assertIsNone(d.nextAttemptAt)
        self.assertEqual(d.attemptCount, 3)

    def testRetrySchedulesNextAttemptWithDelay(self) -> None:
        d = self._delivery()
        d.markProcessing(_now())
        d.recordAttempt(_now(), succeeded=False, delivered=False, retryPolicy=self.policy)
        self.assertEqual(d.status, t.DLV_QUEUED)
        self.assertIsNotNone(d.nextAttemptAt)
        self.assertGreater(d.nextAttemptAt, _now())

    def testDeadLetterCanBeRequeuedByOps(self) -> None:
        d = self._delivery()
        for _ in range(3):
            d.markProcessing(_now())
            d.recordAttempt(_now(), succeeded=False, delivered=False, retryPolicy=self.policy)
        self.assertEqual(d.status, t.DLV_DEAD_LETTER)
        # ops re-queue is allowed by the state map (DEAD_LETTER -> QUEUED)
        self.assertIn(t.DLV_QUEUED, t.DELIVERY_TRANSITIONS[t.DLV_DEAD_LETTER])


class RetryPolicyTests(SimpleTestCase):
    def testExponentialBackoff(self) -> None:
        policy = t.RetryPolicy(
            maxAttempts=5, initialDelaySeconds=30,
            backoffMultiplier=2.0, maxDelaySeconds=3600,
        )
        self.assertEqual(policy.delayForAttempt(1), 0)
        self.assertEqual(policy.delayForAttempt(2), 30)
        self.assertEqual(policy.delayForAttempt(3), 60)
        self.assertEqual(policy.delayForAttempt(4), 120)
        self.assertEqual(policy.delayForAttempt(5), 240)

    def testMaxDelayCap(self) -> None:
        policy = t.RetryPolicy(initialDelaySeconds=3600, maxDelaySeconds=60)
        self.assertEqual(policy.delayForAttempt(3), 60)

    def testExhaustion(self) -> None:
        policy = t.RetryPolicy(maxAttempts=5)
        self.assertFalse(policy.isExhausted(4))
        self.assertTrue(policy.isExhausted(5))

    def testInvalidPolicyRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            t.RetryPolicy(maxAttempts=0)


class QuietHoursTests(SimpleTestCase):
    def testOvernightWindow(self) -> None:
        qh = t.QuietHours(22 * 60, 8 * 60)  # 22:00 -> 08:00
        self.assertTrue(qh.contains(23 * 60))
        self.assertTrue(qh.contains(2 * 60))
        self.assertFalse(qh.contains(12 * 60))
        self.assertFalse(qh.contains(8 * 60))  # end exclusive

    def testSameDayWindow(self) -> None:
        qh = t.QuietHours(9 * 60, 17 * 60)
        self.assertTrue(qh.contains(12 * 60))
        self.assertFalse(qh.contains(20 * 60))

    def testCriticalBypassesQuietHours(self) -> None:
        self.assertTrue(t.shouldBypassQuietHours("CRITICAL", "TASK"))
        self.assertTrue(t.shouldBypassQuietHours("LOW", "SECURITY"))
        self.assertFalse(t.shouldBypassQuietHours("NORMAL", "TASK"))

    def testInvalidWindowRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            t.QuietHours(100, 100)


class PriorityRoutingTests(SimpleTestCase):
    def testCriticalFansOutWidest(self) -> None:
        self.assertIn("SMS", t.PRIORITY_CHANNEL_ROUTING["CRITICAL"])
        self.assertIn("WEBHOOK", t.PRIORITY_CHANNEL_ROUTING["CRITICAL"])

    def testLowIsInAppOnly(self) -> None:
        self.assertEqual(t.PRIORITY_CHANNEL_ROUTING["LOW"], ("IN_APP",))

    def testWebhookChannelPresent(self) -> None:
        self.assertEqual(t.CHANNEL_WEBHOOK, "WEBHOOK")


class RuleTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.now = _now()

    def testRuleMatchesCondition(self) -> None:
        rule = r.NotificationRule.define(
            self.tenant, "overdue high", "TASK_OVERDUE", self.now,
            condition={"priority": "HIGH"}, channels=("IN_APP", "EMAIL"),
        )
        self.assertTrue(rule.matches("TASK_OVERDUE", {"priority": "HIGH"}))
        self.assertFalse(rule.matches("TASK_OVERDUE", {"priority": "LOW"}))
        self.assertFalse(rule.matches("OTHER_EVENT", {"priority": "HIGH"}))

    def testEmptyConditionMatchesByType(self) -> None:
        rule = r.NotificationRule.define(
            self.tenant, "all", "DOCUMENT_APPROVED", self.now
        )
        self.assertTrue(rule.matches("DOCUMENT_APPROVED", {}))

    def testInactiveRuleDoesNotMatch(self) -> None:
        rule = r.NotificationRule.define(
            self.tenant, "x", "X", self.now
        )
        rule.isActive = False
        self.assertFalse(rule.matches("X", {}))


class InboundEventTests(SimpleTestCase):
    def testIdempotentEnvelope(self) -> None:
        ev = r.InboundNotificationEvent.ingest(
            uuid.uuid4(), "evt-1", "TASK_ASSIGNED", _now()
        )
        self.assertFalse(ev.processed)
        ev.markProcessed()
        self.assertTrue(ev.processed)

    def testEventIdRequired(self) -> None:
        with self.assertRaises(ValidationFailedError):
            r.InboundNotificationEvent.ingest(uuid.uuid4(), "  ", "X", _now())
