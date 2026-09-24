"""PM reminders (§30) — schedule scan → notification engine integration.

``SendPmRemindersUseCase`` scans every device's PM schedule and records
``devicePmDueSoon`` / ``devicePmOverdue`` domain events. Those events flow
through the shared in-process dispatcher (§36) into the notification consumer
(§30), which fans them out by ROLE to maintenance technicians and managers.

These tests pin that wiring end-to-end over the public REST boundary:
register a device, complete a PM so the next cycle is near (or past), trigger
the reminder scan, then assert the right role inboxes received the right
notification — and that re-running the scan stays idempotent (§29).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from tests.support.phase6Helpers import (
    loginViaApi,
    platformTenantId,
    seedPlatform,
)


class PmReminderNotificationTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        self.today = timezone.now().date()
        # Reminders fan out by ROLE — both maintenance roles must receive them.
        self.technicianId = self._createRoleUser("tech1", "maintenanceTechnician")
        self.managerId = self._createRoleUser("manager1", "maintenanceManager")

    # -- helpers --------------------------------------------------------------

    def _createRoleUser(self, username: str, roleCode: str) -> uuid.UUID:
        from apps.identity.infrastructure.models import RoleModel, UserModel, UserRoleModel
        from apps.identity.infrastructure.services.authorizationCache import bumpVersion

        user = UserModel.objects.create(
            id=uuid.uuid4(),
            tenantId=self.tenantId,
            username=username,
            email=f"{username}@tekarai.local",
            displayName=username,
            passwordHash="x",
            status="active",
        )
        roleId = RoleModel.objects.get(code=roleCode).id
        UserRoleModel.objects.create(
            id=uuid.uuid4(),
            userId=user.id,
            roleId=roleId,
            tenantId=self.tenantId,
            scopeType="TENANT",
        )
        bumpVersion(user.id)
        return user.id

    def _inbox(self, userId: uuid.UUID) -> list:
        from apps.notifications.application.queries.notificationQueries import (
            ListNotificationsQuery,
        )
        from apps.notifications.infrastructure.container import container

        page = container.listNotificationsUseCase().execute(
            ListNotificationsQuery(tenantId=self.tenantId, recipientId=userId, limit=100)
        )
        return list(page.items)

    def _types(self, userId: uuid.UUID) -> set[str]:
        return {item.notificationType for item in self._inbox(userId)}

    def _createDevice(self, code: str, pmIntervalDays: int) -> dict:
        response = self.client.post(
            "/api/v1/maintenance/devices",
            {
                "code": code,
                "name": f"پمپ {code}",
                "location": "سالن A",
                "department": "general",
                "pmIntervalDays": pmIntervalDays,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def _recordPm(self, deviceId: str, performedOn) -> None:
        response = self.client.post(
            f"/api/v1/maintenance/devices/{deviceId}/pm",
            {"performedOn": performedOn.isoformat()},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

    def _runScan(self, leadDays: int = 3) -> dict:
        response = self.client.post(
            "/api/v1/maintenance/devices/pm-reminders",
            {"leadDays": leadDays},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    # -- tests ----------------------------------------------------------------

    def testDueSoonReminderReachesBothMaintenanceRoles(self) -> None:
        device = self._createDevice("PUMP-R1", pmIntervalDays=30)
        # Last PM 28 days ago with a 30-day interval → due in 2 days.
        self._recordPm(device["id"], self.today - timedelta(days=28))

        body = self._runScan(leadDays=3)
        self.assertEqual(body["meta"]["dueSoonCount"], 1, body)
        self.assertEqual(body["meta"]["overdueCount"], 0, body)

        for userId in (self.technicianId, self.managerId):
            self.assertIn("maintenance.pmDueSoon", self._types(userId))

    def testOverdueReminderIsUrgent(self) -> None:
        device = self._createDevice("PUMP-R2", pmIntervalDays=30)
        # Last PM 40 days ago with a 30-day interval → 10 days overdue.
        self._recordPm(device["id"], self.today - timedelta(days=40))

        body = self._runScan(leadDays=3)
        self.assertEqual(body["meta"]["overdueCount"], 1, body)

        inbox = [
            item
            for item in self._inbox(self.managerId)
            if item.notificationType == "maintenance.pmOverdue"
        ]
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0].priority, "URGENT")
        self.assertEqual(inbox[0].category, "MAINTENANCE")

    def testScanIsIdempotentWithinTheSamePmCycle(self) -> None:
        device = self._createDevice("PUMP-R3", pmIntervalDays=30)
        self._recordPm(device["id"], self.today - timedelta(days=29))

        self._runScan(leadDays=3)
        firstCount = len(self._inbox(self.technicianId))
        self.assertGreater(firstCount, 0)

        # Same cycle, same eventId → §29 idempotency key suppresses duplicates.
        self._runScan(leadDays=3)
        self.assertEqual(len(self._inbox(self.technicianId)), firstCount)

    def testDeviceNotNearDueRaisesNothing(self) -> None:
        device = self._createDevice("PUMP-R4", pmIntervalDays=30)
        self._recordPm(device["id"], self.today)  # next PM a full cycle away

        body = self._runScan(leadDays=3)
        self.assertEqual(body["meta"]["dueSoonCount"], 0, body)
        self.assertEqual(body["meta"]["overdueCount"], 0, body)
        self.assertNotIn("maintenance.pmDueSoon", self._types(self.technicianId))
        self.assertNotIn("maintenance.pmOverdue", self._types(self.technicianId))

    def testManagementCommandScansTenants(self) -> None:
        from apps.maintenance.management.commands.sendPmReminders import scanTenants

        device = self._createDevice("PUMP-R5", pmIntervalDays=30)
        self._recordPm(device["id"], self.today - timedelta(days=28))

        summaries = scanTenants(leadDays=3)
        matching = [s for s in summaries if s["tenantId"] == str(self.tenantId)]
        self.assertEqual(len(matching), 1, summaries)
        self.assertEqual(matching[0]["dueSoon"], 1, summaries)
        self.assertIn("maintenance.pmDueSoon", self._types(self.technicianId))
