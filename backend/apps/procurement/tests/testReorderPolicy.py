"""Unit tests for the reorder decision — pure arithmetic, no database.

These are the rules the whole stock→purchase loop rests on, so they are
tested on their own rather than only through the scan: when a suggested
quantity is wrong, this file says which rule broke.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.procurement.domain.services.reorderPolicy import (
    URGENCY_CRITICAL,
    URGENCY_HIGH,
    URGENCY_NORMAL,
    evaluateReorder,
)

D = Decimal


class ReorderTriggerTests(SimpleTestCase):
    def testHealthyStockIsNotOrdered(self):
        verdict = evaluateReorder(quantityOnHand=D("50"), minimumStock=D("10"))
        self.assertFalse(verdict.shouldOrder)
        self.assertEqual(verdict.suggestedQuantity, D("0"))

    def testExactlyAtMinimumCountsAsLow(self):
        """`<=`, matching SparePart.lowStock.

        If the policy used `<` the purchase loop would disagree with the
        low-stock alert about which parts are in trouble, and a part sitting
        exactly on its minimum would be flagged by one and ignored by the
        other.
        """
        verdict = evaluateReorder(quantityOnHand=D("10"), minimumStock=D("10"))
        self.assertTrue(verdict.shouldOrder)

    def testBelowMinimumIsOrdered(self):
        verdict = evaluateReorder(
            quantityOnHand=D("2"), minimumStock=D("10"), reorderQuantity=D("20")
        )
        self.assertTrue(verdict.shouldOrder)
        self.assertEqual(verdict.shortfall, D("8"))


class QuantityTests(SimpleTestCase):
    def testOrdersUpToTheTargetNotJustTheShortfall(self):
        """Target = minimum + reorderQuantity, so a top-up clears the line.

        Ordering only the shortfall would leave the part resting exactly on
        its reorder point, where the next issue trips the alert again.
        """
        verdict = evaluateReorder(
            quantityOnHand=D("2"), minimumStock=D("10"), reorderQuantity=D("20")
        )
        # target 30, net 2  →  28, not the 8-unit shortfall.
        self.assertEqual(verdict.targetLevel, D("30"))
        self.assertEqual(verdict.suggestedQuantity, D("28.000"))

    def testUnsetReorderQuantityTopsUpToTwiceTheMinimum(self):
        """The loop must work before anybody configures a single part."""
        verdict = evaluateReorder(quantityOnHand=D("0"), minimumStock=D("15"))
        self.assertEqual(verdict.targetLevel, D("30"))
        self.assertEqual(verdict.suggestedQuantity, D("30.000"))

    def testSupplierMinimumOrderQuantityRaisesTheOrder(self):
        """A need of 3 against a MOQ of 10 is an order for 10."""
        verdict = evaluateReorder(
            quantityOnHand=D("9"),
            minimumStock=D("10"),
            reorderQuantity=D("2"),
            supplierMinimumOrderQty=D("10"),
        )
        self.assertEqual(verdict.suggestedQuantity, D("10.000"))

    def testSupplierMinimumNeverShrinksALargerNeed(self):
        verdict = evaluateReorder(
            quantityOnHand=D("0"),
            minimumStock=D("100"),
            reorderQuantity=D("100"),
            supplierMinimumOrderQty=D("5"),
        )
        self.assertEqual(verdict.suggestedQuantity, D("200.000"))

    def testFractionalNeedRoundsUp(self):
        """Rounding down could propose 0 and stall the loop permanently."""
        verdict = evaluateReorder(
            quantityOnHand=D("0.9999"), minimumStock=D("1"), reorderQuantity=D("0.0005")
        )
        self.assertTrue(verdict.shouldOrder)
        self.assertGreater(verdict.suggestedQuantity, D("0"))
        self.assertEqual(verdict.suggestedQuantity.as_tuple().exponent, -3)


class OnOrderTests(SimpleTestCase):
    """The rule that stops the scan spamming duplicate requests."""

    def testGoodsAlreadyOnOrderSuppressTheSuggestion(self):
        verdict = evaluateReorder(
            quantityOnHand=D("2"),
            minimumStock=D("10"),
            reorderQuantity=D("20"),
            onOrderQuantity=D("28"),
        )
        self.assertEqual(verdict.netAvailable, D("30"))
        self.assertFalse(verdict.shouldOrder)

    def testPartialInboundStillLeavesAShortfall(self):
        verdict = evaluateReorder(
            quantityOnHand=D("2"),
            minimumStock=D("10"),
            reorderQuantity=D("20"),
            onOrderQuantity=D("3"),
        )
        # net 5 is still under the minimum of 10 → top up to the target 30.
        self.assertTrue(verdict.shouldOrder)
        self.assertEqual(verdict.suggestedQuantity, D("25.000"))

    def testOnOrderIsReportedForTheUi(self):
        verdict = evaluateReorder(
            quantityOnHand=D("1"), minimumStock=D("10"), onOrderQuantity=D("4")
        )
        self.assertEqual(verdict.onOrderQuantity, D("4"))
        self.assertEqual(verdict.netAvailable, D("5"))


class UrgencyTests(SimpleTestCase):
    def testZeroNetAvailableIsCritical(self):
        verdict = evaluateReorder(quantityOnHand=D("0"), minimumStock=D("10"))
        self.assertEqual(verdict.urgency, URGENCY_CRITICAL)

    def testDeeplyBelowMinimumIsHigh(self):
        verdict = evaluateReorder(quantityOnHand=D("4"), minimumStock=D("10"))
        self.assertEqual(verdict.urgency, URGENCY_HIGH)

    def testJustOnTheLineIsNormal(self):
        verdict = evaluateReorder(quantityOnHand=D("9"), minimumStock=D("10"))
        self.assertEqual(verdict.urgency, URGENCY_NORMAL)

    def testUrgencyValuesMatchTheRequisitionPriorityVocabulary(self):
        """The urgency is stamped on the requisition as its priority, which
        drives the staleness threshold. A value outside the table would
        silently fall back to the 7-day default."""
        from apps.procurement.domain.valueObjects.requisitionState import (
            STALE_DAYS_BY_PRIORITY,
        )

        for urgency in (URGENCY_CRITICAL, URGENCY_HIGH, URGENCY_NORMAL):
            self.assertIn(urgency, STALE_DAYS_BY_PRIORITY)


class OptOutTests(SimpleTestCase):
    def testAutoReorderOffSuppressesTheOrderButKeepsTheNumbers(self):
        verdict = evaluateReorder(
            quantityOnHand=D("0"), minimumStock=D("10"), autoReorder=False
        )
        self.assertFalse(verdict.shouldOrder)
        self.assertEqual(verdict.suggestedQuantity, D("0"))
        # Still reports the position so the UI can explain the skip.
        self.assertEqual(verdict.netAvailable, D("0"))
        self.assertEqual(verdict.reorderPoint, D("10"))
        self.assertIn("خاموش", verdict.reason)


class DegenerateInputTests(SimpleTestCase):
    """Real warehouses contain rows nobody finished filling in."""

    def testNoMinimumAndNoReorderQuantityProposesNothing(self):
        verdict = evaluateReorder(quantityOnHand=D("0"), minimumStock=D("0"))
        self.assertFalse(verdict.shouldOrder)
        self.assertEqual(verdict.suggestedQuantity, D("0"))

    def testNegativeMinimumIsTreatedAsZero(self):
        verdict = evaluateReorder(quantityOnHand=D("5"), minimumStock=D("-3"))
        self.assertEqual(verdict.reorderPoint, D("0"))
        self.assertFalse(verdict.shouldOrder)

    def testNegativeOnOrderIsFlooredRatherThanCreditedAgainstStock(self):
        verdict = evaluateReorder(
            quantityOnHand=D("5"), minimumStock=D("10"), onOrderQuantity=D("-100")
        )
        self.assertEqual(verdict.netAvailable, D("5"))
