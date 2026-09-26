"""Phase 26.1 — operator-defined taxonomy values.

Every registry dropdown ships with a canonical catalogue, but the UI also lets
an operator type a value that was never in the list («سوله», «جوشکاری»). These
tests pin that contract end to end: the new label round-trips through the API
unchanged, it is usable as a filter, canonical codes are still snapped to their
canonical spelling, and genuinely broken input is still rejected.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from tests.support.phase6Helpers import loginViaApi, seedPlatform

BASE = "/api/v1/maintenance"


class OpenTaxonomyApiTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    # -- helpers --------------------------------------------------------------
    def postJson(self, path: str, payload: dict) -> object:
        return self.client.post(f"{BASE}{path}", payload, format="json", **self.auth)

    def createDevice(self, code: str = "PUMP-01", department: str = "mechanical") -> dict:
        response = self.postJson(
            "/devices",
            {
                "code": code,
                "name": "پمپ خنک‌کننده اصلی",
                "location": "سالن تولید A",
                "department": department,
                "pmIntervalDays": 30,
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    # -- location kind ---------------------------------------------------------
    def testLocationAcceptsAPlantDefinedKind(self) -> None:
        response = self.postJson("/locations", {"code": "HALL-3", "name": "سوله شماره ۳", "kind": "سوله"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["data"]["kind"], "سوله")

        listing = self.client.get(f"{BASE}/locations", **self.auth)
        self.assertEqual(listing.status_code, 200)
        kinds = [row["kind"] for row in listing.json()["data"]]
        self.assertIn("سوله", kinds)

    def testLocationKindKeepsCanonicalSpelling(self) -> None:
        response = self.postJson("/locations", {"code": "SITE-1", "name": "سایت مرکزی", "kind": "SITE"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["data"]["kind"], "site")

    def testLocationKindCollapsesInnerWhitespace(self) -> None:
        response = self.postJson(
            "/locations", {"code": "LINE-1", "name": "خط بسته‌بندی", "kind": "  خط   تولید  "}
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["data"]["kind"], "خط تولید")

    def testLocationRejectsEmptyAndOverlongKinds(self) -> None:
        blank = self.postJson("/locations", {"code": "X-1", "name": "بدون نوع", "kind": "   "})
        self.assertEqual(blank.status_code, 400, blank.content)
        overlong = self.postJson("/locations", {"code": "X-2", "name": "نوع بلند", "kind": "x" * 25})
        self.assertEqual(overlong.status_code, 400, overlong.content)

    def testLocationRejectsControlCharactersInKind(self) -> None:
        response = self.postJson("/locations", {"code": "X-3", "name": "مخرب", "kind": "سوله\x07"})
        self.assertEqual(response.status_code, 400, response.content)

    # -- personnel specialty ---------------------------------------------------
    def testPersonnelAcceptsAPlantDefinedSpecialty(self) -> None:
        response = self.postJson(
            "/personnel",
            {
                "personnelCode": "P-100",
                "fullName": "حمید جوشکار",
                "specialty": "جوشکاری",
                "active": True,
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["data"]["specialty"], "جوشکاری")

    # -- PM discipline ---------------------------------------------------------
    def testPmPlanAcceptsAPlantDefinedDiscipline(self) -> None:
        device = self.createDevice()
        response = self.postJson(
            f"/devices/{device['id']}/pm-plans",
            {
                "title": "بازرسی جوش مخزن",
                "discipline": "جوشکاری",
                "checklist": ["بازرسی چشمی درز جوش"],
                "frequencyEvery": 3,
                "frequencyUnit": "month",
                "estimatedMinutes": 90,
                "responsibleName": "حمید جوشکار",
                "active": True,
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["data"]["discipline"], "جوشکاری")

        profile = self.client.get(f"{BASE}/devices/{device['id']}/profile", **self.auth)
        self.assertEqual(profile.status_code, 200)
        disciplines = [plan["discipline"] for plan in profile.json()["data"]["pmPlans"]]
        self.assertIn("جوشکاری", disciplines)

    def testPmPlanStillRejectsAnUnknownFrequencyUnit(self) -> None:
        """Scheduling maths depends on the unit, so that dropdown stays closed."""

        device = self.createDevice()
        response = self.postJson(
            f"/devices/{device['id']}/pm-plans",
            {
                "title": "بازرسی",
                "discipline": "mechanical",
                "frequencyEvery": 1,
                "frequencyUnit": "fortnight",
            },
        )
        self.assertEqual(response.status_code, 400, response.content)

    # -- assignment role -------------------------------------------------------
    def testAssignmentAcceptsAPlantDefinedRole(self) -> None:
        device = self.createDevice()
        person = self.postJson(
            "/personnel",
            {
                "personnelCode": "P-200",
                "fullName": "مینا کاظمی",
                "specialty": "electrical",
                "active": True,
            },
        ).json()["data"]
        response = self.client.put(
            f"{BASE}/devices/{device['id']}/assignments",
            {
                "rows": [
                    {
                        "personnelId": person["id"],
                        "personnelName": person["fullName"],
                        "role": "ناظر ایمنی",
                        "unit": "HSE",
                    }
                ]
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"][0]["role"], "ناظر ایمنی")

    # -- device department + criticality ---------------------------------------
    def testDeviceAcceptsAPlantDefinedDepartment(self) -> None:
        device = self.createDevice(code="WELD-01", department="جوشکاری")
        self.assertEqual(device["department"], "جوشکاری")

        listing = self.client.get(f"{BASE}/devices", **self.auth)
        self.assertEqual(listing.status_code, 200)
        departments = [row["department"] for row in listing.json()["data"]]
        self.assertIn("جوشکاری", departments)

    def testNameplateAcceptsAPlantDefinedCriticality(self) -> None:
        device = self.createDevice(code="PRESS-01")
        response = self.client.patch(
            f"{BASE}/devices/{device['id']}/nameplate",
            {"criticality": "خیلی بحرانی"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["criticality"], "خیلی بحرانی")

    def testFleetAnalyticsFiltersByAPlantDefinedDepartment(self) -> None:
        self.createDevice(code="WELD-02", department="جوشکاری")
        self.createDevice(code="PUMP-09", department="mechanical")
        response = self.client.get(
            f"{BASE}/analytics/fleet", {"department": "جوشکاری"}, **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)
        codes = [row["code"] for row in response.json()["data"]["rows"]]
        self.assertEqual(codes, ["WELD-02"])
