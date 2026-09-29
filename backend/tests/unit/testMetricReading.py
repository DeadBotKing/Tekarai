"""Unit coverage for the framework-free MetricReading domain."""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.test import SimpleTestCase

from apps.analytics.domain.entities.metricDefinition import MetricDefinition
from apps.analytics.domain.entities.metricReading import MetricReading
from apps.analytics.domain.valueObjects.metricTypes import MetricCode, normalizeDimensions
from apps.sharedKernel.domain.errors import ValidationFailedError


class MetricReadingDomainTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.metricId = uuid.uuid4()
        self.now = datetime(2026, 9, 29, 10, 30, tzinfo=UTC)

    def reading(self, **overrides) -> MetricReading:
        values = {
            "tenantId": self.tenantId,
            "metricId": self.metricId,
            "value": "12.3456",
            "periodStart": self.now - timedelta(minutes=1),
            "periodEnd": self.now,
            "dimensions": {"deviceId": "pump-1", "line": 2},
            "quality": "good",
            "sourceType": "device",
            "sourceId": "pump-1",
            "ingestionKey": "gateway-7:100",
            "recordedAt": self.now,
            "recordedById": uuid.uuid4(),
            "correlationId": "corr-1",
        }
        values.update(overrides)
        return MetricReading.record(**values)

    def testNormalizesACompleteReadingAndBuildsEvent(self) -> None:
        reading = self.reading()
        self.assertEqual(reading.value, Decimal("12.345600"))
        self.assertEqual(reading.quality, "GOOD")
        self.assertEqual(list(reading.dimensions), ["deviceId", "line"])
        event = reading.recordedEvent()
        self.assertEqual(event.name, "metricReadingRecorded")
        self.assertEqual(event.payload["readingId"], str(reading.id))

    def testReadingAndItsDimensionsAreImmutable(self) -> None:
        reading = self.reading()
        with self.assertRaises(FrozenInstanceError):
            reading.value = Decimal("99")  # type: ignore[misc]
        with self.assertRaises(TypeError):
            reading.dimensions["deviceId"] = "other"  # type: ignore[index]

    def testRejectsInvalidPeriodAndNonFiniteOrOverPreciseValues(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.reading(periodEnd=self.now - timedelta(minutes=2))
        with self.assertRaises(ValidationFailedError):
            self.reading(value="NaN")
        with self.assertRaises(ValidationFailedError):
            self.reading(value="1.0000001")

    def testSourceFieldsAreAnAtomicPair(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.reading(sourceId="")
        with self.assertRaises(ValidationFailedError):
            self.reading(sourceType="")

    def testIdempotencyComparisonIgnoresIngestionMetadata(self) -> None:
        first = self.reading()
        second = self.reading(recordedAt=self.now + timedelta(seconds=1))
        self.assertTrue(first.sameObservationAs(second))
        self.assertFalse(first.sameObservationAs(self.reading(value="13")))

    def testDimensionsAreBoundedFlatAndRejectSensitiveKeys(self) -> None:
        self.assertEqual(normalizeDimensions({"asset.kind": "pump"}), {"asset.kind": "pump"})
        with self.assertRaises(ValidationFailedError):
            normalizeDimensions({"authToken": "secret"})
        with self.assertRaises(ValidationFailedError):
            normalizeDimensions({"device": {"id": "nested"}})
        with self.assertRaises(ValidationFailedError):
            normalizeDimensions({f"k{index}": index for index in range(33)})


class MetricDefinitionDomainTests(SimpleTestCase):
    def testDefinitionNormalizesCodeAndEnforcesReadingRange(self) -> None:
        definition = MetricDefinition.create(
            tenantId=uuid.uuid4(),
            code=MetricCode("energy.kwh"),
            name="Energy",
            description="",
            formula="",
            unit="kWh",
            aggregation="sum",
            minimumValue=Decimal("0"),
            maximumValue=Decimal("1000"),
            now=datetime(2026, 9, 29, tzinfo=UTC),
        )
        self.assertEqual(str(definition.code), "ENERGY.KWH")
        self.assertEqual(definition.aggregation, "SUM")
        definition.validateReadingValue(Decimal("999"))
        with self.assertRaises(ValidationFailedError):
            definition.validateReadingValue(Decimal("1001"))

    def testDefinitionRejectsInvertedRange(self) -> None:
        with self.assertRaises(ValidationFailedError):
            MetricDefinition.create(
                tenantId=uuid.uuid4(),
                code=MetricCode("TEMP"),
                name="Temperature",
                description="",
                formula="",
                unit="C",
                aggregation="AVERAGE",
                minimumValue=Decimal("100"),
                maximumValue=Decimal("0"),
                now=datetime(2026, 9, 29, tzinfo=UTC),
            )
