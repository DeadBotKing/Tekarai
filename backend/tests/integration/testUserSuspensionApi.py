"""The user status endpoint (v0.17.1) — suspend / reactivate.

The identity domain has had the 8-state lifecycle and the §19 policy for
a while, but nothing HTTP ever reached it: the use case sat in the
container with no route. This file pins the REST contract the users table
now depends on: an admin suspends and reactivates a colleague, nobody
suspends themselves, the anonymous are refused, and an invalid target is
a validation error, not a silent noop.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from tests.support.phase6Helpers import loginViaApi, seedPlatform

BASE = "/api/v1/users"


class UserStatusApi(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        # The platform admin creates a colleague to act on.
        response = self.client.post(
            f"{BASE}",
            {
                "username": "colleague",
                "email": "colleague@tekarai.local",
                "password": "Colleague-Pass-2026",
                "displayName": "همکار آزمون",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.colleagueId = response.json()["data"]["id"]

    def testSuspendAndReactivateRoundTrip(self) -> None:
        response = self.client.patch(
            f"{BASE}/{self.colleagueId}/status",
            {"target": "suspended"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["status"], "suspended")

        # The suspended colleague is gone from the default user list…
        listed = self.client.get(f"{BASE}?status=suspended", **self.auth).json()["data"]
        self.assertTrue(any(row["id"] == self.colleagueId for row in listed))

        # …and comes back with reactivation.
        response = self.client.patch(
            f"{BASE}/{self.colleagueId}/status",
            {"target": "active"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["status"], "active")

    def testNobodySuspendsThemselves(self) -> None:
        from apps.identity.infrastructure.models import UserModel

        admin = UserModel.objects.filter(username="platform-admin").first()
        assert admin is not None
        response = self.client.patch(
            f"{BASE}/{admin.id}/status",
            {"target": "suspended"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 403, response.content)

    def testAnonymousIsRefused(self) -> None:
        response = self.client.patch(
            f"{BASE}/{self.colleagueId}/status",
            {"target": "suspended"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def testAnInvalidTargetIsRejected(self) -> None:
        response = self.client.patch(
            f"{BASE}/{self.colleagueId}/status",
            {"target": "disabled"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)

    def testAnUnknownUserIs404(self) -> None:
        response = self.client.patch(
            f"{BASE}/00000000-0000-0000-0000-000000000000/status",
            {"target": "suspended"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 404)
