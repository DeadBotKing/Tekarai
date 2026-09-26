"""Phase 26 — asset registry + analytics public REST contract.

Walks the whole equipment file the Persian UI consumes: a hierarchical
location, a personnel directory, device nameplate, technical specifications,
PM plans across the seven disciplines, a shared-part bill of materials, device
assignments, and finally the analytics endpoints that count repairs and part
consumption from the recorded rows.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from tests.support.phase6Helpers import loginViaApi, seedPlatform

BASE = "/api/v1/maintenance"


class AssetRegistryApiBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    # -- helpers ----------------------------------------------------------------
    def createDevice(self, code: str = "PUMP-01", department: str = "mechanical") -> dict:
        response = self.client.post(
            f"{BASE}/devices",
            {
                "code": code,
                "name": "پمپ خنک‌کننده اصلی",
                "location": "سالن تولید A",
                "department": department,
                "pmIntervalDays": 30,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def createLocation(self, code: str, name: str, kind: str, parentId: str = "") -> dict:
        response = self.client.post(
            f"{BASE}/locations",
            {"code": code, "name": name, "kind": kind, "parentId": parentId},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def createPersonnel(self, code: str, name: str, specialty: str) -> dict:
        response = self.client.post(
            f"{BASE}/personnel",
            {
                "personnelCode": code,
                "fullName": name,
                "specialty": specialty,
                "unit": "نگهداری و تعمیرات",
                "phone": "09120000000",
                "shift": "صبح",
                "skills": ["تعویض یاتاقان", "هم‌محوری"],
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def createPart(self, code: str, name: str, quantity: str = "20") -> dict:
        response = self.client.post(
            f"{BASE}/spare-parts",
            {"code": code, "name": name, "unit": "عدد", "quantityOnHand": quantity},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def submitWorkOrder(self, deviceId: str, title: str, orderType: str = "corrective") -> dict:
        response = self.client.post(
            f"{BASE}/work-orders",
            {
                "deviceId": deviceId,
                "title": title,
                "description": "شرح خرابی",
                "orderType": orderType,
                "priority": "high",
                "requestedByName": "علی رضایی",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]


class LocationTreeTests(AssetRegistryApiBase):
    def testAuthenticationIsMandatory(self) -> None:
        anonymous = APIClient()
        self.assertEqual(anonymous.get(f"{BASE}/locations").status_code, 401)
        self.assertEqual(anonymous.get(f"{BASE}/personnel").status_code, 401)

    def testNestedLocationsMaterialiseTheirPath(self) -> None:
        site = self.createLocation("SITE-1", "سایت اصفهان", "site")
        building = self.createLocation("BLD-1", "ساختمان تولید", "building", site["id"])
        room = self.createLocation("ROOM-1", "اتاق پمپ‌خانه", "room", building["id"])

        self.assertEqual(site["path"], "سایت اصفهان")
        self.assertEqual(building["path"], "سایت اصفهان / ساختمان تولید")
        self.assertEqual(room["path"], "سایت اصفهان / ساختمان تولید / اتاق پمپ‌خانه")

    def testRenamingAParentRefreshesDescendantPaths(self) -> None:
        site = self.createLocation("SITE-1", "سایت قدیم", "site")
        building = self.createLocation("BLD-1", "ساختمان تولید", "building", site["id"])

        response = self.client.patch(
            f"{BASE}/locations/{site['id']}",
            {"name": "سایت جدید", "kind": "site"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

        listed = self.client.get(f"{BASE}/locations", **self.auth).json()["data"]
        paths = {item["id"]: item["path"] for item in listed}
        self.assertEqual(paths[building["id"]], "سایت جدید / ساختمان تولید")

    def testDuplicateLocationCodeIsRejected(self) -> None:
        self.createLocation("SITE-1", "سایت اصفهان", "site")
        duplicate = self.client.post(
            f"{BASE}/locations",
            {"code": "SITE-1", "name": "سایت دیگر", "kind": "site"},
            format="json",
            **self.auth,
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.content)

    def testLocationCountsAttachedDevices(self) -> None:
        site = self.createLocation("SITE-1", "سایت اصفهان", "site")
        device = self.createDevice()
        self.client.patch(
            f"{BASE}/devices/{device['id']}/nameplate",
            {"locationId": site["id"]},
            format="json",
            **self.auth,
        )
        listed = self.client.get(f"{BASE}/locations", **self.auth).json()["data"]
        self.assertEqual(listed[0]["deviceCount"], 1)


class PersonnelDirectoryTests(AssetRegistryApiBase):
    def testCreateListFilterAndUpdate(self) -> None:
        self.createPersonnel("EMP-1", "رضا محمدی", "mechanical")
        self.createPersonnel("EMP-2", "سارا احمدی", "electrical")

        listed = self.client.get(f"{BASE}/personnel", **self.auth).json()["data"]
        self.assertEqual(len(listed), 2)

        filtered = self.client.get(
            f"{BASE}/personnel?specialty=electrical", **self.auth
        ).json()["data"]
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["fullName"], "سارا احمدی")
        self.assertEqual(filtered[0]["skills"], ["تعویض یاتاقان", "هم‌محوری"])

    def testHydraulicAndPneumaticSpecialtiesAreAccepted(self) -> None:
        for index, specialty in enumerate(("hydraulic", "pneumatic")):
            person = self.createPersonnel(f"EMP-H{index}", f"تکنسین {specialty}", specialty)
            self.assertEqual(person["specialty"], specialty)

    def testDuplicatePersonnelCodeIsRejected(self) -> None:
        self.createPersonnel("EMP-1", "رضا محمدی", "mechanical")
        duplicate = self.client.post(
            f"{BASE}/personnel",
            {"personnelCode": "EMP-1", "fullName": "شخص دیگر", "specialty": "general"},
            format="json",
            **self.auth,
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.content)


class DeviceRegistryTests(AssetRegistryApiBase):
    def testNameplateSpecificationsAndProfile(self) -> None:
        site = self.createLocation("SITE-1", "سایت اصفهان", "site")
        room = self.createLocation("ROOM-1", "اتاق پمپ‌خانه", "room", site["id"])
        device = self.createDevice()

        nameplate = self.client.patch(
            f"{BASE}/devices/{device['id']}/nameplate",
            {
                "manufacturer": "گراندفوس",
                "modelNumber": "NK-125",
                "serialNumber": "SN-99213",
                "criticality": "vital",
                "locationId": room["id"],
                "operatorUnit": "واحد تولید",
                "installedOn": "2024-05-01",
                "purchaseCost": "850000000",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(nameplate.status_code, 200, nameplate.content)
        self.assertEqual(nameplate.json()["data"]["manufacturer"], "گراندفوس")
        self.assertEqual(
            nameplate.json()["data"]["locationPath"], "سایت اصفهان / اتاق پمپ‌خانه"
        )

        specs = self.client.put(
            f"{BASE}/devices/{device['id']}/specifications",
            {
                "rows": [
                    {"label": "دبی", "value": "120", "unit": "مترمکعب بر ساعت"},
                    {"label": "هد", "value": "45", "unit": "متر"},
                ]
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(specs.status_code, 200, specs.content)
        self.assertEqual(len(specs.json()["data"]), 2)

        profile = self.client.get(f"{BASE}/devices/{device['id']}/profile", **self.auth)
        self.assertEqual(profile.status_code, 200, profile.content)
        payload = profile.json()["data"]
        self.assertEqual(payload["device"]["code"], "PUMP-01")
        self.assertEqual(payload["locationPath"], "سایت اصفهان / اتاق پمپ‌خانه")
        self.assertEqual(len(payload["specifications"]), 2)
        self.assertIsNotNone(payload["analytics"])

    def testSpecificationsAreReplacedNotAppended(self) -> None:
        device = self.createDevice()
        for _ in range(2):
            self.client.put(
                f"{BASE}/devices/{device['id']}/specifications",
                {"rows": [{"label": "توان", "value": "75", "unit": "کیلووات"}]},
                format="json",
                **self.auth,
            )
        profile = self.client.get(f"{BASE}/devices/{device['id']}/profile", **self.auth)
        self.assertEqual(len(profile.json()["data"]["specifications"]), 1)

    def testParentChildAssetHierarchy(self) -> None:
        line = self.createDevice(code="LINE-1")
        motor = self.createDevice(code="MOTOR-1")
        self.client.patch(
            f"{BASE}/devices/{motor['id']}/nameplate",
            {"parentDeviceId": line["id"]},
            format="json",
            **self.auth,
        )
        profile = self.client.get(f"{BASE}/devices/{line['id']}/profile", **self.auth)
        children = profile.json()["data"]["children"]
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]["code"], "MOTOR-1")


class PmPlanTests(AssetRegistryApiBase):
    def testPlansCoverAllSevenDisciplines(self) -> None:
        device = self.createDevice()
        disciplines = (
            "mechanical",
            "electrical",
            "instrumentation",
            "general",
            "hydraulic",
            "pneumatic",
            "facilities",
        )
        for discipline in disciplines:
            response = self.client.post(
                f"{BASE}/devices/{device['id']}/pm-plans",
                {
                    "title": f"بازرسی {discipline}",
                    "discipline": discipline,
                    "frequencyEvery": 1,
                    "frequencyUnit": "month",
                    "checklist": ["بازدید چشمی", "ثبت گزارش"],
                },
                format="json",
                **self.auth,
            )
            self.assertEqual(response.status_code, 201, response.content)

        plans = self.client.get(
            f"{BASE}/devices/{device['id']}/pm-plans", **self.auth
        ).json()["data"]
        self.assertEqual(len(plans), 7)
        self.assertEqual({plan["discipline"] for plan in plans}, set(disciplines))
        self.assertEqual(plans[0]["checklist"], ["بازدید چشمی", "ثبت گزارش"])

    def testExecutingAPlanAdvancesItsSchedule(self) -> None:
        device = self.createDevice()
        plan = self.client.post(
            f"{BASE}/devices/{device['id']}/pm-plans",
            {
                "title": "تعویض روغن",
                "discipline": "mechanical",
                "frequencyEvery": 3,
                "frequencyUnit": "month",
            },
            format="json",
            **self.auth,
        ).json()["data"]
        self.assertEqual(plan["periodDays"], 90)
        self.assertEqual(plan["nextDueOn"], "")

        execution = self.client.post(
            f"{BASE}/pm-plans/{plan['id']}/executions",
            {"performedOn": "2026-01-15", "performedByName": "رضا محمدی"},
            format="json",
            **self.auth,
        )
        self.assertEqual(execution.status_code, 201, execution.content)

        plans = self.client.get(
            f"{BASE}/devices/{device['id']}/pm-plans", **self.auth
        ).json()["data"]
        self.assertEqual(plans[0]["lastExecutedOn"], "2026-01-15")
        self.assertEqual(plans[0]["nextDueOn"], "2026-04-15")

    def testPlanCanBeUpdatedAndDeleted(self) -> None:
        device = self.createDevice()
        plan = self.client.post(
            f"{BASE}/devices/{device['id']}/pm-plans",
            {"title": "بازرسی اولیه", "discipline": "general"},
            format="json",
            **self.auth,
        ).json()["data"]

        updated = self.client.patch(
            f"{BASE}/pm-plans/{plan['id']}",
            {"title": "بازرسی ماهانه", "discipline": "hydraulic", "frequencyEvery": 2},
            format="json",
            **self.auth,
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["data"]["discipline"], "hydraulic")

        deleted = self.client.delete(f"{BASE}/pm-plans/{plan['id']}", **self.auth)
        self.assertEqual(deleted.status_code, 200, deleted.content)
        remaining = self.client.get(
            f"{BASE}/devices/{device['id']}/pm-plans", **self.auth
        ).json()["data"]
        self.assertEqual(remaining, [])


class BillOfMaterialsTests(AssetRegistryApiBase):
    def testOnePartCanBeSharedByManyDevices(self) -> None:
        bearing = self.createPart("BRG-6205", "بلبرینگ 6205")
        pump = self.createDevice(code="PUMP-01")
        fan = self.createDevice(code="FAN-01")

        for device in (pump, fan):
            response = self.client.post(
                f"{BASE}/devices/{device['id']}/bom",
                {"partId": bearing["id"], "position": "یاتاقان جلو", "standardQuantity": "2"},
                format="json",
                **self.auth,
            )
            self.assertEqual(response.status_code, 201, response.content)

        for device in (pump, fan):
            profile = self.client.get(f"{BASE}/devices/{device['id']}/profile", **self.auth)
            bom = profile.json()["data"]["bom"]
            self.assertEqual(len(bom), 1)
            self.assertEqual(bom[0]["partCode"], "BRG-6205")
            self.assertEqual(bom[0]["standardQuantity"], "2.000")

    def testBomItemCanBeRemoved(self) -> None:
        part = self.createPart("SEAL-01", "کاسه‌نمد")
        device = self.createDevice()
        self.client.post(
            f"{BASE}/devices/{device['id']}/bom",
            {"partId": part["id"]},
            format="json",
            **self.auth,
        )
        removed = self.client.delete(
            f"{BASE}/devices/{device['id']}/bom/{part['id']}", **self.auth
        )
        self.assertEqual(removed.status_code, 200, removed.content)
        profile = self.client.get(f"{BASE}/devices/{device['id']}/profile", **self.auth)
        self.assertEqual(profile.json()["data"]["bom"], [])


class AssignmentTests(AssetRegistryApiBase):
    def testOperatorResponsibleAndTechniciansAreStoredWithRoles(self) -> None:
        device = self.createDevice()
        operator = self.createPersonnel("EMP-1", "حسین کریمی", "general")
        technician = self.createPersonnel("EMP-2", "رضا محمدی", "mechanical")

        response = self.client.put(
            f"{BASE}/devices/{device['id']}/assignments",
            {
                "rows": [
                    {
                        "personnelId": operator["id"],
                        "role": "operator",
                        "unit": "تولید",
                        "fromDate": "2026-01-01",
                    },
                    {"personnelId": technician["id"], "role": "technician"},
                    {"personnelName": "مهدی نادری", "role": "responsible"},
                ]
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        rows = {item["role"]: item for item in response.json()["data"]}
        self.assertEqual(rows["operator"]["personnelName"], "حسین کریمی")
        self.assertEqual(rows["technician"]["personnelName"], "رضا محمدی")
        self.assertEqual(rows["responsible"]["personnelName"], "مهدی نادری")


class AnalyticsTests(AssetRegistryApiBase):
    def _closeRepair(self, orderId: str, **details: object) -> None:
        payload = {
            "failureType": "wear",
            "failedComponent": "بلبرینگ",
            "rootCause": "روان‌کاری ناکافی",
            "downtimeMinutes": 180,
            "labourCost": "1200000",
            "partsCost": "2400000",
        }
        payload.update(details)
        response = self.client.patch(
            f"{BASE}/work-orders/{orderId}/closure", payload, format="json", **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)

    def testRepairCountAndCostsComeFromRecordedOrders(self) -> None:
        device = self.createDevice()
        first = self.submitWorkOrder(device["id"], "خرابی یاتاقان")
        second = self.submitWorkOrder(device["id"], "نشتی آب‌بند")
        self.submitWorkOrder(device["id"], "PM ماهانه", orderType="preventive")

        self._closeRepair(first["id"])
        self._closeRepair(second["id"], repeatFailure=True, downtimeMinutes=120)

        analytics = self.client.get(f"{BASE}/devices/{device['id']}/analytics", **self.auth)
        self.assertEqual(analytics.status_code, 200, analytics.content)
        data = analytics.json()["data"]

        self.assertEqual(data["repairCount"], 2)
        self.assertEqual(data["preventiveCount"], 1)
        self.assertEqual(data["repeatFailures"], 1)
        self.assertEqual(data["totalDowntimeHours"], 5.0)
        self.assertEqual(data["totalCost"], "7200000.00")
        self.assertEqual(data["byFailureType"][0]["label"], "wear")
        self.assertEqual(data["byFailedComponent"][0]["label"], "بلبرینگ")

    def testPartConsumptionCountsUsagesAndQuantitySeparately(self) -> None:
        device = self.createDevice()
        bearing = self.createPart("BRG-6205", "بلبرینگ 6205", quantity="50")

        for quantity in ("3", "2"):
            order = self.submitWorkOrder(device["id"], "تعویض بلبرینگ")
            consume = self.client.post(
                f"{BASE}/work-orders/{order['id']}/parts",
                {"partId": bearing["id"], "quantity": quantity},
                format="json",
                **self.auth,
            )
            self.assertEqual(consume.status_code, 201, consume.content)

        analytics = self.client.get(
            f"{BASE}/devices/{device['id']}/analytics", **self.auth
        ).json()["data"]
        consumption = analytics["partConsumption"][0]
        self.assertEqual(consumption["partCode"], "BRG-6205")
        self.assertEqual(consumption["usageCount"], 2)
        self.assertEqual(consumption["totalQuantity"], "5.000")

    def testPartUsageReportIsDeviceAware(self) -> None:
        bearing = self.createPart("BRG-6205", "بلبرینگ 6205", quantity="50")
        pump = self.createDevice(code="PUMP-01")
        fan = self.createDevice(code="FAN-01")

        for device, quantity in ((pump, "3"), (pump, "1"), (fan, "2")):
            order = self.submitWorkOrder(device["id"], "تعویض قطعه")
            self.client.post(
                f"{BASE}/work-orders/{order['id']}/parts",
                {"partId": bearing["id"], "quantity": quantity},
                format="json",
                **self.auth,
            )

        report = self.client.get(f"{BASE}/analytics/parts/{bearing['id']}", **self.auth)
        self.assertEqual(report.status_code, 200, report.content)
        data = report.json()["data"]
        self.assertEqual(data["totalUsageCount"], 3)
        self.assertEqual(data["totalQuantity"], "6.000")
        rows = {row["deviceCode"]: row for row in data["devices"]}
        self.assertEqual(rows["PUMP-01"]["usageCount"], 2)
        self.assertEqual(rows["PUMP-01"]["totalQuantity"], "4.000")
        self.assertEqual(rows["FAN-01"]["usageCount"], 1)

    def testBomShowsHowOftenEachFittedPartWasConsumed(self) -> None:
        device = self.createDevice()
        bearing = self.createPart("BRG-6205", "بلبرینگ 6205", quantity="50")
        self.client.post(
            f"{BASE}/devices/{device['id']}/bom",
            {"partId": bearing["id"], "standardQuantity": "2"},
            format="json",
            **self.auth,
        )
        order = self.submitWorkOrder(device["id"], "تعویض بلبرینگ")
        self.client.post(
            f"{BASE}/work-orders/{order['id']}/parts",
            {"partId": bearing["id"], "quantity": "2"},
            format="json",
            **self.auth,
        )

        profile = self.client.get(f"{BASE}/devices/{device['id']}/profile", **self.auth)
        bom = profile.json()["data"]["bom"][0]
        self.assertEqual(bom["usageCount"], 1)
        self.assertEqual(bom["usedQuantity"], "2.000")

    def testFleetAnalyticsRanksDevicesByRepairCount(self) -> None:
        busy = self.createDevice(code="PUMP-01")
        quiet = self.createDevice(code="FAN-01")
        for _ in range(3):
            order = self.submitWorkOrder(busy["id"], "خرابی")
            self._closeRepair(order["id"])
        order = self.submitWorkOrder(quiet["id"], "خرابی")
        self._closeRepair(order["id"])

        fleet = self.client.get(f"{BASE}/analytics/fleet", **self.auth)
        self.assertEqual(fleet.status_code, 200, fleet.content)
        data = fleet.json()["data"]
        self.assertEqual(data["totalRepairs"], 4)
        self.assertEqual(data["rows"][0]["code"], "PUMP-01")
        self.assertEqual(data["rows"][0]["repairCount"], 3)
        self.assertEqual(data["rows"][1]["repairCount"], 1)

    def testAnalyticsRespectsTheRequestedDateWindow(self) -> None:
        device = self.createDevice()
        order = self.submitWorkOrder(device["id"], "خرابی")
        self._closeRepair(order["id"])

        empty = self.client.get(
            f"{BASE}/devices/{device['id']}/analytics?fromDate=2020-01-01&toDate=2020-12-31",
            **self.auth,
        ).json()["data"]
        self.assertEqual(empty["repairCount"], 0)
        self.assertEqual(empty["fromDate"], "2020-01-01")
