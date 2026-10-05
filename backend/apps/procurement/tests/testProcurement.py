from decimal import Decimal

from django.test import SimpleTestCase

from apps.procurement.domain.services.receiptRules import (
    ReceiptQuantityError,
    acceptedQuantity,
    guardReceiptLine,
    remainingQuantity,
)
from apps.procurement.presentation.api.serializers import (
    PurchaseOrderSerializer,
    RequisitionSerializer,
    SupplierSerializer,
)


class ProcurementContractTests(SimpleTestCase):
    def testSupplierRequiresCodeAndName(self):
        serializer = SupplierSerializer(data={"code": "", "name": ""})
        self.assertFalse(serializer.is_valid())

    def testRequisitionRequiresAtLeastOneLine(self):
        serializer = RequisitionSerializer(data={"priority": "normal", "lines": []})
        self.assertFalse(serializer.is_valid())

    def testRequisitionAcceptsQuantityAndEstimatedCost(self):
        serializer = RequisitionSerializer(
            data={
                "requesterName": "تکنسین",
                "priority": "high",
                "lines": [
                    {
                        "partId": "00000000-0000-0000-0000-000000000001",
                        "partCode": "BRG-01",
                        "partName": "بلبرینگ",
                        "quantity": "2",
                        "estimatedUnitCost": "125000",
                    }
                ],
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["lines"][0]["quantity"], Decimal("2"))

    def testPurchaseOrderRequiresSupplierAndLines(self):
        serializer = PurchaseOrderSerializer(
            data={"supplierId": "00000000-0000-0000-0000-000000000001", "lines": []}
        )
        self.assertFalse(serializer.is_valid())


class ReceiptQuantityRuleTests(SimpleTestCase):
    """A delivery may never put more into stock than was ordered."""

    def testRemainingIsWhatIsStillOwed(self):
        self.assertEqual(remainingQuantity(Decimal("10"), Decimal("4")), Decimal("6"))

    def testRemainingNeverGoesNegative(self):
        # Legacy rows written before this guard existed may already be over.
        self.assertEqual(remainingQuantity(Decimal("10"), Decimal("12")), Decimal("0"))

    def testEarlierLinesOfTheSameReceiptCountAgainstTheRemainder(self):
        self.assertEqual(remainingQuantity(Decimal("10"), Decimal("2"), Decimal("5")), Decimal("3"))

    def testRejectedGoodsDoNotEnterStock(self):
        accepted = acceptedQuantity(Decimal("10"), Decimal("3"), "بلبرینگ")
        self.assertEqual(accepted, Decimal("7"))

    def testQuantityMustBePositive(self):
        with self.assertRaises(ReceiptQuantityError):
            acceptedQuantity(Decimal("0"), Decimal("0"), "بلبرینگ")

    def testRejectedCannotExceedDelivered(self):
        with self.assertRaises(ReceiptQuantityError):
            acceptedQuantity(Decimal("5"), Decimal("6"), "بلبرینگ")

    def testReceivingMoreThanOrderedIsRefused(self):
        # The bug: a ten-piece order accepting a thousand-piece delivery.
        with self.assertRaises(ReceiptQuantityError) as caught:
            guardReceiptLine(
                "بلبرینگ",
                Decimal("10"),
                Decimal("0"),
                Decimal("0"),
                Decimal("1000"),
                Decimal("0"),
            )
        self.assertIn("باقیماندهٔ سفارش", str(caught.exception))

    def testASecondDeliveryCannotOvershootTheRemainder(self):
        with self.assertRaises(ReceiptQuantityError):
            guardReceiptLine(
                "بلبرینگ",
                Decimal("10"),
                Decimal("8"),
                Decimal("0"),
                Decimal("3"),
                Decimal("0"),
            )

    def testAFullyReceivedLineTakesNothingMore(self):
        with self.assertRaises(ReceiptQuantityError) as caught:
            guardReceiptLine(
                "بلبرینگ",
                Decimal("10"),
                Decimal("10"),
                Decimal("0"),
                Decimal("1"),
                Decimal("0"),
            )
        self.assertIn("کامل تحویل شده", str(caught.exception))

    def testExactlyTheRemainderIsAllowed(self):
        accepted = guardReceiptLine(
            "بلبرینگ",
            Decimal("10"),
            Decimal("7"),
            Decimal("0"),
            Decimal("3"),
            Decimal("0"),
        )
        self.assertEqual(accepted, Decimal("3"))

    def testRejectedPortionDoesNotCountAgainstTheOrder(self):
        # 12 delivered, 4 rejected ⇒ 8 into stock, which fits the remaining 8.
        accepted = guardReceiptLine(
            "بلبرینگ",
            Decimal("10"),
            Decimal("2"),
            Decimal("0"),
            Decimal("12"),
            Decimal("4"),
        )
        self.assertEqual(accepted, Decimal("8"))

    def testMessagesNameThePartAndTheNumbers(self):
        with self.assertRaises(ReceiptQuantityError) as caught:
            guardReceiptLine(
                "واشر مسی",
                Decimal("5"),
                Decimal("0"),
                Decimal("0"),
                Decimal("9"),
                Decimal("0"),
            )
        message = str(caught.exception)
        self.assertIn("واشر مسی", message)
        self.assertIn("9", message)
        self.assertIn("5", message)
