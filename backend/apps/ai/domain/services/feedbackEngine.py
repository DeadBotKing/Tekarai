"""Pure feedback aggregation and promotion planning for Phase 13-V.

Three deterministic services close the quality loop:

- ``FeedbackAggregator`` — turns a stream of signals into a comparable
  ``FeedbackSummary``: satisfaction, net sentiment, the ranked reasons,
  and the per-target breakdown (model + prompt version, §33);
- ``TrendComparer`` — compares two windows of feedback and says whether
  perceived quality moved beyond tolerance. It is the human-signal twin of
  the Phase 13-U regression detector: U measures what the platform can
  compute, V measures what people actually felt;
- ``PromotionPlanner`` — decides which complaints deserve to become
  Phase 13-U golden cases, groups repeated complaints so one recurring
  problem produces one case, and refuses to promote a signal that carries
  no reproducible content.

The module performs no I/O and has no Django, HTTP, ORM, queue, network,
or vendor dependency.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from apps.ai.domain.entities.feedbackRecords import AIFeedbackEntry
from apps.ai.domain.exceptions import AIFeedbackInvalid, AIFeedbackPolicyInvalid
from apps.ai.domain.valueObjects.feedbackTypes import (
    SCORE_PRECISION,
    FeedbackPolicy,
    netSentiment,
    rankReasons,
    satisfactionScore,
)


@dataclass(frozen=True)
class TargetBreakdown:
    """Signals grouped by model + prompt version (§33)."""

    targetKey: str
    total: int
    positive: int
    negative: int
    satisfaction: float
    netSentiment: float


@dataclass(frozen=True)
class FeedbackSummary:
    """Comparable view of one feedback window (§V.7)."""

    total: int = 0
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    ratedCount: int = 0
    satisfaction: float = 0.0
    netSentiment: float = 0.0
    topReasons: tuple[tuple[str, int], ...] = ()
    targets: tuple[TargetBreakdown, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def negativeRatio(self) -> float:
        if not self.total:
            return 0.0
        return round(self.negative / self.total, SCORE_PRECISION)

    @property
    def isEmpty(self) -> bool:
        return self.total == 0

    def meets(self, policy: FeedbackPolicy) -> bool:
        """Does this window clear the configured satisfaction bar?"""

        if not isinstance(policy, FeedbackPolicy):
            raise AIFeedbackPolicyInvalid("A FeedbackPolicy is required.")
        if self.isEmpty:
            return True
        return self.satisfaction >= policy.minimumSatisfaction


class FeedbackAggregator:
    """Turns raw signals into a summary a human or a gate can read."""

    def summarize(self, entries: Iterable[AIFeedbackEntry]) -> FeedbackSummary:
        materialized = list(entries)
        for entry in materialized:
            if not isinstance(entry, AIFeedbackEntry):
                raise AIFeedbackInvalid("Aggregation requires AIFeedbackEntry values.")
        if not materialized:
            return FeedbackSummary()

        ratings = [entry.rating for entry in materialized if entry.rating is not None]
        sentiments = [entry.sentiment for entry in materialized]
        grouped: dict[str, list[AIFeedbackEntry]] = {}
        for entry in materialized:
            grouped.setdefault(entry.targetKey, []).append(entry)

        targets = tuple(
            TargetBreakdown(
                targetKey=key,
                total=len(group),
                positive=sum(1 for item in group if item.sentiment == "POSITIVE"),
                negative=sum(1 for item in group if item.sentiment == "NEGATIVE"),
                satisfaction=satisfactionScore(
                    [item.rating for item in group if item.rating is not None]
                ),
                netSentiment=netSentiment([item.sentiment for item in group]),
            )
            for key in sorted(grouped)
            for group in (grouped[key],)
        )
        return FeedbackSummary(
            total=len(materialized),
            positive=sum(1 for value in sentiments if value == "POSITIVE"),
            neutral=sum(1 for value in sentiments if value == "NEUTRAL"),
            negative=sum(1 for value in sentiments if value == "NEGATIVE"),
            ratedCount=len(ratings),
            satisfaction=satisfactionScore(ratings),
            netSentiment=netSentiment(sentiments),
            topReasons=rankReasons(entry.reason for entry in materialized),
            targets=targets,
        )


@dataclass(frozen=True)
class SatisfactionTrend:
    """How perceived quality moved between two windows (§V.7)."""

    regressed: bool
    improved: bool
    satisfactionDelta: float
    sentimentDelta: float
    tolerance: float
    baselineTotal: int
    candidateTotal: int
    newReasons: tuple[str, ...] = ()
    reason: str = ""


class TrendComparer:
    """The human-signal twin of the Phase 13-U regression detector."""

    def compare(
        self,
        baseline: FeedbackSummary,
        candidate: FeedbackSummary,
        policy: FeedbackPolicy,
    ) -> SatisfactionTrend:
        if not isinstance(policy, FeedbackPolicy):
            raise AIFeedbackPolicyInvalid("Comparison requires a FeedbackPolicy.")
        if not isinstance(baseline, FeedbackSummary) or not isinstance(candidate, FeedbackSummary):
            raise AIFeedbackInvalid("Comparison requires FeedbackSummary values.")
        tolerance = float(policy.trendTolerance)
        satisfactionDelta = round(candidate.satisfaction - baseline.satisfaction, SCORE_PRECISION)
        sentimentDelta = round(candidate.netSentiment - baseline.netSentiment, SCORE_PRECISION)
        baselineReasons = {reason for reason, _ in baseline.topReasons}
        newReasons = tuple(
            sorted(reason for reason, _ in candidate.topReasons if reason not in baselineReasons)
        )

        # An empty window says nothing; silence is not a regression.
        if baseline.isEmpty or candidate.isEmpty:
            return SatisfactionTrend(
                regressed=False,
                improved=False,
                satisfactionDelta=satisfactionDelta,
                sentimentDelta=sentimentDelta,
                tolerance=tolerance,
                baselineTotal=baseline.total,
                candidateTotal=candidate.total,
                newReasons=newReasons,
                reason="One of the windows has no feedback.",
            )

        regressed = satisfactionDelta < -tolerance or sentimentDelta < -tolerance
        improved = satisfactionDelta > tolerance or sentimentDelta > tolerance
        if regressed:
            reason = (
                f"Satisfaction moved by {satisfactionDelta} and sentiment by "
                f"{sentimentDelta} (tolerance {tolerance})."
            )
        elif improved:
            reason = f"Perceived quality improved by {satisfactionDelta}."
        else:
            reason = "No movement beyond tolerance."
        return SatisfactionTrend(
            regressed=regressed,
            improved=improved,
            satisfactionDelta=satisfactionDelta,
            sentimentDelta=sentimentDelta,
            tolerance=tolerance,
            baselineTotal=baseline.total,
            candidateTotal=candidate.total,
            newReasons=newReasons,
            reason=reason,
        )


@dataclass(frozen=True)
class GoldenCaseDraft:
    """A complaint that earned the right to become an evaluation case."""

    suiteCode: str
    caseCode: str
    question: str
    expectedTerms: tuple[str, ...]
    reason: str
    metric: str
    occurrences: int
    feedbackIds: tuple[Any, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def isRecurring(self) -> bool:
        return self.occurrences > 1


@dataclass(frozen=True)
class PromotionPlan:
    """What the planner decided about a batch of signals (§V.8)."""

    drafts: tuple[GoldenCaseDraft, ...] = ()
    skipped: tuple[tuple[Any, str], ...] = ()

    @property
    def draftCount(self) -> int:
        return len(self.drafts)

    @property
    def skippedCount(self) -> int:
        return len(self.skipped)


class PromotionPlanner:
    """Decides which complaints become Phase 13-U golden cases."""

    def plan(
        self,
        entries: Sequence[AIFeedbackEntry],
        policy: FeedbackPolicy,
        *,
        suiteCode: str = "FEEDBACK_GOLDEN",
        knownQuestions: Iterable[str] = (),
    ) -> PromotionPlan:
        if not isinstance(policy, FeedbackPolicy):
            raise AIFeedbackPolicyInvalid("Planning requires a FeedbackPolicy.")
        known = {self._questionKey(value) for value in knownQuestions}
        eligible: dict[str, list[AIFeedbackEntry]] = {}
        skipped: list[tuple[Any, str]] = []

        for entry in entries:
            if not isinstance(entry, AIFeedbackEntry):
                raise AIFeedbackInvalid("Planning requires AIFeedbackEntry values.")
            if entry.isTerminal:
                skipped.append((entry.id, "Signal is already promoted or rejected."))
                continue
            if not entry.isNegative:
                skipped.append((entry.id, "Only negative signals become cases."))
                continue
            if not entry.question:
                skipped.append((entry.id, "The original question was not captured."))
                continue
            if policy.requireReason and not entry.reason:
                skipped.append((entry.id, "A reason is required for promotion."))
                continue
            if policy.requireCorrection and not entry.correction:
                skipped.append((entry.id, "A correction is required for promotion."))
                continue
            key = self._questionKey(entry.question)
            if key in known:
                skipped.append((entry.id, "A golden case already covers this question."))
                continue
            eligible.setdefault(f"{key}|{entry.reason}", []).append(entry)

        drafts: list[GoldenCaseDraft] = []
        for group in eligible.values():
            ordered = sorted(group, key=lambda item: (item.createdAt, str(item.id)))
            if len(ordered) < policy.promotionThreshold:
                for entry in ordered:
                    skipped.append(
                        (
                            entry.id,
                            f"Reported {len(ordered)} time(s); threshold is "
                            f"{policy.promotionThreshold}.",
                        )
                    )
                continue
            leader = ordered[0]
            draft = leader.toGoldenCaseDraft(suiteCode=suiteCode)
            drafts.append(
                GoldenCaseDraft(
                    suiteCode=draft["suiteCode"],
                    caseCode=draft["caseCode"],
                    question=draft["question"],
                    expectedTerms=tuple(draft["expectedTerms"]),
                    reason=leader.reason,
                    metric=leader.suggestedMetric(),
                    occurrences=len(ordered),
                    feedbackIds=tuple(item.id for item in ordered),
                    metadata=dict(draft["metadata"]),
                )
            )
        drafts.sort(key=lambda item: (-item.occurrences, item.caseCode))
        return PromotionPlan(drafts=tuple(drafts), skipped=tuple(skipped))

    @staticmethod
    def _questionKey(value: str) -> str:
        return " ".join(str(value or "").casefold().split())


__all__ = [
    "FeedbackAggregator",
    "FeedbackSummary",
    "GoldenCaseDraft",
    "PromotionPlan",
    "PromotionPlanner",
    "SatisfactionTrend",
    "TargetBreakdown",
    "TrendComparer",
]
