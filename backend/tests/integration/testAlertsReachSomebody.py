"""Scheduled alerts must land on a real person.

Every operational alert in the product is routed to the ``maintenanceManager``
role. Nobody held that role on a seeded install, so the notification engine
resolved zero recipients, created nothing, and reported success — a low-stock
scan would report "1 low stock part" and notify no one. Two defences are
pinned here:

1. the seed grants the role, so the intended routing works; and
2. the engine falls back to the tenant admins when a target role is empty,
   so a mis-provisioned tenant still gets told.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from apps.identity.application.services import profileDirectory
from apps.maintenance.infrastructure.models import SparePartModel
from apps.notifications.infrastructure.models import NotificationRecordModel
from tests.support.phase6Helpers import PLATFORM_TENANT_CODE, seedPlatform


def _platformTenantId() -> uuid.UUID:
    from apps.tenancy.infrastructure.models import TenantModel

    return TenantModel.objects.get(code=PLATFORM_TENANT_CODE).id


class SeededRoleHoldersTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()

    def testSomebodyHoldsTheRoleAlertsAreRoutedTo(self) -> None:
        holders = profileDirectory.userIdsOfRole(_platformTenantId(), ["maintenanceManager"])
        self.assertTrue(
            holders,
            "no user holds maintenanceManager, so every role-targeted alert is discarded",
        )


class LowStockAlertDeliveryTest(TestCase):
    """The existing maintenance scan, end to end, through the engine."""

    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = _platformTenantId()

    def testLowStockScanProducesANotification(self) -> None:
        from apps.maintenance.management.commands.checkMaintenanceAlerts import scanTenants

        SparePartModel.objects.create(
            tenantId=self.tenantId,
            code="BRG-LOW",
            name="بلبرینگ کم‌موجود",
            quantityOnHand=Decimal("0"),
            minimumStock=Decimal("5"),
        )

        before = NotificationRecordModel.objects.count()
        summaries = scanTenants(str(self.tenantId))
        self.assertEqual(sum(x["lowStockParts"] for x in summaries), 1)
        self.assertGreater(
            NotificationRecordModel.objects.count(),
            before,
            "the scan found a low-stock part but notified nobody",
        )


class EmptyAudienceFallbackTest(TestCase):
    """The engine-level safety net, independent of what the seed does."""

    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = _platformTenantId()

    def _create(self, **overrides):
        from apps.notifications.application.commands.notificationCommands import (
            CreateNotificationCommand,
        )
        from apps.notifications.infrastructure.container import container

        command = CreateNotificationCommand(
            tenantId=self.tenantId,
            recipientSpec={"type": "ROLE", "value": ["roleNobodyHolds"]},
            eventType="testEvent",
            eventId=str(uuid.uuid4()),
            notificationType="maintenance.workOrderOverdue",
            category="MAINTENANCE",
            priority="HIGH",
            title="آزمون",
            body="آزمون",
            **overrides,
        )
        return container.createNotificationService().execute(command)

    def testEmptyRoleWithoutFallbackStillCreatesNothing(self) -> None:
        """Unchanged behaviour where no fallback is configured."""
        before = NotificationRecordModel.objects.count()
        self._create()
        self.assertEqual(NotificationRecordModel.objects.count(), before)

    def testEmptyRoleWithFallbackReachesTheAdmins(self) -> None:
        before = NotificationRecordModel.objects.count()
        self._create(fallbackRecipientSpec={"type": "TENANT_ADMIN"})
        self.assertGreater(NotificationRecordModel.objects.count(), before)

    def testFallbackIsNotUsedWhenThePrimaryAudienceExists(self) -> None:
        """The fallback must not double-notify when the role is populated."""
        from apps.notifications.application.commands.notificationCommands import (
            CreateNotificationCommand,
        )
        from apps.notifications.infrastructure.container import container

        holders = profileDirectory.userIdsOfRole(self.tenantId, ["maintenanceManager"])
        self.assertTrue(holders)

        outcome = container.createNotificationService().execute(
            CreateNotificationCommand(
                tenantId=self.tenantId,
                recipientSpec={"type": "ROLE", "value": ["maintenanceManager"]},
                fallbackRecipientSpec={"type": "TENANT_ADMIN"},
                eventType="testEvent",
                eventId=str(uuid.uuid4()),
                notificationType="maintenance.workOrderOverdue",
                category="MAINTENANCE",
                priority="HIGH",
                title="آزمون",
                body="آزمون",
            )
        )
        self.assertEqual(len(outcome.notifications), len(holders))


class RoutesDeclareAnAudienceFallbackTest(TestCase):
    """Guards the configuration itself, so a new alert cannot be added mute."""

    def testOperationalAlertRoutesCarryAFallback(self) -> None:
        from apps.notifications.infrastructure.eventConsumer import notificationEventRoutes

        routes = notificationEventRoutes()
        operational = [
            "workOrderOverdue",
            "sparePartLowStock",
            "devicePmDueSoon",
            "devicePmOverdue",
            "purchaseRequisitionStale",
        ]
        for name in operational:
            self.assertIn(name, routes)
            self.assertTrue(
                routes[name].get("fallbackRecipientSpec"),
                f"{name} has no fallback audience and would be discarded on a "
                "tenant where its role has no holders",
            )
