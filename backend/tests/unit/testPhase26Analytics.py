"""Phase 26 — maintenance analytics domain rules (no database).

These pin the arithmetic the whole reporting layer rests on: how often an asset
was repaired, how long it was down, MTBF / MTTR / availability, PM compliance,
and the difference between *how many times* a part was used and *how many
units* were consumed.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import TestCase

from apps.maintenance.domain.entities.assetRegistry import PmPlan
from apps.maintenance.domain.services.maintenanceAnalytics import (
    PartUsageReading,
    PmExecutionReading,
    WorkOrderReading,
    buildTrend,
    computeDeviceAnalytics,
    summarisePartUsage,
    summariseTechnicians,
)
from apps.maintenance.domain.valueObjects.maintenanceState import (
    MAINTENANCE_DEPARTMENTS,
    MaintenanceDepartment,
    PmFrequency,
)

UTC = timezone.utc


def moment(day: int, hour: int = 8) -> datetime:
    return datetime(2026, 3, day, hour, 0, tzinfo=UTC)


def correctiveOrder(
    identifier: str,
    day: int,
    downtimeMinutes: int = 120,
    repairHours: int = 2,
    **overrides: object,
) -> WorkOrderReading:
    defaults: dict = {
        "id": identifier,
        "orderType": "corrective",
        "status": "completed",
        "createdAt": moment(day),
        "failureReportedAt": moment(day),
        "repairStartedAt": moment(day, 9),
        "repairFinishedAt": moment(day, 9 + repairHours),
        "returnedToServiceAt": moment(day, 10 + repairHours),
        "closedAt": moment(day, 10 + repairHours),
        "downtimeMinutes": downtimeMinutes,
    }
    defaults.update(overrides)
    return WorkOrderReading(**defaults)  # type: ignore[arg-type]


class DepartmentCatalogueTests(TestCase):
    def testSevenDisciplinesAreAvailable(self) -> None:
        self.assertEqual(
            set(MAINTENANCE_DEPARTMENTS),
            {
                "general",
                "electrical",
                "mechanical",
                "facilities",
                "instrumentation",
                "hydraulic",
                "pneumatic",
            },
        )

    def testHydraulicAndPneumaticAreValidDepartments(self) -> None:
        self.assertEqual(str(MaintenanceDepartment("hydraulic")), "hydraulic")
        self.assertEqual(str(MaintenanceDepartment("pneumatic")), "pneumatic")


class PmFrequencyTests(TestCase):
    def testMonthlyFrequencyNormalisesToDays(self) -> None:
        self.assertEqual(PmFrequency(every=3, unit="month").asDays(), 90)
        self.assertEqual(PmFrequency(every=2, unit="week").asDays(), 14)

    def testRunningHourFrequencyHasNoCalendarPeriod(self) -> None:
        self.assertIsNone(PmFrequency(every=500, unit="runningHour").asDays())

    def testPlanDerivesNextDueAndOverdueFlag(self) -> None:
        plan = PmPlan(
            id=__import__("uuid").uuid4(),
            tenantId=__import__("uuid").uuid4(),
            deviceId=__import__("uuid").uuid4(),
            title="تعویض روغن",
            discipline="mechanical",
            frequencyEvery=3,
            frequencyUnit="month",
            lastExecutedOn=date(2026, 1, 15),
        )
        self.assertEqual(plan.nextDueOn(), date(2026, 4, 15))
        self.assertFalse(plan.isOverdue(date(2026, 4, 1)))
        self.assertTrue(plan.isOverdue(date(2026, 5, 1)))


class DeviceAnalyticsTests(TestCase):
    def testRepairCountExcludesPreventiveWork(self) -> None:
        orders = [
            correctiveOrder("wo-1", 2),
            correctiveOrder("wo-2", 9),
            WorkOrderReading(
                id="wo-3", orderType="preventive", status="completed", createdAt=moment(12)
            ),
            WorkOrderReading(
                id="wo-4", orderType="inspection", status="completed", createdAt=moment(14)
            ),
        ]
        analytics = computeDeviceAnalytics(
            deviceId="dev-1",
            orders=orders,
            partUsages=[],
            pmExecutions=[],
            pmPlansDue=0,
            pmPlansOverdue=0,
            fromDate=date(2026, 3, 1),
            toDate=date(2026, 3, 31),
        )
        self.assertEqual(analytics.repairCount, 2)
        self.assertEqual(analytics.preventiveCount, 1)
        self.assertEqual(analytics.inspectionCount, 1)
        self.assertEqual(analytics.totalOrders, 4)

    def testDowntimeMttrMtbfAndAvailability(self) -> None:
        orders = [
            correctiveOrder("wo-1", 2, downtimeMinutes=120, repairHours=2),
            correctiveOrder("wo-2", 9, downtimeMinutes=240, repairHours=4),
        ]
        analytics = computeDeviceAnalytics(
            deviceId="dev-1",
            orders=orders,
            partUsages=[],
            pmExecutions=[],
            pmPlansDue=0,
            pmPlansOverdue=0,
            fromDate=date(2026, 3, 1),
            toDate=date(2026, 3, 31),  # 31 days = 744 calendar hours
        )
        self.assertEqual(analytics.totalDowntimeHours, 6.0)
        self.assertEqual(analytics.operatingHours, 738.0)
        self.assertEqual(analytics.mttrHours, 3.0)  # (2h + 4h) / 2
        self.assertEqual(analytics.mtbfHours, 369.0)  # 738h / 2 failures
        self.assertEqual(analytics.availabilityPercent, 99.19)

    def testDowntimeFallsBackToReportedAndBackInServiceStamps(self) -> None:
        order = WorkOrderReading(
            id="wo-1",
            orderType="corrective",
            status="completed",
            createdAt=moment(4),
            failureReportedAt=moment(4, 6),
            returnedToServiceAt=moment(4, 11),
            closedAt=moment(4, 11),
            downtimeMinutes=0,
        )
        self.assertEqual(order.downtimeHours(), 5.0)

    def testRepeatFailuresAndFailureModesAreRanked(self) -> None:
        orders = [
            correctiveOrder(
                "wo-1", 2, failureType="wear", failedComponent="بلبرینگ", repeatFailure=True
            ),
            correctiveOrder("wo-2", 9, failureType="wear", failedComponent="بلبرینگ"),
            correctiveOrder("wo-3", 15, failureType="operatorError", failedComponent="کوپلینگ"),
        ]
        analytics = computeDeviceAnalytics(
            deviceId="dev-1",
            orders=orders,
            partUsages=[],
            pmExecutions=[],
            pmPlansDue=0,
            pmPlansOverdue=0,
            fromDate=date(2026, 3, 1),
            toDate=date(2026, 3, 31),
        )
        self.assertEqual(analytics.repeatFailures, 1)
        self.assertEqual(analytics.byFailureType[0].label, "wear")
        self.assertEqual(analytics.byFailureType[0].count, 2)
        self.assertEqual(analytics.byFailedComponent[0].label, "بلبرینگ")

    def testPmComplianceUsesOnTimeExecutions(self) -> None:
        executions = [
            PmExecutionReading(
                planId="plan-1", discipline="mechanical", performedOn=date(2026, 3, 5)
            ),
            PmExecutionReading(
                planId="plan-1",
                discipline="mechanical",
                performedOn=date(2026, 3, 20),
                onTime=False,
            ),
        ]
        analytics = computeDeviceAnalytics(
            deviceId="dev-1",
            orders=[],
            partUsages=[],
            pmExecutions=executions,
            pmPlansDue=4,
            pmPlansOverdue=1,
            fromDate=date(2026, 3, 1),
            toDate=date(2026, 3, 31),
        )
        self.assertEqual(analytics.pmCompleted, 2)
        self.assertEqual(analytics.pmOnTime, 1)
        self.assertEqual(analytics.pmScheduled, 4)
        self.assertEqual(analytics.pmOverdue, 1)
        self.assertEqual(analytics.pmCompliancePercent, 25.0)

    def testCostsAreSummedAcrossOrders(self) -> None:
        orders = [
            correctiveOrder(
                "wo-1", 2, labourCost=Decimal("1500000"), partsCost=Decimal("2400000")
            ),
            correctiveOrder("wo-2", 9, labourCost=Decimal("500000"), partsCost=Decimal("0")),
        ]
        analytics = computeDeviceAnalytics(
            deviceId="dev-1",
            orders=orders,
            partUsages=[],
            pmExecutions=[],
            pmPlansDue=0,
            pmPlansOverdue=0,
            fromDate=date(2026, 3, 1),
            toDate=date(2026, 3, 31),
        )
        self.assertEqual(analytics.labourCost, Decimal("2000000"))
        self.assertEqual(analytics.partsCost, Decimal("2400000"))
        self.assertEqual(analytics.totalCost, Decimal("4400000"))


class PartConsumptionTests(TestCase):
    def testUsageCountAndQuantityAreCountedSeparately(self) -> None:
        usages = [
            PartUsageReading(
                partId="p1",
                partCode="BRG-6205",
                partName="بلبرینگ 6205",
                unit="عدد",
                quantity=Decimal("3"),
                consumedAt=moment(4),
                deviceId="dev-1",
            ),
            PartUsageReading(
                partId="p1",
                partCode="BRG-6205",
                partName="بلبرینگ 6205",
                unit="عدد",
                quantity=Decimal("2"),
                consumedAt=moment(18),
                deviceId="dev-1",
            ),
            PartUsageReading(
                partId="p2",
                partCode="SEAL-01",
                partName="کاسه‌نمد",
                unit="عدد",
                quantity=Decimal("1"),
                consumedAt=moment(20),
                deviceId="dev-1",
            ),
        ]
        stats = {stat.partId: stat for stat in summarisePartUsage(usages)}
        self.assertEqual(stats["p1"].usageCount, 2)
        self.assertEqual(stats["p1"].totalQuantity, Decimal("5"))
        self.assertEqual(stats["p1"].lastUsedAt, moment(18).isoformat())
        self.assertEqual(stats["p2"].usageCount, 1)
        self.assertEqual(stats["p2"].totalQuantity, Decimal("1"))

    def testOnePartSpanningManyDevicesCountsDevices(self) -> None:
        usages = [
            PartUsageReading(
                partId="p1",
                partCode="BRG",
                partName="بلبرینگ",
                unit="عدد",
                quantity=Decimal("1"),
                deviceId=f"dev-{index}",
            )
            for index in range(3)
        ]
        stat = summarisePartUsage(usages)[0]
        self.assertEqual(stat.usageCount, 3)
        self.assertEqual(stat.deviceCount, 3)


class TechnicianAndTrendTests(TestCase):
    def testTechnicianWorkloadIsAggregated(self) -> None:
        orders = [
            correctiveOrder("wo-1", 2, assignedToName="رضا محمدی", repairHours=2),
            correctiveOrder("wo-2", 9, assignedToName="رضا محمدی", repairHours=4),
            WorkOrderReading(
                id="wo-3",
                orderType="preventive",
                status="inProgress",
                assignedToName="رضا محمدی",
                createdAt=moment(12),
            ),
        ]
        stat = summariseTechnicians(orders)[0]
        self.assertEqual(stat.name, "رضا محمدی")
        self.assertEqual(stat.totalOrders, 3)
        self.assertEqual(stat.correctiveOrders, 2)
        self.assertEqual(stat.preventiveOrders, 1)
        self.assertEqual(stat.openOrders, 1)
        self.assertEqual(stat.averageRepairHours, 3.0)

    def testTrendCoversEveryMonthInTheWindow(self) -> None:
        orders = [correctiveOrder("wo-1", 4)]
        buckets = buildTrend(orders, date(2026, 1, 1), date(2026, 4, 30))
        self.assertEqual([bucket.label for bucket in buckets], [
            "2026-01",
            "2026-02",
            "2026-03",
            "2026-04",
        ])
        self.assertEqual(buckets[2].failures, 1)
        self.assertEqual(buckets[0].failures, 0)
