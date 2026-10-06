"""Staleness rules for purchase requisitions, and the end of their lifecycle.

Two behaviours are pinned here:

1. A submitted request that nobody buys becomes stale once it passes the
   limit for its priority, and says so in the API.
2. Fully receiving the purchase order that fulfils a request moves it to
   ``purchased`` — previously it stopped at ``ordered`` forever.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.maintenance.infrastructure.models import SparePartModel
from apps.procurement.application.services.requisitionAlertScan import scanStaleRequisitions
from apps.procurement.domain.services.requisitionAging import evaluateRequisitionAging
from apps.procurement.domain.valueObjects.requisitionState import (
    REQ_APPROVED,
    REQ_DRAFT,
    REQ_ORDERED,
    REQ_PURCHASED,
    REQ_SUBMITTED,
    staleThresholdDaysFor,
)
from apps.procurement.infrastructure.models import (
    PurchaseOrderLineModel,
    PurchaseOrderModel,
    PurchaseRequisitionModel,
)
from tests.support.phase6Helpers import loginViaApi, seedPlatform


class RequisitionAgingRuleTests(SimpleTestCase):
    """The pure rule — no database, clock injected."""

    def setUp(self) -> None:
        self.now = timezone.now()

    def aged(self, days: int, *, status: str = REQ_SUBMITTED, priority: str = "normal"):
        return evaluateRequisitionAging(
            status=status,
            priority=priority,
            submittedAt=self.now - timedelta(days=days),
            now=self.now,
        )

    def testNormalPriorityIsStaleAfterSevenDays(self) -> None:
        self.assertFalse(self.aged(6).isStale)
        self.assertTrue(self.aged(7).isStale)

    def testThresholdFollowsPriority(self) -> None:
        self.assertTrue(self.aged(2, priority="critical").isStale)
        self.assertFalse(self.aged(2, priority="high").isStale)
        self.assertTrue(self.aged(4, priority="high").isStale)
        self.assertFalse(self.aged(7, priority="low").isStale)
        self.assertTrue(self.aged(14, priority="low").isStale)

    def testUnknownPriorityFallsBackToSevenDays(self) -> None:
        """Imported rows carry odd priorities; the scan must not crash."""
        self.assertEqual(staleThresholdDaysFor("مهم"), 7)
        self.assertTrue(self.aged(8, priority="مهم").isStale)

    def testDraftNeverGoesStale(self) -> None:
        """The clock starts at submission, not at creation."""
        self.assertFalse(self.aged(90, status=REQ_DRAFT).isStale)

    def testNeverSubmittedHasNoClock(self) -> None:
        verdict = evaluateRequisitionAging(
            status=REQ_SUBMITTED, priority="normal", submittedAt=None, now=self.now
        )
        self.assertFalse(verdict.isStale)
        self.assertEqual(verdict.daysWaiting, 0)

    def testPurchasedIsNeverStale(self) -> None:
        self.assertFalse(self.aged(365, status=REQ_PURCHASED).isStale)

    def testOrderedStillCountsAsWaiting(self) -> None:
        """Ordered is not delivered: the requester is still empty-handed."""
        self.assertTrue(self.aged(30, status=REQ_ORDERED).isStale)

    def testDaysOverdueIsZeroInsideTheThreshold(self) -> None:
        self.assertEqual(self.aged(3).daysOverdue, 0)
        self.assertEqual(self.aged(10).daysOverdue, 3)


class RequisitionLifecycleApiTests(TestCase):
    """The lifecycle through the real API, against the real database."""

    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    def createRequisition(self, priority: str = "normal") -> dict:
        response = self.client.post(
            "/api/v1/procurement/requisitions",
            {
                "requesterName": "تکنسین",
                "priority": priority,
                "lines": [
                    {
                        "partId": str(uuid.uuid4()),
                        "partCode": "BRG-01",
                        "partName": "بلبرینگ",
                        "quantity": "2",
                        "estimatedUnitCost": "125000",
                    }
                ],
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def submit(self, requisitionId: str) -> dict:
        response = self.client.post(
            f"/api/v1/procurement/requisitions/{requisitionId}/submit", {}, **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]

    def testSubmitStampsTheClock(self) -> None:
        created = self.createRequisition()
        self.assertIsNone(created["submittedAt"])
        self.submit(created["id"])
        row = PurchaseRequisitionModel.objects.get(id=created["id"])
        self.assertIsNotNone(row.submittedAt)

    def testResubmitDoesNotRestartTheClock(self) -> None:
        """Otherwise a late request could be laundered out of the alert list."""
        created = self.createRequisition()
        self.submit(created["id"])
        first = PurchaseRequisitionModel.objects.get(id=created["id"]).submittedAt
        self.submit(created["id"])
        self.assertEqual(PurchaseRequisitionModel.objects.get(id=created["id"]).submittedAt, first)

    def testListReportsStalenessAfterTheThreshold(self) -> None:
        created = self.createRequisition()
        self.submit(created["id"])
        PurchaseRequisitionModel.objects.filter(id=created["id"]).update(
            submittedAt=timezone.now() - timedelta(days=8)
        )
        response = self.client.get("/api/v1/procurement/requisitions", **self.auth)
        item = next(x for x in response.json()["data"] if x["id"] == created["id"])
        self.assertTrue(item["isStale"])
        self.assertEqual(item["daysWaiting"], 8)
        self.assertEqual(item["staleThresholdDays"], 7)

    def testStaleFilterReturnsOnlyLateRequests(self) -> None:
        late = self.createRequisition()
        self.submit(late["id"])
        PurchaseRequisitionModel.objects.filter(id=late["id"]).update(
            submittedAt=timezone.now() - timedelta(days=30)
        )
        fresh = self.createRequisition()
        self.submit(fresh["id"])

        response = self.client.get("/api/v1/procurement/requisitions?stale=true", **self.auth)
        ids = [x["id"] for x in response.json()["data"]]
        self.assertIn(late["id"], ids)
        self.assertNotIn(fresh["id"], ids)

    def testDashboardCountsStaleRequests(self) -> None:
        created = self.createRequisition(priority="critical")
        self.submit(created["id"])
        PurchaseRequisitionModel.objects.filter(id=created["id"]).update(
            submittedAt=timezone.now() - timedelta(days=3)
        )
        response = self.client.get("/api/v1/procurement/dashboard", **self.auth)
        self.assertEqual(response.json()["data"]["staleRequisitions"], 1)

    def testFullReceiptMarksTheRequisitionPurchased(self) -> None:
        """The gap the lifecycle used to have: ordered never became done."""
        created = self.createRequisition()
        self.submit(created["id"])
        self.client.post(
            f"/api/v1/procurement/requisitions/{created['id']}/approve", {}, **self.auth
        )

        tenantId = PurchaseRequisitionModel.objects.get(id=created["id"]).tenantId
        # Receiving goods moves real stock through maintenance's inventory
        # contract, so the line must point at a spare part that exists.
        part = SparePartModel.objects.create(
            tenantId=tenantId, code="BRG-01", name="بلبرینگ", unit="عدد"
        )
        order = PurchaseOrderModel.objects.create(
            tenantId=tenantId,
            number="PO-TEST-1",
            status="approved",
            supplierId=uuid.uuid4(),
            requisitionId=created["id"],
        )
        line = PurchaseOrderLineModel.objects.create(
            tenantId=tenantId,
            purchaseOrderId=order.id,
            partId=part.id,
            partCode="BRG-01",
            partName="بلبرینگ",
            orderedQuantity=Decimal("2"),
            unitPrice=Decimal("125000"),
        )
        PurchaseRequisitionModel.objects.filter(id=created["id"]).update(status=REQ_ORDERED)

        response = self.client.post(
            "/api/v1/procurement/receipts",
            {
                "purchaseOrderId": str(order.id),
                "lines": [
                    {
                        "purchaseOrderLineId": str(line.id),
                        "quantity": "2",
                        "unitCost": "125000",
                    }
                ],
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)

        requisition = PurchaseRequisitionModel.objects.get(id=created["id"])
        self.assertEqual(requisition.status, REQ_PURCHASED)
        self.assertIsNotNone(requisition.purchasedAt)

        purchased = self.client.get(
            "/api/v1/procurement/requisitions?status=purchased", **self.auth
        )
        self.assertIn(created["id"], [x["id"] for x in purchased.json()["data"]])

    def testPurchasedRequestDropsOutOfTheAlertList(self) -> None:
        created = self.createRequisition()
        self.submit(created["id"])
        PurchaseRequisitionModel.objects.filter(id=created["id"]).update(
            submittedAt=timezone.now() - timedelta(days=60), status=REQ_PURCHASED
        )
        response = self.client.get("/api/v1/procurement/requisitions?stale=true", **self.auth)
        self.assertNotIn(created["id"], [x["id"] for x in response.json()["data"]])


class RequisitionAlertScanTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.tenantId = uuid.uuid4()

    def makeRequisition(self, *, days: int, status: str = REQ_SUBMITTED, priority="normal"):
        requisition = PurchaseRequisitionModel.objects.create(
            tenantId=self.tenantId,
            number=f"PR-{uuid.uuid4().hex[:6].upper()}",
            status=status,
            priority=priority,
            requesterName="تکنسین",
        )
        PurchaseRequisitionModel.objects.filter(id=requisition.id).update(
            submittedAt=timezone.now() - timedelta(days=days)
        )
        return requisition

    def testScanFindsOnlyLateOpenRequests(self) -> None:
        late = self.makeRequisition(days=9)
        self.makeRequisition(days=2)
        self.makeRequisition(days=40, status=REQ_PURCHASED)

        result = scanStaleRequisitions(self.tenantId, dispatch=False)
        self.assertEqual(result.staleRequisitions, 1)
        self.assertEqual(result.items[0].requisitionId, str(late.id))
        self.assertEqual(result.items[0].daysWaiting, 9)

    def testApprovedButUnboughtStillAlerts(self) -> None:
        """Approval is not a purchase — the requester still has nothing."""
        self.makeRequisition(days=10, status=REQ_APPROVED)
        self.assertEqual(scanStaleRequisitions(self.tenantId, dispatch=False).staleRequisitions, 1)

    def testEventIdIsStableWithinAnIsoWeek(self) -> None:
        """Daily cron runs must not produce a notification every morning."""
        requisition = self.makeRequisition(days=9)
        monday = timezone.now()
        first = scanStaleRequisitions(self.tenantId, now=monday, dispatch=False)
        second = scanStaleRequisitions(
            self.tenantId, now=monday + timedelta(days=1), dispatch=False
        )
        self.assertEqual(first.isoWeek, second.isoWeek)
        self.assertEqual(first.items[0].requisitionId, str(requisition.id))

    def testScanIsScopedToOneTenant(self) -> None:
        self.makeRequisition(days=30)
        otherTenant = uuid.uuid4()
        self.assertEqual(scanStaleRequisitions(otherTenant, dispatch=False).staleRequisitions, 0)


class ScanTenantEnumerationTests(TestCase):
    """The scheduler must visit each tenant once, not once per requisition.

    ``Meta.ordering`` is ``["-createdAt"]`` and Django adds ordering columns
    to a DISTINCT SELECT, so the obvious ``.values_list(...).distinct()``
    de-duplicates on (tenantId, createdAt) and returns a row per document.
    """

    def testEachTenantIsScannedExactlyOnce(self) -> None:
        from apps.procurement.management.commands.checkProcurementAlerts import scanTenants

        tenantId = uuid.uuid4()
        for index in range(5):
            PurchaseRequisitionModel.objects.create(
                tenantId=tenantId, number=f"PR-DUP-{index}", status=REQ_DRAFT
            )

        summaries = scanTenants()
        self.assertEqual([x["tenantId"] for x in summaries].count(str(tenantId)), 1)


class StaleAlertDeliveryTests(TestCase):
    """The alert has to actually reach a person.

    The first version targeted the ``maintenanceManager`` role. On a fresh
    install nobody holds that role, so the scan reported stale requests and
    created zero notifications — an alarm that rings in an empty room.
    """

    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    def testRequesterIsRecordedOnCreate(self) -> None:
        response = self.client.post(
            "/api/v1/procurement/requisitions",
            {
                "requesterName": "تکنسین",
                "priority": "normal",
                "lines": [
                    {
                        "partId": str(uuid.uuid4()),
                        "partCode": "BRG-01",
                        "partName": "بلبرینگ",
                        "quantity": "1",
                    }
                ],
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNotNone(
            PurchaseRequisitionModel.objects.get(id=response.json()["data"]["id"]).requesterId
        )

    def testScanNotifiesSomebodyWithNoBuyerRoleConfigured(self) -> None:
        from apps.notifications.infrastructure.models import NotificationRecordModel

        created = self.client.post(
            "/api/v1/procurement/requisitions",
            {
                "requesterName": "تکنسین",
                "priority": "normal",
                "lines": [
                    {
                        "partId": str(uuid.uuid4()),
                        "partCode": "BRG-01",
                        "partName": "بلبرینگ",
                        "quantity": "1",
                    }
                ],
            },
            format="json",
            **self.auth,
        ).json()["data"]
        self.client.post(
            f"/api/v1/procurement/requisitions/{created['id']}/submit", {}, **self.auth
        )
        requisition = PurchaseRequisitionModel.objects.get(id=created["id"])
        PurchaseRequisitionModel.objects.filter(id=created["id"]).update(
            submittedAt=timezone.now() - timedelta(days=9)
        )

        before = NotificationRecordModel.objects.count()
        result = scanStaleRequisitions(requisition.tenantId)
        self.assertEqual(result.staleRequisitions, 1)
        self.assertGreater(
            NotificationRecordModel.objects.count(),
            before,
            "a stale requisition produced no notification at all",
        )

    def testRecipientsIncludeTheRequester(self) -> None:
        from apps.procurement.application.services.requisitionAlertScan import (
            resolveAlertRecipients,
        )

        requesterId = uuid.uuid4()
        tenantId = PurchaseRequisitionModel.objects.create(
            tenantId=uuid.uuid4(), number="PR-R", status=REQ_SUBMITTED
        ).tenantId
        self.assertIn(str(requesterId), resolveAlertRecipients(tenantId, requesterId))
