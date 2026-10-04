"""End-to-end guard on goods receipts: stock may not exceed what was ordered.

A receipt is the moment a purchase becomes inventory. Before this guard the
endpoint accepted any quantity, so a ten-piece order could book a thousand
pieces into the warehouse — inflating stock, the part's cost basis, and
closing a purchase order that was never delivered. These tests drive the real
HTTP endpoint and then re-read the database, because the promise that matters
is "nothing moved", not "the response was 400".
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.maintenance.infrastructure.models import PartTransactionModel, SparePartModel
from apps.procurement.infrastructure.models import (
    GoodsReceiptModel,
    PurchaseOrderLineModel,
    PurchaseOrderModel,
    SupplierModel,
)
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform

BASE = "/api/v1/procurement"


class GoodsReceiptQuantityApiTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

        self.part = SparePartModel.objects.create(
            tenantId=self.tenantId,
            code="BRG-01",
            name="بلبرینگ",
            unit="عدد",
            quantityOnHand=Decimal("5"),
            unitCost=Decimal("100000"),
        )
        supplier = SupplierModel.objects.create(
            tenantId=self.tenantId, code="SUP-01", name="تأمین‌کنندهٔ یک"
        )
        self.order = PurchaseOrderModel.objects.create(
            tenantId=self.tenantId,
            number=f"PO-{uuid.uuid4().hex[:6].upper()}",
            status="approved",
            supplierId=supplier.id,
        )
        self.line = PurchaseOrderLineModel.objects.create(
            tenantId=self.tenantId,
            purchaseOrderId=self.order.id,
            partId=self.part.id,
            partCode=self.part.code,
            partName=self.part.name,
            unit="عدد",
            orderedQuantity=Decimal("10"),
            unitPrice=Decimal("120000"),
        )

    # -- helpers ----------------------------------------------------------------
    def postReceipt(self, *lines: dict):
        return self.client.post(
            f"{BASE}/receipts",
            {"purchaseOrderId": str(self.order.id), "lines": list(lines)},
            format="json",
            **self.auth,
        )

    def receiptLine(self, quantity: str, rejected: str = "0") -> dict:
        return {
            "purchaseOrderLineId": str(self.line.id),
            "quantity": quantity,
            "rejectedQuantity": rejected,
            "unitCost": "120000",
        }

    def assertNothingMoved(self) -> None:
        self.part.refresh_from_db()
        self.line.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.part.quantityOnHand, Decimal("5"))
        self.assertEqual(self.part.unitCost, Decimal("100000"))
        self.assertEqual(self.line.receivedQuantity, Decimal("0"))
        self.assertEqual(self.order.status, "approved")
        self.assertFalse(GoodsReceiptModel.objects.filter(tenantId=self.tenantId).exists())
        self.assertFalse(
            PartTransactionModel.objects.filter(
                tenantId=self.tenantId, transactionType="RECEIPT"
            ).exists()
        )

    # -- refusals ---------------------------------------------------------------
    def testReceivingMoreThanOrderedIsRefusedAndNothingMoves(self) -> None:
        response = self.postReceipt(self.receiptLine("1000"))
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn("بلبرینگ", response.content.decode())
        self.assertNothingMoved()

    def testTwoLinesForTheSameOrderLineCannotOvershootTogether(self) -> None:
        # Six and six each fit under ten on their own; together they do not.
        response = self.postReceipt(self.receiptLine("6"), self.receiptLine("6"))
        self.assertEqual(response.status_code, 422, response.content)
        self.assertNothingMoved()

    def testZeroQuantityIsRefused(self) -> None:
        response = self.postReceipt(self.receiptLine("0"))
        self.assertEqual(response.status_code, 422, response.content)
        self.assertNothingMoved()

    def testRejectedCannotExceedDelivered(self) -> None:
        response = self.postReceipt(self.receiptLine("4", rejected="9"))
        self.assertEqual(response.status_code, 422, response.content)
        self.assertNothingMoved()

    def testACancelledOrderAcceptsNoDelivery(self) -> None:
        self.order.status = "cancelled"
        self.order.save(update_fields=["status"])
        response = self.postReceipt(self.receiptLine("1"))
        self.assertEqual(response.status_code, 422, response.content)
        self.part.refresh_from_db()
        self.assertEqual(self.part.quantityOnHand, Decimal("5"))

    def testASecondDeliveryCannotExceedTheRemainder(self) -> None:
        self.assertEqual(self.postReceipt(self.receiptLine("7")).status_code, 201)
        response = self.postReceipt(self.receiptLine("5"))
        self.assertEqual(response.status_code, 422, response.content)
        self.part.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual(self.part.quantityOnHand, Decimal("12"))  # 5 + 7, not 17
        self.assertEqual(self.line.receivedQuantity, Decimal("7"))

    # -- what must keep working -------------------------------------------------
    def testAValidDeliveryStillPostsToStock(self) -> None:
        response = self.postReceipt(self.receiptLine("4"))
        self.assertEqual(response.status_code, 201, response.content)
        self.part.refresh_from_db()
        self.line.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.part.quantityOnHand, Decimal("9"))
        self.assertEqual(self.line.receivedQuantity, Decimal("4"))
        self.assertEqual(self.order.status, "partiallyReceived")
        self.assertTrue(
            PartTransactionModel.objects.filter(
                tenantId=self.tenantId, transactionType="RECEIPT"
            ).exists()
        )

    def testRejectedGoodsAreRecordedButDoNotEnterStock(self) -> None:
        response = self.postReceipt(self.receiptLine("6", rejected="2"))
        self.assertEqual(response.status_code, 201, response.content)
        self.part.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual(self.part.quantityOnHand, Decimal("9"))  # 5 + 4 accepted
        self.assertEqual(self.line.receivedQuantity, Decimal("4"))

    def testDeliveringExactlyTheOrderClosesIt(self) -> None:
        response = self.postReceipt(self.receiptLine("10"))
        self.assertEqual(response.status_code, 201, response.content)
        self.order.refresh_from_db()
        self.part.refresh_from_db()
        self.assertEqual(self.order.status, "received")
        self.assertEqual(self.part.quantityOnHand, Decimal("15"))
