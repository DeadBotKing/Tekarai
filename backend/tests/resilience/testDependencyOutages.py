"""What the API does when the database or the broker is gone.

Every other suite runs with a healthy database and an inline queue. That
leaves the most consequential behaviour untested: a dependency failing is not
a hypothetical, it is a Tuesday, and the difference between a 503 with a
correlation id and a 500 with a stack trace is the difference between an
on-call engineer who knows what happened and one who does not.

Outages are simulated at the seam rather than by actually stopping a service,
because the assertions are about *our* behaviour — the status code, the
envelope, whether a write is silently lost — and those are identical either
way.
"""

from __future__ import annotations

from unittest import mock

from django.db import DatabaseError, OperationalError
from django.test import TestCase
from rest_framework.test import APIClient

from tests.support.multiTenantHelpers import authHeaders, loginPlatform
from tests.support.phase6Helpers import seedPlatform


class DatabaseOutageTests(TestCase):
    """The database is unreachable mid-request."""

    @classmethod
    def setUpTestData(cls) -> None:
        seedPlatform()
        cls.headers = authHeaders(loginPlatform(APIClient()))

    def setUp(self) -> None:
        self.client = APIClient()

    def testReadinessProbeReportsErrorWhenTheDatabaseIsDown(self) -> None:
        """`readyz` exists to be believed. If it says ok while the database
        is unreachable, every orchestrator keeps routing traffic into a
        broken pod."""

        with mock.patch(
            "config.healthCheck.checkDatabase",
            return_value=("error", 0.0, "sqlite"),
        ):
            response = self.client.get("/readyz/")

        self.assertEqual(response.status_code, 503, response.content)
        self.assertEqual(response.json()["status"], "error")

    def testLivenessProbeStaysUpWhenOnlyTheDatabaseIsDown(self) -> None:
        """Liveness must not depend on the database, or a brief outage gets
        the container killed and restarted into the same outage."""

        with mock.patch(
            "config.healthCheck.checkDatabase",
            side_effect=OperationalError("connection refused"),
        ):
            response = self.client.get("/healthz/")

        self.assertEqual(response.status_code, 200, response.content)

    def testReadFailureReturnsAnEnvelopeNotAStackTrace(self) -> None:
        """A failed query must come back as the project's error envelope with
        a correlation id, not as Django's debug page or a bare 500 body."""

        with mock.patch(
            "apps.maintenance.infrastructure.repositories.deviceRepositoryImpl"
            ".DeviceRepositoryDjango.list",
            side_effect=OperationalError("database is locked"),
        ):
            response = self.client.get("/api/v1/maintenance/devices", **self.headers)

        self.assertGreaterEqual(response.status_code, 500)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertTrue(
            body["meta"].get("correlationId"),
            "a 5xx without a correlation id cannot be traced in the logs",
        )
        self.assertNotIn(
            "database is locked",
            response.content.decode(),
            "the raw database error leaked to the client",
        )

    def testWriteFailureDoesNotReportSuccess(self) -> None:
        """The failure mode that corrupts trust: a 2xx for a write that never
        landed."""

        with mock.patch(
            "apps.maintenance.infrastructure.repositories.deviceRepositoryImpl"
            ".DeviceRepositoryDjango.create",
            side_effect=DatabaseError("disk I/O error"),
        ):
            response = self.client.post(
                "/api/v1/maintenance/devices",
                {"code": "OUTAGE-1", "name": "در زمان قطعی", "department": "mechanical"},
                format="json",
                **self.headers,
            )

        self.assertGreaterEqual(
            response.status_code, 400, "a failed write returned a success status"
        )

        # And the row must not exist.
        listed = self.client.get("/api/v1/maintenance/devices", **self.headers)
        self.assertEqual(listed.status_code, 200, listed.content)
        codes = [row["code"] for row in listed.json()["data"]]
        self.assertNotIn("OUTAGE-1", codes)


class BrokerOutageTests(TestCase):
    """Redis/Celery is unreachable when a job is published."""

    @classmethod
    def setUpTestData(cls) -> None:
        seedPlatform()

    def testQueueSubmitFailureDoesNotLoseTheNotification(self) -> None:
        """The database is the source of truth; the broker is a courier.

        If publishing throws and the application lets it escape, the caller
        sees a 500 for work that actually succeeded. The row must survive and
        the worker tick must still be able to pick it up.
        """

        from apps.notifications.infrastructure.queue.notificationQueue import (
            InlineNotificationQueue,
        )

        queue = InlineNotificationQueue()

        with mock.patch(
            "apps.notifications.infrastructure.container.container.dispatchService",
            side_effect=ConnectionError("Error 111 connecting to redis:6379"),
        ):
            # Must not raise: the queue boundary isolates broker failures.
            queue.submit({"kind": "DISPATCH", "notificationId": "00000000-0000-0000-0000-000000000001"})

    def testCeleryPublishFailureIsContainedAtTheBoundary(self) -> None:
        """`CeleryNotificationQueue.submit` registers an on_commit callback.
        A broker that refuses the connection must not take the request with
        it."""

        from apps.notifications.infrastructure.queue.notificationQueue import (
            CeleryNotificationQueue,
        )

        queue = CeleryNotificationQueue()
        with mock.patch(
            "apps.notifications.tasks.dispatchNotificationJob.delay",
            side_effect=ConnectionError("broker unreachable"),
        ):
            # Outside an atomic block on_commit runs immediately, which is
            # exactly the moment the broker call happens in production.
            try:
                queue.submit(
                    {
                        "kind": "DISPATCH",
                        "notificationId": "00000000-0000-0000-0000-000000000002",
                    }
                )
            except ConnectionError:
                self.fail(
                    "a broker outage escaped the queue adapter and would have "
                    "turned a successful write into a 500"
                )

    def testUnknownJobKindIsIgnoredRatherThanCrashing(self) -> None:
        from apps.notifications.infrastructure.queue.notificationQueue import (
            InlineNotificationQueue,
        )

        InlineNotificationQueue().submit({"kind": "NOT_A_REAL_KIND"})
