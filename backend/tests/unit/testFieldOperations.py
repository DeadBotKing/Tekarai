"""Unit tests for field operations: timer arithmetic, scan parsing, sync verdicts.

No database. Every rule that decides *how long someone worked*, *what a
scanned label means* and *whether a replayed operation should be retried*
lives in pure Python so it can be tested at this speed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.test import SimpleTestCase

from apps.maintenance.application.useCases.offlineSyncUseCases import classifyFailure
from apps.maintenance.application.useCases.workTimerUseCases import (
    parseMoment,
    parseRate,
)
from apps.maintenance.domain.entities.workTimer import (
    MAX_SPAN_HOURS,
    MINIMUM_BILLABLE_HOURS,
    WorkTimer,
    quantiseHours,
)
from apps.maintenance.domain.exceptions.fieldOpsErrors import (
    TimerAlreadyRunningError,
    TimerNotRunningError,
    TimerSpanInvalidError,
)
from apps.maintenance.domain.services.scanCodeRules import parseScan
from apps.maintenance.domain.valueObjects.fieldOpsTypes import (
    SCAN_TARGET_DEVICE,
    SCAN_TARGET_LOCATION,
    SCAN_TARGET_SPARE_PART,
    SCAN_TARGET_WORK_ORDER,
    SYNC_STATUS_DUPLICATE,
    SYNC_STATUS_FAILED,
    SYNC_STATUS_REJECTED,
    ScanTarget,
)
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
TENANT = uuid.uuid4()
ORDER = uuid.uuid4()


def buildTimer(**overrides) -> WorkTimer:
    payload = {
        "tenantId": TENANT,
        "workOrderId": ORDER,
        "technicianName": "حسینی",
        "startedAt": NOW,
        "now": NOW,
    }
    payload.update(overrides)
    return WorkTimer.start(**payload)


# =====================================================================================
# Timer arithmetic
# =====================================================================================
class TimerDurationTests(SimpleTestCase):
    def testQuantisesToHundredthsOfAnHour(self) -> None:
        self.assertEqual(quantiseHours(3600), Decimal("1.00"))
        self.assertEqual(quantiseHours(1800), Decimal("0.50"))
        # 36 seconds is exactly one quantum.
        self.assertEqual(quantiseHours(36), Decimal("0.01"))

    def testRoundsHalfUpSoAMinuteIsNotLost(self) -> None:
        # 90 seconds = 0.025 h → 0.03, not 0.02.
        self.assertEqual(quantiseHours(90), Decimal("0.03"))

    def testVeryShortSpanStillBillsOneQuantum(self) -> None:
        """A five-second span must not round to zero.

        The labour-entry table has a ``hours > 0`` check constraint; rounding
        to zero would turn a mis-tap into a 500 instead of a tiny entry the
        technician can delete.
        """
        self.assertEqual(quantiseHours(5), MINIMUM_BILLABLE_HOURS)
        self.assertGreater(quantiseHours(0), Decimal("0"))

    def testElapsedExcludesPausedTime(self) -> None:
        timer = buildTimer()
        timer.pausedSeconds = 600
        self.assertEqual(timer.elapsedSeconds(NOW + timedelta(hours=2)), 6600)
        self.assertEqual(timer.billableHours(NOW + timedelta(hours=2)), Decimal("1.83"))

    def testElapsedNeverGoesNegative(self) -> None:
        timer = buildTimer()
        timer.pausedSeconds = 99999
        self.assertEqual(timer.elapsedSeconds(NOW + timedelta(minutes=5)), 0)

    def testRunningTimerKeepsCountingUntilStopped(self) -> None:
        timer = buildTimer()
        self.assertTrue(timer.isRunning)
        self.assertEqual(timer.elapsedSeconds(NOW + timedelta(minutes=30)), 1800)
        timer.stop(NOW + timedelta(minutes=30), NOW + timedelta(minutes=30))
        self.assertFalse(timer.isRunning)
        # Frozen: asking later does not keep the clock running.
        self.assertEqual(timer.elapsedSeconds(NOW + timedelta(hours=9)), 1800)


class TimerGuardTests(SimpleTestCase):
    def testCannotStartInTheFuture(self) -> None:
        with self.assertRaises(TimerSpanInvalidError):
            buildTimer(startedAt=NOW + timedelta(hours=1))

    def testSmallClockSkewIsTolerated(self) -> None:
        """A phone two minutes ahead must still be able to start work."""
        timer = buildTimer(startedAt=NOW + timedelta(minutes=2))
        self.assertTrue(timer.isRunning)

    def testCannotEndBeforeItStarted(self) -> None:
        timer = buildTimer()
        with self.assertRaises(TimerSpanInvalidError) as caught:
            timer.stop(NOW - timedelta(minutes=5), NOW)
        self.assertEqual(caught.exception.fieldErrors.get("endedAt"), "beforeStart")

    def testCannotEndInTheFuture(self) -> None:
        timer = buildTimer()
        with self.assertRaises(TimerSpanInvalidError):
            timer.stop(NOW + timedelta(hours=3), NOW)

    def testRefusesAForgottenStopwatch(self) -> None:
        timer = buildTimer()
        tooLate = NOW + timedelta(hours=float(MAX_SPAN_HOURS) + 1)
        with self.assertRaises(TimerSpanInvalidError) as caught:
            timer.stop(tooLate, tooLate)
        self.assertEqual(caught.exception.fieldErrors.get("endedAt"), "tooLong")

    def testExactlyTwentyFourHoursIsStillAccepted(self) -> None:
        timer = buildTimer()
        edge = NOW + timedelta(hours=24)
        self.assertEqual(timer.stop(edge, edge), Decimal("24.00"))

    def testPausedTimeCannotExceedTheSpan(self) -> None:
        timer = buildTimer()
        timer.pausedSeconds = 7200
        with self.assertRaises(TimerSpanInvalidError):
            timer.stop(NOW + timedelta(minutes=30), NOW + timedelta(minutes=30))

    def testStoppingTwiceIsRefused(self) -> None:
        timer = buildTimer()
        timer.stop(NOW + timedelta(hours=1), NOW + timedelta(hours=1))
        with self.assertRaises(TimerNotRunningError):
            timer.stop(NOW + timedelta(hours=2), NOW + timedelta(hours=2))

    def testEnsureStartableRejectsASecondRunningSpan(self) -> None:
        running = buildTimer()
        candidate = buildTimer()
        with self.assertRaises(TimerAlreadyRunningError):
            candidate.ensureStartable(running)

    def testEnsureStartableAllowsAfterTheFirstIsClosed(self) -> None:
        previous = buildTimer()
        previous.stop(NOW + timedelta(hours=1), NOW + timedelta(hours=1))
        candidate = buildTimer(startedAt=NOW + timedelta(hours=2), now=NOW + timedelta(hours=2))
        candidate.ensureStartable(previous)  # must not raise

    def testStopEmitsAnEventCarryingTheMeasuredHours(self) -> None:
        timer = buildTimer()
        timer.stop(NOW + timedelta(hours=2, minutes=30), NOW + timedelta(hours=3))
        names = [name for name, _ in timer.events]
        self.assertEqual(names, ["workTimerStarted", "workTimerStopped"])
        self.assertEqual(timer.events[-1][1]["hours"], "2.50")

    def testOfflineStartIsMarkedAsSuch(self) -> None:
        timer = buildTimer(capturedOffline=True)
        self.assertEqual(timer.startedVia, "offline")
        self.assertTrue(timer.events[0][1]["capturedOffline"])


class TimerInputParsingTests(SimpleTestCase):
    def testParsesIsoWithZuluSuffix(self) -> None:
        """``new Date().toISOString()`` ends with Z, which Python 3.10 refused."""
        parsed = parseMoment("2026-10-01T09:30:00.000Z", NOW, "startedAt")
        self.assertEqual(parsed, datetime(2026, 10, 1, 9, 30, tzinfo=UTC))

    def testNaiveInputIsReadAsUtc(self) -> None:
        parsed = parseMoment("2026-10-01T09:30:00", NOW, "startedAt")
        self.assertEqual(parsed.tzinfo, UTC)

    def testEmptyFallsBackToTheServerClock(self) -> None:
        self.assertEqual(parseMoment("", NOW, "startedAt"), NOW)

    def testGarbageIsRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            parseMoment("yesterday", NOW, "startedAt")

    def testRateMustBeInRange(self) -> None:
        self.assertEqual(parseRate("250000"), Decimal("250000.00"))
        with self.assertRaises(ValidationFailedError):
            parseRate("-1")
        with self.assertRaises(ValidationFailedError):
            parseRate("abc")


# =====================================================================================
# Scan parsing
# =====================================================================================
class ScanParsingTests(SimpleTestCase):
    def testAbsoluteDeviceDeepLink(self) -> None:
        identifier = uuid.uuid4()
        intent = parseScan(f"https://plant.local/app/maintenance/devices/{identifier}/profile")
        self.assertEqual(intent.kind, SCAN_TARGET_DEVICE)
        self.assertEqual(intent.entityId, identifier)

    def testRelativeDeviceLinkWithoutAppPrefix(self) -> None:
        identifier = uuid.uuid4()
        intent = parseScan(f"/maintenance/devices/{identifier}")
        self.assertEqual(intent.kind, SCAN_TARGET_DEVICE)
        self.assertEqual(intent.entityId, identifier)

    def testWorkOrderLink(self) -> None:
        identifier = uuid.uuid4()
        intent = parseScan(f"https://x/app/maintenance/work-orders/{identifier}")
        self.assertEqual(intent.kind, SCAN_TARGET_WORK_ORDER)

    def testCompactSchemeForOneDimensionalBarcodes(self) -> None:
        identifier = uuid.uuid4()
        intent = parseScan(f"tekarai://device/{identifier}")
        self.assertEqual(intent.kind, SCAN_TARGET_DEVICE)
        self.assertEqual(intent.entityId, identifier)

    def testCompactSchemeWithBusinessCode(self) -> None:
        intent = parseScan("tekarai://part/brg-6204")
        self.assertEqual(intent.kind, SCAN_TARGET_SPARE_PART)
        self.assertIsNone(intent.entityId)
        self.assertEqual(intent.code, "BRG-6204")

    def testLocationScheme(self) -> None:
        self.assertEqual(parseScan("tekarai://location/HALL-A").kind, SCAN_TARGET_LOCATION)

    def testBareUuidHasNoKindAndIsProbedEverywhere(self) -> None:
        identifier = uuid.uuid4()
        intent = parseScan(str(identifier))
        self.assertEqual(intent.kind, "")
        self.assertEqual(intent.entityId, identifier)

    def testUuidInBracesFromALabelWriter(self) -> None:
        identifier = uuid.uuid4()
        self.assertEqual(parseScan("{" + str(identifier) + "}").entityId, identifier)

    def testPlainBusinessCodeIsUppercased(self) -> None:
        intent = parseScan(" pump-204 ")
        self.assertEqual(intent.code, "PUMP-204")
        self.assertIsNone(intent.entityId)

    def testCodeWithSlashAndDotIsAccepted(self) -> None:
        self.assertEqual(parseScan("LINE1/PMP.204").code, "LINE1/PMP.204")

    def testPersianTextIsNotTreatedAsACode(self) -> None:
        """Someone typing a device *name* must not become a bogus code lookup."""
        self.assertTrue(parseScan("پمپ خط یک").isEmpty)

    def testTextWithSpacesIsNotACode(self) -> None:
        self.assertTrue(parseScan("PUMP 204").isEmpty)

    def testEmptyAndOversizedInputAreEmptyIntents(self) -> None:
        self.assertTrue(parseScan("").isEmpty)
        self.assertTrue(parseScan("x" * 600).isEmpty)

    def testScanTargetRejectsAnUnknownKind(self) -> None:
        with self.assertRaises(ValueError):
            ScanTarget(kind="robot", id="1", code="", title="", subtitle="", route="")


# =====================================================================================
# Sync verdicts
# =====================================================================================
class SyncVerdictTests(SimpleTestCase):
    def testTimerConflictsCountAsDuplicates(self) -> None:
        """The queue must drop these, not retry them and not alarm anyone."""
        status, _code, _message = classifyFailure(TimerNotRunningError("stopped"))
        self.assertEqual(status, SYNC_STATUS_DUPLICATE)
        status, _code, _message = classifyFailure(TimerAlreadyRunningError("running"))
        self.assertEqual(status, SYNC_STATUS_DUPLICATE)

    def testValidationIsRejectedForever(self) -> None:
        status, code, _message = classifyFailure(ValidationFailedError("bad"))
        self.assertEqual(status, SYNC_STATUS_REJECTED)
        self.assertEqual(code, "SYS_VALIDATION_FAILED")

    def testMissingTargetIsRejected(self) -> None:
        status, _code, _message = classifyFailure(EntityNotFoundError("WorkOrder", "x"))
        self.assertEqual(status, SYNC_STATUS_REJECTED)

    def testPermissionDenialIsRejected(self) -> None:
        status, _code, _message = classifyFailure(PermissionDeniedError("nope"))
        self.assertEqual(status, SYNC_STATUS_REJECTED)

    def testUnknownFailureIsRetried(self) -> None:
        status, code, _message = classifyFailure(RuntimeError("database is on fire"))
        self.assertEqual(status, SYNC_STATUS_FAILED)
        self.assertEqual(code, "SYS_REQUEST_FAILED")
