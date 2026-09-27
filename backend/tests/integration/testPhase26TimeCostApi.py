"""Time & cost tracking (ثبت زمان و هزینه) — public REST contract.

Technician labour hours with hourly rates are logged per work order, spare
parts carry a unit price that each consumption snapshots, and both feed two
read models: the per-order cost summary and the tenant-wide maintenance cost
report (گزارش هزینه‌ی نگهداری) with device/department/technician breakdowns.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from tests.support.phase6Helpers import loginViaApi, seedPlatform


class TimeCostApiBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    def createDevice(self, code: str = "PRESS-01", name: str = "پرس هیدرولیک") -> dict:
        response = self.client.post(
            "/api/v1/maintenance/devices",
            {"code": code, "name": name, "department": "mechanical"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def submitWorkOrder(self, deviceId: str, title: str = "نشت روغن از سیل") -> dict:
        response = self.client.post(
            "/api/v1/maintenance/work-orders",
            {
                "deviceId": deviceId,
                "title": title,
                "description": "بررسی و رفع نشتی",
                "priority": "high",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def createPart(self, code: str, name: str, stock: str = "10.000", unitCost: str = "0") -> dict:
        response = self.client.post(
            "/api/v1/maintenance/spare-parts",
            {
                "code": code,
                "name": name,
                "unit": "عدد",
                "quantityOnHand": stock,
                "unitCost": unitCost,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def logLabour(
        self,
        workOrderId: str,
        technician: str = "حسین کریمی",
        hours: str = "2.50",
        rate: str = "500000",
        note: str = "باز و بست سیل",
    ) -> dict:
        response = self.client.post(
            f"/api/v1/maintenance/work-orders/{workOrderId}/labour",
            {
                "technicianName": technician,
                "hours": hours,
                "hourlyRate": rate,
                "note": note,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]


class LabourEntryApiTests(TimeCostApiBase):
    def testAuthenticationIsMandatory(self) -> None:
        anonymous = APIClient()
        order = "00000000-0000-0000-0000-000000000000"
        self.assertEqual(
            anonymous.get(f"/api/v1/maintenance/work-orders/{order}/labour").status_code,
            401,
        )
        self.assertEqual(
            anonymous.post(
                f"/api/v1/maintenance/work-orders/{order}/labour", {}, format="json"
            ).status_code,
            401,
        )
        self.assertEqual(
            anonymous.get("/api/v1/maintenance/reports/maintenance-costs").status_code,
            401,
        )

    def testLogListAndDeleteLabourEntryRollsUpTotals(self) -> None:
        device = self.createDevice()
        order = self.submitWorkOrder(device["id"])

        first = self.logLabour(order["id"], hours="2.00", rate="500000")
        self.assertEqual(first["hours"], "2.00")
        self.assertEqual(first["hourlyRate"], "500000.00")
        self.assertEqual(first["totalCost"], "1000000.00")
        self.assertEqual(first["technicianName"], "حسین کریمی")

        second = self.logLabour(
            order["id"], technician="رضا احمدی", hours="1.50", rate="400000", note="تنظیم"
        )
        self.assertEqual(second["totalCost"], "600000.00")

        listed = self.client.get(
            f"/api/v1/maintenance/work-orders/{order['id']}/labour", **self.auth
        )
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(listed.json()["meta"]["totalCount"], 2)
        self.assertEqual(listed.json()["meta"]["totalHours"], "3.50")
        self.assertEqual(listed.json()["meta"]["totalLabourCost"], "1600000.00")

        # Deleting one entry removes exactly its share from the roll-up.
        deleted = self.client.delete(
            f"/api/v1/maintenance/labour-entries/{first['id']}", **self.auth
        )
        self.assertEqual(deleted.status_code, 200, deleted.content)
        listedAgain = self.client.get(
            f"/api/v1/maintenance/work-orders/{order['id']}/labour", **self.auth
        )
        self.assertEqual(listedAgain.json()["meta"]["totalCount"], 1)
        self.assertEqual(listedAgain.json()["meta"]["totalHours"], "1.50")
        self.assertEqual(listedAgain.json()["meta"]["totalLabourCost"], "600000.00")

    def testLabourValidationRejectsBadHoursAndMissingTechnician(self) -> None:
        device = self.createDevice(code="PRESS-02")
        order = self.submitWorkOrder(device["id"])

        zeroHours = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/labour",
            {"technicianName": "حسین کریمی", "hours": "0"},
            format="json",
            **self.auth,
        )
        self.assertEqual(zeroHours.status_code, 400, zeroHours.content)

        noName = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/labour",
            {"technicianName": " ", "hours": "1.00"},
            format="json",
            **self.auth,
        )
        self.assertEqual(noName.status_code, 400, noName.content)

        unknownOrder = self.client.post(
            "/api/v1/maintenance/work-orders/00000000-0000-0000-0000-000000000000/labour",
            {"technicianName": "حسین کریمی", "hours": "1.00"},
            format="json",
            **self.auth,
        )
        self.assertEqual(unknownOrder.status_code, 404, unknownOrder.content)


class WorkOrderCostSummaryTests(TimeCostApiBase):
    def testSummaryCombinesLabourAndPartsCosts(self) -> None:
        device = self.createDevice(code="PRESS-03")
        order = self.submitWorkOrder(device["id"])

        self.logLabour(order["id"], hours="2.00", rate="500000")  # 1,000,000
        self.logLabour(order["id"], technician="رضا احمدی", hours="1.00", rate="600000")  # 600,000

        part = self.createPart("SEAL-01", "سیل هیدرولیک", unitCost="250000")
        consumed = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/parts",
            {"partId": part["id"], "quantity": "2.000", "note": "تعویض سیل"},
            format="json",
            **self.auth,
        )
        self.assertEqual(consumed.status_code, 201, consumed.content)
        # The consumption snapshots the part price at issue time.
        self.assertEqual(consumed.json()["data"]["unitCost"], "250000.00")
        self.assertEqual(consumed.json()["data"]["totalCost"], "500000.00")

        summary = self.client.get(
            f"/api/v1/maintenance/work-orders/{order['id']}/cost-summary", **self.auth
        )
        self.assertEqual(summary.status_code, 200, summary.content)
        data = summary.json()["data"]
        self.assertEqual(data["labourHours"], "3.00")  # 2.00 + 1.00 hours
        self.assertEqual(data["labourCost"], "1600000.00")
        self.assertEqual(data["partsCost"], "500000.00")
        self.assertEqual(data["totalCost"], "2100000.00")  # 1,600,000 labour + 500,000 parts
        self.assertEqual(len(data["labourEntries"]), 2)
        self.assertEqual(len(data["partUsages"]), 1)

    def testPriceChangeAfterConsumptionKeepsHistoricalCost(self) -> None:
        device = self.createDevice(code="PRESS-04")
        order = self.submitWorkOrder(device["id"])
        part = self.createPart("ORING-01", "اورینگ", unitCost="10000")
        self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/parts",
            {"partId": part["id"], "quantity": "3.000"},
            format="json",
            **self.auth,
        )

        # Price rises later — historical usage rows must not be rewritten.
        updated = self.client.patch(
            f"/api/v1/maintenance/spare-parts/{part['id']}",
            {
                "name": "اورینگ",
                "unit": "عدد",
                "quantityOnHand": "7.000",
                "unitCost": "15000",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["data"]["unitCost"], "15000.00")

        summary = self.client.get(
            f"/api/v1/maintenance/work-orders/{order['id']}/cost-summary", **self.auth
        )
        data = summary.json()["data"]
        self.assertEqual(data["partsCost"], "30000.00")
        self.assertEqual(data["totalCost"], "30000.00")


class MaintenanceCostReportTests(TimeCostApiBase):
    def _populate(self) -> dict:
        deviceA = self.createDevice(code="PRESS-10", name="پرس اول")
        orderA = self.submitWorkOrder(deviceA["id"], title="تعمیر سیل پرس")
        self.logLabour(orderA["id"], technician="حسین کریمی", hours="2.00", rate="500000")
        part = self.createPart("SEAL-10", "سیل", unitCost="200000")
        self.client.post(
            f"/api/v1/maintenance/work-orders/{orderA['id']}/parts",
            {"partId": part["id"], "quantity": "1.000"},
            format="json",
            **self.auth,
        )
        return deviceA

    def testReportTotalsAndBreakdowns(self) -> None:
        deviceA = self._populate()

        report = self.client.get("/api/v1/maintenance/reports/maintenance-costs", **self.auth)
        self.assertEqual(report.status_code, 200, report.content)
        data = report.json()["data"]
        self.assertEqual(data["totalLabourHours"], "2.00")
        self.assertEqual(data["totalLabourCost"], "1000000.00")
        self.assertEqual(data["totalPartsCost"], "200000.00")
        self.assertEqual(data["totalCost"], "1200000.00")

        deviceGroups = {group["key"]: group for group in data["byDevice"]}
        self.assertIn(deviceA["id"], deviceGroups)
        self.assertEqual(deviceGroups[deviceA["id"]]["totalCost"], "1200000.00")

        departmentGroups = {group["key"]: group for group in data["byDepartment"]}
        self.assertIn("mechanical", departmentGroups)
        self.assertEqual(departmentGroups["mechanical"]["totalCost"], "1200000.00")

        technicians = {group["technicianName"]: group for group in data["byTechnician"]}
        self.assertIn("حسین کریمی", technicians)
        self.assertEqual(technicians["حسین کریمی"]["hours"], "2.00")
        self.assertEqual(technicians["حسین کریمی"]["cost"], "1000000.00")

        self.assertTrue(any(item["workOrderId"] for item in data["items"]))

    def testReportFiltersByDevice(self) -> None:
        deviceA = self._populate()
        other = self.createDevice(code="PRESS-11", name="پرس دوم")
        orderB = self.submitWorkOrder(other["id"], title="تعویض روغن")
        self.logLabour(orderB["id"], technician="رضا احمدی", hours="5.00", rate="100000")

        filtered = self.client.get(
            f"/api/v1/maintenance/reports/maintenance-costs?deviceId={deviceA['id']}",
            **self.auth,
        )
        self.assertEqual(filtered.status_code, 200, filtered.content)
        data = filtered.json()["data"]
        # Only device A's order contributes: 2h×500k labour + 200k parts.
        self.assertEqual(data["totalCost"], "1200000.00")
        self.assertEqual(data["totalLabourHours"], "2.00")
        deviceIds = {item["deviceCode"] for item in data["items"]}
        self.assertEqual(deviceIds, {"PRESS-10"})

    def testReportCsvExportIsExcelFriendly(self) -> None:
        self._populate()
        response = self.client.get(
            "/api/v1/maintenance/reports/maintenance-costs?export=csv", **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        body = response.content
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))  # BOM for Excel
        text = body.decode("utf-8-sig")
        self.assertIn("گزارش هزینه‌ی نگهداری", text)
        self.assertIn("ساعت‌کار", text)

    def testReportXlsxExportIsAWorkbook(self) -> None:
        self._populate()
        response = self.client.get(
            "/api/v1/maintenance/reports/maintenance-costs?export=xlsx", **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertTrue(response.content.startswith(b"PK"))  # zip signature of xlsx
