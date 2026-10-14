"""The personnel ↔ account link (v0.16.0).

پرسنل نت is a directory of technicians; «کاربران» is who may sign in.
Linking the two is what lets features match work by identity instead of by
display name. This file pins the REST contract: a link that echoes back
with the account's display name, the three refusals (not a uuid, no such
user, account already taken by another person), and unlinking.
"""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.identity.infrastructure.models import UserModel
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform

BASE = "/api/v1/maintenance"


class PersonnelUserLinkApi(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        self.tenantId = platformTenantId()
        self.reza = UserModel.objects.create(
            id=uuid.uuid4(),
            tenantId=self.tenantId,
            username="reza.ahmadi",
            email="reza@tekarai.local",
            passwordHash="not-a-real-hash",
            displayName="رضا احمدی",
        )

    def createPerson(self, code: str, linkedUserId: str = "") -> tuple[int, dict]:
        response = self.client.post(
            f"{BASE}/personnel",
            {
                "personnelCode": code,
                "fullName": f"نیروی {code}",
                "specialty": "mechanical",
                "linkedUserId": linkedUserId,
            },
            format="json",
            **self.auth,
        )
        return response.status_code, response.json().get("data", {})

    # -- the happy path -------------------------------------------------------

    def testLinkEchoesBackWithTheAccountsDisplayName(self) -> None:
        status, data = self.createPerson("MT-700", str(self.reza.id))
        self.assertEqual(status, 201)
        self.assertEqual(data["linkedUserId"], str(self.reza.id))
        self.assertEqual(data["linkedUserDisplayName"], "رضا احمدی")

        listed = self.client.get(f"{BASE}/personnel", **self.auth).json()["data"]
        row = next(item for item in listed if item["personnelCode"] == "MT-700")
        self.assertEqual(row["linkedUserId"], str(self.reza.id))
        self.assertEqual(row["linkedUserDisplayName"], "رضا احمدی")

    def testUnlinkedPeopleCarryEmptyStringsNotNulls(self) -> None:
        status, data = self.createPerson("MT-701")
        self.assertEqual(status, 201)
        self.assertEqual(data["linkedUserId"], "")
        self.assertEqual(data["linkedUserDisplayName"], "")

    # -- the three refusals ---------------------------------------------------

    def testAnAccountCanBeOwnedByOnlyOnePerson(self) -> None:
        status, _ = self.createPerson("MT-702", str(self.reza.id))
        self.assertEqual(status, 201)

        status, _ = self.createPerson("MT-703", str(self.reza.id))
        self.assertEqual(status, 422)

        # The same person re-saving the same link stays fine — the holder
        # check excludes the record being saved.
        response = self.client.patch(
            f"{BASE}/personnel/{self.personnelId('MT-702')}",
            {
                "personnelCode": "MT-702",
                "fullName": "نیروی MT-702",
                "specialty": "mechanical",
                "linkedUserId": str(self.reza.id),
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)

    def testAnUnknownUserIsRefused(self) -> None:
        status, _ = self.createPerson("MT-704", str(uuid.uuid4()))
        self.assertEqual(status, 422)

    def testANonUuidLinkIsRefused(self) -> None:
        status, _ = self.createPerson("MT-705", "definitely-not-a-uuid")
        self.assertEqual(status, 422)

    def testAUserOfAnotherTenantCannotBeLinked(self) -> None:
        outsider = UserModel.objects.create(
            id=uuid.uuid4(),
            tenantId=uuid.uuid4(),
            username="outsider",
            email="outsider@elsewhere.local",
            passwordHash="not-a-real-hash",
            displayName="خارجی",
        )
        status, _ = self.createPerson("MT-706", str(outsider.id))
        self.assertEqual(status, 422)

    # -- unlinking -------------------------------------------------------------

    def testPatchWithAnEmptyLinkFreesTheAccount(self) -> None:
        self.createPerson("MT-707", str(self.reza.id))
        response = self.client.patch(
            f"{BASE}/personnel/{self.personnelId('MT-707')}",
            {
                "personnelCode": "MT-707",
                "fullName": "نیروی MT-707",
                "specialty": "mechanical",
                "linkedUserId": "",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["linkedUserId"], "")

        # The freed account can now be linked to somebody else.
        status, _ = self.createPerson("MT-708", str(self.reza.id))
        self.assertEqual(status, 201)

    # -- helper ----------------------------------------------------------------

    def personnelId(self, code: str) -> str:
        listed = self.client.get(f"{BASE}/personnel", **self.auth).json()["data"]
        return next(item["id"] for item in listed if item["personnelCode"] == code)
