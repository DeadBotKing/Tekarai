"""Phase 9 application/worker tests (§28–§32, §21–§27, §30).

Runs the real services over the ORM: the eleven-step worker pipeline,
idempotency, anti-storm aggregation, preference override, partial
delivery isolation, retry with backoff, expiration, digests, escalation,
device revocation and the §30 outbox consumer.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import TestCase

from apps.notifications.infrastructure.container import container
from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from apps.tenancy.infrastructure.models import TenantModel
from tests.support.phase6Helpers import seedPlatform
from tests.support.phase8Helpers import ensureTenant, ensureUser
from tests.support.phase9Helpers import (
    asUser,
    grantNotificationAdmin,
    notificationOf,
)


class NotificationEngineBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        seedPlatform()
        self.tenant = TenantModel.objects.get(code="platform")
        self.alice = ensureUser(self.tenant, "ntf-alice")
        self.bob = ensureUser(self.tenant, "ntf-bob")
        grantNotificationAdmin(self.tenant, self.alice)

    def createContext(self, user=None):
        return requestScope(
            RequestContext(
                actorId=str((user or self.alice).id),
                tenantId=str(self.tenant.id),
                actorTenantId=str(self.tenant.id),
            )
        )

    def create(self, command):
        return container.createNotificationService().execute(command)

    def deliveriesOf(self, notificationId):
        return container.deliveryRepository().getForNotification(notificationId)

    def policyFor(self, notificationType, category):
        return container.resolvePolicyService().resolve(
            self.tenant.id, notificationType, category
        )


class WorkerPipelineTests(NotificationEngineBase):
    def testWorkerCreatesInAppDeliveryAndDeliveredState(self) -> None:
        outcome = self.create(notificationOf(self.tenant, self.bob))
        self.assertEqual(len(outcome.notifications), 1)
        notificationId = uuid.UUID(outcome.notifications[0].id)
        # the DTO is pre-dispatch; the inline queue ran §32 after commit
        notification = container.notificationRepository().getById(notificationId)
        self.assertEqual(notification.status, "DELIVERED")
        deliveries = self.deliveriesOf(notificationId)
        self.assertEqual(
            [(d.channel, d.status) for d in deliveries], [("IN_APP", "DELIVERED")]
        )

    def testDuplicateEventReturnsSameNotification(self) -> None:
        command = notificationOf(self.tenant, self.bob, eventId="dup-1")
        first = self.create(command)
        second = self.create(notificationOf(self.tenant, self.bob, eventId="dup-1"))
        self.assertEqual(second.duplicates, 1)
        self.assertEqual(first.notifications[0].id, second.notifications[0].id)
        rows = container.notificationRepository().listForRecipient(
            self.tenant.id, self.bob.id
        )[0]
        self.assertEqual(len(rows), 1)  # exactly one row (§29)

    def testDispatchIsIdempotentOnRerun(self) -> None:
        outcome = self.create(notificationOf(self.tenant, self.bob))
        notificationId = uuid.UUID(outcome.notifications[0].id)
        again = container.dispatchService().dispatchOne(notificationId)
        self.assertEqual(again.status, "DELIVERED")  # unchanged, no duplicate rows
        self.assertEqual(len(self.deliveriesOf(notificationId)), 1)

    def testPreferenceOverrideDropsChannel(self) -> None:
        from apps.notifications.application.commands.notificationCommands import (
            SavePolicyCommand,
        )

        with self.createContext(self.alice):
            container.savePolicyService().execute(
                SavePolicyCommand(
                    tenantId=self.tenant.id,
                    policyKey="prefs.test",
                    matchType="TYPE",
                    matchValue="test.ping",
                    channels=("IN_APP", "EMAIL"),
                    priority="NORMAL",
                )
            )
        # bob turns EMAIL off globally
        from apps.notifications.application.commands.notificationCommands import (
            UpdatePreferencesCommand,
        )

        with self.createContext(self.bob):
            container.updatePreferencesService().execute(
                UpdatePreferencesCommand(
                    tenantId=self.tenant.id,
                    userId=self.bob.id,
                    preferences=(
                        {
                            "level": "GLOBAL",
                            "channel": "EMAIL",
                            "enabled": False,
                        },
                    ),
                )
            )
        outcome = self.create(notificationOf(self.tenant, self.bob))
        channels = [d.channel for d in self.deliveriesOf(uuid.UUID(outcome.notifications[0].id))]
        self.assertNotIn("EMAIL", channels)
        self.assertIn("IN_APP", channels)

    def testTenantRuleForcesChannelDespitePreference(self) -> None:
        from apps.notifications.application.commands.notificationCommands import (
            SavePolicyCommand,
            SaveTenantRuleCommand,
            UpdatePreferencesCommand,
        )

        with self.createContext(self.alice):
            container.savePolicyService().execute(
                SavePolicyCommand(
                    tenantId=self.tenant.id,
                    policyKey="force.email",
                    matchType="TYPE",
                    matchValue="hr.payroll",
                    channels=("IN_APP",),
                    priority="NORMAL",
                )
            )
            container.saveTenantRuleService().execute(
                SaveTenantRuleCommand(
                    tenantId=self.tenant.id,
                    effect="FORCED",
                    channel="EMAIL",
                    notificationType="hr.payroll",
                )
            )
        with self.createContext(self.bob):
            container.updatePreferencesService().execute(
                UpdatePreferencesCommand(
                    tenantId=self.tenant.id,
                    userId=self.bob.id,
                    preferences=({"level": "GLOBAL", "channel": "EMAIL", "enabled": False},),
                )
            )
        outcome = self.create(
            notificationOf(self.tenant, self.bob, notificationType="hr.payroll")
        )
        channels = [d.channel for d in self.deliveriesOf(uuid.UUID(outcome.notifications[0].id))]
        self.assertIn("EMAIL", channels)  # §11 org rule wins

    def testPartialDeliveryIsolation(self) -> None:
        """§47 — EMAIL down must not prevent IN_APP."""
        from apps.notifications.application.commands.notificationCommands import (
            SavePolicyCommand,
        )
        from apps.notifications.infrastructure.channels.deliveryChannels import (
            EmailDeliveryChannel,
        )
        from apps.notifications.infrastructure.providers.channelProviders import (
            ProviderPool,
        )
        from apps.notifications.domain.repositories.notificationRepositories import (
            DeliveryResult,
        )

        class BrokenEmailProvider:
            providerName = "broken"

            def send(self, **kwargs):
                return DeliveryResult(ok=False, errorCode="PROVIDER_ERROR",
                                      errorMessage="smtp down")

        with self.createContext(self.alice):
            container.savePolicyService().execute(
                SavePolicyCommand(
                    tenantId=self.tenant.id,
                    policyKey="partial.test",
                    matchType="TYPE",
                    matchValue="test.ping",
                    channels=("IN_APP", "EMAIL"),
                    priority="NORMAL",
                )
            )
        # swap the email adapter to a failing one
        original = container.dispatchService
        try:
            import apps.notifications.infrastructure.channels.deliveryChannels as channelsModule

            channelsModule.emailProviderPool = lambda: ProviderPool([BrokenEmailProvider()])
            outcome = self.create(notificationOf(self.tenant, self.bob))
            notificationId = uuid.UUID(outcome.notifications[0].id)
            notification = container.notificationRepository().getById(notificationId)
            # §47 — the email outage did NOT prevent in-app delivery; the
            # aggregate is delivered while the email row rides the §24 retry
            # ladder (RETRY_SCHEDULED is in flight, not a hard failure).
            self.assertEqual(notification.status, "DELIVERED")
            statuses = {d.channel: d.status for d in self.deliveriesOf(notificationId)}
            self.assertEqual(statuses["IN_APP"], "DELIVERED")
            self.assertEqual(statuses["EMAIL"], "RETRY_SCHEDULED")
        finally:
            channelsModule.emailProviderPool = (
                __import__(
                    "apps.notifications.infrastructure.providers.channelProviders",
                    fromlist=["emailProviderPool"],
                ).emailProviderPool
            )


class RetryTests(NotificationEngineBase):
    def _failingDelivery(self, errorCode: str):
        from apps.notifications.application.commands.notificationCommands import (
            SavePolicyCommand,
        )
        from apps.notifications.infrastructure.providers.channelProviders import (
            ProviderPool,
        )
        from apps.notifications.domain.repositories.notificationRepositories import (
            DeliveryResult,
        )

        class FlakyProvider:  # noqa: ANN106 — local test double
            providerName = "flaky"

            def __init__(self) -> None:
                self.attempts = 0

            def send(self, **kwargs):
                self.attempts += 1
                if self.attempts < 2:
                    return DeliveryResult(ok=False, errorCode=errorCode,
                                          errorMessage="flaky")
                return DeliveryResult(ok=True)

        provider = FlakyProvider()
        with self.createContext(self.alice):
            container.savePolicyService().execute(
                SavePolicyCommand(
                    tenantId=self.tenant.id,
                    policyKey="retry.test",
                    matchType="TYPE",
                    matchValue="test.ping",
                    channels=("EMAIL",),
                    priority="NORMAL",
                )
            )
        import apps.notifications.infrastructure.channels.deliveryChannels as channelsModule

        original = channelsModule.emailProviderPool
        channelsModule.emailProviderPool = lambda: ProviderPool([provider])
        try:
            outcome = self.create(notificationOf(self.tenant, self.bob))
            notificationId = uuid.UUID(outcome.notifications[0].id)
            delivery = self.deliveriesOf(notificationId)[0]
            return notificationId, delivery
        finally:
            channelsModule.emailProviderPool = original

    def testRetryRecoversAfterBackoff(self) -> None:
        notificationId, delivery = self._failingDelivery("PROVIDER_ERROR")
        self.assertEqual(delivery.status, "RETRY_SCHEDULED")
        from apps.notifications.infrastructure.models import (
            NotificationDeliveryModel,
        )

        # force the backoff window to elapse
        NotificationDeliveryModel.objects.filter(id=delivery.id).update(
            nextAttemptAt=delivery.nextAttemptAt - timedelta(minutes=10)
        )
        result = container.retryService().execute(
            type("RetryCommand", (), {"limit": 10})()
        )
        self.assertEqual(result["recovered"], 1)
        refreshed = self.deliveriesOf(notificationId)[0]
        self.assertEqual(refreshed.status, "DELIVERED")
        notification = container.notificationRepository().getById(notificationId)
        self.assertEqual(notification.status, "DELIVERED")

    def testPermanentErrorNeverRetried(self) -> None:
        from apps.notifications.infrastructure.models import (
            NotificationDeliveryModel,
        )

        notificationId, delivery = self._failingDelivery("INVALID_ADDRESS")
        self.assertEqual(delivery.status, "PERMANENTLY_FAILED")
        NotificationDeliveryModel.objects.filter(id=delivery.id).update(
            nextAttemptAt=delivery.nextAttemptAt - timedelta(hours=1)
            if delivery.nextAttemptAt
            else None
        )
        result = container.retryService().execute(
            type("RetryCommand", (), {"limit": 10})()
        )
        self.assertEqual(result["retried"], 0)  # §24 never retried


class RateLimitAndDigestTests(NotificationEngineBase):
    def testStormAggregatesToDigest(self) -> None:
        from apps.notifications.application.commands.notificationCommands import (
            SavePolicyCommand,
        )
        from apps.notifications.infrastructure.repositories.notificationRepositoriesImpl import (
            dueOpenDigests,
        )

        with self.createContext(self.alice):
            container.savePolicyService().execute(
                SavePolicyCommand(
                    tenantId=self.tenant.id,
                    policyKey="storm.test",
                    matchType="TYPE",
                    matchValue="chat.message",
                    channels=("IN_APP", "EMAIL"),
                    priority="LOW",
                    digestKind="HOURLY",
                    cooldownSeconds=60,
                )
            )
        first = self.create(
            notificationOf(self.tenant, self.bob, notificationType="chat.message",
                           eventId="s-1")
        )
        second = self.create(
            notificationOf(self.tenant, self.bob, notificationType="chat.message",
                           eventId="s-2")
        )
        self.assertEqual(first.aggregatedToDigest, 0)
        self.assertEqual(second.aggregatedToDigest, 1)  # §28 cooldown hit
        secondRow = container.notificationRepository().getById(
            uuid.UUID(second.notifications[0].id)
        )
        self.assertEqual(secondRow.status, "DELIVERED")  # in-app only
        digests = dueOpenDigests("", self._now() + timedelta(hours=2))
        self.assertTrue(any(d.itemCount >= 1 for d in digests))

    def testDigestSendPipeline(self) -> None:
        """§21 — an elapsed window produces one digest.summary row."""
        from apps.notifications.application.commands.notificationCommands import (
            SendDueDigestsCommand,
        )
        from apps.notifications.infrastructure.models import NotificationDigestModel

        container.createDigestService().addItemFor(
            tenantId=self.tenant.id,
            userId=self.bob.id,
            notificationId=uuid.uuid4(),
            now=self._now(),
        )
        # window elapsed → due (shift the whole period into the past)
        NotificationDigestModel.objects.update(
            periodStart=self._now() - timedelta(hours=2),
            periodEnd=self._now() - timedelta(hours=1),
        )
        result = container.sendDigestService().execute(SendDueDigestsCommand(kind=""))
        self.assertEqual(result["digestsSent"], 1)
        rows, _unread, _hasNext = container.notificationRepository().listForRecipient(
            self.tenant.id, self.bob.id
        )
        self.assertIn("digest.summary", [row.notificationType for row in rows])

    @staticmethod
    def _now():
        from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider

        return sharedKernelProvider("clock")().nowUtc()


class ExpirationAndCancellationTests(NotificationEngineBase):
    def testExpiredNotificationIsNeverDelivered(self) -> None:
        outcome = self.create(
            notificationOf(
                self.tenant,
                self.bob,
                eventId="exp-1",
                expiresAt=self._now() - timedelta(seconds=1),
            )
        )
        notificationId = uuid.UUID(outcome.notifications[0].id)
        expired = container.notificationRepository().getById(notificationId)
        self.assertEqual(expired.status, "EXPIRED")
        deliveries = self.deliveriesOf(uuid.UUID(outcome.notifications[0].id))
        self.assertEqual(deliveries, [])  # nothing sent (§23)

    def testExpirySweepExpiresPendingRows(self) -> None:
        outcome = self.create(
            notificationOf(
                self.tenant,
                self.bob,
                eventId="exp-2",
                channels=("IN_APP",),
            )
        )
        notificationId = uuid.UUID(outcome.notifications[0].id)
        # make it pending-with-past-expiry directly in the DB
        from apps.notifications.infrastructure.models import NotificationRecordModel

        NotificationRecordModel.objects.filter(id=notificationId).update(
            status="PENDING", expiresAt=self._now() - timedelta(minutes=1)
        )
        result = container.expireNotificationsService().execute(
            type("ExpireCommand", (), {"limit": 50})()
        )
        self.assertEqual(result["expired"], 1)
        self.assertEqual(
            container.notificationRepository().getById(notificationId).status,
            "EXPIRED",
        )

    def testCancelBeforeDelivery(self) -> None:
        from apps.notifications.application.commands.notificationCommands import (
            CancelNotificationCommand,
        )

        outcome = self.create(notificationOf(self.tenant, self.bob, eventId="c-1"))
        notificationId = uuid.UUID(outcome.notifications[0].id)
        # return the row to PENDING (pre-delivery) — cancel only applies then
        from apps.notifications.infrastructure.models import NotificationRecordModel

        NotificationRecordModel.objects.filter(id=notificationId).update(status="PENDING")
        with self.createContext(self.alice):
            result = container.cancelNotificationService().execute(
                CancelNotificationCommand(notificationId=notificationId)
            )
        self.assertTrue(result["cancelled"])
        self.assertEqual(
            container.notificationRepository().getById(notificationId).status,
            "CANCELLED",
        )

    @staticmethod
    def _now():
        from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider

        return sharedKernelProvider("clock")().nowUtc()


class DeviceRegistryTests(NotificationEngineBase):
    def testRegisterManyDevicesPerUser(self) -> None:
        from apps.notifications.application.commands.notificationCommands import (
            RegisterDeviceCommand,
        )

        with self.createContext(self.bob):
            first = container.registerDeviceService().execute(
                RegisterDeviceCommand(
                    tenantId=self.tenant.id,
                    userId=self.bob.id,
                    platform="IOS",
                    deviceIdentifier="bob-phone",
                    pushToken="token-1",
                )
            )
            second = container.registerDeviceService().execute(
                RegisterDeviceCommand(
                    tenantId=self.tenant.id,
                    userId=self.bob.id,
                    platform="WEB",
                    deviceIdentifier="bob-browser",
                    pushToken="token-2",
                )
            )
            # same identifier again → token rotation, still one row (§15)
            rotated = container.registerDeviceService().execute(
                RegisterDeviceCommand(
                    tenantId=self.tenant.id,
                    userId=self.bob.id,
                    platform="IOS",
                    deviceIdentifier="bob-phone",
                    pushToken="token-3",
                )
            )
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(rotated.id, first.id)
        devices = container.deviceRepository().listForUser(self.tenant.id, self.bob.id)
        self.assertEqual(len(devices), 2)

    def testRevokedDeviceStopsReceivingPushImmediately(self) -> None:
        from apps.notifications.application.commands.notificationCommands import (
            RegisterDeviceCommand,
            SavePolicyCommand,
        )

        with self.createContext(self.bob):
            device = container.registerDeviceService().execute(
                RegisterDeviceCommand(
                    tenantId=self.tenant.id,
                    userId=self.bob.id,
                    platform="ANDROID",
                    deviceIdentifier="bob-android",
                    pushToken="tok",
                )
            )
        with self.createContext(self.alice):
            container.savePolicyService().execute(
                SavePolicyCommand(
                    tenantId=self.tenant.id,
                    policyKey="push.test",
                    matchType="TYPE",
                    matchValue="test.push",
                    channels=("IN_APP", "PUSH"),
                    priority="HIGH",
                )
            )
        outcome = self.create(
            notificationOf(self.tenant, self.bob, notificationType="test.push")
        )
        deliveryStatus = {
            d.channel: d.status
            for d in self.deliveriesOf(uuid.UUID(outcome.notifications[0].id))
        }
        self.assertEqual(deliveryStatus["PUSH"], "DELIVERED")

        from apps.notifications.application.commands.notificationCommands import (
            RevokeDeviceCommand,
        )

        with self.createContext(self.bob):
            container.revokeDeviceService().execute(
                RevokeDeviceCommand(deviceId=uuid.UUID(device.id), userId=self.bob.id)
            )
        second = self.create(
            notificationOf(
                self.tenant, self.bob, notificationType="test.push", eventId="p-2"
            )
        )
        secondRow = container.notificationRepository().getById(
            uuid.UUID(second.notifications[0].id)
        )
        self.assertEqual(secondRow.status, "PARTIALLY_DELIVERED")  # §47 in-app still works
        statuses = {
            d.channel: d.status
            for d in self.deliveriesOf(uuid.UUID(second.notifications[0].id))
        }
        self.assertEqual(statuses["PUSH"], "PERMANENTLY_FAILED")  # NO_ACTIVE_DEVICE


class SchedulingAndEscalationTests(NotificationEngineBase):
    def testDelayedScheduleFiresOnWorkerTick(self) -> None:
        from apps.notifications.application.commands.notificationCommands import (
            ScheduleNotificationCommand,
        )

        with self.createContext(self.alice):
            dto = container.scheduleNotificationService().execute(
                ScheduleNotificationCommand(
                    tenantId=self.tenant.id,
                    kind="DELAYED",
                    recipientSpec={"type": "USER", "value": str(self.bob.id)},
                    notificationType="report.daily",
                    category="REPORT",
                    priority="LOW",
                    title="گزارش روزانه",
                    delaySeconds=0,
                )
            )
        result = container.runDueSchedulesService().execute(
            type("SchedulesCommand", (), {"limit": 10})()
        )
        self.assertEqual(result["created"], 1)
        rows, _unread, _hasNext = container.notificationRepository().listForRecipient(
            self.tenant.id, self.bob.id
        )
        self.assertIn("report.daily", [row.notificationType for row in rows])

    def testRecurringScheduleStaysAlive(self) -> None:
        from apps.notifications.application.commands.notificationCommands import (
            ScheduleNotificationCommand,
        )

        with self.createContext(self.alice):
            dto = container.scheduleNotificationService().execute(
                ScheduleNotificationCommand(
                    tenantId=self.tenant.id,
                    kind="RECURRING",
                    recipientSpec={"type": "USER", "value": str(self.bob.id)},
                    notificationType="pulse.check",
                    category="SYSTEM",
                    priority="LOW",
                    title="pulse",
                    recurEverySeconds=3600,
                    scheduledAt=self._now(),
                )
            )
        container.runDueSchedulesService().execute(
            type("SchedulesCommand", (), {"limit": 10})()
        )
        schedule = container.scheduleRepository().getById(uuid.UUID(dto.id))
        self.assertEqual(schedule.status, "PENDING")  # stays alive (§22)

    @staticmethod
    def _now():
        from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider

        return sharedKernelProvider("clock")().nowUtc()


class OutboxConsumerTests(NotificationEngineBase):
    def testMeetingEventCreatesNotificationsForInvitees(self) -> None:
        from apps.communication.application.commands.communicationCommands import (
            CreateGroupConversationCommand,
            CreateMeetingCommand,
        )
        from apps.communication.infrastructure import container as commContainer
        from tests.support.phase8Helpers import grantCommAdmin

        grantCommAdmin(self.tenant, self.alice)

        with self.createContext(self.alice):
            conversation = commContainer.createGroupUseCase().execute(
                CreateGroupConversationCommand(
                    name="اتاق جلسات", memberIds=[str(self.bob.id)]
                )
            )
            commContainer.createMeetingUseCase().execute(
                CreateMeetingCommand(
                    title="جلسه هم‌راستایی",
                    conversationId=str(conversation.id),
                    inviteeIds=[str(self.bob.id)],
                )
            )
            # flush the outbox (production: the worker tick does this)
            commContainer.outboxDispatcher().dispatchDue()
        rows, _unread, _hasNext = container.notificationRepository().listForRecipient(
            self.tenant.id, self.bob.id
        )
        types = [row.notificationType for row in rows]
        self.assertIn("meeting.invitation", types)  # §30 consumer ran
        for row in rows:
            if row.notificationType == "meeting.invitation":
                self.assertEqual(row.status, "DELIVERED")

    def testTenantIsolationInRecipientResolution(self) -> None:
        other = ensureTenant("ntf_other_tenant")
        from apps.identity.infrastructure.models import TenantMembershipModel

        TenantMembershipModel.objects.create(
            userId=self.bob.id, tenantId=other.id, status="active"
        )
        outcome = self.create(notificationOf(other, self.bob, eventId="iso-1"))
        # listing must be scoped per tenant (§34)
        rows, _unread, _hasNext = container.notificationRepository().listForRecipient(
            self.tenant.id, self.bob.id
        )
        self.assertNotIn(uuid.UUID(outcome.notifications[0].id), [row.id for row in rows])
        otherRows, _u, _h = container.notificationRepository().listForRecipient(
            other.id, self.bob.id
        )
        self.assertIn(uuid.UUID(outcome.notifications[0].id), [row.id for row in otherRows])
