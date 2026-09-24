"""Phase 24 — unified device timeline.

Pins the timeline boundary the Persian frontend consumes on the device detail
page: every device lifecycle event (registration, detail update, status change,
PM completion) persisted as append-only history, merged with the milestones of
the work orders raised against the device, returned newest-first.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from tests.support.phase6Helpers import loginViaApi, seedPlatform


class DeviceTimelineBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    def createDevice(self, code: str = "PUMP-T1") -> dict:
        response = self.client.post(
            "/api/v1/maintenance/devices",
            {
                "code": code,
                "name": "پمپ خنک‌کننده",
                "location": "سالن A",
                "department": "mechanical",
                "pmIntervalDays": 30,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def submitOrder(self, deviceId: str, title: str = "عیب پمپ") -> dict:
        response = self.client.post(
            "/api/v1/maintenance/work-orders",
            {
                "deviceId": deviceId,
                "title": title,
                "description": "بررسی",
                "orderType": "corrective",
                "priority": "high",
                "requestedByName": "کاربر",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def timeline(self, deviceId: str):
        response = self.client.get(
            f"/api/v1/maintenance/devices/{deviceId}/timeline", **self.auth
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class DeviceTimelineTests(DeviceTimelineBase):
    def testAuthenticationIsMandatory(self) -> None:
        device = self.createDevice()
        anonymous = APIClient()
        self.assertEqual(
            anonymous.get(
                f"/api/v1/maintenance/devices/{device['id']}/timeline"
            ).status_code,
            401,
        )

    def testRegistrationIsRecorded(self) -> None:
        device = self.createDevice()
        body = self.timeline(device["id"])
        items = body["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "device")
        self.assertEqual(items[0]["action"], "registered")
        self.assertEqual(body["data"]["device"]["id"], device["id"])

    def testStatusChangeAndPmAreRecorded(self) -> None:
        device = self.createDevice()
        self.assertEqual(
            self.client.post(
                f"/api/v1/maintenance/devices/{device['id']}/status",
                {"target": "underMaintenance"},
                format="json",
                **self.auth,
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/maintenance/devices/{device['id']}/pm",
                {"performedOn": "2026-09-01"},
                format="json",
                **self.auth,
            ).status_code,
            200,
        )
        actions = [i["action"] for i in self.timeline(device["id"])["data"]["items"]]
        self.assertIn("statusChanged", actions)
        self.assertIn("pmCompleted", actions)
        self.assertIn("registered", actions)

    def testStatusChangeCapturesFromTo(self) -> None:
        device = self.createDevice()
        self.client.post(
            f"/api/v1/maintenance/devices/{device['id']}/status",
            {"target": "underMaintenance"},
            format="json",
            **self.auth,
        )
        entry = next(
            i
            for i in self.timeline(device["id"])["data"]["items"]
            if i["action"] == "statusChanged"
        )
        self.assertEqual(entry["fromStatus"], "operational")
        self.assertEqual(entry["toStatus"], "underMaintenance")

    def testWorkOrderMilestonesAppearOnTimeline(self) -> None:
        device = self.createDevice()
        order = self.submitOrder(device["id"], "کار تعمیر")
        items = self.timeline(device["id"])["data"]["items"]
        raised = [i for i in items if i["action"] == "workOrderRaised"]
        self.assertEqual(len(raised), 1)
        self.assertEqual(raised[0]["source"], "workOrder")
        self.assertEqual(raised[0]["workOrderId"], order["id"])
        self.assertEqual(raised[0]["workOrderTitle"], "کار تعمیر")

    def testTimelineIsSortedNewestFirst(self) -> None:
        device = self.createDevice()
        self.submitOrder(device["id"], "کار اول")
        self.client.post(
            f"/api/v1/maintenance/devices/{device['id']}/status",
            {"target": "underMaintenance"},
            format="json",
            **self.auth,
        )
        items = self.timeline(device["id"])["data"]["items"]
        timestamps = [i["at"] for i in items]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def testTimelineIsTenantIsolatedByDevice(self) -> None:
        deviceA = self.createDevice("PUMP-A")
        deviceB = self.createDevice("PUMP-B")
        self.submitOrder(deviceA["id"], "کار A")
        itemsB = self.timeline(deviceB["id"])["data"]["items"]
        self.assertTrue(all(i["source"] == "device" for i in itemsB))
        self.assertEqual(len(itemsB), 1)

    def testUnknownDeviceReturns404(self) -> None:
        self.assertEqual(
            self.client.get(
                "/api/v1/maintenance/devices/"
                "00000000-0000-0000-0000-000000000000/timeline",
                **self.auth,
            ).status_code,
            404,
        )
