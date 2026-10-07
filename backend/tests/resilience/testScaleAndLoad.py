"""How the API behaves with a realistic amount of data in it, and under
concurrent callers.

Every functional test in this repository runs against a handful of rows. That
hides the two failures that actually take a CMMS down in its second year: a
list endpoint whose query count grows with the number of rows (N+1), and an
endpoint with no ceiling on how much it will return.

These are not benchmarks. Wall-clock numbers from a shared CI box are noise.
The assertions are on things that stay true regardless of the machine: how
many queries a request costs, whether the page size is bounded, and whether
concurrent requests from different tenants keep their data apart.
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from tests.support.multiTenantHelpers import (
    authHeaders,
    createTenantWithAdmin,
    loginAs,
    loginPlatform,
)
from tests.support.phase6Helpers import platformTenantId, seedPlatform

DEVICE_COUNT = 500
WORK_ORDER_COUNT = 500


def seedDevices(tenantId: uuid.UUID, count: int) -> list[uuid.UUID]:
    """Rows written in bulk, straight at the model.

    Going through the API would take minutes and would be testing the write
    path, which has its own suite. What matters here is what the *read* path
    does once the table is big.
    """

    from apps.maintenance.infrastructure.models import DeviceModel

    now = datetime.now(tz=UTC)
    devices = [
        DeviceModel(
            id=uuid.uuid4(),
            tenantId=tenantId,
            code=f"SCALE-{index:05d}",
            name=f"تجهیز شماره {index}",
            department="mechanical",
            status="operational",
            criticality="medium",
            createdAt=now,
        )
        for index in range(count)
    ]
    DeviceModel.objects.bulk_create(devices, batch_size=500)
    return [device.id for device in devices]


class DeviceListScaleTests(TestCase):
    """500 devices in one tenant."""

    @classmethod
    def setUpTestData(cls) -> None:
        seedPlatform()
        cls.tenantId = platformTenantId()
        cls.deviceIds = seedDevices(cls.tenantId, DEVICE_COUNT)
        cls.headers = authHeaders(loginPlatform(APIClient()))

    def setUp(self) -> None:
        self.client = APIClient()

    def testListIsPagedRatherThanReturningEverything(self) -> None:
        """An endpoint that returns 500 rows today returns 50,000 in year
        three and takes the browser with it."""

        response = self.client.get("/api/v1/maintenance/devices", **self.headers)
        self.assertEqual(response.status_code, 200, response.content[:400])

        rows = response.json()["data"]
        self.assertLess(
            len(rows),
            DEVICE_COUNT,
            "the device list returned every row — there is no default page size",
        )

    def testQueryCountDoesNotGrowWithTheNumberOfRows(self) -> None:
        """The N+1 test.

        A page of 50 costing 50-plus queries is the single most common way a
        Django list endpoint dies. Comparing two page sizes separates a fixed
        overhead from a per-row cost without hard-coding a number that every
        future migration would have to update.
        """

        with self.assertNumQueries(0):
            pass  # establishes the connection warm-up before measuring

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as small:
            self.client.get("/api/v1/maintenance/devices?limit=5", **self.headers)
        with CaptureQueriesContext(connection) as large:
            self.client.get("/api/v1/maintenance/devices?limit=100", **self.headers)

        self.assertLessEqual(
            len(large.captured_queries),
            len(small.captured_queries) + 2,
            "query count grows with page size: "
            f"{len(small.captured_queries)} queries for 5 rows, "
            f"{len(large.captured_queries)} for 100 — an N+1 in the device list",
        )

    def testAnAbsurdPageSizeIsClampedNotHonoured(self) -> None:
        """`?limit=100000` must not be a denial-of-service primitive."""

        response = self.client.get(
            "/api/v1/maintenance/devices?limit=100000", **self.headers
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertLessEqual(
            len(response.json()["data"]),
            1000,
            "an unbounded limit was honoured",
        )

    def testSearchAcrossALargeTableStillAnswers(self) -> None:
        response = self.client.get(
            "/api/v1/maintenance/devices?search=SCALE-00042", **self.headers
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        codes = [row["code"] for row in response.json()["data"]]
        self.assertIn("SCALE-00042", codes)


class WorkOrderScaleTests(TestCase):
    """500 work orders against one device."""

    @classmethod
    def setUpTestData(cls) -> None:
        from apps.maintenance.infrastructure.models import WorkOrderModel

        seedPlatform()
        cls.tenantId = platformTenantId()
        deviceIds = seedDevices(cls.tenantId, 5)
        now = datetime.now(tz=UTC)
        WorkOrderModel.objects.bulk_create(
            [
                WorkOrderModel(
                    id=uuid.uuid4(),
                    tenantId=cls.tenantId,
                    deviceId=deviceIds[index % len(deviceIds)],
                    title=f"WO-SCALE-{index:05d} سفارش کار",
                    orderType="corrective",
                    priority="normal",
                    status="submitted",
                    department="mechanical",
                    createdAt=now,
                )
                for index in range(WORK_ORDER_COUNT)
            ],
            batch_size=500,
        )
        cls.headers = authHeaders(loginPlatform(APIClient()))

    def setUp(self) -> None:
        self.client = APIClient()

    def testWorkOrderListIsPaged(self) -> None:
        response = self.client.get("/api/v1/maintenance/work-orders", **self.headers)
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertLess(
            len(response.json()["data"]),
            WORK_ORDER_COUNT,
            "the work order list has no default page size",
        )

    def testWorkOrderListHasNoPerRowQuery(self) -> None:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as small:
            self.client.get("/api/v1/maintenance/work-orders?limit=5", **self.headers)
        with CaptureQueriesContext(connection) as large:
            self.client.get("/api/v1/maintenance/work-orders?limit=100", **self.headers)

        self.assertLessEqual(
            len(large.captured_queries),
            len(small.captured_queries) + 2,
            "query count grows with page size: "
            f"{len(small.captured_queries)} vs {len(large.captured_queries)} — "
            "the work order list has an N+1, probably the device join",
        )


@override_settings(DEBUG=False)
class ConcurrentTenantTests(TransactionTestCase):
    """Two tenants hitting the API at the same time, on different threads.

    Tenant scope is carried in a request-scoped context. If that context is
    stored anywhere shared between threads — a module global, a mutable
    default, a cached singleton — concurrency is what exposes it, and a
    single-threaded test suite never will. Tenant A receiving one row of
    tenant B's data under load is the worst bug this system could have.
    """

    reset_sequences = True

    def setUp(self) -> None:
        # Concurrent SQLite writers log a wall of expected OperationalErrors.
        logging.disable(logging.ERROR)
        self.addCleanup(logging.disable, logging.NOTSET)
        seedPlatform()
        self.tenantAId = platformTenantId()
        self.tenantB = createTenantWithAdmin("concurrent-b")
        self.headersA = authHeaders(loginPlatform(APIClient()))
        self.headersB = authHeaders(loginAs(APIClient(), self.tenantB))

        seedDevices(self.tenantAId, 40)
        from apps.maintenance.infrastructure.models import DeviceModel

        now = datetime.now(tz=UTC)
        DeviceModel.objects.bulk_create(
            [
                DeviceModel(
                    id=uuid.uuid4(),
                    tenantId=self.tenantB["tenantId"],
                    code=f"BTEN-{index:05d}",
                    name=f"تجهیز ب {index}",
                    department="electrical",
                    status="operational",
                    criticality="medium",
                    createdAt=now,
                )
                for index in range(40)
            ]
        )

    def testInterleavedRequestsNeverSeeTheOtherTenantsRows(self) -> None:
        def fetch(headers: dict[str, str]) -> list[str] | None:
            client = APIClient()
            response = client.get("/api/v1/maintenance/devices?limit=100", **headers)
            if response.status_code != 200:
                # SQLite serialises writers and every authenticated request
                # writes `Session.lastActivityAt`, so a few of these come back
                # "database is locked" in this environment. That is a property
                # of the test database, not of tenant scoping — the claim
                # under test is about the responses that *did* succeed.
                return None
            return [row["code"] for row in response.json()["data"]]

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(fetch, self.headersA if index % 2 == 0 else self.headersB)
                for index in range(24)
            ]
            results = [(index, future.result()) for index, future in enumerate(futures)]

        answered = [(index, codes) for index, codes in results if codes is not None]
        self.assertGreaterEqual(
            len(answered), 6, "too few concurrent requests succeeded to conclude anything"
        )

        for index, codes in answered:
            if index % 2 == 0:
                self.assertFalse(
                    [code for code in codes if code.startswith("BTEN-")],
                    "tenant A saw tenant B's devices under concurrent load",
                )
            else:
                self.assertFalse(
                    [code for code in codes if code.startswith("SCALE-")],
                    "tenant B saw tenant A's devices under concurrent load",
                )

    def testConcurrentWritesFromTwoTenantsStayInTheirOwnTenant(self) -> None:
        def create(headers: dict[str, str], code: str) -> int:
            # SQLite admits one writer at a time and every authenticated
            # request also writes Session.lastActivityAt, so a burst of
            # concurrent POSTs collides on the lock. Retrying is what a real
            # client does; without it this measures SQLite, not tenancy.
            client = APIClient()
            for _ in range(8):
                response = client.post(
                    "/api/v1/maintenance/devices",
                    {"code": code, "name": code, "department": "mechanical"},
                    format="json",
                    **headers,
                )
                if response.status_code < 500:
                    return response.status_code
                time.sleep(0.05)
            return response.status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(
                    create,
                    self.headersA if index % 2 == 0 else self.headersB,
                    f"CONC-{'A' if index % 2 == 0 else 'B'}-{index:03d}",
                )
                for index in range(16)
            ]
            statuses = [future.result() for future in futures]

        # Same caveat as above: SQLite rejects some concurrent writers. The
        # assertion that matters is where the accepted writes landed.
        self.assertGreaterEqual(
            sum(1 for status in statuses if status in (200, 201)),
            4,
            f"almost every concurrent write failed: {statuses}",
        )

        from apps.maintenance.infrastructure.models import DeviceModel

        strayInA = DeviceModel.objects.filter(
            tenantId=self.tenantAId, code__startswith="CONC-B-"
        ).count()
        strayInB = DeviceModel.objects.filter(
            tenantId=self.tenantB["tenantId"], code__startswith="CONC-A-"
        ).count()
        self.assertEqual(strayInA, 0, "a tenant B write landed in tenant A")
        self.assertEqual(strayInB, 0, "a tenant A write landed in tenant B")
