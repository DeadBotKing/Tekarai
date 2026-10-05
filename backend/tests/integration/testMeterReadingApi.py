"""End-to-end REST and persistence contract for manual + sensor meter readings.

Covers the whole slice the way the plant uses it: define a meter, type a
reading, push a sensor batch, correct a mistake, read the summary, and watch a
"every 500 running hours" PM plan actually become due.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.maintenance.domain.exceptions.meterErrors import MeterReadingImmutableError
from apps.maintenance.infrastructure.models import (
    DeviceModel,
    MeterPointModel,
    MeterReadingModel,
    PmPlanModel,
)
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform

BASE = "/api/v1/maintenance"


class MeterApiBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        # Far enough back that the later offsets in these tests still land in
        # the past and never trip the five-minute future-skew guard.
        self.now = datetime.now(tz=UTC).replace(microsecond=0) - timedelta(days=10)

    # -- helpers ----------------------------------------------------------------
    def createDevice(self, code: str = "PUMP-01") -> dict:
        response = self.client.post(
            f"{BASE}/devices",
            {
                "code": code,
                "name": "پمپ خنک‌کننده اصلی",
                "location": "سالن تولید A",
                "department": "mechanical",
                "pmIntervalDays": 30,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def createPoint(self, deviceId: str, **overrides) -> dict:
        payload = {
            "code": "RUNNING_HOURS",
            "name": "ساعت کارکرد",
            "unit": "ساعت",
            "kind": "cumulative",
            "sensorKey": "Line1/Pump01.Hours",
            "drivesRunningHours": True,
        }
        payload.update(overrides)
        response = self.client.post(
            f"{BASE}/devices/{deviceId}/meter-points", payload, format="json", **self.auth
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def recordManual(self, deviceId: str, value: str, **overrides) -> dict:
        payload = {"meterCode": "RUNNING_HOURS", "value": value}
        payload.update(overrides)
        return self.client.post(
            f"{BASE}/devices/{deviceId}/meter-readings", payload, format="json", **self.auth
        )

    def ingest(self, readings: list[dict], atomic: bool = False):  # noqa: ANN201
        return self.client.post(
            f"{BASE}/meter-readings/ingest",
            {"readings": readings, "atomic": atomic},
            format="json",
            **self.auth,
        )


class MeterPointApiTests(MeterApiBase):
    def testDefineListAndRetireAMeterPoint(self) -> None:
        device = self.createDevice()
        point = self.createPoint(device["id"])
        self.assertEqual(point["code"], "RUNNING_HOURS")
        self.assertEqual(point["kind"], "cumulative")
        self.assertTrue(point["drivesRunningHours"])

        listing = self.client.get(f"{BASE}/devices/{device['id']}/meter-points", **self.auth)
        self.assertEqual(listing.status_code, 200, listing.content)
        self.assertEqual(len(listing.json()["data"]), 1)

        retired = self.client.delete(f"{BASE}/meter-points/{point['id']}", **self.auth)
        self.assertEqual(retired.status_code, 200, retired.content)
        self.assertIsNotNone(
            MeterPointModel.objects.get(id=point["id"]).deletedAt,
            "retiring a point must be a soft delete so its readings survive",
        )

    def testMeterCodeIsUppercasedAndUniquePerDevice(self) -> None:
        device = self.createDevice()
        created = self.createPoint(
            device["id"], code="pump.kwh", sensorKey="", kind="cumulative", drivesRunningHours=False
        )
        self.assertEqual(created["code"], "PUMP.KWH")

        duplicate = self.client.post(
            f"{BASE}/devices/{device['id']}/meter-points",
            {"code": "PUMP.KWH", "name": "دوباره", "kind": "cumulative"},
            format="json",
            **self.auth,
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.content)

    def testSensorKeyCannotBeBoundTwice(self) -> None:
        first = self.createDevice("PUMP-01")
        second = self.createDevice("PUMP-02")
        self.createPoint(first["id"])
        clash = self.client.post(
            f"{BASE}/devices/{second['id']}/meter-points",
            {
                "code": "RUNNING_HOURS",
                "name": "ساعت کارکرد",
                "kind": "cumulative",
                "sensorKey": "Line1/Pump01.Hours",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(clash.status_code, 409, clash.content)

    def testGaugeCannotDeclareRolloverOrDriveRunningHours(self) -> None:
        device = self.createDevice()
        rollover = self.client.post(
            f"{BASE}/devices/{device['id']}/meter-points",
            {
                "code": "BEARING_TEMP",
                "name": "دما",
                "kind": "gauge",
                "rolloverMaximum": "100",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(rollover.status_code, 422, rollover.content)

        hours = self.client.post(
            f"{BASE}/devices/{device['id']}/meter-points",
            {
                "code": "BEARING_TEMP",
                "name": "دما",
                "kind": "gauge",
                "drivesRunningHours": True,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(hours.status_code, 422, hours.content)

    def testAuthenticationIsRequired(self) -> None:
        anonymous = APIClient()
        self.assertEqual(anonymous.get(f"{BASE}/meter-points").status_code, 401)
        self.assertEqual(anonymous.get(f"{BASE}/meter-readings").status_code, 401)
        self.assertEqual(
            anonymous.post(f"{BASE}/meter-readings/ingest", {}, format="json").status_code,
            401,
        )


class ManualReadingApiTests(MeterApiBase):
    def testRecordManualReadingAttributesItToTheSession(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        response = self.recordManual(
            device["id"], "8400.5", capturedAt=self.now.isoformat(), note="قرائت شیفت صبح"
        )
        self.assertEqual(response.status_code, 201, response.content)
        reading = response.json()["data"]
        self.assertEqual(reading["value"], "8400.5000")
        self.assertEqual(reading["captureMode"], "manual")
        self.assertEqual(reading["quality"], "good")
        # First reading of a series has no delta — zero would be a lie.
        self.assertEqual(reading["delta"], "")
        self.assertTrue(reading["provenance"].startswith("manual"))

    def testDecimalPrecisionSurvivesTheRoundTrip(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"], code="PUMP.KWH", sensorKey="", drivesRunningHours=False)
        response = self.recordManual(device["id"], "124578901.2345", meterCode="PUMP.KWH")
        self.assertEqual(response.json()["data"]["value"], "124578901.2345")

    def testSecondReadingCarriesTheDelta(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        self.recordManual(device["id"], "8400", capturedAt=self.now.isoformat())
        second = self.recordManual(
            device["id"], "8410.25", capturedAt=(self.now + timedelta(hours=10)).isoformat()
        )
        self.assertEqual(second.json()["data"]["delta"], "10.2500")

    def testRunningHoursOnTheDeviceBecomeDerived(self) -> None:
        """The nameplate field is no longer typed — it follows the meter."""
        device = self.createDevice()
        self.createPoint(device["id"])
        self.recordManual(device["id"], "8400", capturedAt=self.now.isoformat())
        self.assertEqual(DeviceModel.objects.get(id=device["id"]).runningHours, Decimal("8400.00"))
        self.recordManual(
            device["id"], "8460", capturedAt=(self.now + timedelta(hours=60)).isoformat()
        )
        self.assertEqual(DeviceModel.objects.get(id=device["id"]).runningHours, Decimal("8460.00"))

    def testBackwardsCounterIsKeptButFlaggedSuspect(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"], rolloverMaximum="999999")
        self.recordManual(device["id"], "8400", capturedAt=self.now.isoformat())
        typo = self.recordManual(
            device["id"], "840", capturedAt=(self.now + timedelta(hours=1)).isoformat()
        )
        self.assertEqual(typo.status_code, 201, typo.content)
        body = typo.json()["data"]
        self.assertEqual(body["quality"], "suspect")
        self.assertEqual(body["delta"], "", "a suspect value must not produce consumption")

    def testCounterRolloverIsReconstructedThroughTheApi(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"], rolloverMaximum="999999")
        self.recordManual(device["id"], "999950", capturedAt=self.now.isoformat())
        wrapped = self.recordManual(
            device["id"], "41", capturedAt=(self.now + timedelta(hours=90)).isoformat()
        )
        body = wrapped.json()["data"]
        self.assertTrue(body["rolloverApplied"])
        self.assertEqual(body["delta"], "90.0000")

    def testReadingOutsideTheDeclaredRangeIsRejected(self) -> None:
        device = self.createDevice()
        self.createPoint(
            device["id"],
            code="BEARING_TEMP",
            kind="gauge",
            sensorKey="",
            drivesRunningHours=False,
            minimumValue="-50",
            maximumValue="250",
        )
        response = self.recordManual(device["id"], "900", meterCode="BEARING_TEMP")
        self.assertEqual(response.status_code, 422, response.content)

    def testFutureReadingIsRejected(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        future = datetime.now(tz=UTC) + timedelta(hours=2)
        response = self.recordManual(device["id"], "8400", capturedAt=future.isoformat())
        self.assertEqual(response.status_code, 422, response.content)

    def testUnknownMeterCodeIsNotFound(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        response = self.recordManual(device["id"], "1", meterCode="NOPE")
        self.assertEqual(response.status_code, 404, response.content)

    def testAmbiguousAddressingIsRejected(self) -> None:
        device = self.createDevice()
        point = self.createPoint(device["id"])
        response = self.recordManual(
            device["id"], "1", meterCode="RUNNING_HOURS", meterPointId=point["id"]
        )
        self.assertEqual(response.status_code, 422, response.content)


class SensorIngestApiTests(MeterApiBase):
    def testGatewayBatchResolvesPointsBySensorKey(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        response = self.ingest(
            [
                {
                    "sensorKey": "Line1/Pump01.Hours",
                    "value": "8400.0",
                    "capturedAt": self.now.isoformat(),
                    "ingestionKey": "gw1:1",
                },
                {
                    "sensorKey": "Line1/Pump01.Hours",
                    "value": "8401.0",
                    "capturedAt": (self.now + timedelta(hours=1)).isoformat(),
                    "ingestionKey": "gw1:2",
                },
            ]
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["meta"]["accepted"], 2)
        self.assertEqual(body["meta"]["rejected"], 0)
        self.assertEqual(body["data"][1]["delta"], "1.0000")
        self.assertEqual(MeterReadingModel.objects.filter(captureMode="sensor").count(), 2)

    def testReplayingTheSameBatchIsIdempotent(self) -> None:
        """A gateway retry must never double-count a counter."""
        device = self.createDevice()
        self.createPoint(device["id"])
        sample = [
            {
                "sensorKey": "Line1/Pump01.Hours",
                "value": "8400.0",
                "capturedAt": self.now.isoformat(),
                "ingestionKey": "gw1:1",
            }
        ]
        first = self.ingest(sample)
        second = self.ingest(sample)
        self.assertEqual(first.json()["meta"]["accepted"], 1)
        self.assertEqual(second.json()["meta"]["duplicates"], 1)
        self.assertEqual(second.json()["data"][0]["status"], "duplicate")
        self.assertEqual(MeterReadingModel.objects.count(), 1)

    def testSameKeyWithADifferentValueIsAConflict(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        self.ingest(
            [
                {
                    "sensorKey": "Line1/Pump01.Hours",
                    "value": "8400.0",
                    "ingestionKey": "gw1:1",
                }
            ]
        )
        conflicting = self.ingest(
            [
                {
                    "sensorKey": "Line1/Pump01.Hours",
                    "value": "9999.0",
                    "ingestionKey": "gw1:1",
                }
            ]
        )
        result = conflicting.json()["data"][0]
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["errorCode"], "MAINT_METER_INGESTION_CONFLICT")

    def testOneBadSampleDoesNotLoseTheGoodOnes(self) -> None:
        """Partial success is the point: telemetry that rejects wholesale is dropped."""
        device = self.createDevice()
        self.createPoint(device["id"])
        response = self.ingest(
            [
                {"sensorKey": "Line1/Pump01.Hours", "value": "8400.0", "ingestionKey": "a"},
                {"sensorKey": "Line1/NOT-BOUND", "value": "1", "ingestionKey": "b"},
                {"sensorKey": "Line1/Pump01.Hours", "value": "8402.0", "ingestionKey": "c"},
            ]
        )
        meta = response.json()["meta"]
        self.assertEqual(meta["accepted"], 2)
        self.assertEqual(meta["rejected"], 1)
        self.assertEqual(response.json()["data"][1]["errorCode"], "MAINT_METER_POINT_NOT_BOUND")

    def testAtomicBatchRollsEverythingBack(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        response = self.ingest(
            [
                {"sensorKey": "Line1/Pump01.Hours", "value": "8400.0", "ingestionKey": "a"},
                {"sensorKey": "Line1/NOT-BOUND", "value": "1", "ingestionKey": "b"},
            ],
            atomic=True,
        )
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(
            MeterReadingModel.objects.count(), 0, "atomic batch must leave nothing behind"
        )

    def testDuplicateKeysInsideOneBatchAreRejectedUpFront(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        response = self.ingest(
            [
                {"sensorKey": "Line1/Pump01.Hours", "value": "1", "ingestionKey": "same"},
                {"sensorKey": "Line1/Pump01.Hours", "value": "2", "ingestionKey": "same"},
            ]
        )
        self.assertEqual(response.status_code, 422, response.content)

    def testInactivePointRefusesSensorInput(self) -> None:
        device = self.createDevice()
        point = self.createPoint(device["id"])
        self.client.patch(
            f"{BASE}/meter-points/{point['id']}",
            {"active": False},
            format="json",
            **self.auth,
        )
        response = self.ingest(
            [{"sensorKey": "Line1/Pump01.Hours", "value": "1", "ingestionKey": "x"}]
        )
        self.assertEqual(response.json()["data"][0]["status"], "rejected")

    def testBatchSizeIsCapped(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        oversized = [
            {"sensorKey": "Line1/Pump01.Hours", "value": "1", "ingestionKey": f"k{i}"}
            for i in range(501)
        ]
        self.assertEqual(self.ingest(oversized).status_code, 400)


class AppendOnlyTests(MeterApiBase):
    def testThereIsNoUpdateOrDeleteRoute(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        created = self.recordManual(device["id"], "8400").json()["data"]
        detail = f"{BASE}/meter-readings/{created['id']}"
        self.assertIn(
            self.client.patch(detail, {"value": "1"}, format="json", **self.auth).status_code,
            (404, 405),
        )
        self.assertIn(self.client.delete(detail, **self.auth).status_code, (404, 405))

    def testModelRefusesInPlaceUpdate(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        self.recordManual(device["id"], "8400")
        row = MeterReadingModel.objects.first()
        row.value = Decimal("1")
        with self.assertRaises(MeterReadingImmutableError):
            row.save()

    def testQuerySetRefusesBulkUpdateAndDelete(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        self.recordManual(device["id"], "8400")
        with self.assertRaises(MeterReadingImmutableError):
            MeterReadingModel.objects.all().update(value=Decimal("1"))
        with self.assertRaises(MeterReadingImmutableError):
            MeterReadingModel.objects.all().delete()

    def testModelRefusesIndividualDelete(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        self.recordManual(device["id"], "8400")
        with self.assertRaises(MeterReadingImmutableError):
            MeterReadingModel.objects.first().delete()


class CorrectionTests(MeterApiBase):
    def testCorrectionAppendsAndSupersedesInsteadOfEditing(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        wrong = self.recordManual(device["id"], "84000", capturedAt=self.now.isoformat()).json()[
            "data"
        ]

        corrected = self.client.post(
            f"{BASE}/meter-readings/{wrong['id']}/correct",
            {"value": "8400", "note": "صفر اضافه تایپ شده بود"},
            format="json",
            **self.auth,
        )
        self.assertEqual(corrected.status_code, 201, corrected.content)
        body = corrected.json()["data"]
        self.assertEqual(body["value"], "8400.0000")
        self.assertEqual(body["correctsReadingId"], wrong["id"])
        # The correction keeps the original observation time.
        self.assertEqual(body["capturedAt"], wrong["capturedAt"])

        original = MeterReadingModel.objects.get(id=wrong["id"])
        self.assertEqual(str(original.supersededByReadingId), body["id"])
        self.assertEqual(
            MeterReadingModel.objects.count(), 2, "both rows must survive a correction"
        )

    def testCorrectionWithoutAReasonIsRejected(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        reading = self.recordManual(device["id"], "8400").json()["data"]
        response = self.client.post(
            f"{BASE}/meter-readings/{reading['id']}/correct",
            {"value": "1"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400, response.content)

    def testTheSameReadingCannotBeCorrectedTwice(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        reading = self.recordManual(device["id"], "8400").json()["data"]
        payload = {"value": "8401", "note": "اصلاح"}
        self.client.post(
            f"{BASE}/meter-readings/{reading['id']}/correct",
            payload,
            format="json",
            **self.auth,
        )
        again = self.client.post(
            f"{BASE}/meter-readings/{reading['id']}/correct",
            payload,
            format="json",
            **self.auth,
        )
        self.assertEqual(again.status_code, 409, again.content)

    def testASupersededReadingStopsDrivingLaterDeltas(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        wrong = self.recordManual(device["id"], "84000", capturedAt=self.now.isoformat()).json()[
            "data"
        ]
        self.client.post(
            f"{BASE}/meter-readings/{wrong['id']}/correct",
            {"value": "8400", "note": "اصلاح"},
            format="json",
            **self.auth,
        )
        later = self.recordManual(
            device["id"], "8410", capturedAt=(self.now + timedelta(hours=10)).isoformat()
        ).json()["data"]
        self.assertEqual(
            later["delta"], "10.0000", "the delta must follow the correction, not the typo"
        )


class ReadingQueryTests(MeterApiBase):
    def testFilterByCaptureModeAndPaginate(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        for index in range(3):
            self.recordManual(
                device["id"],
                str(8400 + index),
                capturedAt=(self.now + timedelta(hours=index)).isoformat(),
            )
        self.ingest(
            [
                {
                    "sensorKey": "Line1/Pump01.Hours",
                    "value": "8500",
                    "capturedAt": (self.now + timedelta(hours=10)).isoformat(),
                    "ingestionKey": "s1",
                }
            ]
        )

        manual = self.client.get(f"{BASE}/meter-readings?captureMode=manual", **self.auth)
        self.assertEqual(manual.json()["meta"]["total"], 3)
        sensor = self.client.get(f"{BASE}/meter-readings?captureMode=sensor", **self.auth)
        self.assertEqual(sensor.json()["meta"]["total"], 1)

        paged = self.client.get(f"{BASE}/meter-readings?pageSize=2&page=1", **self.auth)
        self.assertEqual(len(paged.json()["data"]), 2)
        self.assertEqual(paged.json()["meta"]["total"], 4)

    def testSummarySeparatesManualFromSensorAndTotalsConsumption(self) -> None:
        device = self.createDevice()
        point = self.createPoint(device["id"])
        self.recordManual(device["id"], "8400", capturedAt=self.now.isoformat())
        self.ingest(
            [
                {
                    "sensorKey": "Line1/Pump01.Hours",
                    "value": "8410",
                    "capturedAt": (self.now + timedelta(hours=10)).isoformat(),
                    "ingestionKey": "s1",
                },
                {
                    "sensorKey": "Line1/Pump01.Hours",
                    "value": "8425",
                    "capturedAt": (self.now + timedelta(hours=25)).isoformat(),
                    "ingestionKey": "s2",
                },
            ]
        )
        response = self.client.get(f"{BASE}/meter-points/{point['id']}/summary", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        summary = response.json()["data"]
        self.assertEqual(summary["readingCount"], 3)
        self.assertEqual(summary["manualCount"], 1)
        self.assertEqual(summary["sensorCount"], 2)
        self.assertEqual(summary["firstValue"], "8400.0000")
        self.assertEqual(summary["lastValue"], "8425.0000")
        self.assertEqual(summary["totalConsumption"], "25.0000")

    def testGaugeSummaryHasNoConsumptionButHasAnAverage(self) -> None:
        device = self.createDevice()
        point = self.createPoint(
            device["id"],
            code="BEARING_TEMP",
            kind="gauge",
            sensorKey="",
            drivesRunningHours=False,
        )
        for index, value in enumerate(("70", "72", "74")):
            self.recordManual(
                device["id"],
                value,
                meterCode="BEARING_TEMP",
                capturedAt=(self.now + timedelta(hours=index)).isoformat(),
            )
        summary = self.client.get(f"{BASE}/meter-points/{point['id']}/summary", **self.auth).json()[
            "data"
        ]
        self.assertEqual(summary["totalConsumption"], "")
        self.assertEqual(summary["minimumValue"], "70.0000")
        self.assertEqual(summary["maximumValue"], "74.0000")
        self.assertTrue(summary["averageValue"].startswith("72"))


class TenantIsolationTests(MeterApiBase):
    def testReadingsOfAnotherTenantAreInvisible(self) -> None:
        device = self.createDevice()
        point = self.createPoint(device["id"])
        self.recordManual(device["id"], "8400")

        strangerTenant = uuid.uuid4()
        MeterPointModel.objects.filter(id=point["id"]).update(tenantId=strangerTenant)
        # Readings are append-only even for tests, so re-home them in SQL.
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE "MeterReading" SET "tenantId" = %s WHERE "tenantId" IN (%s, %s)',
                [strangerTenant.hex, self.tenantId.hex, str(self.tenantId)],
            )

        listing = self.client.get(f"{BASE}/meter-readings", **self.auth)
        self.assertEqual(listing.json()["meta"]["total"], 0)
        detail = self.client.get(f"{BASE}/meter-points/{point['id']}/summary", **self.auth)
        self.assertEqual(detail.status_code, 404, detail.content)


class MeterDrivenPmTests(MeterApiBase):
    """The end-to-end proof that an 'every N running hours' plan now fires."""

    def createMeterPlan(self, deviceId: str, **overrides) -> dict:
        payload = {
            "title": "تعویض روغن هر ۵۰۰ ساعت",
            "discipline": "mechanical",
            "frequencyEvery": 500,
            "frequencyUnit": "runningHour",
            "metricType": "RUNNING_HOURS",
            "metricUnit": "ساعت",
            "warningValue": "50",
        }
        payload.update(overrides)
        response = self.client.post(
            f"{BASE}/devices/{deviceId}/pm-plans", payload, format="json", **self.auth
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def testCreatingAPmPlanWorksAtAll(self) -> None:
        """Regression: migration 0012 made every PM plan POST return 500."""
        device = self.createDevice()
        response = self.client.post(
            f"{BASE}/devices/{device['id']}/pm-plans",
            {"title": "بازدید ماهانه", "discipline": "mechanical"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["data"]["triggerType"], "calendar")

    def testRunningHourPlanIsStoredAsAMeterTrigger(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        plan = self.createMeterPlan(device["id"])
        self.assertEqual(plan["triggerType"], "meter")
        self.assertEqual(Decimal(plan["metricInterval"]), Decimal("500"))

    def testMeterPlanBecomesDueWhenTheHoursArrive(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        plan = self.createMeterPlan(device["id"])

        # Baseline: the first reading adopts the plan's starting point so the
        # plan is not born overdue on a machine with existing hours.
        self.recordManual(device["id"], "8000", capturedAt=self.now.isoformat())
        status = self.client.get(f"{BASE}/meter-pm-status", **self.auth).json()["data"]
        self.assertEqual(status[0]["status"], "ok")
        self.assertEqual(status[0]["dueAtValue"], "8500.0000")

        # Approaching the interval raises a warning.
        self.recordManual(
            device["id"], "8460", capturedAt=(self.now + timedelta(hours=1)).isoformat()
        )
        status = self.client.get(f"{BASE}/meter-pm-status", **self.auth).json()["data"]
        self.assertEqual(status[0]["status"], "warning")

        # Crossing it makes the plan due.
        self.recordManual(
            device["id"], "8505", capturedAt=(self.now + timedelta(hours=2)).isoformat()
        )
        status = self.client.get(f"{BASE}/meter-pm-status", **self.auth).json()["data"]
        self.assertEqual(status[0]["status"], "due")
        self.assertEqual(status[0]["planId"], plan["id"])

        listed = self.client.get(f"{BASE}/devices/{device['id']}/pm-plans", **self.auth).json()[
            "data"
        ]
        self.assertTrue(listed[0]["overdue"], "a due meter plan must report as overdue")

    def testExecutingAMeterPlanStartsANewCycle(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        plan = self.createMeterPlan(device["id"])
        self.recordManual(device["id"], "8000", capturedAt=self.now.isoformat())
        self.recordManual(
            device["id"], "8505", capturedAt=(self.now + timedelta(hours=1)).isoformat()
        )

        executed = self.client.post(
            f"{BASE}/pm-plans/{plan['id']}/executions",
            {"performedByName": "رضا", "durationMinutes": 45},
            format="json",
            **self.auth,
        )
        self.assertEqual(executed.status_code, 201, executed.content)
        self.assertEqual(Decimal(executed.json()["data"]["meterValue"]), Decimal("8505"))

        status = self.client.get(f"{BASE}/meter-pm-status", **self.auth).json()["data"]
        self.assertEqual(status[0]["status"], "ok")
        self.assertEqual(
            status[0]["dueAtValue"], "9005.0000", "the next cycle counts from the execution"
        )

    def testConditionTriggerFiresOnAThreshold(self) -> None:
        device = self.createDevice()
        self.createPoint(
            device["id"],
            code="VIBRATION",
            kind="gauge",
            sensorKey="Line1/Pump01.Vib",
            drivesRunningHours=False,
        )
        self.createMeterPlan(
            device["id"],
            title="بازرسی ارتعاش",
            frequencyUnit="month",
            triggerType="condition",
            metricType="VIBRATION",
            thresholdOperator=">=",
            thresholdValue="7.1",
            warningValue="4.5",
            metricUnit="mm/s",
        )
        self.ingest(
            [
                {
                    "sensorKey": "Line1/Pump01.Vib",
                    "value": "7.4",
                    "capturedAt": self.now.isoformat(),
                    "ingestionKey": "v1",
                }
            ]
        )
        status = self.client.get(f"{BASE}/meter-pm-status?status=due", **self.auth).json()["data"]
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0]["metricType"], "VIBRATION")

    def testMeterPlanWithoutAMeterIsRejected(self) -> None:
        device = self.createDevice()
        response = self.client.post(
            f"{BASE}/devices/{device['id']}/pm-plans",
            {
                "title": "بدون کنتور",
                "discipline": "mechanical",
                "triggerType": "meter",
                "metricInterval": "500",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422, response.content)

    def testDatabaseRefusesAMeterPlanWithNoInterval(self) -> None:
        """The constraint holds even if the application layer is bypassed."""
        device = self.createDevice()
        with self.assertRaises(IntegrityError), transaction.atomic():
            PmPlanModel.objects.create(
                tenantId=self.tenantId,
                deviceId=uuid.UUID(device["id"]),
                title="bypass",
                discipline="mechanical",
                triggerType="meter",
                metricType="RUNNING_HOURS",
                metricInterval=Decimal("0"),
                createdAt=datetime.now(tz=UTC),
            )


class DerivedRunningHoursTests(MeterApiBase):
    """Bug 3: the nameplate form must stop competing with the meter."""

    def nameplate(self, deviceId: str, **values):  # noqa: ANN201
        payload = {"manufacturer": "ABB", "serialNumber": "SN-1"}
        payload.update(values)
        return self.client.patch(
            f"{BASE}/devices/{deviceId}/nameplate", payload, format="json", **self.auth
        )

    def testNameplateStillAcceptsHoursWhileNoMeterExists(self) -> None:
        device = self.createDevice()
        response = self.nameplate(device["id"], runningHours="1200")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(DeviceModel.objects.get(id=device["id"]).runningHours, Decimal("1200.00"))
        self.assertFalse(response.json()["data"]["runningHoursDerived"])

    def testNameplateCannotOverwriteMeterDrivenHours(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        self.recordManual(device["id"], "8400", capturedAt=self.now.isoformat())

        response = self.nameplate(device["id"], runningHours="5")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            DeviceModel.objects.get(id=device["id"]).runningHours,
            Decimal("8400.00"),
            "a typed number must not overwrite a dated, attributed reading",
        )

    def testOtherNameplateFieldsStillSaveAlongside(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        self.recordManual(device["id"], "8400", capturedAt=self.now.isoformat())
        response = self.nameplate(
            device["id"], runningHours="5", purchaseCost="250000", manufacturer="Siemens"
        )
        self.assertEqual(response.status_code, 200, response.content)
        row = DeviceModel.objects.get(id=device["id"])
        self.assertEqual(row.manufacturer, "Siemens")
        self.assertEqual(row.purchaseCost, Decimal("250000.00"))
        self.assertEqual(row.runningHours, Decimal("8400.00"))

    def testNameplateReportsThatHoursAreDerived(self) -> None:
        device = self.createDevice()
        self.createPoint(device["id"])
        profile = self.client.get(f"{BASE}/devices/{device['id']}/profile", **self.auth)
        self.assertTrue(profile.json()["data"]["nameplate"]["runningHoursDerived"])


class RepositoryPortConformanceTests(TestCase):
    """The Django repositories must satisfy the domain-owned contracts."""

    def testImplementationsSatisfyTheirPorts(self) -> None:
        from apps.maintenance.domain.repositories.maintenanceRepositories import (
            MeterPointRepository,
            MeterReadingRepository,
        )
        from apps.maintenance.infrastructure.repositories.meterReadingRepositoryImpl import (
            MeterPointRepositoryDjango,
            MeterReadingRepositoryDjango,
        )

        self.assertIsInstance(MeterPointRepositoryDjango(), MeterPointRepository)
        self.assertIsInstance(MeterReadingRepositoryDjango(), MeterReadingRepository)
