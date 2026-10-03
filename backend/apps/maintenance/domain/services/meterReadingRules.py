"""Meter-reading domain rules — delta, rollover, quality and PM triggers.

This module holds the judgement calls that make meter data trustworthy. It is
pure Python with no framework imports, so every rule here is unit-testable
without a database.

The three hard problems it solves
---------------------------------
1. **A counter that appears to go backwards.** Three different events look
   identical in the raw data: a physical roll-over at the end of the dial, a
   mistyped digit, and a replaced meter. They need three different answers, so
   the rules distinguish them by *how far* backwards the value went relative to
   the counter's declared capacity.
2. **A physically impossible jump.** A 90-hour jump on an hour meter read one
   hour ago is not a reading, it is a fault. It is kept (data is never thrown
   away) but flagged ``suspect`` so it does not silently advance a PM trigger.
3. **When a meter-driven PM becomes due.** "Every 500 running hours" needs a
   baseline — the meter value at the last execution — not a date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from apps.maintenance.domain.entities.meterReading import MeterPoint, MeterReading
from apps.maintenance.domain.valueObjects.meterTypes import (
    QUALITY_BAD,
    QUALITY_GOOD,
    QUALITY_SUSPECT,
    TRIGGER_CONDITION,
    TRIGGER_DUE,
    TRIGGER_METER,
    TRIGGER_OK,
    TRIGGER_UNKNOWN,
    TRIGGER_WARNING,
    quantiseValue,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

#: A reading timestamped further than this into the future is rejected. Small
#: clock skew between a gateway and the server is normal; an hour is not.
MAX_FUTURE_SKEW = timedelta(minutes=5)

#: Below this fraction of the counter's capacity, a backwards step is treated
#: as a typo rather than a wrap. A genuine roll-over lands near the top of the
#: dial; a mistyped leading digit usually does not.
ROLLOVER_RECOGNITION_RATIO = Decimal("0.5")

#: Guard for the step check when two readings share a timestamp.
MINIMUM_STEP_WINDOW_HOURS = Decimal("0.0167")  # one minute


@dataclass(frozen=True)
class DeltaOutcome:
    """Result of comparing a new cumulative value against the previous one."""

    delta: Decimal | None
    rolloverApplied: bool = False
    quality: str = QUALITY_GOOD
    reason: str = ""

    @property
    def isRegression(self) -> bool:
        return self.reason == "counterWentBackwards"


def computeDelta(
    point: MeterPoint,
    newValue: Decimal,
    previous: MeterReading | None,
) -> DeltaOutcome:
    """Consumption between two cumulative readings, roll-over aware.

    * No previous reading → the series starts here; the delta is unknown
      (``None``), *not* zero. Reporting zero would claim the pump ran for no
      hours before we started watching, which is a different statement.
    * Value grew → plain difference.
    * Value shrank but the counter declares a capacity and the drop is large
      relative to it → a wrap: ``(capacity - previous) + new``.
    * Value shrank otherwise → a regression. The reading is kept and flagged
      ``suspect`` with no delta, because a wrong number must not be allowed to
      produce a wrong consumption figure.
    """
    if not point.isCumulative:
        return DeltaOutcome(delta=None)
    if previous is None:
        return DeltaOutcome(delta=None, reason="firstReading")

    previousValue = previous.value
    if newValue >= previousValue:
        return DeltaOutcome(delta=quantiseValue(newValue - previousValue))

    capacity = point.rolloverMaximum
    if capacity is not None and capacity > 0:
        drop = previousValue - newValue
        if drop >= capacity * ROLLOVER_RECOGNITION_RATIO:
            wrapped = (capacity - previousValue) + newValue
            if wrapped >= 0:
                return DeltaOutcome(
                    delta=quantiseValue(wrapped),
                    rolloverApplied=True,
                    reason="rollover",
                )

    return DeltaOutcome(delta=None, quality=QUALITY_SUSPECT, reason="counterWentBackwards")


def assessStep(
    point: MeterPoint,
    delta: Decimal | None,
    capturedAt: datetime,
    previous: MeterReading | None,
) -> tuple[str, str]:
    """Flag physically impossible accumulation rates.

    Returns ``(quality, reason)``. Only ever *downgrades* quality — a rule that
    could upgrade a reading to ``good`` would let a gateway launder bad data.
    """
    if delta is None or previous is None or point.maximumStepPerHour is None:
        return QUALITY_GOOD, ""
    if point.maximumStepPerHour <= 0:
        return QUALITY_GOOD, ""

    elapsed = (capturedAt - previous.capturedAt).total_seconds() / 3600
    hours = max(Decimal(str(round(elapsed, 6))), MINIMUM_STEP_WINDOW_HOURS)
    allowed = point.maximumStepPerHour * hours
    if delta > allowed:
        return QUALITY_SUSPECT, "stepTooLarge"
    return QUALITY_GOOD, ""


def validateReadingTime(capturedAt: datetime, now: datetime) -> None:
    """Reject readings from the future beyond tolerable clock skew."""
    if capturedAt > now + MAX_FUTURE_SKEW:
        raise ValidationFailedError(
            "Reading timestamp is in the future.",
            fieldErrors={"capturedAt": "future"},
        )


def validateAgainstPoint(point: MeterPoint, value: Decimal) -> None:
    """Enforce the point's declared physical range and active state."""
    if not point.active:
        raise ValidationFailedError(
            "Meter point is inactive and cannot accept new readings.",
            fieldErrors={"meterPointId": "inactive"},
        )
    if point.minimumValue is not None and value < point.minimumValue:
        raise ValidationFailedError(
            "Reading is below the meter point minimum.",
            fieldErrors={"value": "belowMinimum"},
        )
    if point.maximumValue is not None and value > point.maximumValue:
        raise ValidationFailedError(
            "Reading is above the meter point maximum.",
            fieldErrors={"value": "aboveMaximum"},
        )
    if point.rolloverMaximum is not None and value > point.rolloverMaximum:
        raise ValidationFailedError(
            "Reading exceeds the counter capacity.",
            fieldErrors={"value": "aboveCapacity"},
        )


def worstQuality(*qualities: str) -> str:
    """Pick the least-trusted of several assessments.

    Severity order is explicit rather than alphabetical so that adding a new
    quality later cannot silently reorder it.
    """
    severity = {QUALITY_GOOD: 0, "estimated": 1, QUALITY_SUSPECT: 2, QUALITY_BAD: 3}
    chosen = QUALITY_GOOD
    for quality in qualities:
        if not quality:
            continue
        if severity.get(quality, 0) > severity.get(chosen, 0):
            chosen = quality
    return chosen


@dataclass(frozen=True)
class ReadingAssessment:
    """Everything the application layer needs to persist one reading."""

    delta: Decimal | None
    quality: str
    rolloverApplied: bool
    reason: str


def assessReading(
    point: MeterPoint,
    value: Decimal,
    capturedAt: datetime,
    previous: MeterReading | None,
    now: datetime,
    requestedQuality: str = QUALITY_GOOD,
) -> ReadingAssessment:
    """Run every rule for one new reading and return the verdict.

    The caller-supplied ``requestedQuality`` can only make the verdict worse —
    a gateway may declare its own sample suspect, but may not declare a
    suspect sample good.
    """
    validateReadingTime(capturedAt, now)
    validateAgainstPoint(point, value)

    outcome = computeDelta(point, value, previous)
    stepQuality, stepReason = assessStep(point, outcome.delta, capturedAt, previous)
    quality = worstQuality(requestedQuality, outcome.quality, stepQuality)

    # A reading judged bad carries no consumption: a known-wrong number must
    # never contribute to a total that someone will later bill against.
    delta = None if quality == QUALITY_BAD else outcome.delta
    return ReadingAssessment(
        delta=delta,
        quality=quality,
        rolloverApplied=outcome.rolloverApplied,
        reason=stepReason or outcome.reason,
    )


# =====================================================================================
# PM trigger evaluation — what makes a meter-based plan actually become due
# =====================================================================================
@dataclass(frozen=True)
class TriggerEvaluation:
    """Where a meter-driven PM plan stands against the current meter value."""

    status: str = TRIGGER_UNKNOWN
    currentValue: Decimal | None = None
    dueAtValue: Decimal | None = None
    remaining: Decimal | None = None
    reason: str = ""

    @property
    def isDue(self) -> bool:
        return self.status == TRIGGER_DUE

    @property
    def isWarning(self) -> bool:
        return self.status == TRIGGER_WARNING


def evaluateMeterTrigger(
    *,
    interval: Decimal,
    baseline: Decimal | None,
    currentValue: Decimal | None,
    warningLead: Decimal | None = None,
) -> TriggerEvaluation:
    """"Every N meter units since the last execution."

    ``baseline`` is the meter value recorded at the last execution. When a plan
    has never been executed, the first reading ever taken on the point becomes
    the baseline — otherwise a plan attached to a pump with 40 000 existing
    hours would be born overdue by eighty cycles.
    """
    if currentValue is None:
        return TriggerEvaluation(reason="noReadings")
    if interval is None or interval <= 0:
        return TriggerEvaluation(currentValue=currentValue, reason="noInterval")
    if baseline is None:
        return TriggerEvaluation(currentValue=currentValue, reason="noBaseline")

    dueAt = quantiseValue(baseline + interval)
    remaining = quantiseValue(dueAt - currentValue)
    if remaining <= 0:
        status = TRIGGER_DUE
    elif warningLead is not None and warningLead > 0 and remaining <= warningLead:
        status = TRIGGER_WARNING
    else:
        status = TRIGGER_OK
    return TriggerEvaluation(
        status=status,
        currentValue=quantiseValue(currentValue),
        dueAtValue=dueAt,
        remaining=remaining,
    )


def evaluateConditionTrigger(
    *,
    operator: str,
    thresholdValue: Decimal,
    warningValue: Decimal | None,
    currentValue: Decimal | None,
) -> TriggerEvaluation:
    """"When the value crosses a threshold" — condition-based maintenance.

    The warning level is checked with the same operator, so a ``<=`` trigger
    (bearing oil level dropping) warns *before* it trips, exactly like a ``>=``
    trigger (vibration rising) does.
    """
    if currentValue is None:
        return TriggerEvaluation(reason="noReadings")

    comparisons = {
        ">=": lambda left, right: left >= right,
        "<=": lambda left, right: left <= right,
        ">": lambda left, right: left > right,
        "<": lambda left, right: left < right,
    }
    compare = comparisons.get(operator)
    if compare is None:
        return TriggerEvaluation(currentValue=currentValue, reason="badOperator")

    current = quantiseValue(currentValue)
    if compare(current, thresholdValue):
        return TriggerEvaluation(
            status=TRIGGER_DUE,
            currentValue=current,
            dueAtValue=quantiseValue(thresholdValue),
            remaining=Decimal("0.0000"),
        )
    if warningValue is not None and warningValue != 0 and compare(current, warningValue):
        return TriggerEvaluation(
            status=TRIGGER_WARNING,
            currentValue=current,
            dueAtValue=quantiseValue(thresholdValue),
            remaining=quantiseValue(abs(thresholdValue - current)),
        )
    return TriggerEvaluation(
        status=TRIGGER_OK,
        currentValue=current,
        dueAtValue=quantiseValue(thresholdValue),
        remaining=quantiseValue(abs(thresholdValue - current)),
    )


def evaluatePlanTrigger(plan: object, currentValue: Decimal | None) -> TriggerEvaluation:
    """Dispatch a PM plan to the evaluator matching its trigger type."""
    triggerType = getattr(plan, "triggerType", "")
    if triggerType == TRIGGER_METER:
        return evaluateMeterTrigger(
            interval=getattr(plan, "metricInterval", Decimal("0")) or Decimal("0"),
            baseline=getattr(plan, "lastExecutedMeterValue", None),
            currentValue=currentValue,
            warningLead=getattr(plan, "warningValue", None) or None,
        )
    if triggerType == TRIGGER_CONDITION:
        return evaluateConditionTrigger(
            operator=getattr(plan, "thresholdOperator", ">=") or ">=",
            thresholdValue=getattr(plan, "thresholdValue", Decimal("0")) or Decimal("0"),
            warningValue=getattr(plan, "warningValue", None) or None,
            currentValue=currentValue,
        )
    return TriggerEvaluation(reason="notMeterDriven")


__all__ = [
    "MAX_FUTURE_SKEW",
    "ROLLOVER_RECOGNITION_RATIO",
    "DeltaOutcome",
    "ReadingAssessment",
    "TriggerEvaluation",
    "assessReading",
    "assessStep",
    "computeDelta",
    "evaluateConditionTrigger",
    "evaluateMeterTrigger",
    "evaluatePlanTrigger",
    "validateAgainstPoint",
    "validateReadingTime",
    "worstQuality",
]
