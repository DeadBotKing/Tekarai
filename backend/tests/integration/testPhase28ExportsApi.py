"""Report export downloads (گزارش خروجی Excel/PDF) — public REST contract.

Phase 28 adds direct export streams for the two list surfaces (work orders,
PM schedule) and shaped-Persian PDF alongside the existing CSV/XLSX device +
cost reports. These tests assert the wire contract: HTTP status, content
type, file signature, and that filters still apply in export mode.
"""

from __future__ import annotations

from tests.integration.testPhase26TimeCostApi import TimeCostApiBase

XLSX_MAGIC = b"PK\x03\x04"
PDF_MAGIC = b"%PDF"
CSV_BOM = b"\xef\xbb\xbf"


class MaintenanceExportsApiTests(TimeCostApiBase):
    def setUp(self) -> None:
        super().setUp()
        self.device = self.createDevice()
        self.order = self.submitWorkOrder(self.device["id"], "تعویض یاتاقان موتور")

    # -- work orders ---------------------------------------------------------

    def testWorkOrdersExportCsv(self) -> None:
        response = self.client.get("/api/v1/maintenance/work-orders?export=csv", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("text/csv", response.headers["Content-Type"])
        content = bytes(response.content)
        self.assertTrue(content.startswith(CSV_BOM))
        text = content.decode("utf-8")
        self.assertIn("عنوان", text)
        self.assertIn("تعویض یاتاقان موتور", text)

    def testWorkOrdersExportXlsx(self) -> None:
        response = self.client.get("/api/v1/maintenance/work-orders?export=xlsx", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("spreadsheetml", response.headers["Content-Type"])
        self.assertTrue(bytes(response.content).startswith(XLSX_MAGIC))

    def testWorkOrdersExportPdf(self) -> None:
        response = self.client.get("/api/v1/maintenance/work-orders?export=pdf", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
        self.assertTrue(bytes(response.content).startswith(PDF_MAGIC))

    def testWorkOrdersExportRespectsFilters(self) -> None:
        response = self.client.get(
            "/api/v1/maintenance/work-orders?status=cancelled&export=csv", **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)
        text = bytes(response.content).decode("utf-8")
        # The submitted order must be filtered OUT of the export too.
        self.assertNotIn("تعویض یاتاقان موتور", text)
        # But the header row survives so the file still makes sense.
        self.assertIn("عنوان", text)

    # -- PM schedule ---------------------------------------------------------

    def _createPlanWithExecution(self) -> str:
        plan = self.client.post(
            f"/api/v1/maintenance/devices/{self.device['id']}/pm-plans",
            {
                "title": "روغن‌کاری ماهانه",
                "discipline": "mechanical",
                "frequencyEvery": 1,
                "frequencyUnit": "month",
                "checklist": [],
                "estimatedMinutes": 30,
                "responsibleName": "رضا",
                "active": True,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(plan.status_code, 201, plan.content)
        planId = plan.json()["data"]["id"]
        execution = self.client.post(
            f"/api/v1/maintenance/pm-plans/{planId}/executions",
            {"performedOn": "2026-08-01", "performedByName": "رضا"},
            format="json",
            **self.auth,
        )
        self.assertEqual(execution.status_code, 201, execution.content)
        return planId

    def testPmScheduleExportCsvAndPdf(self) -> None:
        self._createPlanWithExecution()
        response = self.client.get("/api/v1/maintenance/pm-schedule?export=csv", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        text = bytes(response.content).decode("utf-8")
        self.assertIn("موعد", text)
        self.assertIn("روغن‌کاری ماهانه", text)

        pdf = self.client.get("/api/v1/maintenance/pm-schedule?export=pdf", **self.auth)
        self.assertEqual(pdf.status_code, 200, pdf.content)
        self.assertTrue(bytes(pdf.content).startswith(PDF_MAGIC))

    # -- existing reports gain PDF -------------------------------------------

    def testCostReportPdf(self) -> None:
        response = self.client.get(
            "/api/v1/maintenance/reports/maintenance-costs?export=pdf", **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
        self.assertTrue(bytes(response.content).startswith(PDF_MAGIC))

    def testDeviceReportPdf(self) -> None:
        response = self.client.get(
            f"/api/v1/maintenance/devices/{self.device['id']}/report?export=pdf",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
        self.assertTrue(bytes(response.content).startswith(PDF_MAGIC))

    # -- auth gate ------------------------------------------------------------

    def testExportsRequireAuthentication(self) -> None:
        response = self.client.get("/api/v1/maintenance/work-orders?export=pdf")
        self.assertIn(response.status_code, (401, 403))
