from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from apps.maintenance.domain.services.equipmentLifecycle import (
    EquipmentLifecycleSnapshot,
    LifecycleMeterReading,
    LifecyclePartUse,
    LifecyclePerformancePoint,
    LifecycleWorkOrder,
    analyzeEquipmentLifecycle,
    suggestRepairScope,
)


class EquipmentLifecycleDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.asOf = datetime(2026, 10, 20, tzinfo=timezone.utc)

    def workOrder(
        self,
        index: int,
        *,
        daysAgo: int,
        scope: str = "unclassified",
        status: str = "completed",
        downtimeMinutes: int = 0,
    ) -> LifecycleWorkOrder:
        return LifecycleWorkOrder(
            id=f"wo-{index}",
            orderType="corrective",
            status=status,
            repairScope=scope,
            createdAt=self.asOf - timedelta(days=daysAgo),
            downtimeMinutes=downtimeMinutes,
        )

    def test_every_corrective_order_is_counted_but_minor_repairs_do_not_consume_major_life(self) -> None:
        orders = tuple(
            [self.workOrder(index, daysAgo=index * 5, scope="minor") for index in range(1, 11)]
            + [self.workOrder(99, daysAgo=400, status="cancelled", scope="major")]
        )
        analysis = analyzeEquipmentLifecycle(
            EquipmentLifecycleSnapshot(
                workOrders=orders,
                retiredPeerMajorRepairCounts=(2, 4, 6),
                cohortType="modelNumber",
                cohortLabel="P-100",
            ),
            asOf=self.asOf,
            deviceId="device-1",
        )

        self.assertEqual(analysis["events"]["correctiveCount"], 10)
        self.assertEqual(analysis["events"]["majorRepairCount"], 0)
        self.assertEqual(analysis["lifeEstimate"]["currentMajorRepairCount"], 0)
        self.assertEqual(analysis["lifeEstimate"]["typicalMajorRepairsAtRetirement"], 4.0)
        self.assertEqual(analysis["lifeEstimate"]["estimatedRemainingMajorRepairs"], 4.0)
        self.assertEqual(analysis["reliability"]["failureFrequencyTrend"], "increasing")
        self.assertEqual(analysis["reliability"]["majorRepairFrequencyTrend"], "stable")
        self.assertEqual(analysis["condition"], "stable")

    def test_rising_human_confirmed_major_repairs_are_an_advisory_decline_signal(self) -> None:
        analysis = analyzeEquipmentLifecycle(
            EquipmentLifecycleSnapshot(
                workOrders=(
                    self.workOrder(1, daysAgo=15, scope="major"),
                    self.workOrder(2, daysAgo=30, scope="overhaul"),
                ),
            ),
            asOf=self.asOf,
            deviceId="device-major-trend",
        )

        self.assertEqual(analysis["reliability"]["majorRepairFrequencyTrend"], "increasing")
        self.assertEqual(analysis["condition"], "watch")
        self.assertTrue(analysis["advisoryOnly"])

    def test_configured_gauge_trend_contributes_to_advisory_condition(self) -> None:
        point = LifecyclePerformancePoint(
            id="meter-1",
            name="Flow",
            unit="L/s",
            role="higherIsBetter",
        )
        readings = (
            LifecycleMeterReading("meter-1", Decimal("100"), self.asOf - timedelta(days=20)),
            LifecycleMeterReading("meter-1", Decimal("70"), self.asOf - timedelta(days=1)),
        )
        analysis = analyzeEquipmentLifecycle(
            EquipmentLifecycleSnapshot(
                performancePoints=(point,),
                performanceReadings=readings,
            ),
            asOf=self.asOf,
            deviceId="device-meter-trend",
        )

        self.assertEqual(analysis["performance"]["trend"], "declining")
        self.assertEqual(analysis["condition"], "watch")

    def test_life_estimate_requires_three_usable_retired_peers(self) -> None:
        analysis = analyzeEquipmentLifecycle(
            EquipmentLifecycleSnapshot(
                workOrders=(self.workOrder(1, daysAgo=20, scope="major"),),
                retiredPeerMajorRepairCounts=(2, 5),
            ),
            asOf=self.asOf,
            deviceId="device-2",
        )

        self.assertEqual(analysis["lifeEstimate"]["status"], "insufficientData")
        self.assertIsNone(analysis["lifeEstimate"]["estimatedRemainingMajorRepairs"])
        self.assertEqual(analysis["condition"], "stable")

    def test_bearing_and_consumable_evidence_never_becomes_overhaul_from_quantity(self) -> None:
        suggestion = suggestRepairScope(
            description="تعویض بلبرینگ و فیلتر",
            partUses=(
                LifecyclePartUse(
                    workOrderId="wo-1",
                    partCode="BRG-6204",
                    partName="بلبرینگ",
                    quantity=Decimal("100"),
                    lifecycleImpact="minor",
                ),
            ),
        )

        self.assertEqual(suggestion.suggestedScope, "minor")
        self.assertTrue(suggestion.requiresHumanConfirmation)

    def test_confirmed_major_part_is_only_a_suggestion_and_needs_human_confirmation(self) -> None:
        suggestion = suggestRepairScope(
            partUses=(
                LifecyclePartUse(
                    workOrderId="wo-2",
                    partCode="ROTOR-1",
                    partName="روتور",
                    quantity=Decimal("1"),
                    lifecycleImpact="major",
                ),
            ),
        )

        self.assertEqual(suggestion.suggestedScope, "major")
        self.assertIn("medium", suggestion.confidence)
        self.assertTrue(suggestion.requiresHumanConfirmation)


if __name__ == "__main__":
    unittest.main()
