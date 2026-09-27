"""PM calendar schedule (برنامه‌ی زمان‌بندی PM تقویمی) — public REST contract.

One aggregated feed, ``GET /api/v1/maintenance/pm-schedule``, powers the
Jalali month grid: active PM plans whose next run falls inside the requested
window, every overdue plan no matter how far back, never-executed plans as
undated rows, and the legacy device-level PM only for devices that carry no
plan at all (so a device never shows up twice).
"""

from __future__ import annotations

from datetime import date, timedelta

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from tests.support.phase6Helpers import loginViaApi, seedPlatform

BASE = "/api/v1/maintenance"


class PmScheduleApiBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    def createDevice(self, code: str, department: str = "mechanical") -> dict:
        response = self.client.post(
            f"{BASE}/devices",
            {"code": code, "name": f"دستگاه {code}", "department": department, "pmIntervalDays": 30},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def createPlan(self, deviceId: str, title: str = "تعویض روغن", discipline: str = "mechanical") -> dict:
        response = self.client.post(
            f"{BASE}/devices/{deviceId}/pm-plans",
            {
                "title": title,
                "discipline": discipline,
                "frequencyEvery": 1,
                "frequencyUnit": "month",
                "estimatedMinutes": 60,
                "responsibleName": "حسین کریمی",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def executePlan(self, planId: str, performedOn: date) -> None:
        response = self.client.post(
            f"{BASE}/pm-plans/{planId}/executions",
            {"performedOn": performedOn.isoformat(), "performedByName": "حسین کریمی"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)

    def schedule(self, **params: str) -> list[dict]:
        response = self.client.get(f"{BASE}/pm-schedule", params, **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]


class PmScheduleAuthTests(PmScheduleApiBase):
    def testRequiresAuthentication(self) -> None:
        response = APIClient().get(f"{BASE}/pm-schedule")
        self.assertEqual(response.status_code, 401)


class PmSchedulePlanRowsTests(PmScheduleApiBase):
    def testOverduePlanAppearsWithComputedDueDate(self) -> None:
        """Executed 45 days ago on a monthly plan → due 15 days ago → overdue."""
        today = date.today()
        device = self.createDevice("PMP-A")
        plan = self.createPlan(device["id"])
        self.executePlan(plan["id"], today - timedelta(days=45))

        rows = self.schedule()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["source"], "plan")
        self.assertEqual(row["planId"], plan["id"])
        self.assertEqual(row["deviceCode"], "PMP-A")
        self.assertEqual(row["title"], "تعویض روغن")
        self.assertEqual(row["dueOn"], (today - timedelta(days=15)).isoformat())
        self.assertTrue(row["overdue"])
        self.assertEqual(row["responsibleName"], "حسین کریمی")

    def testInWindowPlanAppears(self) -> None:
        """Due in 5 days; a 30-day window from today must contain it."""
        today = date.today()
        device = self.createDevice("PMP-B")
        plan = self.createPlan(device["id"])
        self.executePlan(plan["id"], today - timedelta(days=25))

        rows = self.schedule(
            fromDate=today.isoformat(), toDate=(today + timedelta(days=30)).isoformat()
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["dueOn"], (today + timedelta(days=5)).isoformat())
        self.assertFalse(rows[0]["overdue"])

    def testFarFuturePlanDropsOutOfWindow(self) -> None:
        """A quarterly plan due in ~65 days is outside the 30-day window."""
        today = date.today()
        device = self.createDevice("PMP-C")
        response = self.client.post(
            f"{BASE}/devices/{device['id']}/pm-plans",
            {
                "title": "بازرسی فصلی",
                "discipline": "mechanical",
                "frequencyEvery": 3,
                "frequencyUnit": "month",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.executePlan(response.json()["data"]["id"], today - timedelta(days=25))

        rows = self.schedule(
            fromDate=today.isoformat(), toDate=(today + timedelta(days=30)).isoformat()
        )
        self.assertEqual(rows, [])

    def testNeverExecutedPlanIsListedAsUndated(self) -> None:
        device = self.createDevice("PMP-D")
        self.createPlan(device["id"])

        rows = self.schedule()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["dueOn"], "")
        self.assertFalse(rows[0]["overdue"])

    def testDisciplineFilter(self) -> None:
        mechanical = self.createDevice("PMP-E", department="mechanical")
        electrical = self.createDevice("PMP-F", department="electrical")
        self.createPlan(mechanical["id"], discipline="mechanical")
        self.createPlan(electrical["id"], title="بازرسی تابلوی برق", discipline="electrical")

        rows = self.schedule(discipline="electrical")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["discipline"], "electrical")
        self.assertEqual(rows[0]["deviceCode"], "PMP-F")


class PmScheduleDeviceFallbackTests(PmScheduleApiBase):
    def recordDevicePm(self, deviceId: str, performedOn: date) -> None:
        response = self.client.post(
            f"{BASE}/devices/{deviceId}/pm",
            {"performedOn": performedOn.isoformat()},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

    def testDeviceWithoutPlanFallsBackToLegacyPm(self) -> None:
        """pmIntervalDays-based PM: 40 days ago on a 30-day cadence → overdue row."""
        today = date.today()
        device = self.createDevice("PMP-G")
        self.recordDevicePm(device["id"], today - timedelta(days=40))

        rows = self.schedule()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["source"], "device")
        self.assertEqual(row["deviceCode"], "PMP-G")
        self.assertTrue(row["overdue"])
        self.assertEqual(row["dueOn"], (today - timedelta(days=10)).isoformat())

    def testDeviceWithPlanIsNotDuplicated(self) -> None:
        """The named plan wins; no extra legacy device row beside it."""
        today = date.today()
        device = self.createDevice("PMP-H")
        self.recordDevicePm(device["id"], today - timedelta(days=40))
        plan = self.createPlan(device["id"])
        self.executePlan(plan["id"], today - timedelta(days=25))

        rows = self.schedule()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "plan")

    def testDeviceFallbackRespectsWindow(self) -> None:
        """Legacy PM due in 10 days appears in a 30-day window but not a 5-day one."""
        today = date.today()
        device = self.createDevice("PMP-I")
        self.recordDevicePm(device["id"], today - timedelta(days=20))

        inWindow = self.schedule(
            fromDate=today.isoformat(), toDate=(today + timedelta(days=30)).isoformat()
        )
        self.assertEqual(len(inWindow), 1)
        narrow = self.schedule(
            fromDate=today.isoformat(), toDate=(today + timedelta(days=5)).isoformat()
        )
        self.assertEqual(narrow, [])
