"""Phase 12 integration tests — REST contract for the multi-recipient
notification platform (docs/Phases/Phase12.md).

Real HTTP login → bearer → view → service → ORM over /api/v1/notifications:
broadcast creation + fan-out (§12.3/§12.5), per-recipient read state (§12.8),
unread count, dead-letter deliveries + retry (§12.18), rules (§12.24) and
idempotent event intake (§12.38). §12.26/§12.51: unauthenticated refused.
"""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.identity.infrastructure.models import UserModel
from apps.tenancy.infrastructure.models import TenantModel
from tests.support.phase6Helpers import (
    PLATFORM_ADMIN_PASSWORD,
    PLATFORM_ADMIN_USERNAME,
    seedPlatform,
)
from tests.support.phase8Helpers import ensureUser
from tests.support.phase9Helpers import grantNotificationAdmin

BASE = "/api/v1/notifications"


class Phase12ApiBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        seedPlatform()
        from tests.support.phase6Helpers import platformTenantId

        self.tenantId = str(platformTenantId())
        self.tenant = TenantModel.objects.get(id=self.tenantId)
        grantNotificationAdmin(
            self.tenant,
            UserModel.objects.get(username=PLATFORM_ADMIN_USERNAME),
        )
        self.admin = UserModel.objects.get(username=PLATFORM_ADMIN_USERNAME)
        self.u1 = ensureUser(self.tenant, "p12_bob")
        self.client = APIClient()
        self.token = self.login(PLATFORM_ADMIN_USERNAME)

    def login(self, username: str, password: str = PLATFORM_ADMIN_PASSWORD) -> str:
        response = self.client.post(
            "/api/v1/auth/login",
            {"tenantCode": "platform", "identifier": username, "password": password},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]["accessToken"]

    def auth(self, token: str | None = None) -> dict:
        return {"HTTP_AUTHORIZATION": f"Bearer {token or self.token}"}


class BroadcastApiTests(Phase12ApiBase):
    def _create(self, priority="NORMAL", recipient=None, idem=""):
        return self.client.post(
            f"{BASE}/broadcasts",
            {
                "notificationType": "TASK_ASSIGNED",
                "title": "Task assigned",
                "body": "please review",
                "recipientIds": [str(recipient or self.u1.id)],
                "priority": priority,
                "idempotencyKey": idem,
            },
            format="json",
            **self.auth(),
        )

    def testCreateBroadcastFanOut(self) -> None:
        res = self._create(priority="CRITICAL", idem="b-1")
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()["data"]
        self.assertEqual(data["priority"], "CRITICAL")
        # CRITICAL fans out to IN_APP/EMAIL/PUSH/SMS/WEBHOOK
        deliveries = self.client.get(
            f"{BASE}/deliveries?notificationId={data['id']}", **self.auth()
        ).json()["data"]
        channels = {d["channel"] for d in deliveries}
        self.assertIn("SMS", channels)
        self.assertIn("WEBHOOK", channels)

    def testUnauthenticatedRefused(self) -> None:
        res = self.client.post(
            f"{BASE}/broadcasts",
            {"notificationType": "X", "title": "t", "recipientIds": [str(self.u1.id)]},
            format="json",
        )
        self.assertEqual(res.status_code, 401)

    def testEmptyRecipientsRejected(self) -> None:
        res = self.client.post(
            f"{BASE}/broadcasts",
            {"notificationType": "X", "title": "t", "recipientIds": []},
            format="json",
            **self.auth(),
        )
        self.assertEqual(res.status_code, 400)


class RecipientStateApiTests(Phase12ApiBase):
    def testUnreadCountAndReadState(self) -> None:
        create = self.client.post(
            f"{BASE}/broadcasts",
            {
                "notificationType": "X",
                "title": "hi",
                "recipientIds": [str(self.admin.id)],
                "priority": "LOW",
            },
            format="json",
            **self.auth(),
        )
        nid = create.json()["data"]["id"]
        # admin is a recipient
        count = self.client.get(f"{BASE}/broadcasts/unread-count", **self.auth())
        self.assertEqual(count.json()["data"]["unreadCount"], 1)
        read = self.client.post(
            f"{BASE}/broadcasts/{nid}/read", {}, **self.auth()
        )
        self.assertEqual(read.status_code, 200, read.content)
        self.assertEqual(read.json()["data"]["state"], "READ")
        count = self.client.get(f"{BASE}/broadcasts/unread-count", **self.auth())
        self.assertEqual(count.json()["data"]["unreadCount"], 0)
        unread = self.client.post(
            f"{BASE}/broadcasts/{nid}/unread", {}, **self.auth()
        )
        self.assertEqual(unread.json()["data"]["state"], "UNREAD")

    def testInboxList(self) -> None:
        self.client.post(
            f"{BASE}/broadcasts",
            {"notificationType": "X", "title": "a", "recipientIds": [str(self.admin.id)],
             "priority": "LOW"},
            format="json", **self.auth(),
        )
        items = self.client.get(f"{BASE}/broadcasts", **self.auth()).json()["data"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["state"], "UNREAD")


class DeliveryApiTests(Phase12ApiBase):
    def testDeadLetterAndRetry(self) -> None:
        # create a CRITICAL broadcast then force a delivery into DEAD_LETTER
        res = self.client.post(
            f"{BASE}/broadcasts",
            {"notificationType": "X", "title": "t",
             "recipientIds": [str(self.u1.id)], "priority": "CRITICAL"},
            format="json", **self.auth(),
        )
        nid = res.json()["data"]["id"]
        from apps.notifications.infrastructure.models import (
            NotificationRecipientDeliveryModel,
        )

        delivery = NotificationRecipientDeliveryModel.objects.filter(
            notificationId=uuid.UUID(nid), channel="EMAIL"
        ).first()
        self.assertIsNotNone(delivery)
        delivery.deliveryStatus = "DEAD_LETTER"
        delivery.save()
        # ops lists dead letters
        dead = self.client.get(
            f"{BASE}/deliveries?deadLetterOnly=1", **self.auth()
        ).json()["data"]
        self.assertTrue(any(d["id"] == str(delivery.id) for d in dead))
        # manual retry
        retry = self.client.post(
            f"{BASE}/deliveries/{delivery.id}/retry", {}, **self.auth()
        )
        self.assertEqual(retry.status_code, 200, retry.content)
        self.assertIn(retry.json()["data"]["status"], ("DELIVERED", "QUEUED", "DEAD_LETTER"))


class RuleAndEventApiTests(Phase12ApiBase):
    def testRuleThenEventCreatesNotification(self) -> None:
        rule = self.client.post(
            f"{BASE}/rules",
            {
                "name": "task assigned",
                "eventType": "TASK_ASSIGNED",
                "recipientStrategy": "TARGET",
                "channels": ["IN_APP"],
                "priority": "HIGH",
            },
            format="json", **self.auth(),
        )
        self.assertEqual(rule.status_code, 201, rule.content)
        # ingest event twice -> only one notification
        payload = {
            "eventId": "evt-api-1",
            "eventType": "TASK_ASSIGNED",
            "payload": {"title": "You have a task", "recipientIds": [str(self.u1.id)]},
        }
        first = self.client.post(f"{BASE}/events", payload, format="json", **self.auth())
        second = self.client.post(f"{BASE}/events", payload, format="json", **self.auth())
        self.assertEqual(first.json()["data"]["created"], 1)
        self.assertEqual(second.json()["data"]["created"], 0)

    def testEventNotMatchingRuleCreatesNothing(self) -> None:
        self.client.post(
            f"{BASE}/rules",
            {"name": "high overdue", "eventType": "TASK_OVERDUE",
             "condition": {"priority": "HIGH"}, "recipientStrategy": "TARGET"},
            format="json", **self.auth(),
        )
        res = self.client.post(
            f"{BASE}/events",
            {"eventId": "evt-api-2", "eventType": "TASK_OVERDUE",
             "payload": {"priority": "LOW", "recipientIds": [str(self.u1.id)]}},
            format="json", **self.auth(),
        )
        self.assertEqual(res.json()["data"]["created"], 0)
