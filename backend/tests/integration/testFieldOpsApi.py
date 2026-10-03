"""End-to-end REST contract for field operations.

Three slices, one shift in the life of a technician:

* **scan** a label on a machine and land on the right page;
* **start / stop** the stopwatch and see the labour entry it minted;
* **sync** everything that was captured while the phone had no network, twice,
  and prove the second replay changes nothing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.maintenance.infrastructure.models import (
    DeviceModel,
    MaintenanceLocationModel,
    OfflineSyncOperationModel,
    SparePartModel,
    WorkOrderLabourEntryModel,
    WorkOrderModel,
    WorkTimerModel,
)
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform

BASE = "/api/v1/maintenance"


class FieldOpsApiBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        # Far enough back that every "+N hours" offset below still lands in
        # the past and never trips the five-minute future-skew guard.
        self.now = datetime.now(tz=UTC).replace(microsecond=0) - timedelta(days=2)

    # -- fixtures ---------------------------------------------------------------
    def createDevice(self, code: str = "PUMP-204", **overrides) -> dict:
        payload = {
            "code": code,
            "name": "پمپ خط یک",
            "location": "سالن A",
            "department": "mechanical",
            "pmIntervalDays": 30,
        }
        payload.update(overrides)
        response = self.client.post(f"{BASE}/devices", payload, format="json", **self.auth)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def createWorkOrder(self, deviceId: str, **overrides) -> dict:
        payload = {
            "deviceId": deviceId,
            "title": "تعویض بلبرینگ",
            "description": "صدای غیرعادی",
            "orderType": "corrective",
            "priority": "normal",
        }
        payload.update(overrides)
        response = self.client.post(
            f"{BASE}/work-orders", payload, format="json", **self.auth
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def assign(self, workOrderId: str, name: str = "حسینی") -> None:
        """Move a fresh order to ``assigned`` — the only startable state."""
        response = self.client.post(
            f"{BASE}/work-orders/{workOrderId}/assign",
            {"assignedToName": name},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

    def readyOrder(self, code: str = "PUMP-204") -> tuple[str, str]:
        device = self.createDevice(code)
        order = self.createWorkOrder(device["id"])
        self.assign(order["id"])
        return device["id"], order["id"]

    def startTimer(self, workOrderId: str, **payload):  # noqa: ANN201
        return self.client.post(
            f"{BASE}/work-orders/{workOrderId}/timer/start",
            payload,
            format="json",
            **self.auth,
        )

    def stopTimer(self, workOrderId: str, **payload):  # noqa: ANN201
        return self.client.post(
            f"{BASE}/work-orders/{workOrderId}/timer/stop",
            payload,
            format="json",
            **self.auth,
        )

    def sync(self, operations: list[dict], **extra):  # noqa: ANN201
        body = {"operations": operations}
        body.update(extra)
        return self.client.post(f"{BASE}/sync", body, format="json", **self.auth)

    @staticmethod
    def operation(kind: str, payload: dict, key: str = "", occurredAt: str = "") -> dict:
        return {
            "clientRequestId": key or uuid.uuid4().hex,
            "kind": kind,
            "payload": payload,
            "occurredAt": occurredAt,
        }


# =====================================================================================
# Scanning
# =====================================================================================
class ScanResolutionApiTests(FieldOpsApiBase):
    def testResolvesADeviceByItsBusinessCode(self) -> None:
        """The common case: a Code 128 label carrying «PUMP-204»."""
        device = self.createDevice("PUMP-204")
        response = self.client.get(
            f"{BASE}/scan", {"code": "PUMP-204", "symbology": "code_128"}, **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertEqual(data["kind"], "device")
        self.assertEqual(data["id"], device["id"])
        self.assertEqual(data["route"], f"/app/maintenance/devices/{device['id']}/profile")

    def testCodeLookupIsCaseInsensitive(self) -> None:
        self.createDevice("PUMP-204")
        response = self.client.get(f"{BASE}/scan", {"code": "pump-204"}, **self.auth)
        self.assertEqual(response.status_code, 200)

    def testResolvesADeviceByItsVendorSerialSticker(self) -> None:
        device = self.createDevice("PUMP-205")
        DeviceModel.objects.filter(id=device["id"]).update(serialNumber="SN-99812")
        response = self.client.get(f"{BASE}/scan", {"code": "SN-99812"}, **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["id"], device["id"])

    def testResolvesTheQrDeepLinkThisSystemPrints(self) -> None:
        device = self.createDevice("PUMP-206")
        link = f"https://plant.local/app/maintenance/devices/{device['id']}/profile"
        response = self.client.get(
            f"{BASE}/scan", {"code": link, "symbology": "qr_code"}, **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["kind"], "device")

    def testResolvesAWorkOrderQr(self) -> None:
        _deviceId, orderId = self.readyOrder("PUMP-207")
        response = self.client.get(
            f"{BASE}/scan", {"code": f"tekarai://work-order/{orderId}"}, **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertEqual(data["kind"], "workOrder")
        self.assertEqual(data["status"], "assigned")

    def testResolvesASparePartLabel(self) -> None:
        part = SparePartModel.objects.create(
            tenantId=self.tenantId, code="BRG-6204", name="بلبرینگ ۶۲۰۴", unit="عدد"
        )
        response = self.client.get(f"{BASE}/scan", {"code": "BRG-6204"}, **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertEqual(data["kind"], "sparePart")
        self.assertEqual(data["id"], str(part.id))

    def testResolvesALocationLabel(self) -> None:
        location = MaintenanceLocationModel.objects.create(
            tenantId=self.tenantId,
            code="HALL-A",
            name="سالن A",
            kind="area",
            createdAt=self.now,
        )
        response = self.client.get(f"{BASE}/scan", {"code": "HALL-A"}, **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["id"], str(location.id))

    def testDeviceWinsWhenACodeIsAmbiguous(self) -> None:
        """Equipment is what people scan in the field; it is probed first."""
        device = self.createDevice("DUP-1")
        SparePartModel.objects.create(
            tenantId=self.tenantId, code="DUP-1", name="قطعه هم‌کد", unit="عدد"
        )
        response = self.client.get(f"{BASE}/scan", {"code": "DUP-1"}, **self.auth)
        self.assertEqual(response.json()["data"]["id"], device["id"])

    def testUnknownCodeIs404(self) -> None:
        response = self.client.get(f"{BASE}/scan", {"code": "NOPE-1"}, **self.auth)
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(
            response.json()["errors"][0]["code"], "MAINT_SCAN_TARGET_NOT_FOUND"
        )

    def testUnreadableTextIs422(self) -> None:
        response = self.client.get(f"{BASE}/scan", {"code": "پمپ خط یک"}, **self.auth)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(
            response.json()["errors"][0]["code"], "MAINT_SCAN_CODE_UNREADABLE"
        )

    def testAnotherTenantsLabelDoesNotResolve(self) -> None:
        """Tenant isolation: the row exists, but not for this tenant."""
        DeviceModel.objects.create(
            tenantId=uuid.uuid4(), code="FOREIGN-1", name="دستگاه سازمان دیگر"
        )
        response = self.client.get(f"{BASE}/scan", {"code": "FOREIGN-1"}, **self.auth)
        self.assertEqual(response.status_code, 404, response.content)

    def testScanRequiresAuthentication(self) -> None:
        anonymous = APIClient()
        response = anonymous.get(f"{BASE}/scan", {"code": "PUMP-204"})
        self.assertEqual(response.status_code, 401)


# =====================================================================================
# Work timers
# =====================================================================================
class WorkTimerApiTests(FieldOpsApiBase):
    def testStartingATimerMovesTheOrderToInProgress(self) -> None:
        _deviceId, orderId = self.readyOrder()
        response = self.startTimer(orderId)
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()["data"]
        self.assertTrue(data["running"])
        self.assertEqual(data["endedAt"], "")
        self.assertEqual(
            WorkOrderModel.objects.get(id=orderId).status, "inProgress"
        )

    def testTimerInheritsTheSignedInTechniciansName(self) -> None:
        _deviceId, orderId = self.readyOrder()
        data = self.startTimer(orderId).json()["data"]
        self.assertTrue(data["technicianName"])

    def testCannotStartTwiceForTheSameTechnician(self) -> None:
        _deviceId, orderId = self.readyOrder()
        self.assertEqual(self.startTimer(orderId).status_code, 201)
        second = self.startTimer(orderId)
        self.assertEqual(second.status_code, 409, second.content)
        self.assertEqual(
            second.json()["errors"][0]["code"], "MAINT_TIMER_ALREADY_RUNNING"
        )

    def testTwoTechniciansMayWorkTheSameOrderAtOnce(self) -> None:
        _deviceId, orderId = self.readyOrder()
        self.assertEqual(self.startTimer(orderId, technicianName="حسینی").status_code, 201)
        self.assertEqual(self.startTimer(orderId, technicianName="رضایی").status_code, 201)
        self.assertEqual(
            WorkTimerModel.objects.filter(workOrderId=orderId, endedAt__isnull=True).count(),
            2,
        )

    def testStoppingMintsALabourEntryWithTheMeasuredHours(self) -> None:
        _deviceId, orderId = self.readyOrder()
        started = (self.now - timedelta(hours=2, minutes=30)).isoformat()
        self.startTimer(orderId, technicianName="حسینی", startedAt=started, hourlyRate="200000")
        response = self.stopTimer(
            orderId, technicianName="حسینی", endedAt=self.now.isoformat(), note="تمام شد"
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertEqual(data["hours"], "2.50")
        self.assertEqual(data["labourCost"], "500000.00")
        entry = WorkOrderLabourEntryModel.objects.get(id=data["labourEntryId"])
        self.assertEqual(entry.hours, Decimal("2.50"))
        self.assertEqual(entry.technicianName, "حسینی")

    def testStoppingRollsTheCostUpOntoTheWorkOrder(self) -> None:
        _deviceId, orderId = self.readyOrder()
        started = (self.now - timedelta(hours=1)).isoformat()
        self.startTimer(orderId, startedAt=started, hourlyRate="100000")
        self.stopTimer(orderId, endedAt=self.now.isoformat())
        order = WorkOrderModel.objects.get(id=orderId)
        self.assertEqual(order.labourHours, Decimal("1.00"))
        self.assertEqual(order.labourCost, Decimal("100000.00"))

    def testPausedMinutesAreNotBilled(self) -> None:
        _deviceId, orderId = self.readyOrder()
        started = (self.now - timedelta(hours=3)).isoformat()
        self.startTimer(orderId, startedAt=started)
        response = self.stopTimer(
            orderId, endedAt=self.now.isoformat(), pausedSeconds=1800
        )
        self.assertEqual(response.json()["data"]["hours"], "2.50")

    def testStoppingTwiceIs409(self) -> None:
        _deviceId, orderId = self.readyOrder()
        self.startTimer(orderId)
        self.assertEqual(self.stopTimer(orderId).status_code, 200)
        second = self.stopTimer(orderId)
        # No running timer left → «already stopped», a conflict, not a 404.
        self.assertEqual(second.status_code, 409, second.content)
        self.assertEqual(
            second.json()["errors"][0]["code"], "MAINT_TIMER_NOT_RUNNING"
        )

    def testStoppingByTimerIdAlsoWorks(self) -> None:
        _deviceId, orderId = self.readyOrder()
        timerId = self.startTimer(orderId).json()["data"]["id"]
        response = self.stopTimer(orderId, timerId=timerId)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["timer"]["id"], timerId)

    def testAFutureStartIsRefused(self) -> None:
        _deviceId, orderId = self.readyOrder()
        future = (datetime.now(tz=UTC) + timedelta(hours=2)).isoformat()
        response = self.startTimer(orderId, startedAt=future)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["errors"][0]["code"], "MAINT_TIMER_SPAN_INVALID")

    def testAForgottenStopwatchIsRefusedRatherThanBilled(self) -> None:
        _deviceId, orderId = self.readyOrder()
        started = (datetime.now(tz=UTC) - timedelta(hours=30)).isoformat()
        self.startTimer(orderId, startedAt=started)
        response = self.stopTimer(orderId)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(
            response.json()["errors"][0]["details"]["fields"]["endedAt"], "tooLong"
        )

    def testCannotStartOnAnUnassignedOrder(self) -> None:
        device = self.createDevice("PUMP-301")
        order = self.createWorkOrder(device["id"])
        response = self.startTimer(order["id"])
        self.assertEqual(response.status_code, 422, response.content)

    def testCancellingDiscardsTheSpanWithoutCost(self) -> None:
        _deviceId, orderId = self.readyOrder()
        timerId = self.startTimer(orderId).json()["data"]["id"]
        response = self.client.delete(f"{BASE}/work-timers/{timerId}", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(WorkTimerModel.objects.filter(id=timerId).exists())
        self.assertFalse(WorkOrderLabourEntryModel.objects.filter(workOrderId=orderId).exists())

    def testActiveTimersSurviveAnAppRestart(self) -> None:
        _deviceId, orderId = self.readyOrder()
        self.startTimer(orderId)
        response = self.client.get(f"{BASE}/work-timers/active", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertGreaterEqual(rows[0]["elapsedSeconds"], 0)

    def testTimerHistoryIsListedPerOrder(self) -> None:
        _deviceId, orderId = self.readyOrder()
        self.startTimer(orderId, startedAt=(self.now - timedelta(hours=1)).isoformat())
        self.stopTimer(orderId, endedAt=self.now.isoformat())
        self.startTimer(orderId)
        response = self.client.get(f"{BASE}/work-orders/{orderId}/timers", **self.auth)
        self.assertEqual(len(response.json()["data"]), 2)
        running = self.client.get(
            f"{BASE}/work-orders/{orderId}/timers", {"runningOnly": "true"}, **self.auth
        )
        self.assertEqual(len(running.json()["data"]), 1)

    def testTimerEndpointsRequireAuthentication(self) -> None:
        _deviceId, orderId = self.readyOrder()
        anonymous = APIClient()
        self.assertEqual(
            anonymous.post(f"{BASE}/work-orders/{orderId}/timer/start", {}, format="json").status_code,
            401,
        )


# =====================================================================================
# Offline sync
# =====================================================================================
class OfflineSyncApiTests(FieldOpsApiBase):
    def testReplaysAWholeShiftCapturedOffline(self) -> None:
        _deviceId, orderId = self.readyOrder()
        startedAt = (self.now - timedelta(hours=4)).isoformat()
        endedAt = (self.now - timedelta(hours=2)).isoformat()
        operations = [
            self.operation(
                "workTimer.start",
                {"workOrderId": orderId, "technicianName": "حسینی", "startedAt": startedAt},
            ),
            self.operation(
                "workTimer.stop",
                {
                    "workOrderId": orderId,
                    "technicianName": "حسینی",
                    "endedAt": endedAt,
                    "note": "ثبت‌شده در حالت آفلاین",
                },
            ),
            self.operation(
                "workOrder.status",
                {"workOrderId": orderId, "target": "pendingApproval", "resolutionNote": "انجام شد"},
            ),
        ]
        response = self.sync(operations, deviceLabel="Galaxy A14 - حسینی")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual([item["status"] for item in body["data"]], ["applied"] * 3)
        self.assertEqual(body["meta"]["appliedCount"], 3)
        self.assertEqual(WorkOrderModel.objects.get(id=orderId).status, "pendingApproval")
        entry = WorkOrderLabourEntryModel.objects.get(workOrderId=orderId)
        self.assertEqual(entry.hours, Decimal("2.00"))

    def testTheOfflineMomentIsPreservedNotTheSyncMoment(self) -> None:
        """A reading taken at 08:00 and synced at 17:00 belongs to 08:00."""
        _deviceId, orderId = self.readyOrder()
        startedAt = (self.now - timedelta(hours=6)).replace(microsecond=0)
        self.sync(
            [
                self.operation(
                    "workTimer.start",
                    {"workOrderId": orderId, "technicianName": "حسینی"},
                    occurredAt=startedAt.isoformat(),
                )
            ]
        )
        timer = WorkTimerModel.objects.get(workOrderId=orderId)
        self.assertEqual(timer.startedAt.replace(microsecond=0), startedAt)
        self.assertTrue(timer.capturedOffline)
        self.assertEqual(timer.startedVia, "offline")

    def testReplayingTheSameBatchChangesNothing(self) -> None:
        """The core offline promise: sync twice, charge once."""
        _deviceId, orderId = self.readyOrder()
        operations = [
            self.operation(
                "workOrder.labour",
                {
                    "workOrderId": orderId,
                    "technicianName": "حسینی",
                    "hours": "1.5",
                    "hourlyRate": "100000",
                },
                key="fixed-key-1",
            )
        ]
        first = self.sync(operations)
        second = self.sync(operations)
        self.assertEqual(first.json()["data"][0]["status"], "applied")
        self.assertEqual(second.json()["data"][0]["status"], "duplicate")
        self.assertEqual(
            second.json()["data"][0]["resultId"], first.json()["data"][0]["resultId"]
        )
        self.assertEqual(WorkOrderLabourEntryModel.objects.filter(workOrderId=orderId).count(), 1)

    def testAPartIsNeverConsumedTwiceByAReplay(self) -> None:
        _deviceId, orderId = self.readyOrder()
        part = SparePartModel.objects.create(
            tenantId=self.tenantId,
            code="BRG-6204",
            name="بلبرینگ",
            unit="عدد",
            quantityOnHand=Decimal("10"),
            unitCost=Decimal("50000"),
        )
        operations = [
            self.operation(
                "workOrder.partUsage",
                {"workOrderId": orderId, "partId": str(part.id), "quantity": "3"},
                key="part-key-1",
            )
        ]
        self.sync(operations)
        self.sync(operations)
        part.refresh_from_db()
        self.assertEqual(part.quantityOnHand, Decimal("7.000"))

    def testPartialSuccessKeepsTheGoodItems(self) -> None:
        _deviceId, orderId = self.readyOrder()
        operations = [
            self.operation(
                "workOrder.labour",
                {"workOrderId": orderId, "technicianName": "حسینی", "hours": "1"},
            ),
            self.operation(
                "workOrder.labour",
                {"workOrderId": str(uuid.uuid4()), "technicianName": "حسینی", "hours": "1"},
            ),
            self.operation(
                "workOrder.labour",
                {"workOrderId": orderId, "technicianName": "رضایی", "hours": "2"},
            ),
        ]
        response = self.sync(operations)
        statuses = [item["status"] for item in response.json()["data"]]
        self.assertEqual(statuses, ["applied", "rejected", "applied"])
        self.assertEqual(response.json()["meta"]["rejectedCount"], 1)
        self.assertEqual(WorkOrderLabourEntryModel.objects.filter(workOrderId=orderId).count(), 2)

    def testARejectedItemStaysRejectedOnRetry(self) -> None:
        """The queue must stop retrying what can never succeed."""
        operations = [
            self.operation(
                "workOrder.status",
                {"workOrderId": str(uuid.uuid4()), "target": "completed"},
                key="doomed-1",
            )
        ]
        self.assertEqual(self.sync(operations).json()["data"][0]["status"], "rejected")
        again = self.sync(operations).json()["data"][0]
        self.assertEqual(again["status"], "rejected")
        self.assertTrue(again["errorCode"])

    def testAnIllegalStatusJumpIsRejectedNotRetried(self) -> None:
        _deviceId, orderId = self.readyOrder()
        response = self.sync(
            [self.operation("workOrder.status", {"workOrderId": orderId, "target": "completed"})]
        )
        item = response.json()["data"][0]
        self.assertEqual(item["status"], "rejected")
        self.assertEqual(item["errorCode"], "STATE_INVALID_TRANSITION")

    def testReplayedTimerStopCountsAsDuplicateNotFailure(self) -> None:
        """Phone sent the stop, lost the ack, and retried with a *new* id.

        The second attempt cannot be recognised by ``clientRequestId``, so the
        verdict has to come from the domain: "nothing is running" means the
        first stop landed. That must read as ``duplicate`` — a ``failed``
        verdict would keep the item in the queue forever.
        """
        _deviceId, orderId = self.readyOrder()
        self.startTimer(
            orderId,
            technicianName="حسینی",
            startedAt=(self.now - timedelta(hours=1)).isoformat(),
        )
        stop = self.operation(
            "workTimer.stop",
            {"workOrderId": orderId, "technicianName": "حسینی", "endedAt": self.now.isoformat()},
            key="stop-1",
        )
        self.assertEqual(self.sync([stop]).json()["data"][0]["status"], "applied")
        retry = dict(stop, clientRequestId="stop-2")
        self.assertEqual(self.sync([retry]).json()["data"][0]["status"], "duplicate")
        self.assertEqual(
            WorkOrderLabourEntryModel.objects.filter(workOrderId=orderId).count(), 1
        )

    def testDuplicateStartIsReportedAsDuplicate(self) -> None:
        _deviceId, orderId = self.readyOrder()
        self.startTimer(orderId, technicianName="حسینی")
        response = self.sync(
            [
                self.operation(
                    "workTimer.start",
                    {"workOrderId": orderId, "technicianName": "حسینی"},
                    key="start-again",
                )
            ]
        )
        self.assertEqual(response.json()["data"][0]["status"], "duplicate")

    def testUnknownKindIsRejectedWithoutTouchingAnything(self) -> None:
        response = self.sync(
            [{"clientRequestId": "x-1", "kind": "workOrder.status", "payload": {}}]
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["status"], "rejected")

    def testKindOutsideTheCatalogueIsRefusedBySerializer(self) -> None:
        """An unknown kind never reaches the domain — 400 from the serializer."""
        response = self.sync([{"clientRequestId": "x-2", "kind": "robot.dance", "payload": {}}])
        self.assertEqual(response.status_code, 400, response.content)

    def testDuplicateClientRequestIdInsideOneBatchIsRefused(self) -> None:
        _deviceId, orderId = self.readyOrder()
        payload = {"workOrderId": orderId, "technicianName": "حسینی", "hours": "1"}
        response = self.sync(
            [
                self.operation("workOrder.labour", payload, key="same"),
                self.operation("workOrder.labour", payload, key="same"),
            ]
        )
        self.assertEqual(response.status_code, 422, response.content)

    def testEmptyBatchIsAcceptedAsANoOp(self) -> None:
        """A phone that comes online with nothing queued must not see an error."""
        response = self.sync([])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["meta"]["appliedCount"], 0)

    def testAnOversizedBatchIsRefused(self) -> None:
        operations = [
            self.operation("workOrder.status", {"workOrderId": str(uuid.uuid4()), "target": "routed"})
            for _ in range(201)
        ]
        response = self.sync(operations)
        self.assertEqual(response.status_code, 400, response.content)

    def testDeviceStatusCapturedOfflineIsApplied(self) -> None:
        device = self.createDevice("PUMP-401")
        response = self.sync(
            [
                self.operation(
                    "device.status", {"deviceId": device["id"], "target": "underMaintenance"}
                )
            ]
        )
        self.assertEqual(response.json()["data"][0]["status"], "applied")
        self.assertEqual(
            DeviceModel.objects.get(id=device["id"]).status, "underMaintenance"
        )

    def testMeterReadingCapturedOfflineKeepsItsMoment(self) -> None:
        device = self.createDevice("PUMP-402")
        self.client.post(
            f"{BASE}/devices/{device['id']}/meter-points",
            {
                "code": "RUNNING_HOURS",
                "name": "ساعت کارکرد",
                "unit": "ساعت",
                "kind": "cumulative",
                "drivesRunningHours": True,
            },
            format="json",
            **self.auth,
        )
        capturedAt = (self.now - timedelta(hours=5)).isoformat()
        response = self.sync(
            [
                self.operation(
                    "meter.reading",
                    {
                        "deviceId": device["id"],
                        "meterCode": "RUNNING_HOURS",
                        "value": "1200.5",
                        "capturedAt": capturedAt,
                    },
                )
            ]
        )
        item = response.json()["data"][0]
        self.assertEqual(item["status"], "applied")
        self.assertEqual(item["result"]["value"], "1200.5000")

    def testTheLedgerRecordsWhatWasReplayed(self) -> None:
        _deviceId, orderId = self.readyOrder()
        self.sync(
            [
                self.operation(
                    "workOrder.labour",
                    {"workOrderId": orderId, "technicianName": "حسینی", "hours": "1"},
                    key="ledger-1",
                )
            ],
            deviceLabel="Nokia - انبار",
        )
        row = OfflineSyncOperationModel.objects.get(clientRequestId="ledger-1")
        self.assertEqual(row.kind, "workOrder.labour")
        self.assertEqual(row.status, "applied")
        self.assertEqual(row.deviceLabel, "Nokia - انبار")
        history = self.client.get(f"{BASE}/sync/history", **self.auth)
        self.assertEqual(history.status_code, 200, history.content)
        self.assertEqual(history.json()["data"][0]["clientRequestId"], "ledger-1")

    def testAnotherTenantsClientRequestIdDoesNotCollide(self) -> None:
        """The ledger is keyed per tenant; two plants may mint the same id."""
        _deviceId, orderId = self.readyOrder()
        OfflineSyncOperationModel.objects.create(
            tenantId=uuid.uuid4(),
            clientRequestId="shared-key",
            kind="workOrder.labour",
            status="applied",
            receivedAt=self.now,
        )
        response = self.sync(
            [
                self.operation(
                    "workOrder.labour",
                    {"workOrderId": orderId, "technicianName": "حسینی", "hours": "1"},
                    key="shared-key",
                )
            ]
        )
        self.assertEqual(response.json()["data"][0]["status"], "applied")

    def testSyncRequiresAuthentication(self) -> None:
        anonymous = APIClient()
        response = anonymous.post(f"{BASE}/sync", {"operations": []}, format="json")
        self.assertEqual(response.status_code, 401)

    def testSyncCannotBeUsedToEscapePermissions(self) -> None:
        """Inner use cases still run their own permission checks.

        A requester-level session may not change a device's status; routing
        the same intent through the sync endpoint must not launder it.
        """
        from apps.identity.infrastructure.models import (
            RoleModel,
            UserModel,
            UserRoleModel,
        )

        device = DeviceModel.objects.create(
            tenantId=self.tenantId, code="PERM-1", name="دستگاه تست دسترسی"
        )
        admin = UserModel.objects.get(username="platform-admin")
        UserRoleModel.objects.filter(userId=admin.id).delete()
        requester = RoleModel.objects.filter(code="maintenanceRequester").first()
        self.assertIsNotNone(requester)
        UserRoleModel.objects.create(
            userId=admin.id, tenantId=self.tenantId, roleId=requester.id
        )
        cache.clear()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

        response = self.sync(
            [self.operation("device.status", {"deviceId": str(device.id), "target": "retired"})]
        )
        item = response.json()["data"][0]
        self.assertEqual(item["status"], "rejected")
        self.assertEqual(item["errorCode"], "PERM_PERMISSION_DENIED")
        self.assertEqual(DeviceModel.objects.get(id=device.id).status, "operational")
