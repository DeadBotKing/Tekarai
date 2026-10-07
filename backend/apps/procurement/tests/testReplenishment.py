"""The stock→purchase loop end to end: low stock becomes a purchase request.

Covers the scan service, the API, the management command and — the test
that matters most — that running the scan twice does not order everything
twice.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.maintenance.infrastructure.models import SparePartModel
from apps.procurement.application.services.replenishmentScan import scanReplenishment
from apps.procurement.infrastructure.models import (
    PurchaseOrderLineModel,
    PurchaseOrderModel,
    PurchaseRequisitionLineModel,
    PurchaseRequisitionModel,
    SupplierModel,
    SupplierPartModel,
)
from apps.procurement.infrastructure.replenishmentRepository import quantitiesOnOrder
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform

D = Decimal


class ReplenishmentFixtureMixin:
    """Warehouse + supplier catalogue the scan can be pointed at.

    The annotation is declaration-only: every concrete test case assigns
    ``tenantId`` in ``setUp``, but a mixin has no ``__init__`` of its own,
    so without it the type checker cannot see the attribute.
    """

    tenantId: uuid.UUID

    def makePart(
        self,
        code: str,
        *,
        onHand: str = "0",
        minimum: str = "10",
        reorderQuantity: str = "0",
        unitCost: str = "100",
        autoReorder: bool = True,
    ) -> SparePartModel:
        return SparePartModel.objects.create(
            tenantId=self.tenantId,
            code=code,
            name=f"قطعه {code}",
            unit="عدد",
            quantityOnHand=D(onHand),
            minimumStock=D(minimum),
            reorderQuantity=D(reorderQuantity),
            unitCost=D(unitCost),
            autoReorder=autoReorder,
        )

    def makeSupplier(self, code: str, name: str) -> SupplierModel:
        return SupplierModel.objects.create(
            tenantId=self.tenantId, code=code, name=name, status="active"
        )

    def linkSupplier(
        self,
        supplier: SupplierModel,
        part: SparePartModel,
        *,
        unitPrice: str = "0",
        preferred: bool = False,
        moq: str = "0",
        leadTimeDays: int = 0,
    ) -> SupplierPartModel:
        return SupplierPartModel.objects.create(
            tenantId=self.tenantId,
            supplierId=supplier.id,
            partId=part.id,
            unitPrice=D(unitPrice),
            minimumOrderQty=D(moq),
            leadTimeDays=leadTimeDays,
            isPreferred=preferred,
        )


class ReplenishmentScanTests(ReplenishmentFixtureMixin, TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()

    def testPartBelowMinimumIsSuggested(self) -> None:
        self.makePart("P-LOW", onHand="2", minimum="10", reorderQuantity="20")
        result = scanReplenishment(self.tenantId)
        codes = [x.partCode for x in result.suggestions]
        self.assertIn("P-LOW", codes)
        suggestion = next(x for x in result.suggestions if x.partCode == "P-LOW")
        self.assertEqual(D(suggestion.suggestedQuantity), D("28.000"))

    def testHealthyPartIsNotSuggested(self) -> None:
        self.makePart("P-OK", onHand="500", minimum="10")
        result = scanReplenishment(self.tenantId)
        self.assertEqual([x.partCode for x in result.suggestions], [])

    def testDeletedPartIsIgnored(self) -> None:
        from django.utils import timezone

        part = self.makePart("P-GONE", onHand="0", minimum="10")
        part.deletedAt = timezone.now()
        part.save(update_fields=["deletedAt"])
        result = scanReplenishment(self.tenantId)
        self.assertEqual([x.partCode for x in result.suggestions], [])

    def testPreferredSupplierSuppliesThePriceAndLeadTime(self) -> None:
        part = self.makePart("P-SUP", onHand="0", minimum="5", unitCost="999")
        cheap = self.makeSupplier("S-CHEAP", "ارزان")
        preferred = self.makeSupplier("S-PREF", "ترجیحی")
        self.linkSupplier(cheap, part, unitPrice="100")
        self.linkSupplier(preferred, part, unitPrice="250", preferred=True, leadTimeDays=5)

        suggestion = scanReplenishment(self.tenantId).suggestions[0]
        # The flagged preferred supplier wins even though it is dearer, and
        # its quote replaces the part's own last-paid cost.
        self.assertEqual(suggestion.supplierName, "ترجیحی")
        self.assertEqual(D(suggestion.estimatedUnitCost), D("250"))
        self.assertEqual(suggestion.leadTimeDays, 5)

    def testWithoutAPreferredFlagTheCheapestQuoteWins(self) -> None:
        part = self.makePart("P-CHEAP", onHand="0", minimum="5")
        a = self.makeSupplier("S-A", "الف")
        b = self.makeSupplier("S-B", "ب")
        self.linkSupplier(a, part, unitPrice="300")
        self.linkSupplier(b, part, unitPrice="120")
        suggestion = scanReplenishment(self.tenantId).suggestions[0]
        self.assertEqual(suggestion.supplierName, "ب")

    def testPartWithNoSupplierFallsBackToItsOwnLastPaidCost(self) -> None:
        self.makePart("P-NOSUP", onHand="0", minimum="4", unitCost="77")
        suggestion = scanReplenishment(self.tenantId).suggestions[0]
        self.assertIsNone(suggestion.supplierId)
        self.assertEqual(D(suggestion.estimatedUnitCost), D("77"))

    def testAutoReorderOffIsReportedAsSkippedNotDropped(self) -> None:
        """A part excluded from the loop must still be visible.

        Silently omitting it looks identical to the scan failing to notice
        the part at all.
        """
        self.makePart("P-MANUAL", onHand="0", minimum="10", autoReorder=False)
        result = scanReplenishment(self.tenantId)
        self.assertEqual([x.partCode for x in result.suggestions], [])
        self.assertEqual([x["partCode"] for x in result.skipped], ["P-MANUAL"])

    def testSuggestionsAreOrderedWorstFirst(self) -> None:
        self.makePart("P-NORMAL", onHand="9", minimum="10")
        self.makePart("P-OUT", onHand="0", minimum="10")
        self.makePart("P-HIGH", onHand="3", minimum="10")
        urgencies = [x.urgency for x in scanReplenishment(self.tenantId).suggestions]
        self.assertEqual(urgencies, ["critical", "high", "normal"])

    def testPreviewWritesNothing(self) -> None:
        self.makePart("P-PREVIEW", onHand="0", minimum="10")
        scanReplenishment(self.tenantId)
        self.assertEqual(PurchaseRequisitionModel.objects.count(), 0)


class OnOrderArithmeticTests(ReplenishmentFixtureMixin, TestCase):
    """Goods already coming must count, or the scan duplicates every night."""

    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.part = self.makePart("P-INBOUND", onHand="2", minimum="10", reorderQuantity="20")

    def makeRequisition(self, status: str, quantity: str) -> PurchaseRequisitionModel:
        requisition = PurchaseRequisitionModel.objects.create(
            tenantId=self.tenantId, number=f"PR-{uuid.uuid4().hex[:8].upper()}", status=status
        )
        PurchaseRequisitionLineModel.objects.create(
            tenantId=self.tenantId,
            requisitionId=requisition.id,
            partId=self.part.id,
            partCode=self.part.code,
            partName=self.part.name,
            quantity=D(quantity),
        )
        return requisition

    def makeOrder(self, status: str, ordered: str, received: str) -> PurchaseOrderModel:
        order = PurchaseOrderModel.objects.create(
            tenantId=self.tenantId,
            number=f"PO-{uuid.uuid4().hex[:8].upper()}",
            status=status,
            supplierId=uuid.uuid4(),
        )
        PurchaseOrderLineModel.objects.create(
            tenantId=self.tenantId,
            purchaseOrderId=order.id,
            partId=self.part.id,
            partCode=self.part.code,
            partName=self.part.name,
            orderedQuantity=D(ordered),
            receivedQuantity=D(received),
            unitPrice=D("10"),
        )
        return order

    def testOpenRequisitionCounts(self) -> None:
        self.makeRequisition("submitted", "50")
        self.assertEqual(quantitiesOnOrder(self.tenantId)[self.part.id], D("50"))
        self.assertEqual(scanReplenishment(self.tenantId).suggestions, [])

    def testDraftRequisitionCounts(self) -> None:
        """Including the drafts this scan itself produces — that is what
        makes a second run propose nothing."""
        self.makeRequisition("draft", "50")
        self.assertEqual(scanReplenishment(self.tenantId).suggestions, [])

    def testCancelledRequisitionDoesNotCount(self) -> None:
        self.makeRequisition("cancelled", "50")
        self.assertNotIn(self.part.id, quantitiesOnOrder(self.tenantId))
        self.assertEqual(len(scanReplenishment(self.tenantId).suggestions), 1)

    def testPurchasedRequisitionDoesNotCount(self) -> None:
        """Its goods are on the shelf already and counted in quantityOnHand;
        counting them again would hide a genuine shortage."""
        self.makeRequisition("purchased", "50")
        self.assertNotIn(self.part.id, quantitiesOnOrder(self.tenantId))

    def testOnlyTheUndeliveredOrderBalanceCounts(self) -> None:
        self.makeOrder("partiallyReceived", ordered="30", received="25")
        self.assertEqual(quantitiesOnOrder(self.tenantId)[self.part.id], D("5"))

    def testFullyReceivedOrderCountsForNothing(self) -> None:
        self.makeOrder("received", ordered="30", received="30")
        self.assertNotIn(self.part.id, quantitiesOnOrder(self.tenantId))

    def testCancelledOrderCountsForNothing(self) -> None:
        self.makeOrder("cancelled", ordered="30", received="0")
        self.assertNotIn(self.part.id, quantitiesOnOrder(self.tenantId))

    def testOverDeliveryIsNotCreditedAsNegativeInbound(self) -> None:
        self.makeOrder("partiallyReceived", ordered="10", received="14")
        self.assertEqual(quantitiesOnOrder(self.tenantId).get(self.part.id, D("0")), D("0"))


class ApplyTests(ReplenishmentFixtureMixin, TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()

    def testApplyCreatesADraftRequisitionWithLines(self) -> None:
        self.makePart("P-A", onHand="0", minimum="10", reorderQuantity="10", unitCost="50")
        result = scanReplenishment(self.tenantId, apply=True)

        self.assertEqual(len(result.createdRequisitions), 1)
        requisition = PurchaseRequisitionModel.objects.get()
        # Draft, not submitted: a machine may spot the need, a person still
        # decides to spend the money.
        self.assertEqual(requisition.status, "draft")
        self.assertIsNone(requisition.submittedAt)

        line = PurchaseRequisitionLineModel.objects.get()
        self.assertEqual(line.partCode, "P-A")
        self.assertEqual(line.quantity, D("20.000"))
        self.assertEqual(requisition.totalEstimated, D("1000.00"))

    def testLinesAreGroupedIntoOneRequisitionPerSupplier(self) -> None:
        alpha = self.makeSupplier("S-1", "آلفا")
        beta = self.makeSupplier("S-2", "بتا")
        for code in ("P-1", "P-2"):
            part = self.makePart(code, onHand="0", minimum="5")
            self.linkSupplier(alpha, part, unitPrice="10", preferred=True)
        third = self.makePart("P-3", onHand="0", minimum="5")
        self.linkSupplier(beta, third, unitPrice="10", preferred=True)

        scanReplenishment(self.tenantId, apply=True)

        self.assertEqual(PurchaseRequisitionModel.objects.count(), 2)
        counts = sorted(
            PurchaseRequisitionLineModel.objects.filter(
                tenantId=self.tenantId, requisitionId=r.id
            ).count()
            for r in PurchaseRequisitionModel.objects.all()
        )
        self.assertEqual(counts, [1, 2])

    def testPartsWithoutASupplierShareOneRequisition(self) -> None:
        self.makePart("P-X", onHand="0", minimum="5")
        self.makePart("P-Y", onHand="0", minimum="5")
        scanReplenishment(self.tenantId, apply=True)
        self.assertEqual(PurchaseRequisitionModel.objects.count(), 1)
        self.assertEqual(PurchaseRequisitionLineModel.objects.count(), 2)

    def testRequisitionInheritsTheMostUrgentLinePriority(self) -> None:
        """A stockout mixed into a routine order must not be slowed to the
        routine staleness threshold."""
        supplier = self.makeSupplier("S-M", "مخلوط")
        routine = self.makePart("P-ROUTINE", onHand="9", minimum="10")
        urgent = self.makePart("P-URGENT", onHand="0", minimum="10")
        self.linkSupplier(supplier, routine, unitPrice="1", preferred=True)
        self.linkSupplier(supplier, urgent, unitPrice="1", preferred=True)

        scanReplenishment(self.tenantId, apply=True)
        self.assertEqual(PurchaseRequisitionModel.objects.get().priority, "critical")

    def testTheReasonTravelsOntoTheLine(self) -> None:
        self.makePart("P-WHY", onHand="0", minimum="10")
        scanReplenishment(self.tenantId, apply=True)
        self.assertTrue(PurchaseRequisitionLineModel.objects.get().note.strip())

    def testGeneratedRequisitionsAreMarked(self) -> None:
        self.makePart("P-MARK", onHand="0", minimum="10")
        scanReplenishment(self.tenantId, apply=True)
        self.assertIn("خودکار", PurchaseRequisitionModel.objects.get().justification)

    def testPreferredSupplierIsStampedOnTheLine(self) -> None:
        supplier = self.makeSupplier("S-STAMP", "مهر")
        part = self.makePart("P-STAMP", onHand="0", minimum="5")
        self.linkSupplier(supplier, part, unitPrice="10", preferred=True)
        scanReplenishment(self.tenantId, apply=True)
        self.assertEqual(
            PurchaseRequisitionLineModel.objects.get().preferredSupplierId, supplier.id
        )

    def testSupplierMinimumOrderQuantityIsHonouredOnTheLine(self) -> None:
        supplier = self.makeSupplier("S-MOQ", "حداقل‌دار")
        part = self.makePart("P-MOQ", onHand="9", minimum="10", reorderQuantity="1")
        self.linkSupplier(supplier, part, unitPrice="5", preferred=True, moq="100")
        scanReplenishment(self.tenantId, apply=True)
        self.assertEqual(PurchaseRequisitionLineModel.objects.get().quantity, D("100.000"))


class IdempotencyTests(ReplenishmentFixtureMixin, TestCase):
    """The property the whole design hangs on.

    A daily cron that re-orders everything it ordered yesterday is worse
    than no automation at all, because somebody has to go and cancel the
    duplicates. Nothing here relies on a deduplication key: the draft the
    first run created counts as stock on order, so the second run simply
    finds nothing below its minimum.
    """

    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()

    def testSecondRunCreatesNothing(self) -> None:
        self.makePart("P-ONCE", onHand="0", minimum="10", reorderQuantity="10")

        first = scanReplenishment(self.tenantId, apply=True)
        self.assertEqual(len(first.createdRequisitions), 1)

        second = scanReplenishment(self.tenantId, apply=True)
        self.assertEqual(second.createdRequisitions, [])
        self.assertEqual(second.suggestions, [])
        self.assertEqual(PurchaseRequisitionModel.objects.count(), 1)
        self.assertEqual(PurchaseRequisitionLineModel.objects.count(), 1)

    def testTenConsecutiveRunsStillProduceOneRequisition(self) -> None:
        self.makePart("P-CRON", onHand="1", minimum="20")
        for _ in range(10):
            scanReplenishment(self.tenantId, apply=True)
        self.assertEqual(PurchaseRequisitionModel.objects.count(), 1)

    def testCancellingTheDraftLetsThePartBeProposedAgain(self) -> None:
        """Idempotency must not become amnesia: if the buyer throws the
        draft away the need is real again."""
        self.makePart("P-REDO", onHand="0", minimum="10")
        scanReplenishment(self.tenantId, apply=True)
        PurchaseRequisitionModel.objects.update(status="cancelled")

        again = scanReplenishment(self.tenantId, apply=True)
        self.assertEqual(len(again.createdRequisitions), 1)
        self.assertEqual(PurchaseRequisitionModel.objects.count(), 2)

    def testFurtherConsumptionTopsUpAgainThenSettles(self) -> None:
        """Idempotency is not paralysis.

        Suppressing a repeat order is only correct while the inbound
        quantity still covers the minimum. If consumption carries on
        draining the shelf, the loop must be able to ask for more — and
        then stop again, rather than adding a line every night.
        """
        part = self.makePart("P-MORE", onHand="10", minimum="10", reorderQuantity="10")
        scanReplenishment(self.tenantId, apply=True)
        self.assertEqual(PurchaseRequisitionLineModel.objects.count(), 1)

        # The 10 that was ordered has not arrived, and the shelf empties.
        part.quantityOnHand = D("0")
        part.save(update_fields=["quantityOnHand"])
        scanReplenishment(self.tenantId, apply=True)
        # net = 0 on hand + 10 inbound = exactly the minimum, which still
        # counts as low (`<=`, matching the low-stock alert), so a second
        # top-up to the target of 20 is correct.
        self.assertEqual(PurchaseRequisitionLineModel.objects.count(), 2)

        # And now it settles: net = 0 + 20 is clear of the minimum, so a
        # third run adds nothing. The loop converges instead of running away.
        scanReplenishment(self.tenantId, apply=True)
        self.assertEqual(PurchaseRequisitionLineModel.objects.count(), 2)


class TenantIsolationTests(ReplenishmentFixtureMixin, TestCase):
    """A scan must never see, count or buy another tenant's stock."""

    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.otherTenantId = uuid.uuid4()

    def testOtherTenantsLowStockIsNotSuggested(self) -> None:
        SparePartModel.objects.create(
            tenantId=self.otherTenantId,
            code="P-OTHER",
            name="مال دیگری",
            quantityOnHand=D("0"),
            minimumStock=D("10"),
        )
        self.assertEqual(scanReplenishment(self.tenantId).suggestions, [])

    def testOtherTenantsOpenRequisitionDoesNotSuppressOurOrder(self) -> None:
        """Counting a foreign requisition as our incoming stock would stop
        us buying a part we genuinely need."""
        part = self.makePart("P-SHARED", onHand="0", minimum="10")
        foreign = PurchaseRequisitionModel.objects.create(
            tenantId=self.otherTenantId, number="PR-FOREIGN", status="submitted"
        )
        PurchaseRequisitionLineModel.objects.create(
            tenantId=self.otherTenantId,
            requisitionId=foreign.id,
            partId=part.id,
            partCode=part.code,
            partName=part.name,
            quantity=D("9999"),
        )
        self.assertEqual(len(scanReplenishment(self.tenantId).suggestions), 1)

    def testApplyWritesOnlyIntoTheScannedTenant(self) -> None:
        self.makePart("P-MINE", onHand="0", minimum="10")
        scanReplenishment(self.tenantId, apply=True)
        self.assertEqual(
            PurchaseRequisitionModel.objects.exclude(tenantId=self.tenantId).count(), 0
        )


class ReplenishmentApiTests(ReplenishmentFixtureMixin, TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    def testGetPreviewsWithoutWriting(self) -> None:
        self.makePart("P-API", onHand="0", minimum="10", reorderQuantity="5")
        response = self.client.get("/api/v1/procurement/replenishment", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["partCode"], "P-API")
        self.assertEqual(body["meta"]["suggestedCount"], 1)
        self.assertEqual(PurchaseRequisitionModel.objects.count(), 0)

    def testPostRaisesTheRequisitions(self) -> None:
        self.makePart("P-POST", onHand="0", minimum="10", reorderQuantity="5", unitCost="20")
        response = self.client.post("/api/v1/procurement/replenishment", {}, **self.auth)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()["data"]
        self.assertEqual(len(body["createdRequisitions"]), 1)
        self.assertEqual(PurchaseRequisitionModel.objects.count(), 1)

    def testPostWithNothingToBuyIsNotAnError(self) -> None:
        self.makePart("P-FULL", onHand="900", minimum="10")
        response = self.client.post("/api/v1/procurement/replenishment", {}, **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["createdRequisitions"], [])

    def testUnauthenticatedCallIsRejected(self) -> None:
        response = self.client.get("/api/v1/procurement/replenishment")
        self.assertIn(response.status_code, (401, 403))

    def testGeneratedRequisitionAppearsInTheNormalRequisitionList(self) -> None:
        """The loop must feed the existing screens, not a parallel world."""
        self.makePart("P-FEED", onHand="0", minimum="10")
        self.client.post("/api/v1/procurement/replenishment", {}, **self.auth)
        listed = self.client.get(
            "/api/v1/procurement/requisitions?status=draft", **self.auth
        ).json()["data"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["lines"][0]["partCode"], "P-FEED")


class SparePartReorderFieldApiTests(TestCase):
    """The new policy fields have to be reachable from the parts screen."""

    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    def testCreateAcceptsAndReturnsThem(self) -> None:
        response = self.client.post(
            "/api/v1/maintenance/spare-parts",
            {
                "code": "RP-1",
                "name": "قطعه با سیاست سفارش",
                "unit": "عدد",
                "quantityOnHand": "5",
                "minimumStock": "10",
                "reorderQuantity": "40",
                "autoReorder": False,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()["data"]
        self.assertEqual(D(data["reorderQuantity"]), D("40"))
        self.assertFalse(data["autoReorder"])

    def testOmittingThemKeepsTodaysBehaviour(self) -> None:
        """Existing clients that know nothing about the loop must keep
        working, and their parts must stay opted in."""
        response = self.client.post(
            "/api/v1/maintenance/spare-parts",
            {"code": "RP-2", "name": "قطعه ساده", "quantityOnHand": "1", "minimumStock": "2"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()["data"]
        self.assertEqual(D(data["reorderQuantity"]), D("0"))
        self.assertTrue(data["autoReorder"])

    def testPatchUpdatesThePolicy(self) -> None:
        created = self.client.post(
            "/api/v1/maintenance/spare-parts",
            {"code": "RP-3", "name": "قطعه", "quantityOnHand": "1", "minimumStock": "2"},
            format="json",
            **self.auth,
        ).json()["data"]
        response = self.client.patch(
            f"/api/v1/maintenance/spare-parts/{created['id']}",
            {
                "name": "قطعه",
                "unit": "عدد",
                "quantityOnHand": "1",
                "minimumStock": "2",
                "reorderQuantity": "15",
                "autoReorder": False,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(D(response.json()["data"]["reorderQuantity"]), D("15"))


class ManagementCommandTests(ReplenishmentFixtureMixin, TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.makePart("P-CMD", onHand="0", minimum="10")

    def testDryRunIsTheDefaultAndWritesNothing(self) -> None:
        """A cron line that was meant to report must not start spending."""
        out = StringIO()
        call_command("runReplenishment", stdout=out)
        self.assertEqual(PurchaseRequisitionModel.objects.count(), 0)
        self.assertIn("--apply", out.getvalue())

    def testApplyCreatesTheRequisitions(self) -> None:
        out = StringIO()
        call_command("runReplenishment", "--apply", stdout=out)
        self.assertEqual(PurchaseRequisitionModel.objects.count(), 1)

    def testTenantFilterIsHonoured(self) -> None:
        out = StringIO()
        call_command("runReplenishment", "--apply", tenant=str(uuid.uuid4()), stdout=out)
        self.assertEqual(PurchaseRequisitionModel.objects.count(), 0)

    def testEachTenantIsScannedOnce(self) -> None:
        """Regression: Meta.ordering joining a DISTINCT select returned one
        row per part, so a tenant with 50 parts was scanned 50 times."""
        self.makePart("P-CMD-2", onHand="0", minimum="10")
        self.makePart("P-CMD-3", onHand="0", minimum="10")
        summaries = []
        out = StringIO()
        call_command("runReplenishment", stdout=out)
        summaries = [line for line in out.getvalue().splitlines() if "tenantId" in line]
        self.assertEqual(len(summaries), 1)
