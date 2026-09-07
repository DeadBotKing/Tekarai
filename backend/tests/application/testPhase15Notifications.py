"""Phase 15 Notification Platform completion tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from unittest import mock

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.notifications.application.commands.notificationCommands import RegisterDeviceCommand
from apps.notifications.application.commands.phase12Commands import (
    CreateBroadcastCommand,
)
from apps.notifications.application.commands.phase15Commands import (
    ProcessProviderWebhookCommand,
    RegisterPushSubscriptionCommand,
    RunNotificationCleanupCommand,
    SaveProviderConfigurationCommand,
    SearchNotificationsQuery,
)
from apps.notifications.domain.entities.phase12Records import BroadcastNotification
from apps.notifications.domain.valueObjects.phase15Types import (
    sanitizedMetadata,
    verifyWebhookSignature,
)
from apps.notifications.infrastructure import container
from apps.notifications.infrastructure.models import (
    NotificationAuditModel,
    NotificationCleanupRunModel,
    NotificationDeviceModel,
    NotificationModel,
    NotificationPushSubscriptionModel,
    NotificationRecipientDeliveryModel,
)
from apps.notifications.infrastructure.queue.notificationQueue import CeleryNotificationQueue
from apps.sharedKernel.domain.errors import ConflictError, ValidationFailedError
from tests.application.testPhase12UseCases import Phase12Base


class Phase15NotificationTests(Phase12Base):
    def testNotificationLifecycleAndVersionedPayload(self) -> None:
        now = timezone.now()
        notification = BroadcastNotification.create(
            self.tenant.id,
            "SECURITY_ALERT",
            "Alert",
            "Review",
            [self.u1.id],
            now,
            actorId=self.admin.id,
            payloadVersion=2,
            expiresAt=now + timedelta(hours=1),
        )
        self.assertTrue(notification.canSend(now))
        notification.queue(now)
        self.assertEqual(notification.status, "QUEUED")
        self.assertEqual(notification.payloadVersion, 2)
        notification.cancel(now)
        self.assertEqual(notification.status, "CANCELLED")

    def testWebhookSignatureAndMetadataSecurity(self) -> None:
        body = b'{"status":"DELIVERED"}'
        timestamp = str(int(time.time()))
        signature = hmac.new(
            b"secret", timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        verifyWebhookSignature(
            body,
            signature=signature,
            timestamp=timestamp,
            secret="secret",
            nowEpoch=int(time.time()),
        )
        with self.assertRaises(ValidationFailedError):
            verifyWebhookSignature(
                body,
                signature="bad",
                timestamp=timestamp,
                secret="secret",
                nowEpoch=int(time.time()),
            )
        self.assertEqual(
            sanitizedMetadata({"apiKey": "secret", "safe": "yes"})["apiKey"],
            "[REDACTED]",
        )

    def testDeviceTokenIsEncryptedAtRestAndRotates(self) -> None:
        with self.context(self.tenant, self.u1):
            container.container.registerDeviceService().execute(
                RegisterDeviceCommand(
                    tenantId=self.tenant.id,
                    userId=self.u1.id,
                    platform="WEB",
                    deviceIdentifier="browser-1",
                    pushToken="plain-sensitive-token",
                )
            )
        row = NotificationDeviceModel.objects.get(deviceIdentifier="browser-1")
        self.assertNotIn("plain-sensitive-token", row.pushToken)
        self.assertTrue(row.pushToken.startswith("ntf1."))
        loaded = container.container.deviceRepository().getById(row.id)
        self.assertEqual(loaded.pushToken, "plain-sensitive-token")

    def testWebPushSubscriptionNeverReturnsOrStoresPlainSecrets(self) -> None:
        with self.context(self.tenant, self.u1):
            result = container.phase15PushSubscriptionService().execute(
                RegisterPushSubscriptionCommand(
                    endpoint="https://push.example.test/sub/123",
                    publicKey="public-key",
                    authSecret="private-auth-secret",
                )
            )
            listed = container.phase15PushSubscriptionService().execute(None)
        row = NotificationPushSubscriptionModel.objects.get(id=result["id"])
        self.assertNotIn("private-auth-secret", row.encryptedSubscription)
        self.assertNotIn("push.example.test", row.encryptedSubscription)
        self.assertNotIn("endpoint", result)
        self.assertEqual(listed[0]["endpointHash"], result["endpointHash"])
        webDevices = [
            device
            for device in container.container.deviceRepository().activeForUser(
                self.tenant.id, self.u1.id
            )
            if device.provider == "WEB_PUSH"
        ]
        self.assertEqual(webDevices[0].pushToken, "https://push.example.test/sub/123")

    def testProviderConfigurationStoresReferenceNotRawCredential(self) -> None:
        with self.context(self.tenant, self.admin):
            result = container.phase15ProviderConfigurationService().execute(
                SaveProviderConfigurationCommand(
                    channel="EMAIL",
                    provider="ACME",
                    credentialRef="vault://notifications/acme",
                    configuration={"region": "eu", "apiKey": "must-not-store"},
                )
            )
        self.assertEqual(result["credentialRef"], "vault://notifications/acme")
        self.assertEqual(result["configuration"]["apiKey"], "[REDACTED]")

    @override_settings(NOTIFICATION_WEBHOOK_SECRETS={"ACME": "callback-secret"})
    def testProviderWebhookIsSignedIdempotentAndMonotonic(self) -> None:
        delivery = NotificationRecipientDeliveryModel.objects.create(
            tenantId=self.tenant.id,
            notificationId=uuid.uuid4(),
            recipientId=self.u1.id,
            channel="EMAIL",
            provider="ACME",
            providerMessageId="provider-message-1",
            deliveryStatus="SENT",
            sentAt=timezone.now(),
        )
        payload = {
            "eventId": "provider-event-1",
            "providerMessageId": "provider-message-1",
            "status": "DELIVERED",
            "metadata": {"region": "eu"},
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(
            b"callback-secret", timestamp.encode() + b"." + raw, hashlib.sha256
        ).hexdigest()
        command = ProcessProviderWebhookCommand(
            tenantId=str(self.tenant.id),
            provider="ACME",
            providerEventId=payload["eventId"],
            providerMessageId=payload["providerMessageId"],
            status=payload["status"],
            timestamp=timestamp,
            signature=signature,
            rawBody=raw,
            metadata=payload["metadata"],
        )
        first = container.phase15ProviderWebhookService().execute(command)
        second = container.phase15ProviderWebhookService().execute(command)
        delivery.refresh_from_db()
        self.assertTrue(first["processed"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(delivery.deliveryStatus, "DELIVERED")
        changed = ProcessProviderWebhookCommand(**{**command.__dict__, "status": "FAILED"})
        with self.assertRaises(ConflictError):
            container.phase15ProviderWebhookService().execute(changed)

    def testSearchIsTenantAndRecipientScoped(self) -> None:
        with self.context(self.tenant, self.admin):
            mine = container.createBroadcastService().execute(
                CreateBroadcastCommand(
                    notificationType="TASK_ASSIGNED",
                    title="Unique searchable title",
                    recipientIds=(self.u1.id,),
                )
            )
            container.deliveryDispatchService().fanOut(mine)
        with self.context(self.tenant, self.u1):
            found = container.phase15SearchService().execute(
                SearchNotificationsQuery(query="searchable", readState="UNREAD")
            )
        with self.context(self.tenant, self.u2):
            hidden = container.phase15SearchService().execute(
                SearchNotificationsQuery(query="searchable")
            )
        self.assertEqual(found[0]["id"], str(mine.id))
        self.assertEqual(hidden, ())

    def testBulkFanoutUsesBoundedDatabaseQueries(self) -> None:
        recipients = tuple(uuid.uuid4() for _ in range(1000))
        with self.context(self.tenant, self.admin):
            with CaptureQueriesContext(connection) as captured:
                notification = container.createBroadcastService().execute(
                    CreateBroadcastCommand(
                        notificationType="BULK",
                        title="Bulk",
                        recipientIds=recipients,
                    )
                )
                container.deliveryDispatchService().fanOut(notification)
        self.assertEqual(len(notification.recipients), 1000)
        self.assertEqual(
            NotificationRecipientDeliveryModel.objects.filter(
                notificationId=notification.id
            ).count(),
            2000,  # NORMAL routes to IN_APP + EMAIL
        )
        self.assertLess(len(captured), 30)

    def testCleanupPreviewExecutionRetainsImmutableAudit(self) -> None:
        with self.context(self.tenant, self.admin):
            notification = container.createBroadcastService().execute(
                CreateBroadcastCommand(
                    notificationType="OLD", title="Old", recipientIds=(self.u1.id,)
                )
            )
        old = timezone.now() - timedelta(days=400)
        NotificationModel.objects.filter(id=notification.id).update(
            status="DELIVERED", createdAt=old, deliveredAt=old
        )
        NotificationAuditModel.objects.create(
            tenantId=self.tenant.id,
            eventType="NOTIFICATION_DELIVERED",
            resourceType="Notification",
            resourceId=str(notification.id),
        )
        with self.context(self.tenant, self.admin):
            preview = container.phase15CleanupService().execute(
                RunNotificationCleanupCommand(retentionDays=365, dryRun=True)
            )
            executed = container.phase15CleanupService().execute(
                RunNotificationCleanupCommand(retentionDays=365, dryRun=False)
            )
        self.assertEqual(preview["counts"]["notifications"], 1)
        self.assertEqual(executed["counts"]["notifications"], 1)
        self.assertFalse(NotificationModel.objects.filter(id=notification.id).exists())
        self.assertTrue(NotificationAuditModel.objects.exists())
        self.assertEqual(NotificationCleanupRunModel.objects.count(), 2)

    def testCeleryQueuePublishesOnlyAfterCommit(self) -> None:
        queue = CeleryNotificationQueue()
        with mock.patch("apps.notifications.tasks.dispatchNotificationJob.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                queue.submit({"kind": "DISPATCH", "notificationId": "n-1"})
        delay.assert_called_once_with("n-1")
