"""Phase 22 (§30) — maintenance workflow → notification engine integration.

The work-order lifecycle records domain events (assigned / submittedForApproval
/ approved / rejected). Those events flow through the shared in-process
dispatcher (§36) into the notification consumer (§30), which fans them out to
recipients by ROLE. These tests pin that wiring end-to-end: run the guarded WO
lifecycle over the public REST boundary, then assert the right role's inbox
received the right notification.
"""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from tests.support.phase6Helpers import (
    loginViaApi,
    platformTenantId,
    seedPlatform,
)


class WorkflowNotificationTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        # Recipients targeted by ROLE — the WO payload only carries a display
        # name, so notifications fan out to whoever holds the role.
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

    def _createDevice(self) -> dict:
        response = self.client.post(
            "/api/v1/maintenance/devices",
            {
                "code": "PUMP-N1",
                "name": "پمپ",
                "location": "سالن A",
                "department": "general",
                "pmIntervalDays": 30,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def _submit(self, deviceId: str) -> dict:
        response = self.client.post(
            "/api/v1/maintenance/work-orders",
            {
                "deviceId": deviceId,
                "title": "عیب پمپ",
                "description": "بررسی",
                "orderType": "corrective",
                "priority": "high",
                "requestedByName": "کاربر",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def _assign(self, orderId: str) -> None:
        response = self.client.post(
            f"/api/v1/maintenance/work-orders/{orderId}/assign",
            {"assignedToName": "رضا"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

    def _start(self, orderId: str) -> None:
        response = self.client.post(
            f"/api/v1/maintenance/work-orders/{orderId}/status",
            {"target": "inProgress"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

    def _submitForApproval(self, orderId: str) -> None:
        response = self.client.post(
            f"/api/v1/maintenance/work-orders/{orderId}/status",
            {"target": "pendingApproval", "resolutionNote": "انجام شد"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

    # -- tests ----------------------------------------------------------------

    def testAssignNotifiesTechnician(self) -> None:
        device = self._createDevice()
        order = self._submit(device["id"])
        self._assign(order["id"])
        self.assertIn("maintenance.workOrderAssigned", self._types(self.technicianId))

    def testSubmitForApprovalNotifiesManager(self) -> None:
        device = self._createDevice()
        order = self._submit(device["id"])
        self._assign(order["id"])
        self._start(order["id"])
        self._submitForApproval(order["id"])
        self.assertIn(
            "maintenance.workOrderSubmittedForApproval",
            self._types(self.managerId),
        )

    def testApproveNotifiesTechnician(self) -> None:
        device = self._createDevice()
        order = self._submit(device["id"])
        self._assign(order["id"])
        self._start(order["id"])
        self._submitForApproval(order["id"])
        response = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/approve",
            {"note": "تأیید شد"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("maintenance.workOrderApproved", self._types(self.technicianId))

    def testRejectNotifiesTechnician(self) -> None:
        device = self._createDevice()
        order = self._submit(device["id"])
        self._assign(order["id"])
        self._start(order["id"])
        self._submitForApproval(order["id"])
        response = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/reject",
            {"note": "نیاز به اصلاح"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("maintenance.workOrderRejected", self._types(self.technicianId))

    def testManagerDoesNotReceiveTechnicianNotifications(self) -> None:
        device = self._createDevice()
        order = self._submit(device["id"])
        self._assign(order["id"])
        # The assignment notification targets technicians, not managers.
        self.assertNotIn("maintenance.workOrderAssigned", self._types(self.managerId))
