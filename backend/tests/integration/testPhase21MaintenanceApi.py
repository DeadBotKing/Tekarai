"""Phase 21 — Maintenance / CMMS public REST contract.

Two aggregates — Device and WorkOrder — with a preventive-maintenance (PM)
schedule, a guarded work-order lifecycle, and three CMMS roles. These tests
pin the public boundary the Persian frontend consumes.
"""

from __future__ import annotations

from tempfile import TemporaryDirectory

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from tests.support.phase6Helpers import loginViaApi, seedPlatform


class MaintenanceApiBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    def createDevice(
        self,
        code: str = "PUMP-01",
        name: str = "پمپ خنک‌کننده",
        pmIntervalDays: int = 30,
        department: str = "general",
    ) -> dict:
        response = self.client.post(
            "/api/v1/maintenance/devices",
            {
                "code": code,
                "name": name,
                "location": "سالن تولید A",
                "department": department,
                "pmIntervalDays": pmIntervalDays,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def submitWorkOrder(
        self,
        deviceId: str,
        title: str = "صدای غیرعادی از یاتاقان",
        orderType: str = "corrective",
        priority: str = "high",
    ) -> dict:
        response = self.client.post(
            "/api/v1/maintenance/work-orders",
            {
                "deviceId": deviceId,
                "title": title,
                "description": "بررسی و رفع عیب",
                "orderType": orderType,
                "priority": priority,
                "requestedByName": "علی رضایی",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]


class DeviceApiTests(MaintenanceApiBase):
    def testAuthenticationIsMandatory(self) -> None:
        anonymous = APIClient()
        self.assertEqual(anonymous.get("/api/v1/maintenance/devices").status_code, 401)
        self.assertEqual(
            anonymous.post("/api/v1/maintenance/devices", {}, format="json").status_code,
            401,
        )

    def testRegisterListDetailUpdateAndStatusFlow(self) -> None:
        created = self.createDevice()
        self.assertEqual(created["status"], "operational")
        self.assertEqual(created["code"], "PUMP-01")
        self.assertEqual(created["pmIntervalDays"], 30)

        listed = self.client.get("/api/v1/maintenance/devices", **self.auth)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertTrue(listed.json()["success"])
        self.assertGreaterEqual(listed.json()["meta"]["totalCount"], 1)
        self.assertIn(created["id"], [item["id"] for item in listed.json()["data"]])

        detail = self.client.get(f"/api/v1/maintenance/devices/{created['id']}", **self.auth)
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["data"]["name"], "پمپ خنک‌کننده")

        updated = self.client.patch(
            f"/api/v1/maintenance/devices/{created['id']}",
            {"name": "پمپ خنک‌کننده اصلی", "location": "سالن B", "pmIntervalDays": 45},
            format="json",
            **self.auth,
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["data"]["name"], "پمپ خنک‌کننده اصلی")
        self.assertEqual(updated.json()["data"]["pmIntervalDays"], 45)

        transitioned = self.client.post(
            f"/api/v1/maintenance/devices/{created['id']}/status",
            {"target": "underMaintenance"},
            format="json",
            **self.auth,
        )
        self.assertEqual(transitioned.status_code, 200, transitioned.content)
        self.assertEqual(transitioned.json()["data"]["status"], "underMaintenance")

    def testDuplicateDeviceCodeIsRejected(self) -> None:
        self.createDevice(code="DUP-DEV")
        duplicate = self.client.post(
            "/api/v1/maintenance/devices",
            {"code": "DUP-DEV", "name": "دستگاه تکراری"},
            format="json",
            **self.auth,
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.content)
        self.assertFalse(duplicate.json()["success"])

    def testInvalidDeviceStatusIsRejected(self) -> None:
        created = self.createDevice()
        bad = self.client.post(
            f"/api/v1/maintenance/devices/{created['id']}/status",
            {"target": "flyingMode"},
            format="json",
            **self.auth,
        )
        self.assertEqual(bad.status_code, 400, bad.content)

    def testUnknownDeviceIs404(self) -> None:
        missing = self.client.get(
            "/api/v1/maintenance/devices/00000000-0000-0000-0000-000000000000",
            **self.auth,
        )
        self.assertEqual(missing.status_code, 404, missing.content)


class PreventiveMaintenanceTests(MaintenanceApiBase):
    def testRecordPmComputesNextDueDate(self) -> None:
        created = self.createDevice(pmIntervalDays=30)
        recorded = self.client.post(
            f"/api/v1/maintenance/devices/{created['id']}/pm",
            {"performedOn": "2026-09-01"},
            format="json",
            **self.auth,
        )
        self.assertEqual(recorded.status_code, 200, recorded.content)
        data = recorded.json()["data"]
        self.assertEqual(data["lastPmDate"], "2026-09-01")
        self.assertEqual(data["nextDueDate"], "2026-10-01")

    def testDuePmListSurfacesOverdueDevices(self) -> None:
        overdue = self.createDevice(code="OVERDUE-1", pmIntervalDays=10)
        self.client.post(
            f"/api/v1/maintenance/devices/{overdue['id']}/pm",
            {"performedOn": "2020-01-01"},
            format="json",
            **self.auth,
        )
        # A device with no PM baseline should NOT appear as due.
        self.createDevice(code="FRESH-1", pmIntervalDays=0)

        due = self.client.get("/api/v1/maintenance/devices/due-pm", **self.auth)
        self.assertEqual(due.status_code, 200, due.content)
        ids = [item["id"] for item in due.json()["data"]]
        self.assertIn(overdue["id"], ids)
        self.assertTrue(all(item["pmDue"] for item in due.json()["data"]))


class WorkOrderApiTests(MaintenanceApiBase):
    def testAuthenticationIsMandatory(self) -> None:
        anonymous = APIClient()
        self.assertEqual(anonymous.get("/api/v1/maintenance/work-orders").status_code, 401)

    def testSubmitAssignProgressAndCompleteLifecycle(self) -> None:
        device = self.createDevice()
        order = self.submitWorkOrder(device["id"])
        self.assertEqual(order["status"], "submitted")
        self.assertEqual(order["deviceId"], device["id"])

        listed = self.client.get("/api/v1/maintenance/work-orders", **self.auth)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertGreaterEqual(listed.json()["meta"]["totalCount"], 1)

        assigned = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/assign",
            {"assignedToName": "رضا احمدی"},
            format="json",
            **self.auth,
        )
        self.assertEqual(assigned.status_code, 200, assigned.content)
        self.assertEqual(assigned.json()["data"]["status"], "assigned")
        self.assertEqual(assigned.json()["data"]["assignedToName"], "رضا احمدی")

        started = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/status",
            {"target": "inProgress"},
            format="json",
            **self.auth,
        )
        self.assertEqual(started.status_code, 200, started.content)
        self.assertEqual(started.json()["data"]["status"], "inProgress")

        # Completion is gated by manager approval: the technician sends the work
        # for approval (inProgress → pendingApproval), never straight to done.
        pending = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/status",
            {"target": "pendingApproval", "resolutionNote": "یاتاقان تعویض شد"},
            format="json",
            **self.auth,
        )
        self.assertEqual(pending.status_code, 200, pending.content)
        self.assertEqual(pending.json()["data"]["status"], "pendingApproval")

        # Direct inProgress → completed is now blocked.
        blocked = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/status",
            {"target": "completed"},
            format="json",
            **self.auth,
        )
        self.assertEqual(blocked.status_code, 409, blocked.content)

        # A manager approves the pending order → completed.
        completed = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/approve",
            {"note": "تأیید شد"},
            format="json",
            **self.auth,
        )
        self.assertEqual(completed.status_code, 200, completed.content)
        self.assertEqual(completed.json()["data"]["status"], "completed")
        self.assertEqual(completed.json()["data"]["resolutionNote"], "یاتاقان تعویض شد")
        self.assertNotEqual(completed.json()["data"]["closedAt"], "")

        # The timeline records every transition in order.
        history = self.client.get(
            f"/api/v1/maintenance/work-orders/{order['id']}/history",
            **self.auth,
        )
        self.assertEqual(history.status_code, 200, history.content)
        actions = [entry["action"] for entry in history.json()["data"]]
        self.assertEqual(
            actions,
            [
                "submitted",
                "assigned",
                "statusChanged",
                "submittedForApproval",
                "approved",
            ],
        )

    def testIllegalTransitionIsRejected(self) -> None:
        device = self.createDevice()
        order = self.submitWorkOrder(device["id"])
        # submitted → completed is not allowed (must be assigned/in-progress first).
        illegal = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/status",
            {"target": "completed"},
            format="json",
            **self.auth,
        )
        self.assertEqual(illegal.status_code, 409, illegal.content)

    def testWorkOrderAgainstUnknownDeviceIs404(self) -> None:
        response = self.client.post(
            "/api/v1/maintenance/work-orders",
            {
                "deviceId": "00000000-0000-0000-0000-000000000000",
                "title": "خطا",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 404, response.content)

    def testUpdateAndFilterByStatus(self) -> None:
        device = self.createDevice()
        order = self.submitWorkOrder(device["id"], priority="normal")
        updated = self.client.patch(
            f"/api/v1/maintenance/work-orders/{order['id']}",
            {"title": "بازبینی مجدد", "priority": "critical"},
            format="json",
            **self.auth,
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["data"]["priority"], "critical")

        filtered = self.client.get(
            "/api/v1/maintenance/work-orders?status=submitted",
            **self.auth,
        )
        self.assertEqual(filtered.status_code, 200, filtered.content)
        self.assertTrue(all(item["status"] == "submitted" for item in filtered.json()["data"]))


class DepartmentRoutingTests(MaintenanceApiBase):
    def testDeviceCarriesDepartmentAndWorkOrderInheritsIt(self) -> None:
        device = self.createDevice(code="ELEC-01", department="electrical")
        self.assertEqual(device["department"], "electrical")

        # A submitted order with no explicit department inherits the device's.
        order = self.submitWorkOrder(device["id"])
        self.assertEqual(order["department"], "electrical")
        self.assertEqual(order["status"], "submitted")

    def testTwoStepRouteThenAssign(self) -> None:
        device = self.createDevice(code="MECH-01", department="general")
        order = self.submitWorkOrder(device["id"])

        # Step 1 — a manager routes the request to the electrical department.
        routed = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/route",
            {"department": "electrical"},
            format="json",
            **self.auth,
        )
        self.assertEqual(routed.status_code, 200, routed.content)
        self.assertEqual(routed.json()["data"]["status"], "routed")
        self.assertEqual(routed.json()["data"]["department"], "electrical")

        # Step 2 — a technician of that unit is assigned.
        assigned = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/assign",
            {"assignedToName": "حسین برقی"},
            format="json",
            **self.auth,
        )
        self.assertEqual(assigned.status_code, 200, assigned.content)
        self.assertEqual(assigned.json()["data"]["status"], "assigned")
        self.assertEqual(assigned.json()["data"]["department"], "electrical")
        self.assertEqual(assigned.json()["data"]["assignedToName"], "حسین برقی")

    def testDepartmentAcceptsAPlantDefinedLabelButRejectsGarbage(self) -> None:
        """Phase 26.1: routing departments are an open vocabulary.

        A plant may add its own discipline from the registry UI (for example
        «جوشکاری»), so an unknown label routes like any other. Input that could
        not be a label at all — blank, longer than the column, or carrying
        control characters — is still rejected.
        """

        device = self.createDevice(code="BAD-DEP-1")
        order = self.submitWorkOrder(device["id"])
        accepted = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/route",
            {"department": "جوشکاری"},
            format="json",
            **self.auth,
        )
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual(accepted.json()["data"]["department"], "جوشکاری")

        for invalid in ("", "   ", "x" * 25, "برق\x07"):
            rejected = self.client.post(
                f"/api/v1/maintenance/work-orders/{order['id']}/route",
                {"department": invalid},
                format="json",
                **self.auth,
            )
            self.assertEqual(rejected.status_code, 400, rejected.content)

    def testFilterWorkOrdersByDepartment(self) -> None:
        elec = self.createDevice(code="F-ELEC", department="electrical")
        mech = self.createDevice(code="F-MECH", department="mechanical")
        self.submitWorkOrder(elec["id"], title="اتصالی برق")
        self.submitWorkOrder(mech["id"], title="لرزش موتور")

        filtered = self.client.get(
            "/api/v1/maintenance/work-orders?department=electrical",
            **self.auth,
        )
        self.assertEqual(filtered.status_code, 200, filtered.content)
        data = filtered.json()["data"]
        self.assertTrue(len(data) >= 1)
        self.assertTrue(all(item["department"] == "electrical" for item in data))


class PmAutoGenerationTests(MaintenanceApiBase):
    def testGeneratePmCreatesRoutedPreventiveOrders(self) -> None:
        overdue = self.createDevice(
            code="PM-AUTO-1", department="mechanical", pmIntervalDays=10
        )
        self.client.post(
            f"/api/v1/maintenance/devices/{overdue['id']}/pm",
            {"performedOn": "2020-01-01"},
            format="json",
            **self.auth,
        )

        generated = self.client.post(
            "/api/v1/maintenance/work-orders/generate-pm",
            {},
            format="json",
            **self.auth,
        )
        self.assertEqual(generated.status_code, 201, generated.content)
        items = generated.json()["data"]
        matching = [i for i in items if i["deviceId"] == overdue["id"]]
        self.assertEqual(len(matching), 1)
        auto = matching[0]
        self.assertEqual(auto["orderType"], "preventive")
        self.assertEqual(auto["status"], "routed")
        self.assertEqual(auto["department"], "mechanical")

    def testGeneratePmIsIdempotentPerDevice(self) -> None:
        overdue = self.createDevice(
            code="PM-AUTO-2", department="electrical", pmIntervalDays=10
        )
        self.client.post(
            f"/api/v1/maintenance/devices/{overdue['id']}/pm",
            {"performedOn": "2020-01-01"},
            format="json",
            **self.auth,
        )
        first = self.client.post(
            "/api/v1/maintenance/work-orders/generate-pm", {}, format="json", **self.auth
        )
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(
            len([i for i in first.json()["data"] if i["deviceId"] == overdue["id"]]), 1
        )
        # Second run must NOT create another order while the first is still open.
        second = self.client.post(
            "/api/v1/maintenance/work-orders/generate-pm", {}, format="json", **self.auth
        )
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(
            len([i for i in second.json()["data"] if i["deviceId"] == overdue["id"]]), 0
        )

    def testScheduledTaskAutomaticallyCreatesDuePmOrder(self) -> None:
        """Celery Beat's system task runs the same idempotent generator."""
        overdue = self.createDevice(
            code="PM-SCHEDULED-1", department="facilities", pmIntervalDays=7
        )
        recorded = self.client.post(
            f"/api/v1/maintenance/devices/{overdue['id']}/pm",
            {"performedOn": "2020-01-01"},
            format="json",
            **self.auth,
        )
        self.assertEqual(recorded.status_code, 200, recorded.content)

        from apps.maintenance.infrastructure.models import WorkOrderModel
        from apps.maintenance.infrastructure.tasks import generateDuePmWorkOrders

        first = generateDuePmWorkOrders()
        self.assertGreaterEqual(first["createdCount"], 1)
        generated = WorkOrderModel.objects.filter(
            deviceId=overdue["id"],
            orderType="preventive",
            deletedAt__isnull=True,
        )
        self.assertEqual(generated.count(), 1)
        self.assertEqual(generated.get().status, "routed")
        self.assertEqual(generated.get().department, "facilities")
        self.assertEqual(generated.get().requestedByName, "سامانه (خودکار)")

        # A subsequent hourly Beat tick must not duplicate the open request.
        second = generateDuePmWorkOrders()
        self.assertEqual(second["createdCount"], 0)
        self.assertEqual(generated.count(), 1)


class MaintenanceAttachmentTests(MaintenanceApiBase):
    def setUp(self) -> None:
        self.mediaDirectory = TemporaryDirectory()
        self.mediaOverride = override_settings(MEDIA_ROOT=self.mediaDirectory.name)
        self.mediaOverride.enable()
        self.addCleanup(self.mediaOverride.disable)
        self.addCleanup(self.mediaDirectory.cleanup)
        super().setUp()

    def testUploadListDownloadAndDeleteDeviceAttachment(self) -> None:
        device = self.createDevice(code="ATTACH-DEVICE")
        uploaded = self.client.post(
            f"/api/v1/maintenance/devices/{device['id']}/attachments",
            {
                "category": "manual",
                "file": SimpleUploadedFile(
                    "راهنما.pdf", b"%PDF-1.4\nTekarai manual\n%%EOF", "application/pdf"
                ),
            },
            format="multipart",
            **self.auth,
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.content)
        attachment = uploaded.json()["data"]
        self.assertEqual(attachment["category"], "manual")
        self.assertEqual(attachment["mimeType"], "application/pdf")
        self.assertGreater(attachment["sizeBytes"], 0)

        listed = self.client.get(
            f"/api/v1/maintenance/devices/{device['id']}/attachments", **self.auth
        )
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(len(listed.json()["data"]), 1)

        downloaded = self.client.get(
            f"/api/v1/maintenance/attachments/{attachment['id']}/download", **self.auth
        )
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded["Content-Type"], "application/pdf")
        self.assertEqual(b"".join(downloaded.streaming_content)[:4], b"%PDF")

        removed = self.client.delete(
            f"/api/v1/maintenance/attachments/{attachment['id']}", **self.auth
        )
        self.assertEqual(removed.status_code, 200, removed.content)
        listedAgain = self.client.get(
            f"/api/v1/maintenance/devices/{device['id']}/attachments", **self.auth
        )
        self.assertEqual(listedAgain.json()["data"], [])

    def testWorkOrderPhotoAttachmentAndInvalidFileRejection(self) -> None:
        device = self.createDevice(code="ATTACH-WO-DEVICE")
        order = self.submitWorkOrder(device["id"], title="خرابی پمپ")
        photo = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/attachments",
            {
                "category": "failurePhoto",
                "file": SimpleUploadedFile("fault.jpg", b"\xff\xd8\xffdemo", "image/jpeg"),
            },
            format="multipart",
            **self.auth,
        )
        self.assertEqual(photo.status_code, 201, photo.content)

        rejected = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/attachments",
            {
                "category": "other",
                "file": SimpleUploadedFile("script.exe", b"MZ", "application/octet-stream"),
            },
            format="multipart",
            **self.auth,
        )
        self.assertEqual(rejected.status_code, 422, rejected.content)


class SparePartsInventoryTests(MaintenanceApiBase):
    def testConsumePartDeductsStockAndRecordsWorkOrderUsage(self) -> None:
        device = self.createDevice(code="PART-DEVICE")
        order = self.submitWorkOrder(device["id"], title="تعویض فیلتر")
        created = self.client.post(
            "/api/v1/maintenance/spare-parts",
            {
                "code": "FILTER-01",
                "name": "فیلتر روغن",
                "unit": "عدد",
                "quantityOnHand": "10.000",
                "minimumStock": "3.000",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(created.status_code, 201, created.content)
        part = created.json()["data"]

        consumed = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/parts",
            {"partId": part["id"], "quantity": "2.000", "note": "تعویض دوره‌ای"},
            format="json",
            **self.auth,
        )
        self.assertEqual(consumed.status_code, 201, consumed.content)
        self.assertEqual(consumed.json()["data"]["partCode"], "FILTER-01")
        self.assertEqual(consumed.json()["data"]["quantity"], "2.000")

        inventory = self.client.get("/api/v1/maintenance/spare-parts", **self.auth)
        self.assertEqual(inventory.status_code, 200, inventory.content)
        saved = next(item for item in inventory.json()["data"] if item["id"] == part["id"])
        self.assertEqual(saved["quantityOnHand"], "8.000")
        self.assertFalse(saved["lowStock"])

        usage = self.client.get(
            f"/api/v1/maintenance/work-orders/{order['id']}/parts", **self.auth
        )
        self.assertEqual(usage.status_code, 200, usage.content)
        self.assertEqual(len(usage.json()["data"]), 1)
        self.assertEqual(usage.json()["data"][0]["note"], "تعویض دوره‌ای")

    def testInsufficientStockIsRejectedWithoutPartialDeduction(self) -> None:
        device = self.createDevice(code="PART-DEVICE-2")
        order = self.submitWorkOrder(device["id"], title="تعمیر یاتاقان")
        created = self.client.post(
            "/api/v1/maintenance/spare-parts",
            {
                "code": "BEARING-01",
                "name": "یاتاقان",
                "quantityOnHand": "1.000",
                "minimumStock": "1.000",
            },
            format="json",
            **self.auth,
        ).json()["data"]
        rejected = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/parts",
            {"partId": created["id"], "quantity": "2.000"},
            format="json",
            **self.auth,
        )
        self.assertEqual(rejected.status_code, 409, rejected.content)
        inventory = self.client.get("/api/v1/maintenance/spare-parts", **self.auth)
        saved = next(item for item in inventory.json()["data"] if item["id"] == created["id"])
        self.assertEqual(saved["quantityOnHand"], "1.000")


class WorkOrderWorkflowTests(MaintenanceApiBase):
    """Phase 22 — approval gate, SLA/overdue, auto-assign, rejection, timeline."""

    def _toInProgress(self, orderId: str, technician: str = "رضا احمدی") -> None:
        self.client.post(
            f"/api/v1/maintenance/work-orders/{orderId}/assign",
            {"assignedToName": technician},
            format="json",
            **self.auth,
        )
        self.client.post(
            f"/api/v1/maintenance/work-orders/{orderId}/status",
            {"target": "inProgress"},
            format="json",
            **self.auth,
        )

    def testRejectSendsPendingOrderBackToInProgress(self) -> None:
        device = self.createDevice()
        order = self.submitWorkOrder(device["id"])
        self._toInProgress(order["id"])
        self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/status",
            {"target": "pendingApproval", "resolutionNote": "انجام شد"},
            format="json",
            **self.auth,
        )
        rejected = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/reject",
            {"note": "کار ناقص است"},
            format="json",
            **self.auth,
        )
        self.assertEqual(rejected.status_code, 200, rejected.content)
        self.assertEqual(rejected.json()["data"]["status"], "inProgress")

        history = self.client.get(
            f"/api/v1/maintenance/work-orders/{order['id']}/history", **self.auth
        )
        actions = [entry["action"] for entry in history.json()["data"]]
        self.assertIn("rejected", actions)

    def testSlaFieldsAndOverdueFlagArePresent(self) -> None:
        device = self.createDevice()
        # A critical order has a 4-hour SLA window.
        order = self.submitWorkOrder(device["id"], priority="critical")
        self.assertTrue(order["slaDueAt"])  # deadline computed
        self.assertFalse(order["overdue"])  # freshly created → not overdue

    def testAutoAssignPicksLeastLoadedTechnician(self) -> None:
        device = self.createDevice(department="electrical")
        # Seed load: رضا already has two open orders in electrical.
        for _ in range(2):
            busy = self.submitWorkOrder(device["id"])
            self.client.post(
                f"/api/v1/maintenance/work-orders/{busy['id']}/assign",
                {"assignedToName": "رضا احمدی"},
                format="json",
                **self.auth,
            )
        # مریم has just one.
        light = self.submitWorkOrder(device["id"])
        self.client.post(
            f"/api/v1/maintenance/work-orders/{light['id']}/assign",
            {"assignedToName": "مریم کریمی"},
            format="json",
            **self.auth,
        )
        # New order auto-assigns to the least-loaded technician (مریم).
        target = self.submitWorkOrder(device["id"])
        auto = self.client.post(
            f"/api/v1/maintenance/work-orders/{target['id']}/assign",
            {"auto": True},
            format="json",
            **self.auth,
        )
        self.assertEqual(auto.status_code, 200, auto.content)
        self.assertEqual(auto.json()["data"]["assignedToName"], "مریم کریمی")

    def testApproveRequiresPermissionGateAllowsAdmin(self) -> None:
        device = self.createDevice()
        order = self.submitWorkOrder(device["id"])
        self._toInProgress(order["id"])
        self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/status",
            {"target": "pendingApproval"},
            format="json",
            **self.auth,
        )
        approved = self.client.post(
            f"/api/v1/maintenance/work-orders/{order['id']}/approve",
            {"note": "ok"},
            format="json",
            **self.auth,
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["data"]["status"], "completed")


class MaintenancePermissionCatalogTests(TestCase):
    def testLoginPayloadCarriesMaintenancePermissions(self) -> None:
        cache.clear()
        seedPlatform()
        client = APIClient()
        from tests.support.phase6Helpers import loginPayload

        response = client.post("/api/v1/auth/login", loginPayload(), format="json")
        self.assertEqual(response.status_code, 200, response.content)
        permissions = response.json()["data"].get("permissions")
        self.assertIn("maintenance.device.manage", permissions)
        self.assertIn("maintenance.workorder.create", permissions)
        self.assertIn("maintenance.workorder.route", permissions)
        self.assertIn("maintenance.workorder.assign", permissions)
        self.assertIn("maintenance.workorder.approve", permissions)

    def testCmmsRolesAreSeeded(self) -> None:
        cache.clear()
        seedPlatform()
        from apps.identity.infrastructure.models import RoleModel

        for code in (
            "maintenanceRequester",
            "maintenanceTechnician",
            "maintenanceManager",
        ):
            self.assertTrue(
                RoleModel.objects.filter(code=code).exists(),
                f"expected role {code} to be seeded",
            )
