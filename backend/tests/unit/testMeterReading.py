"""Unit tests for the meter-reading domain rules.

These run without a database: every rule that decides whether a number is
trustworthy lives in pure Python precisely so it can be tested this way.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.test import SimpleTestCase

from apps.maintenance.domain.entities.assetRegistry import PmPlan
from apps.maintenance.domain.entities.meterReading import MeterPoint, MeterReading
from apps.maintenance.domain.services.meterReadingRules import (
    assessReading,
    assessStep,
    computeDelta,
    evaluateConditionTrigger,
    evaluateMeterTrigger,
    validateAgainstPoint,
    validateReadingTime,
    worstQuality,
)
from apps.maintenance.domain.valueObjects.maintenanceState import PmFrequency
from apps.maintenance.domain.valueObjects.meterTypes import (
    CAPTURE_MANUAL,
    CAPTURE_SENSOR,
    METER_CUMULATIVE,
    METER_GAUGE,
    QUALITY_BAD,
    QUALITY_GOOD,
    QUALITY_SUSPECT,
    MeterValue,
    normalizeMeterCode,
    normalizeSensorKey,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def buildPoint(**overrides) -> MeterPoint:
    defaults = dict(
        id=uuid.uuid4(),
        tenantId=uuid.uuid4(),
        deviceId=uuid.uuid4(),
        code="RUNNING_HOURS",
        name="ساعت کارکرد",
        unit="ساعت",
        kind=METER_CUMULATIVE,
    )
    defaults.update(overrides)
    return MeterPoint(**defaults)


def buildReading(point: MeterPoint, value: str, capturedAt: datetime, **overrides) -> MeterReading:
    defaults = dict(
        id=uuid.uuid4(),
        tenantId=point.tenantId,
        deviceId=point.deviceId,
        meterPointId=point.id,
        value=Decimal(value),
        capturedAt=capturedAt,
    )
    defaults.update(overrides)
    return MeterReading(**defaults)


class MeterValueTests(SimpleTestCase):
    def testParsesDecimalStringWithoutFloatRounding(self) -> None:
        self.assertEqual(MeterValue.parse("124578901.2345").amount, Decimal("124578901.2345"))

    def testQuantisesToFourDecimals(self) -> None:
        self.assertEqual(MeterValue.parse("1.000049").amount, Decimal("1.0000"))

    def testRejectsNaNAndInfinity(self) -> None:
        for bad in ("NaN", "Infinity", "-inf"):
            with self.subTest(value=bad), self.assertRaises(ValidationFailedError):
                MeterValue.parse(bad)

    def testRejectsNonNumericText(self) -> None:
        with self.assertRaises(ValidationFailedError):
            MeterValue.parse("هشتاد")

    def testRejectsValueBeyondColumnCapacity(self) -> None:
        with self.assertRaises(ValidationFailedError):
            MeterValue.parse("9" * 20)


class CodeNormalisationTests(SimpleTestCase):
    def testMeterCodeIsUppercased(self) -> None:
        self.assertEqual(normalizeMeterCode(" pump.hours "), "PUMP.HOURS")

    def testMeterCodeRejectsSpaces(self) -> None:
        with self.assertRaises(ValidationFailedError):
            normalizeMeterCode("pump hours")

    def testSensorKeyKeepsCaseButTrims(self) -> None:
        self.assertEqual(normalizeSensorKey("  Plant/Line1/Pump01.Hours "), "Plant/Line1/Pump01.Hours")

    def testSensorKeyRejectsControlCharacters(self) -> None:
        with self.assertRaises(ValidationFailedError):
            normalizeSensorKey("tag\nbroken")


class DeltaTests(SimpleTestCase):
    def testFirstReadingHasUnknownDeltaNotZero(self) -> None:
        """Zero would claim the machine ran for no hours before we watched."""
        outcome = computeDelta(buildPoint(), Decimal("8400"), None)
        self.assertIsNone(outcome.delta)
        self.assertEqual(outcome.reason, "firstReading")

    def testGrowingCounterYieldsPlainDifference(self) -> None:
        point = buildPoint()
        previous = buildReading(point, "8400", NOW - timedelta(hours=10))
        outcome = computeDelta(point, Decimal("8410.5"), previous)
        self.assertEqual(outcome.delta, Decimal("10.5000"))
        self.assertFalse(outcome.rolloverApplied)

    def testGaugeNeverCarriesADelta(self) -> None:
        point = buildPoint(kind=METER_GAUGE, code="BEARING_TEMP")
        previous = buildReading(point, "70", NOW - timedelta(hours=1))
        self.assertIsNone(computeDelta(point, Decimal("64"), previous).delta)

    def testCounterRolloverIsReconstructed(self) -> None:
        """A 6-digit hour meter wrapping 999950 -> 40 consumed 90 hours."""
        point = buildPoint(rolloverMaximum=Decimal("999999"))
        previous = buildReading(point, "999950", NOW - timedelta(hours=90))
        outcome = computeDelta(point, Decimal("41"), previous)
        self.assertTrue(outcome.rolloverApplied)
        self.assertEqual(outcome.delta, Decimal("90.0000"))

    def testSmallBackwardsStepIsATypoNotARollover(self) -> None:
        """8400 -> 840 is a dropped digit, not a wrap of a 999999 counter."""
        point = buildPoint(rolloverMaximum=Decimal("999999"))
        previous = buildReading(point, "8400", NOW - timedelta(hours=1))
        outcome = computeDelta(point, Decimal("840"), previous)
        self.assertFalse(outcome.rolloverApplied)
        self.assertIsNone(outcome.delta)
        self.assertEqual(outcome.quality, QUALITY_SUSPECT)
        self.assertTrue(outcome.isRegression)

    def testBackwardsStepWithoutDeclaredCapacityIsSuspect(self) -> None:
        point = buildPoint()
        previous = buildReading(point, "8400", NOW - timedelta(hours=1))
        outcome = computeDelta(point, Decimal("10"), previous)
        self.assertEqual(outcome.quality, QUALITY_SUSPECT)
        self.assertIsNone(outcome.delta)


class StepGuardTests(SimpleTestCase):
    def testImpossibleAccumulationRateIsFlagged(self) -> None:
        """A pump cannot accumulate 90 running hours in one hour."""
        point = buildPoint(maximumStepPerHour=Decimal("1.2"))
        previous = buildReading(point, "8400", NOW - timedelta(hours=1))
        quality, reason = assessStep(point, Decimal("90"), NOW, previous)
        self.assertEqual(quality, QUALITY_SUSPECT)
        self.assertEqual(reason, "stepTooLarge")

    def testPlausibleRateIsAccepted(self) -> None:
        point = buildPoint(maximumStepPerHour=Decimal("1.2"))
        previous = buildReading(point, "8400", NOW - timedelta(hours=10))
        quality, _ = assessStep(point, Decimal("9.5"), NOW, previous)
        self.assertEqual(quality, QUALITY_GOOD)

    def testNoGuardConfiguredMeansNoJudgement(self) -> None:
        point = buildPoint()
        previous = buildReading(point, "8400", NOW - timedelta(hours=1))
        quality, _ = assessStep(point, Decimal("5000"), NOW, previous)
        self.assertEqual(quality, QUALITY_GOOD)


class BoundsTests(SimpleTestCase):
    def testReadingBelowMinimumIsRejected(self) -> None:
        point = buildPoint(minimumValue=Decimal("0"))
        with self.assertRaises(ValidationFailedError):
            validateAgainstPoint(point, Decimal("-1"))

    def testReadingAboveMaximumIsRejected(self) -> None:
        point = buildPoint(kind=METER_GAUGE, maximumValue=Decimal("250"))
        with self.assertRaises(ValidationFailedError):
            validateAgainstPoint(point, Decimal("251"))

    def testInactivePointRefusesReadings(self) -> None:
        with self.assertRaises(ValidationFailedError):
            validateAgainstPoint(buildPoint(active=False), Decimal("1"))

    def testReadingAboveCounterCapacityIsRejected(self) -> None:
        point = buildPoint(rolloverMaximum=Decimal("999999"))
        with self.assertRaises(ValidationFailedError):
            validateAgainstPoint(point, Decimal("1000000"))

    def testFutureTimestampIsRejectedBeyondSkew(self) -> None:
        with self.assertRaises(ValidationFailedError):
            validateReadingTime(NOW + timedelta(hours=1), NOW)

    def testSmallClockSkewIsTolerated(self) -> None:
        validateReadingTime(NOW + timedelta(minutes=2), NOW)


class QualityTests(SimpleTestCase):
    def testWorstQualityWins(self) -> None:
        self.assertEqual(worstQuality(QUALITY_GOOD, QUALITY_SUSPECT), QUALITY_SUSPECT)
        self.assertEqual(worstQuality(QUALITY_SUSPECT, QUALITY_BAD), QUALITY_BAD)
        self.assertEqual(worstQuality(QUALITY_GOOD, "", QUALITY_GOOD), QUALITY_GOOD)

    def testCallerCannotLaunderASuspectReadingIntoAGoodOne(self) -> None:
        point = buildPoint(rolloverMaximum=Decimal("999999"))
        previous = buildReading(point, "8400", NOW - timedelta(hours=1))
        assessment = assessReading(
            point, Decimal("840"), NOW, previous, NOW, requestedQuality=QUALITY_GOOD
        )
        self.assertEqual(assessment.quality, QUALITY_SUSPECT)

    def testBadReadingCarriesNoConsumption(self) -> None:
        point = buildPoint()
        previous = buildReading(point, "8400", NOW - timedelta(hours=1))
        assessment = assessReading(
            point, Decimal("8410"), NOW, previous, NOW, requestedQuality=QUALITY_BAD
        )
        self.assertEqual(assessment.quality, QUALITY_BAD)
        self.assertIsNone(assessment.delta)


class ReadingEntityTests(SimpleTestCase):
    def testProvenanceDistinguishesManualFromSensor(self) -> None:
        point = buildPoint()
        manual = buildReading(
            point, "10", NOW, captureMode=CAPTURE_MANUAL, recordedByName="رضا"
        )
        sensor = buildReading(
            point, "10", NOW, captureMode=CAPTURE_SENSOR, sensorKey="Line1/Pump01.Hours"
        )
        self.assertEqual(manual.provenance(), "manual:رضا")
        self.assertEqual(sensor.provenance(), "sensor:Line1/Pump01.Hours")

    def testSupersededReadingIsNotTrusted(self) -> None:
        point = buildPoint()
        reading = buildReading(point, "10", NOW, supersededByReadingId=uuid.uuid4())
        self.assertTrue(reading.isSuperseded)
        self.assertFalse(reading.isTrusted)


# =====================================================================================
# PM triggers — the bug this feature exists to fix
# =====================================================================================
class MeterTriggerTests(SimpleTestCase):
    def testPlanIsDueOnceTheIntervalIsConsumed(self) -> None:
        evaluation = evaluateMeterTrigger(
            interval=Decimal("500"), baseline=Decimal("8000"), currentValue=Decimal("8500")
        )
        self.assertTrue(evaluation.isDue)
        self.assertEqual(evaluation.dueAtValue, Decimal("8500.0000"))

    def testPlanWarnsBeforeItTrips(self) -> None:
        evaluation = evaluateMeterTrigger(
            interval=Decimal("500"),
            baseline=Decimal("8000"),
            currentValue=Decimal("8460"),
            warningLead=Decimal("50"),
        )
        self.assertTrue(evaluation.isWarning)
        self.assertEqual(evaluation.remaining, Decimal("40.0000"))

    def testPlanWithNoReadingsIsUnknownNotDue(self) -> None:
        evaluation = evaluateMeterTrigger(
            interval=Decimal("500"), baseline=Decimal("8000"), currentValue=None
        )
        self.assertFalse(evaluation.isDue)
        self.assertEqual(evaluation.reason, "noReadings")

    def testPlanWithNoBaselineIsNotBornOverdue(self) -> None:
        """A plan attached to a pump with 40 000 hours must not be 80 cycles late."""
        evaluation = evaluateMeterTrigger(
            interval=Decimal("500"), baseline=None, currentValue=Decimal("40000")
        )
        self.assertFalse(evaluation.isDue)
        self.assertEqual(evaluation.reason, "noBaseline")


class ConditionTriggerTests(SimpleTestCase):
    def testRisingThresholdTrips(self) -> None:
        evaluation = evaluateConditionTrigger(
            operator=">=",
            thresholdValue=Decimal("7.1"),
            warningValue=Decimal("4.5"),
            currentValue=Decimal("7.4"),
        )
        self.assertTrue(evaluation.isDue)

    def testFallingThresholdWarnsBeforeTripping(self) -> None:
        """A '<=' trigger must warn above the limit, not below it."""
        evaluation = evaluateConditionTrigger(
            operator="<=",
            thresholdValue=Decimal("2.0"),
            warningValue=Decimal("3.0"),
            currentValue=Decimal("2.5"),
        )
        self.assertTrue(evaluation.isWarning)

    def testBelowWarningIsOk(self) -> None:
        evaluation = evaluateConditionTrigger(
            operator=">=",
            thresholdValue=Decimal("7.1"),
            warningValue=Decimal("4.5"),
            currentValue=Decimal("2.0"),
        )
        self.assertEqual(evaluation.status, "ok")


class PmPlanMeterTests(SimpleTestCase):
    """The regression tests for the inert-plan bug."""

    def buildPlan(self, **overrides) -> PmPlan:
        defaults = dict(
            id=uuid.uuid4(),
            tenantId=uuid.uuid4(),
            deviceId=uuid.uuid4(),
            title="تعویض روغن هر ۵۰۰ ساعت",
            discipline="mechanical",
            frequencyEvery=500,
            frequencyUnit="runningHour",
            triggerType="meter",
            metricType="RUNNING_HOURS",
            metricInterval=Decimal("500"),
            lastExecutedMeterValue=Decimal("8000"),
        )
        defaults.update(overrides)
        return PmPlan(**defaults)

    def testMeterPlanBecomesOverdue(self) -> None:
        """Before this feature, isOverdue() answered False forever here."""
        plan = self.buildPlan(lastMetricValue=Decimal("8600"))
        self.assertTrue(plan.isMeterOverdue())
        self.assertTrue(plan.isOverdue(NOW.date()))

    def testMeterPlanIsNotOverdueBeforeTheInterval(self) -> None:
        plan = self.buildPlan(lastMetricValue=Decimal("8100"))
        self.assertFalse(plan.isOverdue(NOW.date()))

    def testMeterPlanHasNoCalendarPeriod(self) -> None:
        self.assertIsNone(self.buildPlan().periodDays())
        self.assertIsNone(self.buildPlan().nextDueOn())

    def testInactiveMeterPlanNeverFires(self) -> None:
        plan = self.buildPlan(lastMetricValue=Decimal("99999"), active=False)
        self.assertFalse(plan.isOverdue(NOW.date()))

    def testCalendarPlanStillUsesDates(self) -> None:
        import datetime as dt

        plan = PmPlan(
            id=uuid.uuid4(),
            tenantId=uuid.uuid4(),
            deviceId=uuid.uuid4(),
            title="بازدید ماهانه",
            discipline="general",
            frequencyEvery=1,
            frequencyUnit="month",
            lastExecutedOn=dt.date(2026, 1, 1),
        )
        self.assertEqual(plan.periodDays(), 30)
        self.assertEqual(plan.nextDueOn(), dt.date(2026, 1, 31))
        self.assertTrue(plan.isOverdue(dt.date(2026, 3, 1)))

    def testCurrentValueArgumentOverridesTheCachedOne(self) -> None:
        plan = self.buildPlan(lastMetricValue=Decimal("8100"))
        self.assertTrue(plan.isOverdue(NOW.date(), Decimal("8900")))


class PmFrequencyTests(SimpleTestCase):
    def testRunningHourFrequencyIsMeterBased(self) -> None:
        frequency = PmFrequency(every=500, unit="runningHour")
        self.assertTrue(frequency.isMeterBased)
        self.assertIsNone(frequency.asDays())
        self.assertEqual(frequency.asMeterUnits(), 500)

    def testCalendarFrequencyIsNotMeterBased(self) -> None:
        frequency = PmFrequency(every=3, unit="month")
        self.assertFalse(frequency.isMeterBased)
        self.assertEqual(frequency.asDays(), 90)
        self.assertIsNone(frequency.asMeterUnits())
