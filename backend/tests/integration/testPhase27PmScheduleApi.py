"""PM schedule calendar (برنامه‌ی زمان‌بندی PM تقویمی) — public REST contract.

``GET /api/v1/maintenance/pm-schedule`` returns the cross-device upcoming-PM
feed that powers the maintenance calendar page: named plan rows (with dueOn
recomputed from the last execution) plus a legacy device-level PM row only
for devices that carry no plan — so nothing is double-counted. Overdue rows
always travel, whatever the window; never-executed plans travel undated.
"""

from __future__ import annotations

import datetime

from tests.integration.testPhase26AssetRegistry import AssetRegistryApiBase


class PmScheduleApiTests(AssetRegistryApiBase):
    BASE = "/api/v1/maintenance"

    TODAY = datetime.date.today()

    def iso(self, offsetDays: int) -> str:
        return (self.TODAY + datetime.timedelta(days=offsetDays)).isoformat()

    def registerPlanOn(self, deviceId: str, title: str = "سرویس ماهانه", discipline: str = "electrical") -> dict:
        response = self.client.post(
            f"{self.BASE}/devices/{deviceId}/pm-plans",
            {
                "title": title,
                "discipline": discipline,
                "frequencyEvery": 1,
                "frequencyUnit": "month",
                "estimatedMinutes": 60,
                "responsibleName": "مهندس نگهداری",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def executePlan(self, planId: str, performedOn: str) -> None:
        response = self.client.post(
            f"{self.BASE}/pm-plans/{planId}/executions",
            {"performedOn": performedOn, "performedByName": "تیم نگهداری"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)

    def fetchSchedule(self, query: str = "") -> list[dict]:
        response = self.client.get(f"{self.BASE}/pm-schedule{query}", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]

    # ------------------------------------------------------------------ auth

    def testRequiresAuthentication(self) -> None:
        response = self.client.get(f"{self.BASE}/pm-schedule")
        self.assertIn(response.status_code, (401, 403))

    # ------------------------------------------------------------- plan rows

    def testOverduePlanIsAlwaysIncluded(self) -> None:
        device = self.createDevice()
        plan = self.registerPlanOn(device["id"])
        self.executePlan(plan["id"], performedOn=self.iso(-30))

        items = self.fetchSchedule()
        match = [item for item in items if item.get("planId") == plan["id"]]
        self.assertEqual(len(match), 1, items)
        item = match[0]
        self.assertEqual(item["source"], "plan")
        self.assertTrue(item["overdue"], item)
        # monthly plan: dueOn = performedOn + 30 days
        expected = (self.TODAY + datetime.timedelta(days=-30 + 30)).isoformat()
        self.assertEqual(item["dueOn"], expected, item)
        self.assertEqual(item["deviceCode"], "")

    def testPlanInWindowIsIncluded(self) -> None:
        device = self.createDevice()
        plan = self.registerPlanOn(device["id"])
        self.executePlan(plan["id"], performedOn=self.iso(-20))

        items = self.fetchSchedule()  # default window today → today+60
        match = [item for item in items if item.get("planId") == plan["id"]]
        self.assertEqual(len(match), 1, items)
        self.assertFalse(match[0]["overdue"], match[0])

    def testFarFuturePlanIsExcludedFromDefaultWindow(self) -> None:
        device = self.createDevice()
        plan = self.registerPlanOn(device["id"], title="بازدید سالانه")
        self.executePlan(plan["id"], performedOn=self.iso(45))

        items = self.fetchSchedule()
        self.assertFalse(
            any(item.get("planId") == plan["id"] for item in items), items
        )

    def testNeverExecutedPlanTravelsUndated(self) -> None:
        device = self.createDevice()
        plan = self.registerPlanOn(device["id"])

        items = self.fetchSchedule()
        match = [item for item in items if item.get("planId") == plan["id"]]
        self.assertEqual(len(match), 1, items)
        self.assertEqual(match[0]["dueOn"], "", match[0])
        self.assertFalse(match[0]["overdue"], match[0])

    def testDisciplineFilterNarrowsTheFeed(self) -> None:
        device = self.createDevice()
        plan = self.registerPlanOn(device["id"], discipline="electrical")

        items = self.fetchSchedule("?discipline=mechanical")
        self.assertFalse(any(item.get("planId") == plan["id"] for item in items), items)

        items = self.fetchSchedule("?discipline=electrical")
        self.assertTrue(any(item.get("planId") == plan["id"] for item in items), items)

    # ----------------------------------------------------------- device rows

    def testDeviceWithoutPlanGetsFallbackRow(self) -> None:
        device = self.createDevice()
        response = self.client.post(
            f"{self.BASE}/devices/{device['id']}/pm",
            {"performedOn": self.iso(-20)},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

        dueOn = self.iso(10)
        items = self.fetchSchedule(f"?toDate={dueOn}")
        match = [item for item in items if item.get("deviceId") == device["id"]]
        self.assertEqual(len(match), 1, items)
        self.assertEqual(match[0]["source"], "device", match[0])
        self.assertEqual(match[0]["dueOn"], dueOn, match[0])

    def testDeviceWithPlanHasNoDeviceRow(self) -> None:
        device = self.createDevice()
        response = self.client.post(
            f"{self.BASE}/devices/{device['id']}/pm",
            {"performedOn": self.iso(-20)},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        plan = self.registerPlanOn(device["id"])
        self.executePlan(plan["id"], performedOn=self.iso(-20))

        items = self.fetchSchedule()
        match = [item for item in items if item.get("deviceId") == device["id"]]
        self.assertEqual(len(match), 1, items)
        self.assertEqual(match[0]["source"], "plan", match[0])

    def testDeviceFallbackRespectsWindow(self) -> None:
        device = self.createDevice()
        response = self.client.post(
            f"{self.BASE}/devices/{device['id']}/pm",
            {"performedOn": self.iso(-20)},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

        items = self.fetchSchedule(f"?toDate={self.iso(9)}")  # due is today+10
        self.assertFalse(
            any(item.get("deviceId") == device["id"] for item in items), items
        )
