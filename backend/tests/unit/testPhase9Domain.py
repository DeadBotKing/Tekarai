"""Phase 9 domain unit tests (§3–§29).

Pure-domain behaviour without Django: aggregate lifecycle, per-channel
delivery classification with §24 backoff, §10 preference resolution,
§18/§19 templates, §29 dedup keys, §21/§22 digests and schedules.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from apps.notifications.domain.entities.notification import Notification
from apps.notifications.domain.entities.notificationDelivery import (
    NotificationDelivery,
    backoffDelay,
)
from apps.notifications.domain.entities.notificationDigest import (
    NotificationDigest,
    NotificationSchedule,
)
from apps.notifications.domain.entities.notificationPolicy import NotificationPolicy
from apps.notifications.domain.entities.notificationPreference import (
    NotificationPreference,
    NotificationPreferenceRule,
)
from apps.notifications.domain.entities.notificationTemplate import NotificationTemplate
from apps.notifications.domain.services.notificationRules import (
    resolveChannels,
    resolveLanguage,
    withinCooldown,
)
from apps.notifications.domain.valueObjects.notificationTypes import (
    BYPASS_ALLOWED_CATEGORIES,
    DELIVERY_PERMANENTLY_FAILED,
    DELIVERY_RETRY_SCHEDULED,
    PERMANENT_ERROR_CODES,
    PRIORITY_CRITICAL,
    PREF_LEVEL_CATEGORY,
    PREF_LEVEL_GLOBAL,
    PREF_LEVEL_TYPE,
    idempotencyKeyOf,
)
from apps.sharedKernel.domain.errors import (
    ConflictError,
    ValidationFailedError,
)

NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)


def makeNotification(**overrides) -> Notification:
    defaults = dict(
        id=uuid.uuid4(),
        tenantId=uuid.uuid4(),
        recipientId=uuid.uuid4(),
        notificationType="test.ping",
        category="SYSTEM",
        title="t",
        body="b",
        priority="NORMAL",
        createdAt=NOW,
    )
    defaults.update(overrides)
    return Notification(**defaults)


def makeDelivery(**overrides) -> NotificationDelivery:
    defaults = dict(
        id=uuid.uuid4(),
        tenantId=uuid.uuid4(),
        notificationId=uuid.uuid4(),
        channel="EMAIL",
        provider="logging-email",
        maxAttempts=3,
    )
    defaults.update(overrides)
    return NotificationDelivery(**defaults)


class NotificationAggregateTests(SimpleTestCase):
    def testLifecycleStartProcessingThenDelivered(self) -> None:
        notification = makeNotification()
        notification.startProcessing(NOW)
        notification.applyDeliveryOutcome(deliveredChannels=2, failedChannels=0, now=NOW)
        self.assertEqual(notification.status, "DELIVERED")
        self.assertEqual(
            [event.name for event in notification.pullEvents()],
            ["notificationDeliveryCompleted"],
        )

    def testPartialDeliveryIsItsOwnState(self) -> None:
        notification = makeNotification()
        notification.startProcessing(NOW)
        notification.applyDeliveryOutcome(deliveredChannels=1, failedChannels=1, now=NOW)
        self.assertEqual(notification.status, "PARTIALLY_DELIVERED")

    def testTotalFailureMarksFailed(self) -> None:
        notification = makeNotification()
        notification.startProcessing(NOW)
        notification.applyDeliveryOutcome(deliveredChannels=0, failedChannels=2, now=NOW)
        self.assertEqual(notification.status, "FAILED")

    def testCancelIsIdempotentButDeliveredCannotCancel(self) -> None:
        notification = makeNotification()
        notification.cancel(NOW)
        notification.cancel(NOW)  # idempotent
        self.assertEqual(notification.status, "CANCELLED")
        delivered = makeNotification(status="DELIVERED")
        with self.assertRaises(ConflictError):
            delivered.cancel(NOW)

    def testExpiryOnlyWhenDueAndUndelivered(self) -> None:
        active = makeNotification(expiresAt=NOW + timedelta(minutes=5))
        self.assertFalse(active.expire(NOW))
        due = makeNotification(expiresAt=NOW - timedelta(seconds=1))
        self.assertTrue(due.expire(NOW))
        self.assertFalse(due.expire(NOW))  # idempotent
        self.assertEqual(due.status, "EXPIRED")

    def testReadUnreadAcknowledgeGuards(self) -> None:
        notification = makeNotification()
        notification.markRead(NOW)
        self.assertIsNotNone(notification.readAt)
        notification.markUnread(NOW)
        self.assertIsNone(notification.readAt)
        notification.acknowledge(NOW, notification.recipientId)
        self.assertIsNotNone(notification.acknowledgedAt)
        # acknowledged cannot return to unread (§26)
        with self.assertRaises(ConflictError):
            notification.markUnread(NOW)

    def testArchiveIsSoftDelete(self) -> None:
        notification = makeNotification()
        notification.archive(NOW)
        self.assertIsNotNone(notification.deletedAt)

    def testEmptyTitleRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            makeNotification(title="   ")


class DeliveryEntityTests(SimpleTestCase):
    def testBackoffScheduleIsExponentialAndCapped(self) -> None:
        self.assertEqual(backoffDelay(1), 30)    # 30s
        self.assertEqual(backoffDelay(2), 120)   # 2m
        self.assertEqual(backoffDelay(3), 480)   # 8m
        self.assertEqual(backoffDelay(4), 600)   # capped §24
        self.assertEqual(backoffDelay(9), 600)

    def testRetryableFailureSchedulesRetry(self) -> None:
        delivery = makeDelivery()
        delivery.attemptCount = 1
        retried = delivery.markFailed(NOW, errorCode="PROVIDER_ERROR", errorMessage="x")
        self.assertTrue(retried)
        self.assertEqual(delivery.status, DELIVERY_RETRY_SCHEDULED)
        self.assertEqual(
            delivery.nextAttemptAt, NOW + timedelta(seconds=backoffDelay(2))
        )
        self.assertTrue(delivery.isPendingRetry())

    def testPermanentErrorIsNeverRetried(self) -> None:
        delivery = makeDelivery()
        delivery.attemptCount = 1
        retried = delivery.markFailed(
            NOW, errorCode=PERMANENT_ERROR_CODES[0], errorMessage="x"
        )
        self.assertFalse(retried)
        self.assertEqual(delivery.status, DELIVERY_PERMANENTLY_FAILED)

    def testExhaustedAttemptsStopRetrying(self) -> None:
        delivery = makeDelivery(maxAttempts=2)
        delivery.attemptCount = 2
        retried = delivery.markFailed(NOW, errorCode="PROVIDER_ERROR", errorMessage="x")
        self.assertFalse(retried)

    def testRetryDueRespectsBackoffWindow(self) -> None:
        delivery = makeDelivery()
        delivery.attemptCount = 1
        delivery.markFailed(NOW, errorCode="TIMEOUT", errorMessage="x")
        self.assertFalse(delivery.retryIsDue(NOW))
        self.assertTrue(delivery.retryIsDue(NOW + timedelta(seconds=121)))

    def testSkipIsNotAFailure(self) -> None:
        delivery = makeDelivery()
        delivery.skip(NOW, "user preference disabled")
        self.assertEqual(delivery.status, "SKIPPED")


class PreferenceResolutionTests(SimpleTestCase):
    def testMostSpecificPreferenceWins(self) -> None:
        rows = [
            (PREF_LEVEL_GLOBAL, "", "", "EMAIL", False),     # email off globally
            (PREF_LEVEL_CATEGORY, "SYSTEM", "", "EMAIL", True),  # but on for SYSTEM
        ]
        channels, _trace = resolveChannels(
            policyChannels=("IN_APP", "EMAIL"),
            forcedChannels=(),
            deniedChannels=(),
            preferenceRows=rows,
            notificationType="test.ping",
            category="SYSTEM",
            priority="NORMAL",
            allowPreferenceBypass=False,
        )
        self.assertEqual(channels, ("IN_APP", "EMAIL"))

    def testTypeLevelBeatsCategoryLevel(self) -> None:
        rows = [
            (PREF_LEVEL_CATEGORY, "SYSTEM", "", "PUSH", True),
            (PREF_LEVEL_TYPE, "", "test.ping", "PUSH", False),
        ]
        channels, _trace = resolveChannels(
            policyChannels=("IN_APP", "PUSH"),
            forcedChannels=(),
            deniedChannels=(),
            preferenceRows=rows,
            notificationType="test.ping",
            category="SYSTEM",
            priority="NORMAL",
            allowPreferenceBypass=False,
        )
        self.assertEqual(channels, ("IN_APP",))

    def testTenantDenyRemovesEvenWhenUserWantsIt(self) -> None:
        channels, _trace = resolveChannels(
            policyChannels=("IN_APP", "SMS"),
            forcedChannels=(),
            deniedChannels=("SMS",),
            preferenceRows=[],
            notificationType="x",
            category="SYSTEM",
            priority="NORMAL",
            allowPreferenceBypass=False,
        )
        self.assertEqual(channels, ("IN_APP",))

    def testTenantForceAddsDespiteUserPreference(self) -> None:
        channels, _trace = resolveChannels(
            policyChannels=("IN_APP",),
            forcedChannels=("EMAIL",),
            deniedChannels=(),
            preferenceRows=[(PREF_LEVEL_GLOBAL, "", "", "EMAIL", False)],
            notificationType="x",
            category="SYSTEM",
            priority="NORMAL",
            allowPreferenceBypass=False,
        )
        self.assertIn("EMAIL", channels)

    def testCriticalBypassOnlyWhenPolicyAllowsAndCategoryPermits(self) -> None:
        rows = [(PREF_LEVEL_GLOBAL, "", "", "IN_APP", False)]
        # SECURITY is in BYPASS_ALLOWED_CATEGORIES and policy allows → bypass
        channels, trace = resolveChannels(
            policyChannels=("IN_APP",),
            forcedChannels=(),
            deniedChannels=(),
            preferenceRows=rows,
            notificationType="security.alert",
            category=BYPASS_ALLOWED_CATEGORIES[0],
            priority=PRIORITY_CRITICAL,
            allowPreferenceBypass=True,
        )
        self.assertEqual(channels, ("IN_APP",))
        self.assertIn("critical-bypass(user prefs ignored)", trace)
        # policy does NOT allow → user preference honoured (§5)
        channels, _trace = resolveChannels(
            policyChannels=("IN_APP",),
            forcedChannels=(),
            deniedChannels=(),
            preferenceRows=rows,
            notificationType="task.due",
            category="TASK",
            priority=PRIORITY_CRITICAL,
            allowPreferenceBypass=False,
        )
        self.assertEqual(channels, ())

    def testPreferenceLevelValidation(self) -> None:
        with self.assertRaises(ValidationFailedError):
            NotificationPreference(
                id=uuid.uuid4(),
                tenantId=uuid.uuid4(),
                userId=uuid.uuid4(),
                level=PREF_LEVEL_TYPE,
                channel="EMAIL",
                notificationType="",
            )


class TemplateTests(SimpleTestCase):
    def makeTemplate(self, **overrides) -> NotificationTemplate:
        defaults = dict(
            id=uuid.uuid4(),
            tenantId=uuid.uuid4(),
            templateKey="meeting.invitation",
            language="fa-IR",
            channel="IN_APP",
            version=1,
            title="دعوت به جلسه {title}",
            subject="",
            body="شما به جلسه {title} دعوت شده‌اید.",
        )
        defaults.update(overrides)
        return NotificationTemplate(**defaults)

    def testSafeTokenSubstitutionOnly(self) -> None:
        template = self.makeTemplate(
            title="{a} و {b}",
            subject="{a}",
            body="__import__('os') {c}",
        )
        title, subject, body = template.render({"a": "۱", "b": "۲", "c": "۳"})
        self.assertEqual(title, "۱ و ۲")
        self.assertEqual(subject, "۱")
        self.assertIn("۳", body)  # literal substitution, never executed
        self.assertEqual(template.placeholders(), ("a", "b", "c"))

    def testMissingPlaceholderRendersEmpty(self) -> None:
        template = self.makeTemplate(title="[{x}]")
        title, _subject, _body = template.render({})
        self.assertEqual(title, "[]")

    def testNextVersionIncrements(self) -> None:
        template = self.makeTemplate()
        versionTwo = template.nextVersion(title="v2", subject="", body="")
        self.assertEqual(versionTwo.version, 2)
        self.assertEqual(versionTwo.templateKey, template.templateKey)


class PolicyEntityTests(SimpleTestCase):
    def testTypeMatchBeatsCategoryMatch(self) -> None:
        policy = NotificationPolicy(
            id=uuid.uuid4(),
            tenantId=uuid.uuid4(),
            policyKey="by.type",
            notificationType="meeting.invitation",
            category="",
            channels=("IN_APP", "PUSH"),
        )
        self.assertTrue(policy.appliesTo("meeting.invitation", "MEETING"))
        self.assertFalse(policy.appliesTo("other.type", "MEETING"))

    def testEscalationStagesSortByDelay(self) -> None:
        policy = NotificationPolicy(
            id=uuid.uuid4(),
            tenantId=uuid.uuid4(),
            policyKey="esc",
            channels=("IN_APP",),
            escalation=[
                {"afterSeconds": 900, "recipientSpec": {"type": "TENANT_ADMIN"}},
                {"afterSeconds": 300, "recipientSpec": {"type": "ROLE", "value": "manager"}},
            ],
        )
        due = policy.escalationFor(600)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["afterSeconds"], 300)


class DigestAndScheduleTests(SimpleTestCase):
    def testDigestAccumulatesThenSends(self) -> None:
        digest = NotificationDigest(
            id=uuid.uuid4(),
            tenantId=uuid.uuid4(),
            userId=uuid.uuid4(),
            kind="HOURLY",
            periodStart=NOW,
            periodEnd=NOW + timedelta(hours=1),
        )
        digest.addItem()
        digest.addItem()
        self.assertEqual(digest.itemCount, 2)
        digest.markSent(NOW)
        with self.assertRaises(ValidationFailedError):
            digest.addItem()

    def testScheduleDueAndRecurring(self) -> None:
        schedule = NotificationSchedule(
            id=uuid.uuid4(),
            tenantId=uuid.uuid4(),
            kind="RECURRING",
            recipientSpec={"type": "USER", "value": str(uuid.uuid4())},
            notificationType="report.weekly",
            category="REPORT",
            priority="LOW",
            title="گزارش هفتگی",
            recurEverySeconds=3600,
            nextRunAt=NOW - timedelta(seconds=1),
        )
        self.assertTrue(schedule.isDue(NOW))
        staysAlive = schedule.recordRun(NOW)
        self.assertTrue(staysAlive)
        self.assertEqual(schedule.nextRunAt, NOW + timedelta(seconds=3600))
        self.assertFalse(schedule.isDue(NOW))

    def testOneShotScheduleCompletes(self) -> None:
        schedule = NotificationSchedule(
            id=uuid.uuid4(),
            tenantId=uuid.uuid4(),
            kind="DELAYED",
            recipientSpec={"type": "USER", "value": str(uuid.uuid4())},
            notificationType="x.y",
            category="SYSTEM",
            priority="LOW",
            title="t",
            nextRunAt=NOW,
        )
        self.assertFalse(schedule.recordRun(NOW))
        self.assertEqual(schedule.status, "DONE")


class ValueObjectTests(SimpleTestCase):
    def testIdempotencyKeyIsStableHash(self) -> None:
        first = idempotencyKeyOf(
            tenantId="T", eventType="E", eventId="1",
            recipientId="R", notificationType="N",
        )
        second = idempotencyKeyOf(
            tenantId="T", eventType="E", eventId="1",
            recipientId="R", notificationType="N",
        )
        different = idempotencyKeyOf(
            tenantId="T", eventType="E", eventId="2",
            recipientId="R", notificationType="N",
        )
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertEqual(len(first), 64)  # sha256 hex

    def testLanguageResolutionOrder(self) -> None:
        self.assertEqual(resolveLanguage(userLanguage="", tenantDefault="fa-IR"), "fa-IR")
        self.assertEqual(
            resolveLanguage(userLanguage="de-DE", tenantDefault="fa-IR"), "de-DE"
        )
        self.assertEqual(
            resolveLanguage(userLanguage="", tenantDefault="", platformDefault="en-US"),
            "en-US",
        )

    def testCooldownWindow(self) -> None:
        last = NOW - timedelta(seconds=59)
        self.assertTrue(withinCooldown(last, NOW, 60))
        earlier = NOW - timedelta(seconds=61)
        self.assertFalse(withinCooldown(earlier, NOW, 60))


class TenantRuleTests(SimpleTestCase):
    def testRuleActionsAreConstrained(self) -> None:
        with self.assertRaises(ValidationFailedError):
            NotificationPreferenceRule(
                id=uuid.uuid4(),
                tenantId=uuid.uuid4(),
                channel="SMS",
                action="MAYBE",
            )
