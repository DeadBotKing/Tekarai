"""End-to-end REST and persistence contract for MetricReading."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.analytics.domain.exceptions.metricErrors import MetricReadingImmutableError
from apps.analytics.infrastructure.models import MetricDefinitionModel, MetricReadingModel
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform

BASE = "/api/v1/analytics"


class MetricReadingApiTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        self.now = datetime.now(tz=UTC).replace(microsecond=0) - timedelta(minutes=10)

    def createDefinition(self, code: str = "DEVICE.TEMPERATURE") -> dict:
        response = self.client.post(
            f"{BASE}/metric-definitions",
            {
                "code": code,
                "name": "دمای تجهیز",
                "description": "دمای یاتاقان پمپ",
                "unit": "°C",
                "aggregation": "AVERAGE",
                "minimumValue": "-50",
                "maximumValue": "250",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def readingPayload(self, **overrides) -> dict:
        payload = {
            "metricCode": "DEVICE.TEMPERATURE",
            "value": "72.125",
            "occurredAt": self.now.isoformat(),
            "dimensions": {"deviceId": "PUMP-01", "location": "LINE-A"},
            "quality": "good",
            "sourceType": "device",
            "sourceId": "PUMP-01",
            "ingestionKey": "gateway-1:sequence-100",
        }
        payload.update(overrides)
        return payload

    def testAuthenticationIsMandatory(self) -> None:
        anonymous = APIClient()
        self.assertEqual(
            anonymous.get(f"{BASE}/metric-readings").status_code,
            401,
        )
        self.assertEqual(
            anonymous.post(f"{BASE}/metric-readings", {}, format="json").status_code,
            401,
        )

    def testDefinitionAndReadingFullLifecycle(self) -> None:
        definition = self.createDefinition()
        created = self.client.post(
            f"{BASE}/metric-readings",
            self.readingPayload(),
            format="json",
            **self.auth,
        )
        self.assertEqual(created.status_code, 201, created.content)
        reading = created.json()["data"]
        self.assertEqual(reading["metricId"], definition["id"])
        self.assertEqual(reading["metricCode"], "DEVICE.TEMPERATURE")
        self.assertEqual(reading["value"], "72.125000")
        self.assertEqual(reading["quality"], "GOOD")
        self.assertFalse(reading["replayed"])

        detail = self.client.get(f"{BASE}/metric-readings/{reading['id']}", **self.auth)
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["data"]["dimensions"]["deviceId"], "PUMP-01")

        listed = self.client.get(
            f"{BASE}/metric-readings?metricCode=DEVICE.TEMPERATURE&quality=good",
            **self.auth,
        )
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(len(listed.json()["data"]), 1)
        self.assertEqual(listed.json()["meta"]["pagination"]["totalCount"], 1)

    def testDurableIdempotencyReplaysAndRejectsKeyReuse(self) -> None:
        self.createDefinition()
        first = self.client.post(
            f"{BASE}/metric-readings",
            self.readingPayload(),
            format="json",
            **self.auth,
        )
        replay = self.client.post(
            f"{BASE}/metric-readings",
            self.readingPayload(),
            format="json",
            **self.auth,
        )
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(first.json()["data"]["id"], replay.json()["data"]["id"])
        self.assertTrue(replay.json()["data"]["replayed"])
        self.assertEqual(MetricReadingModel.objects.count(), 1)

        conflict = self.client.post(
            f"{BASE}/metric-readings",
            self.readingPayload(value="73"),
            format="json",
            **self.auth,
        )
        self.assertEqual(conflict.status_code, 409, conflict.content)
        self.assertEqual(
            conflict.json()["errors"][0]["code"],
            "ANALYTICS_INGESTION_CONFLICT",
        )
        self.assertEqual(MetricReadingModel.objects.count(), 1)

    def testAtomicBatchAndSummary(self) -> None:
        self.createDefinition()
        payloads = [
            self.readingPayload(
                value=value,
                occurredAt=(self.now + timedelta(minutes=index)).isoformat(),
                ingestionKey=f"batch:{index}",
            )
            for index, value in enumerate(("10", "20", "30"))
        ]
        response = self.client.post(
            f"{BASE}/metric-readings/batch",
            {"readings": payloads},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["meta"]["createdCount"], 3)

        summary = self.client.get(
            f"{BASE}/metric-readings/summary?metricCode=DEVICE.TEMPERATURE",
            **self.auth,
        )
        self.assertEqual(summary.status_code, 200, summary.content)
        data = summary.json()["data"]
        self.assertEqual(data["count"], 3)
        self.assertEqual(Decimal(data["minimum"]), Decimal("10"))
        self.assertEqual(Decimal(data["maximum"]), Decimal("30"))
        self.assertEqual(Decimal(data["average"]), Decimal("20"))
        self.assertEqual(Decimal(data["total"]), Decimal("60"))
        self.assertEqual(data["first"]["value"], "10.000000")
        self.assertEqual(data["last"]["value"], "30.000000")

    def testInvalidBatchRollsBackEveryReading(self) -> None:
        self.createDefinition()
        valid = self.readingPayload(ingestionKey="atomic:1")
        invalid = self.readingPayload(
            ingestionKey="atomic:2",
            dimensions={"apiToken": "must-not-be-stored"},
        )
        response = self.client.post(
            f"{BASE}/metric-readings/batch",
            {"readings": [valid, invalid]},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(MetricReadingModel.objects.count(), 0)

    def testDefinitionBoundsAndInactiveStateAreEnforced(self) -> None:
        definition = self.createDefinition()
        outOfRange = self.client.post(
            f"{BASE}/metric-readings",
            self.readingPayload(value="251"),
            format="json",
            **self.auth,
        )
        self.assertEqual(outOfRange.status_code, 422, outOfRange.content)

        disabled = self.client.patch(
            f"{BASE}/metric-definitions/{definition['id']}",
            {"isActive": False},
            format="json",
            **self.auth,
        )
        self.assertEqual(disabled.status_code, 200, disabled.content)
        inactive = self.client.post(
            f"{BASE}/metric-readings",
            self.readingPayload(ingestionKey="inactive:1"),
            format="json",
            **self.auth,
        )
        self.assertEqual(inactive.status_code, 422, inactive.content)

    def testDuplicateMetricCodeIsRejectedPerTenant(self) -> None:
        self.createDefinition()
        duplicate = self.client.post(
            f"{BASE}/metric-definitions",
            {"code": "device.temperature", "name": "Duplicate"},
            format="json",
            **self.auth,
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.content)

    def testReadingsAreAppendOnlyAtApiAndModelBoundaries(self) -> None:
        self.createDefinition()
        response = self.client.post(
            f"{BASE}/metric-readings",
            self.readingPayload(),
            format="json",
            **self.auth,
        )
        readingId = response.json()["data"]["id"]
        self.assertEqual(
            self.client.patch(
                f"{BASE}/metric-readings/{readingId}",
                {"value": "1"},
                format="json",
                **self.auth,
            ).status_code,
            405,
        )
        self.assertEqual(
            self.client.delete(f"{BASE}/metric-readings/{readingId}", **self.auth).status_code,
            405,
        )
        model = MetricReadingModel.objects.get(id=readingId)
        model.value = Decimal("1")
        with self.assertRaises(MetricReadingImmutableError):
            model.save()
        with self.assertRaises(MetricReadingImmutableError):
            model.delete()
        with self.assertRaises(MetricReadingImmutableError):
            MetricReadingModel.objects.filter(id=readingId).update(value=Decimal("2"))
        with self.assertRaises(MetricReadingImmutableError):
            MetricReadingModel.objects.filter(id=readingId).delete()

    def testTenantIsolationHidesForeignReading(self) -> None:
        definition = self.createDefinition()
        ownDefinition = MetricDefinitionModel.objects.get(id=definition["id"])
        otherTenantId = uuid.uuid4()
        foreignDefinition = MetricDefinitionModel.objects.create(
            tenantId=otherTenantId,
            code="DEVICE.TEMPERATURE",
            name="Foreign",
            unit="°C",
        )
        foreign = MetricReadingModel.objects.create(
            tenantId=otherTenantId,
            metric=foreignDefinition,
            value=Decimal("20"),
            dimensions={},
            periodStart=self.now,
            periodEnd=self.now,
        )
        self.assertNotEqual(ownDefinition.tenantId, foreignDefinition.tenantId)
        hidden = self.client.get(f"{BASE}/metric-readings/{foreign.id}", **self.auth)
        self.assertEqual(hidden.status_code, 404, hidden.content)
        listed = self.client.get(f"{BASE}/metric-readings", **self.auth)
        self.assertEqual(listed.json()["data"], [])
