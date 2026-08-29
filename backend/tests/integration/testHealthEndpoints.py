"""Integration tests for the health check endpoints (Phase 01 §17)."""

from __future__ import annotations

from typing import Any
from unittest import mock

from django.db import connections
from django.test import SimpleTestCase, TestCase


def patchDatabaseCursor(sideEffect: Any) -> mock._patch:
    """Patch ``cursor`` on the real database wrapper.

    Patching the ``django.db.connection`` proxy confuses Django's test
    teardown (the proxy's ``__dict__`` does not hold the wrapper's
    attributes), so tests patch the concrete wrapper from the handler.
    """
    return mock.patch.object(connections["default"], "cursor", side_effect=sideEffect)


class HealthLiveEndpointTests(SimpleTestCase):
    def testReturnsOkStatus(self) -> None:
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["phase"], "01-foundation")

    def testReportsApplicationComponent(self) -> None:
        response = self.client.get("/healthz/")
        components = response.json()["components"]
        self.assertIn("application", components)
        self.assertEqual(components["application"]["status"], "ok")

    def testDatabaseIsNotTouchedByLiveness(self) -> None:
        with patchDatabaseCursor(AssertionError):
            response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)

    def testRejectsNonGetRequests(self) -> None:
        self.assertEqual(self.client.post("/healthz/").status_code, 405)


class HealthReadyEndpointTests(TestCase):
    def testReturnsOkStatusWithDatabase(self) -> None:
        response = self.client.get("/readyz/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")

    def testReportsDatabaseComponentDetails(self) -> None:
        response = self.client.get("/readyz/")
        database = response.json()["components"]["database"]
        self.assertEqual(database["status"], "ok")
        self.assertIn("latencyMs", database)
        self.assertIn("engine", database)

    def testNeverLeaksCredentialsInPayload(self) -> None:
        from django.conf import settings

        response = self.client.get("/readyz/")
        rawPayload = response.content.decode("utf-8")
        dbPassword = settings.DATABASES["default"].get("PASSWORD") or ""
        if dbPassword:
            self.assertNotIn(dbPassword, rawPayload)

    def testReturns503WhenDatabaseIsDown(self) -> None:
        with patchDatabaseCursor(RuntimeError("database unreachable")):
            response = self.client.get("/readyz/")
        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["components"]["database"]["status"], "error")

    def testRejectsNonGetRequests(self) -> None:
        self.assertEqual(self.client.post("/readyz/").status_code, 405)
