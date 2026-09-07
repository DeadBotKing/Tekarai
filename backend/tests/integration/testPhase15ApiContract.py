"""Phase 15 HTTP, webhook and security contract tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

from django.test import override_settings

from apps.notifications.infrastructure.models import (
    NotificationProviderConfigurationModel,
    NotificationRecipientDeliveryModel,
)
from tests.integration.testPhase12ApiContract import Phase12ApiBase
from tests.support.phase9Helpers import sessionTokenFor

BASE = "/api/v1/notifications"


class Phase15ApiContractTests(Phase12ApiBase):
    def testAuthenticatedNonAdminCannotCreateBroadcast(self) -> None:
        token = sessionTokenFor(self.u1.id, self.tenant.id)
        response = self.client.post(
            f"{BASE}/broadcasts",
            {
                "notificationType": "ABUSE",
                "title": "forbidden",
                "recipientIds": [str(self.admin.id)],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 403, response.content)

    def testPushSubscriptionAndProviderConfiguration(self) -> None:
        subscription = self.client.post(
            f"{BASE}/push-subscriptions",
            {
                "endpoint": "https://push.example.test/api/subscription",
                "publicKey": "public-key",
                "authSecret": "private-secret",
            },
            format="json",
            **self.auth(),
        )
        self.assertEqual(subscription.status_code, 201, subscription.content)
        self.assertNotIn("private-secret", str(subscription.json()))
        listed = self.client.get(f"{BASE}/push-subscriptions", **self.auth())
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(len(listed.json()["data"]), 1)

        configured = self.client.post(
            f"{BASE}/admin/providers",
            {
                "channel": "EMAIL",
                "provider": "ACME",
                "credentialRef": "vault://acme",
                "configuration": {"region": "eu", "password": "redact-me"},
            },
            format="json",
            **self.auth(),
        )
        self.assertEqual(configured.status_code, 201, configured.content)
        self.assertNotIn("redact-me", str(configured.json()))
        self.assertEqual(NotificationProviderConfigurationModel.objects.count(), 1)

    def testSearchAndCleanupRequireAuthentication(self) -> None:
        for method, path in (
            ("get", f"{BASE}/search?q=alert"),
            ("get", f"{BASE}/push-subscriptions"),
            ("get", f"{BASE}/admin/providers"),
            ("post", f"{BASE}/admin/cleanup-runs"),
        ):
            response = getattr(self.client, method)(path, {}, format="json")
            self.assertEqual(response.status_code, 401, (path, response.content))

    @override_settings(NOTIFICATION_WEBHOOK_SECRETS={"ACME": "api-secret"})
    def testSignedProviderWebhookAndDuplicate(self) -> None:
        delivery = NotificationRecipientDeliveryModel.objects.create(
            tenantId=self.tenant.id,
            notificationId=uuid.uuid4(),
            recipientId=self.admin.id,
            channel="EMAIL",
            provider="ACME",
            providerMessageId="msg-api-1",
            deliveryStatus="SENT",
        )
        payload = {
            "eventId": "evt-api-1",
            "providerMessageId": "msg-api-1",
            "status": "DELIVERED",
            "metadata": {"source": "provider"},
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(
            b"api-secret", timestamp.encode() + b"." + raw, hashlib.sha256
        ).hexdigest()
        path = f"{BASE}/provider-webhooks/{self.tenant.id}/ACME"
        headers = {
            "HTTP_X_WEBHOOK_TIMESTAMP": timestamp,
            "HTTP_X_WEBHOOK_SIGNATURE": signature,
        }
        first = self.client.generic("POST", path, raw, content_type="application/json", **headers)
        second = self.client.generic("POST", path, raw, content_type="application/json", **headers)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertTrue(second.json()["data"]["duplicate"])
        delivery.refresh_from_db()
        self.assertEqual(delivery.deliveryStatus, "DELIVERED")

    @override_settings(NOTIFICATION_WEBHOOK_SECRETS={"ACME": "api-secret"})
    def testProviderWebhookRejectsInvalidSignature(self) -> None:
        payload = {
            "eventId": "evt-invalid",
            "providerMessageId": "missing",
            "status": "FAILED",
        }
        raw = json.dumps(payload).encode()
        response = self.client.generic(
            "POST",
            f"{BASE}/provider-webhooks/{self.tenant.id}/ACME",
            raw,
            content_type="application/json",
            HTTP_X_WEBHOOK_TIMESTAMP=str(int(time.time())),
            HTTP_X_WEBHOOK_SIGNATURE="invalid",
        )
        self.assertIn(response.status_code, (400, 422))
