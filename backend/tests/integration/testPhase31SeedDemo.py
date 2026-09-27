"""seedDemo management command — smoke coverage (Phase 31).

Seeding must populate a rich, realistic demo dataset (devices with nameplates,
PM plans with recent executions, work orders with labour & part costs) for the
platform tenant, and MUST be idempotent: a second run creates nothing.
"""

from __future__ import annotations

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase

from apps.maintenance.infrastructure.models import (
    DeviceModel,
    WorkOrderLabourEntryModel,
    WorkOrderPartUsageModel,
    PmExecutionModel,
    PmPlanModel,
    SparePartModel,
    WorkOrderModel,
)
from tests.support.phase6Helpers import seedPlatform


class SeedDemoCommandTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()

    def testSeedsRealisticDemoDataAndIsIdempotent(self) -> None:
        call_command("seedDemo")
        self.assertGreaterEqual(DeviceModel.objects.count(), 8)
        self.assertGreaterEqual(WorkOrderModel.objects.count(), 10)
        self.assertGreaterEqual(SparePartModel.objects.count(), 6)
        self.assertGreaterEqual(PmPlanModel.objects.count(), 7)
        self.assertGreaterEqual(PmExecutionModel.objects.count(), 7)
        self.assertGreater(WorkOrderLabourEntryModel.objects.count(), 0)
        self.assertGreater(WorkOrderPartUsageModel.objects.count(), 0)

        devicesAfter = DeviceModel.objects.count()
        workOrdersAfter = WorkOrderModel.objects.count()
        partsAfter = SparePartModel.objects.count()

        call_command("seedDemo")  # second run must create nothing
        self.assertEqual(DeviceModel.objects.count(), devicesAfter)
        self.assertEqual(WorkOrderModel.objects.count(), workOrdersAfter)
        self.assertEqual(SparePartModel.objects.count(), partsAfter)
