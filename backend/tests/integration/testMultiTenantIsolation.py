"""Two tenants, one database: can either one reach the other's rows?

Every other suite in this repository runs with exactly one tenant, which
makes tenant scoping untestable — a missing filter has nothing to leak when
there is nothing else in the table. These tests create a real second tenant
and then try, from tenant A's authenticated session, to read and write
tenant B's data.

The write cases matter more than the read cases. Several maintenance,
projects and tasks endpoints accept a `tenantId` in the request body and feed
it straight to `resolveTenantId`, which until now returned whatever it was
handed without comparing it to the authenticated context.
"""

from __future__ import annotations

import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from tests.support.multiTenantHelpers import (
    authHeaders,
    createTenantWithAdmin,
    loginAs,
    loginPlatform,
)
from tests.support.phase6Helpers import platformTenantId, seedPlatform


class MultiTenantIsolationTests(TestCase):
    """Tenant A must not be able to read or write tenant B."""

    @classmethod
    def setUpTestData(cls) -> None:
        seedPlatform()
        cls.tenantAId = platformTenantId()
        cls.tenantB = createTenantWithAdmin("isolation-b")
        # Logging in once per class, not per test: the login endpoint is rate
        # limited, and six logins in a row trips it. Tokens are what these
        # tests need, not repeated proof that login works.
        cls.headersA = authHeaders(loginPlatform(APIClient()))
        cls.headersB = authHeaders(loginAs(APIClient(), cls.tenantB))

    def setUp(self) -> None:
        self.client = APIClient()

    # -- reads ------------------------------------------------------------

    def testEachTenantSeesOnlyItsOwnDevices(self) -> None:
        """The basic claim. A device created by B must be invisible to A."""

        clientB = APIClient()
        created = clientB.post(
            "/api/v1/maintenance/devices",
            {
                "code": "B-ONLY-1",
                "name": "دستگاه اختصاصی تنانت ب",
                "department": "mechanical",
            },
            format="json",
            **self.headersB,
        )
        self.assertIn(created.status_code, (200, 201), created.content)

        listedByA = self.client.get(
            "/api/v1/maintenance/devices", **self.headersA
        )
        self.assertEqual(listedByA.status_code, 200, listedByA.content)
        codes = [row["code"] for row in listedByA.json()["data"]]
        self.assertNotIn(
            "B-ONLY-1",
            codes,
            "tenant A can see a device belonging to tenant B",
        )

    def testTenantCannotFetchAnotherTenantsDeviceById(self) -> None:
        """Guessing an id must not work either — list filtering is not enough."""

        clientB = APIClient()
        created = clientB.post(
            "/api/v1/maintenance/devices",
            {"code": "B-ONLY-2", "name": "دومی", "department": "mechanical"},
            format="json",
            **self.headersB,
        )
        self.assertIn(created.status_code, (200, 201), created.content)
        deviceId = created.json()["data"]["id"]

        fetched = self.client.get(
            f"/api/v1/maintenance/devices/{deviceId}", **self.headersA
        )
        self.assertIn(
            fetched.status_code,
            (403, 404),
            f"tenant A fetched tenant B's device: {fetched.status_code}",
        )

    # -- writes -----------------------------------------------------------

    def testRequestBodyCannotRedirectAWriteIntoAnotherTenant(self) -> None:
        """The one that found a real hole.

        `POST /maintenance/devices` reads `tenantId` from the request body.
        If that value is trusted, any authenticated user can plant rows in
        any tenant they can name — and tenant ids are not secrets; they are
        returned by the API in every payload.
        """

        response = self.client.post(
            "/api/v1/maintenance/devices",
            {
                "tenantId": str(self.tenantB["tenantId"]),
                "code": "PLANTED-BY-A",
                "name": "کاشته‌شده توسط تنانت الف",
                "department": "mechanical",
            },
            format="json",
            **self.headersA,
        )

        self.assertIn(
            response.status_code,
            (400, 403),
            "a cross-tenant write was accepted instead of refused",
        )

        # And nothing may have landed in B regardless of the status code.
        listedByB = APIClient().get("/api/v1/maintenance/devices", **self.headersB)
        self.assertEqual(listedByB.status_code, 200, listedByB.content)
        codes = [row["code"] for row in listedByB.json()["data"]]
        self.assertNotIn(
            "PLANTED-BY-A",
            codes,
            "tenant A wrote a device into tenant B's data",
        )

    def testWorkOrderSubmissionCannotBeRedirected(self) -> None:
        """Same attack through the work-order endpoint."""

        clientB = APIClient()
        deviceB = clientB.post(
            "/api/v1/maintenance/devices",
            {"code": "B-DEV-WO", "name": "تجهیز ب", "department": "mechanical"},
            format="json",
            **self.headersB,
        )
        self.assertIn(deviceB.status_code, (200, 201), deviceB.content)
        deviceBId = deviceB.json()["data"]["id"]

        response = self.client.post(
            "/api/v1/maintenance/work-orders",
            {
                "tenantId": str(self.tenantB["tenantId"]),
                "deviceId": deviceBId,
                "title": "سفارش کار جعلی",
                "orderType": "corrective",
                "priority": "high",
            },
            format="json",
            **self.headersA,
        )
        self.assertIn(
            response.status_code,
            (400, 403, 404),
            "tenant A submitted a work order against tenant B's device",
        )

    def testUnknownTenantIdIsRejectedNotSilentlyAccepted(self) -> None:
        """A tenantId that exists nowhere must not create a shadow tenant."""

        response = self.client.post(
            "/api/v1/maintenance/devices",
            {
                "tenantId": str(uuid.uuid4()),
                "code": "GHOST-1",
                "name": "تنانت وهمی",
                "department": "mechanical",
            },
            format="json",
            **self.headersA,
        )
        self.assertIn(response.status_code, (400, 403, 404), response.content)

    def testOwnTenantIdInTheBodyIsStillAccepted(self) -> None:
        """The fix must not break the legitimate case.

        Clients do send their own tenantId. Rejecting a *matching* value
        would be a regression dressed up as a security fix.
        """

        response = self.client.post(
            "/api/v1/maintenance/devices",
            {
                "tenantId": str(self.tenantAId),
                "code": "OWN-TENANT-OK",
                "name": "تجهیز خودی",
                "department": "mechanical",
            },
            format="json",
            **self.headersA,
        )
        self.assertIn(response.status_code, (200, 201), response.content)
