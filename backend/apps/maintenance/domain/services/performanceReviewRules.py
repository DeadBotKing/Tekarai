"""Performance review arithmetic (ارزیابی عملکرد کارکنان) — Phase 29.

Pure functions. No ORM, no Django, no clock: every answer is derived from the
arguments, so the whole module is testable without a database and gives the
same answer in a test, a task queue and a request.

The problem this solves
-----------------------
Ten managers may rate one technician, and some of them have a stake in the
answer. The production manager who likes جواد marks him 95; the technical
manager who does not marks him 40; the unit head, who simply watched the work,
marks him 72. Averaging those three produces 69 — a number that says more
about the raters than about جواد, and that moves whenever someone decides to
push it.

So a plain weighted average is not enough. Three things are layered on it:

1. **Consensus by median, not mean.** The median of a set of scores barely
   moves when one rater goes to an extreme; the mean follows them. This alone
   removes most of the leverage a single biased rater has.

2. **Damping by distance from consensus.** A score far outside the spread of
   its peers keeps less of its weight. The further out, the less it counts —
   smoothly, so there is no cliff edge where one point of difference flips a
   rater from fully counted to ignored.

3. **Reliability learned across cycles.** A rater who is *persistently* far
   from the consensus loses standing permanently, not just in the cycle where
   it showed. This is the part that actually learns: nobody labels a rater as
   biased, it emerges from their own history.

What this deliberately does not do
----------------------------------
It does not decide who is lying. A rater sitting alone may be the only honest
one in the room, which is why damping has a floor and never reaches zero, and
why every number the engine produces is reported with the reason it was
produced. A review a technician cannot have explained to them is not a review,
it is a verdict.

It also does not damp at all below ``MIN_RATERS_FOR_DAMPING`` raters, because
with three scores the "consensus" is one person's opinion and damping would
entrench bias rather than remove it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol, runtime_checkable

from apps.maintenance.domain.valueObjects.performanceState import (
    DEFAULT_DAMPING_TOLERANCE,
    DEFAULT_RELIABILITY,
    DEFAULT_ROLE_WEIGHTS,
    DEFAULT_SYSTEM_WEIGHT_PERCENT,
    MAD_TO_SIGMA,
    MIN_CYCLES_FOR_RELIABILITY,
    MIN_DAMPING_FACTOR,
    MIN_RATERS_FOR_DAMPING,
    MIN_RELIABILITY,
    MIN_SPREAD,
    RATER_ROLES,
    REASON_DAMPED_ABOVE,
    REASON_DAMPED_BELOW,
    REASON_FULL_WEIGHT,
    REASON_UNRELIABLE,
    SCORE_MAX,
    SCORE_MIN,
    SYSTEM_METRIC_WEIGHTS,
)

__all__ = [
    "RaterScore",
    "ScoredRater",
    "SystemMetrics",
    "ReviewOutcome",
    "clampScore",
    "median",
    "medianAbsoluteDeviation",
    "roleWeight",
    "dampingFactor",
    "reliabilityFromHistory",
    "systemScore",
    "scoreReview",
    "rankOutcomes",
]


def _round2(value: float) -> float:
    """Round half-up to two places.

    Python's banker's rounding would make 72.125 and 72.135 both land on
    72.12, which is indefensible on a document somebody signs.
    """
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def clampScore(value: object) -> float:
    """Pull any number onto the 0..100 scale; ``None`` and non-numbers become 0."""
    if value is None:
        return float(SCORE_MIN)
    try:
        number = float(value)  # type: ignore[arg-type]  # guarded by the except below
    except (TypeError, ValueError):
        return float(SCORE_MIN)
    if number != number:  # NaN
        return float(SCORE_MIN)
    return float(min(max(number, SCORE_MIN), SCORE_MAX))


def median(values: Sequence[float]) -> float:
    """Middle value; mean of the middle two when the count is even."""
    if not values:
        return 0.0
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    if count % 2 == 1:
        return float(ordered[middle])
    return float((ordered[middle - 1] + ordered[middle]) / 2.0)


def medianAbsoluteDeviation(values: Sequence[float]) -> float:
    """Robust spread: the median of each value's distance from the median.

    Chosen over standard deviation because the outliers this engine exists to
    handle would inflate a standard deviation and thereby hide themselves.
    """
    if not values:
        return 0.0
    centre = median(values)
    return median([abs(value - centre) for value in values])


@dataclass(frozen=True)
class RaterScore:
    """One manager's mark for one person in one cycle."""

    raterRole: str
    score: float
    raterName: str = ""
    note: str = ""
    # Mean absolute z-distance this rater has sat from consensus in past
    # cycles, and how many cycles that covers. Supplied by the caller because
    # the domain layer never reads a database.
    historicalDeviation: float | None = None
    historicalCycles: int = 0


@dataclass(frozen=True)
class ScoredRater:
    """A rater's contribution after weighting — the audit trail of one mark."""

    raterRole: str
    raterName: str
    rawScore: float
    baseWeight: float
    deviation: float
    damping: float
    reliability: float
    effectiveWeight: float
    contribution: float
    damped: bool
    reason: str


@dataclass(frozen=True)
class SystemMetrics:
    """What the record says, independently of anyone's opinion.

    Every field is a percentage already on the 0..100 scale. ``None`` means
    "no evidence either way" and is skipped rather than counted as zero — a
    technician with no PM assigned must not be marked down for PM compliance.
    """

    pmCompliance: float | None = None
    onTimeCompletion: float | None = None
    completionRate: float | None = None
    reworkPenalty: float | None = None

    def asDict(self) -> dict[str, float | None]:
        return {
            "pmCompliance": self.pmCompliance,
            "onTimeCompletion": self.onTimeCompletion,
            "completionRate": self.completionRate,
            "reworkPenalty": self.reworkPenalty,
        }


@dataclass(frozen=True)
class ReviewOutcome:
    """The complete, explainable result for one person in one cycle."""

    personnelId: str
    personnelName: str = ""
    finalScore: float = 0.0
    humanScore: float = 0.0
    systemScoreValue: float | None = None
    consensus: float = 0.0
    spread: float = 0.0
    raterCount: int = 0
    dampedCount: int = 0
    dampingApplied: bool = False
    systemWeightPercent: int = DEFAULT_SYSTEM_WEIGHT_PERCENT
    raters: list[ScoredRater] = field(default_factory=list)
    systemMetrics: dict[str, float | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def roleWeight(raterRole: str, overrides: Mapping[str, object] | None = None) -> float:
    """Relative weight of a role, honouring a per-cycle override table.

    An unknown role is worth nothing rather than a default share: a typo in a
    role name must not quietly buy someone a vote.
    """
    table = dict(DEFAULT_ROLE_WEIGHTS)
    if overrides:
        for key, value in overrides.items():
            if key in DEFAULT_ROLE_WEIGHTS or key in RATER_ROLES:
                try:
                    # Overrides arrive from stored cycle config, so the value is
                    # untrusted; the except below is the contract, not a guard.
                    table[key] = max(0, int(value))  # type: ignore[call-overload]
                except (TypeError, ValueError):
                    continue
    return float(table.get(raterRole, 0))


def dampingFactor(deviation: float, tolerance: float = DEFAULT_DAMPING_TOLERANCE) -> float:
    """How much of a rater's weight survives their distance from consensus.

    ``deviation`` is a signed robust z-score. Inside the tolerance band the
    factor is exactly 1.0 — ordinary disagreement is free. Beyond it the
    factor falls away as 1/(1+excess²), which is smooth (no cliff where one
    point flips a rater from counted to ignored) and never reaches zero.
    """
    excess = abs(deviation) - max(0.0, tolerance)
    if excess <= 0:
        return 1.0
    factor = 1.0 / (1.0 + excess * excess)
    return max(MIN_DAMPING_FACTOR, factor)


def reliabilityFromHistory(historicalDeviation: float | None, cycles: int) -> float:
    """Standing earned over past cycles, in (MIN_RELIABILITY .. 1.0].

    Full trust until there is enough history to justify less — a new rater is
    not a suspect. Once enough cycles exist, a rater who habitually sits a
    long way from consensus keeps proportionally less of their weight.
    """
    if historicalDeviation is None or cycles < MIN_CYCLES_FOR_RELIABILITY:
        return DEFAULT_RELIABILITY
    try:
        average = abs(float(historicalDeviation))
    except (TypeError, ValueError):
        return DEFAULT_RELIABILITY
    if average <= DEFAULT_DAMPING_TOLERANCE:
        return DEFAULT_RELIABILITY
    excess = average - DEFAULT_DAMPING_TOLERANCE
    value = 1.0 / (1.0 + excess)
    return max(MIN_RELIABILITY, value)


def systemScore(metrics: SystemMetrics, weights: dict[str, int] | None = None) -> float | None:
    """Blend the measured metrics into one 0..100 mark.

    Returns ``None`` when nothing was measured at all, which the caller must
    treat as "no system score" rather than as zero. Metrics that are ``None``
    individually are dropped and the remaining weights renormalised, so a
    technician who was never assigned PM is judged on what they did do.
    """
    table = dict(SYSTEM_METRIC_WEIGHTS)
    if weights:
        for key, value in weights.items():
            if key in SYSTEM_METRIC_WEIGHTS:
                try:
                    table[key] = max(0, int(value))
                except (TypeError, ValueError):
                    continue

    total = 0.0
    weightSum = 0.0
    for key, metricValue in metrics.asDict().items():
        # Named apart from the `value` of the weight-parsing loop above: the
        # two held different types under one name, which is how a weight could
        # be silently read where a metric was meant.
        if metricValue is None:
            continue
        weight = float(table.get(key, 0) or 0)
        if weight <= 0:
            continue
        total += clampScore(metricValue) * weight
        weightSum += weight
    if weightSum <= 0:
        return None
    return _round2(total / weightSum)


def _describe(damping: float, reliability: float, deviation: float) -> str:
    """Why this rater's weight ended up where it did, as a stable code.

    A code rather than a sentence on purpose. This engine has no business
    deciding what language an employee reads their own appraisal in, and a
    phrase built here would arrive in the Persian interface in English. The
    UI owns the wording; the domain owns the fact.

    Numbers are appended so the interface can interpolate them without
    recomputing anything: ``dampedAbove:85``, ``dampedBelow:85;unreliable:60``.
    """
    if damping >= 1.0 and reliability >= 1.0:
        return REASON_FULL_WEIGHT
    parts = []
    if damping < 1.0:
        code = REASON_DAMPED_ABOVE if deviation > 0 else REASON_DAMPED_BELOW
        parts.append(f"{code}:{int(round((1 - damping) * 100))}")
    if reliability < 1.0:
        parts.append(f"{REASON_UNRELIABLE}:{int(round((1 - reliability) * 100))}")
    return ";".join(parts)


def scoreReview(
    personnelId: str,
    raters: list[RaterScore],
    metrics: SystemMetrics | None = None,
    *,
    personnelName: str = "",
    systemWeightPercent: int = DEFAULT_SYSTEM_WEIGHT_PERCENT,
    roleWeights: dict[str, int] | None = None,
    systemMetricWeights: dict[str, int] | None = None,
    dampingTolerance: float = DEFAULT_DAMPING_TOLERANCE,
) -> ReviewOutcome:
    """Turn a pile of opinions plus a work record into one defensible mark.

    The returned outcome carries every intermediate number — each rater's raw
    score, the weight they started with, how far they sat from consensus, what
    that cost them and why — because the first question anyone asks about a
    performance score is "where did that come from".
    """
    cleanRaters = [
        rater
        for rater in raters
        if rater is not None and roleWeight(rater.raterRole, roleWeights) > 0
    ]

    notes: list[str] = []
    measured = systemScore(metrics, systemMetricWeights) if metrics else None

    if not cleanRaters:
        # Nobody rated. The system score, if any, stands alone rather than
        # being blended with a human average that does not exist.
        notes.append("noRaters")
        final = measured if measured is not None else 0.0
        return ReviewOutcome(
            personnelId=personnelId,
            personnelName=personnelName,
            finalScore=_round2(final),
            humanScore=0.0,
            systemScoreValue=measured,
            raterCount=0,
            systemWeightPercent=100 if measured is not None else 0,
            systemMetrics=metrics.asDict() if metrics else {},
            notes=notes,
        )

    scores = [clampScore(rater.score) for rater in cleanRaters]
    consensus = median(scores)
    rawSpread = medianAbsoluteDeviation(scores) * MAD_TO_SIGMA
    spread = max(rawSpread, MIN_SPREAD)

    damp = len(cleanRaters) >= MIN_RATERS_FOR_DAMPING
    if not damp:
        notes.append("tooFewRatersToDamp")

    scored: list[ScoredRater] = []
    weightedTotal = 0.0
    weightTotal = 0.0
    dampedCount = 0

    for rater in cleanRaters:
        raw = clampScore(rater.score)
        base = roleWeight(rater.raterRole, roleWeights)
        deviation = (raw - consensus) / spread if spread > 0 else 0.0
        factor = dampingFactor(deviation, dampingTolerance) if damp else 1.0
        trust = reliabilityFromHistory(rater.historicalDeviation, rater.historicalCycles)
        effective = base * factor * trust
        weightedTotal += raw * effective
        weightTotal += effective
        wasDamped = factor < 1.0 or trust < 1.0
        if wasDamped:
            dampedCount += 1
        scored.append(
            ScoredRater(
                raterRole=rater.raterRole,
                raterName=rater.raterName,
                rawScore=_round2(raw),
                baseWeight=base,
                deviation=_round2(deviation),
                damping=_round2(factor),
                reliability=_round2(trust),
                effectiveWeight=_round2(effective),
                contribution=0.0,
                damped=wasDamped,
                reason=_describe(factor, trust, deviation),
            )
        )

    human = (weightedTotal / weightTotal) if weightTotal > 0 else consensus

    # Restate each rater's effective weight as a share of the human half, so
    # the breakdown adds to 100% and can be read straight off a screen.
    withShares: list[ScoredRater] = []
    for row in scored:
        share = (row.effectiveWeight / weightTotal * 100.0) if weightTotal > 0 else 0.0
        withShares.append(
            ScoredRater(
                raterRole=row.raterRole,
                raterName=row.raterName,
                rawScore=row.rawScore,
                baseWeight=row.baseWeight,
                deviation=row.deviation,
                damping=row.damping,
                reliability=row.reliability,
                effectiveWeight=row.effectiveWeight,
                contribution=_round2(share),
                damped=row.damped,
                reason=row.reason,
            )
        )

    weight = max(0, min(100, int(systemWeightPercent)))
    if measured is None:
        # No measured evidence: the opinions carry the whole mark rather than
        # a missing system score dragging it toward zero.
        final = human
        weight = 0
        notes.append("noSystemMetrics")
    else:
        final = (measured * weight + human * (100 - weight)) / 100.0

    return ReviewOutcome(
        personnelId=personnelId,
        personnelName=personnelName,
        finalScore=_round2(final),
        humanScore=_round2(human),
        systemScoreValue=measured,
        consensus=_round2(consensus),
        spread=_round2(spread),
        raterCount=len(cleanRaters),
        dampedCount=dampedCount,
        dampingApplied=damp,
        systemWeightPercent=weight,
        raters=withShares,
        systemMetrics=metrics.asDict() if metrics else {},
        notes=notes,
    )


@runtime_checkable
class RankableOutcome(Protocol):
    """The three fields `rankOutcomes` actually reads.

    The parameter used to be typed `list[ReviewOutcome]` while a comment
    explained that stored rows could be ranked too; callers duly passed
    `SimpleNamespace` stand-ins and the annotation quietly lied. Stating the
    structural requirement makes the documented contract the checked one.
    """

    personnelId: str
    personnelName: str
    finalScore: float


def rankOutcomes[T: RankableOutcome](outcomes: Sequence[T]) -> list[tuple[int, T]]:
    """Order people by final score, highest first, with ties sharing a rank.

    Equal scores must share a rank: handing one of two identical performers
    the higher number would invent a difference the data does not support.
    """
    ordered = sorted(
        outcomes, key=lambda row: (-row.finalScore, row.personnelName, row.personnelId)
    )
    ranked: list[tuple[int, T]] = []
    previous: float | None = None
    rank = 0
    for index, outcome in enumerate(ordered, start=1):
        if previous is None or outcome.finalScore != previous:
            rank = index
            previous = outcome.finalScore
        ranked.append((rank, outcome))
    return ranked
