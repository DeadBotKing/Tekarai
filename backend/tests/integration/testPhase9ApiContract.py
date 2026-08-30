"""Phase 9 API contract tests (§40 REST, §34 isolation, §42 recovery)."""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.notifications.infrastructure.container import container
from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from apps.tenancy.infrastructure.models import TenantModel
from tests.support.phase6Helpers import seedPlatform
from tests.support.phase8Helpers import ensureTenant, ensureUser
from tests.support.phase9Helpers import (
    apiClientWithToken,
    asUser,
    grantNotificationAdmin,
    notificationOf,
    sessionTokenFor,
)

BASE = "/api/v1/notifications"


class NotificationApiBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        seedPlatform()
        self.tenant = TenantModel.objects.get(code="platform")
        self.alice = ensureUser(self.tenant, "api-ntf-alice")
        self.bob = ensureUser(self.tenant, "api-ntf-bob")
        grantNotificationAdmin(self.tenant, self.alice)
        self.adminClient = apiClientWithToken(
            sessionTokenFor(self.alice.id, self.tenant.id)
        )
        self.bobClient = apiClientWithToken(sessionTokenFor(self.bob.id, self.tenant.id))

    def createFor(self, user, **overrides):
        with asUser(self.tenant.id, self.alice.id):
            return container.createNotificationService().execute(
                notificationOf(self.tenant, user, **overrides)
            )


class OwnNotificationApiTests(NotificationApiBase):
    def testListUnreadAndDetail(self) -> None:
        outcome = self.createFor(self.bob)
        notificationId = outcome.notifications[0].id

        response = self.bobClient.get(f"{BASE}/")
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertTrue(any(item["id"] == notificationId for item in body))
        self.assertEqual(response.json()["meta"]["unreadCount"], 1)

        unread = self.bobClient.get(f"{BASE}/?unread=true").json()["data"]
        self.assertEqual(len(unread), 1)

        detail = self.bobClient.get(f"{BASE}/{notificationId}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["data"]["status"], "DELIVERED")
        self.assertEqual(detail.json()["data"]["channels"], ["IN_APP"])

    def testMarkReadThenUnreadThenAcknowledge(self) -> None:
        notificationId = self.createFor(self.bob).notifications[0].id
        self.assertEqual(
            self.bobClient.post(f"{BASE}/{notificationId}/read").status_code, 200
        )
        self.assertEqual(
            self.bobClient.get(f"{BASE}/unread-count").json()["data"]["unreadCount"], 0
        )
        self.assertEqual(
            self.bobClient.delete(f"{BASE}/{notificationId}/read").status_code, 200
        )
        # §26 — acknowledge without requirement is refused
        ack = self.bobClient.post(f"{BASE}/{notificationId}/acknowledge")
        self.assertEqual(ack.status_code, 403)

    def testAcknowledgeRequiredFlow(self) -> None:
        notificationId = self.createFor(
            self.bob, eventId="ack-1", ackRequired=True
        ).notifications[0].id
        acknowledged = self.bobClient.post(f"{BASE}/{notificationId}/acknowledge")
        self.assertEqual(acknowledged.status_code, 200)
        detail = self.bobClient.get(f"{BASE}/{notificationId}").json()["data"]
        self.assertIsNotNone(detail["acknowledgedAt"])
        self.assertIsNotNone(detail["readAt"])  # ack implies read
        # unread blocked after acknowledgement (§26)
        self.assertEqual(
            self.bobClient.delete(f"{BASE}/{notificationId}/read").status_code, 409
        )

    def testArchiveHidesFromList(self) -> None:
        notificationId = self.createFor(self.bob, eventId="arch-1").notifications[0].id
        self.assertEqual(
            self.bobClient.post(f"{BASE}/{notificationId}/archive").status_code, 200
        )
        self.assertEqual(self.bobClient.get(f"{BASE}/").json()["data"], [])
        archived = self.bobClient.get(f"{BASE}/?archived=true").json()["data"]
        self.assertEqual(len(archived), 1)

    def testBulkReadForRecovery(self) -> None:
        first = self.createFor(self.bob, eventId="bulk-1").notifications[0].id
        second = self.createFor(self.bob, eventId="bulk-2").notifications[0].id
        response = self.bobClient.post(
            f"{BASE}/read-bulk", {"notificationIds": [first, second]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["markedRead"], 2)
        self.assertEqual(
            self.bobClient.get(f"{BASE}/unread-count").json()["data"]["unreadCount"], 0
        )

    def testCrossRecipientAccessIs404(self) -> None:
        notificationId = self.createFor(self.bob, eventId="iso-404").notifications[0].id
        self.assertEqual(self.adminClient.get(f"{BASE}/{notificationId}").status_code, 404)
        self.assertEqual(
            self.adminClient.post(f"{BASE}/{notificationId}/read").status_code, 404
        )


class PreferenceApiTests(NotificationApiBase):
    def testGetAndUpdatePreferences(self) -> None:
        initial = self.bobClient.get(f"{BASE}/preferences")
        self.assertEqual(initial.status_code, 200)
        self.assertIn("EMAIL", initial.json()["data"]["channels"])

        updated = self.bobClient.put(
            f"{BASE}/preferences",
            {
                "preferences": [
                    {"level": "GLOBAL", "channel": "EMAIL", "enabled": False},
                    {"level": "CATEGORY", "channel": "SMS",
                     "category": "SECURITY", "enabled": True},
                ]
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        channels = {row["channel"]: row for row in updated.json()["data"]}
        self.assertFalse(channels["EMAIL"]["enabled"])
        self.assertTrue(channels["SMS"]["enabled"])

    def testInvalidPreferenceRejected(self) -> None:
        response = self.bobClient.put(
            f"{BASE}/preferences",
            {"preferences": [{"level": "GLOBAL", "channel": "CARRIER_PIGEON"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 422)


class DeviceApiTests(NotificationApiBase):
    def testRegisterListRevoke(self) -> None:
        registered = self.bobClient.post(
            f"{BASE}/devices",
            {
                "platform": "IOS",
                "deviceIdentifier": "api-phone",
                "pushToken": "secret-token",  # §33 — never echoed back
            },
            format="json",
        )
        self.assertEqual(registered.status_code, 201)
        deviceId = registered.json()["data"]["id"]
        self.assertNotIn("pushToken", str(registered.json()["data"]))
        self.assertNotIn("secret-token", registered.content.decode())

        listed = self.bobClient.get(f"{BASE}/devices").json()["data"]
        self.assertEqual(len(listed), 1)

        revoked = self.bobClient.delete(f"{BASE}/devices/{deviceId}")
        self.assertEqual(revoked.status_code, 200)
        active = self.bobClient.get(f"{BASE}/devices?active=true").json()["data"]
        self.assertEqual(active, [])


class AdminApiTests(NotificationApiBase):
    def testMemberCannotSendButAdminCan(self) -> None:
        forbidden = self.bobClient.post(
            f"{BASE}/admin/send",
            {
                "recipientType": "USER",
                "recipientValue": [str(self.bob.id)],
                "notificationType": "admin.push",
                "category": "SYSTEM",
                "priority": "NORMAL",
                "title": "از مدیر",
            },
            format="json",
        )
        self.assertEqual(forbidden.status_code, 403)

        allowed = self.adminClient.post(
            f"{BASE}/admin/send",
            {
                "recipientType": "USER",
                "recipientValue": [str(self.bob.id)],
                "notificationType": "admin.push",
                "category": "SYSTEM",
                "priority": "NORMAL",
                "title": "از مدیر",
            },
            format="json",
        )
        self.assertEqual(allowed.status_code, 201)
        self.assertEqual(len(allowed.json()["data"]["notifications"]), 1)

    def testTemplateVersioningThroughApi(self) -> None:
        first = self.adminClient.post(
            f"{BASE}/admin/templates",
            {
                "templateKey": "api.test",
                "language": "fa-IR",
                "channel": "IN_APP",
                "title": "نسخه یک",
            },
            format="json",
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["data"]["version"], 1)
        second = self.adminClient.post(
            f"{BASE}/admin/templates",
            {
                "templateKey": "api.test",
                "language": "fa-IR",
                "channel": "IN_APP",
                "title": "نسخه دو",
            },
            format="json",
        )
        self.assertEqual(second.json()["data"]["version"], 2)  # §19
        versions = self.adminClient.get(
            f"{BASE}/admin/templates?templateKey=api.test&language=fa-IR&channel=IN_APP"
        ).json()["data"]
        self.assertEqual(len(versions), 1)  # only the active row lists
        self.assertEqual(versions[0]["version"], 2)

    def testPolicyAndTenantRuleLifecycle(self) -> None:
        policy = self.adminClient.post(
            f"{BASE}/admin/policies",
            {
                "policyKey": "api.policy",
                "matchType": "TYPE",
                "matchValue": "api.typed",
                "channels": ["IN_APP", "PUSH"],
                "priority": "HIGH",
            },
            format="json",
        )
        self.assertEqual(policy.status_code, 201)
        policyId = policy.json()["data"]["id"]
        listed = self.adminClient.get(f"{BASE}/admin/policies").json()["data"]
        self.assertTrue(any(item["id"] == policyId for item in listed))

        rule = self.adminClient.post(
            f"{BASE}/admin/tenant-rules",
            {"effect": "DENIED", "channel": "SMS"},
            format="json",
        )
        self.assertEqual(rule.status_code, 201)
        ruleId = rule.json()["data"]["id"]
        deleted = self.adminClient.delete(f"{BASE}/admin/tenant-rules/{ruleId}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            self.adminClient.delete(f"{BASE}/admin/policies/{policyId}").status_code, 200
        )

    def testTenantRuleCannotDenySecurityInApp(self) -> None:
        """§11 — tenant rules may never weaken platform security delivery."""
        response = self.adminClient.post(
            f"{BASE}/admin/tenant-rules",
            {"effect": "DENIED", "channel": "IN_APP", "category": "SECURITY"},
            format="json",
        )
        self.assertEqual(response.status_code, 422)

    def testChannelCatalogAndMetrics(self) -> None:
        channels = self.adminClient.get(f"{BASE}/admin/channels")
        self.assertEqual(channels.status_code, 200)
        names = [row["channel"] for row in channels.json()["data"]["channels"]]
        self.assertIn("IN_APP", names)
        self.assertIn("EMAIL", names)

        self.createFor(self.bob, eventId="metrics-1")
        metrics = self.adminClient.get(f"{BASE}/admin/metrics").json()["data"]
        for key in (
            "notificationsCreated",
            "notificationsDelivered",
            "deliveryLatencyMs",
            "readRate",
            "acknowledgementRate",
            "channelUsage",
            "retryRate",
            "providerFailureRate",
            "notificationVolume",
        ):
            self.assertIn(key, metrics)  # §44 exact names

    def testScheduleLifecycle(self) -> None:
        created = self.adminClient.post(
            f"{BASE}/admin/schedules",
            {
                "kind": "SCHEDULED",
                "recipientType": "USER",
                "recipientValue": [str(self.bob.id)],
                "notificationType": "api.scheduled",
                "category": "SYSTEM",
                "priority": "LOW",
                "title": "زمان‌بندی‌شده",
                "scheduledAt": "2026-09-01T09:00:00Z",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        scheduleId = created.json()["data"]["id"]
        listed = self.adminClient.get(f"{BASE}/admin/schedules").json()["data"]
        self.assertTrue(any(item["id"] == scheduleId for item in listed))
        cancelled = self.adminClient.delete(f"{BASE}/admin/schedules/{scheduleId}")
        self.assertEqual(cancelled.status_code, 200)
