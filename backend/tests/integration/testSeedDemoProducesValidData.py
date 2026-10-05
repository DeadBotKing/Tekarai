"""The demo seed must produce data the application can actually read back.

`seedDemo` writes through the ORM, which performs no domain validation. One
work order was seeded with `type="coordinating"` -- a value absent from
`WORK_ORDER_TYPES` -- and nothing complained at write time. Reading the work
order list back through the use case raised `SYS_VALIDATION_FAILED`, so the
work orders page was broken for everyone who followed the documented setup.
The static table is checked here, and the list endpoint is exercised against
seeded data so a write/read mismatch cannot pass again.
"""

from __future__ import annotations

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.maintenance.domain.valueObjects.maintenanceState import (
    DEVICE_STATUSES,
    WORK_ORDER_PRIORITIES,
    WORK_ORDER_STATUSES,
    WORK_ORDER_TYPES,
)
from apps.maintenance.management.commands.seedDemo import DEVICES, WORK_ORDERS
from tests.support.phase6Helpers import loginViaApi, seedPlatform


class SeedDemoDataIsValidTest(TestCase):
    def testSeededWorkOrderFieldsAreInTheDomainEnums(self) -> None:
        for row in WORK_ORDERS:
            self.assertIn(row["type"], WORK_ORDER_TYPES, f"{row['title']}: bad type")
            self.assertIn(row["priority"], WORK_ORDER_PRIORITIES, f"{row['title']}: bad priority")
            self.assertIn(row["status"], WORK_ORDER_STATUSES, f"{row['title']}: bad status")

    def testSeededDeviceStatusesAreInTheDomainEnum(self) -> None:
        for row in DEVICES:
            self.assertIn(row["status"], DEVICE_STATUSES, f"{row['code']}: bad status")

    def testWorkOrderListIsReadableAfterSeeding(self) -> None:
        """The regression itself: seed, then read the list back through the API."""
        cache.clear()
        seedPlatform()
        call_command("seedDemo")

        client = APIClient()
        tokens = loginViaApi(client)
        response = client.get(
            "/api/v1/maintenance/work-orders",
            **{"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertGreater(len(response.json()["data"]), 0)
