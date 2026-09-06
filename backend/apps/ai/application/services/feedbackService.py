"""Application orchestration for the Phase 13-V feedback platform.

``FeedbackApplicationService`` closes the quality loop the platform has
been building since Q: a human says the answer was wrong, that complaint
is triaged, and — if it is reproducible and recurring — it becomes a
Phase 13-U golden case that every future run is graded against.

Behaviour worth stating once:

- **Submission is idempotent.** One signal of one kind per user per
  response; re-submitting revises the same slot instead of stuffing the
  ballot box (§V.5).
- **Every signal ends somewhere.** Feedback is not a write-only inbox:
  a signal is promoted into a case or rejected with a stated reason, and
  both transitions are audited.
- **Promotion requires reproducibility.** A complaint becomes a case only
  when the original question was captured, a reason is given, a
  correction shows what "right" looks like, and the same problem was
  reported at least ``promotionThreshold`` times (configurable).
- **V never imports U.** The evaluation service is reached through the
  narrow ``GoldenCasePublisher`` port, so the loop is wired at the
  composition root, not baked into the domain.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings as djangoSettings

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.feedbackRecords import AIFeedbackEntry
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIFeedbackInvalid,
    AIFeedbackNotFound,
    AIFeedbackNotPromotable,
)
from apps.ai.domain.feedbackPorts import (
    FeedbackAuditLogger,
    FeedbackStore,
    GoldenCasePublisher,
)
from apps.ai.domain.services.feedbackEngine import (
    FeedbackAggregator,
    FeedbackSummary,
    PromotionPlan,
    PromotionPlanner,
    SatisfactionTrend,
    TrendComparer,
)
from apps.ai.domain.valueObjects.feedbackTypes import (
    FeedbackPolicy,
    ensureFeedbackKind,
    ensureFeedbackStatus,
    ensureSentiment,
    feedbackFingerprint,
)

#: Audit actions used by V. Submission reuses the Phase 13-O
#: ``FEEDBACK_RECEIVED`` action from the §36 event list rather than
#: inventing a second name for the same concept.
AUDIT_FEEDBACK_RECEIVED = "FEEDBACK_RECEIVED"
AUDIT_FEEDBACK_TRIAGED = "FEEDBACK_TRIAGED"
AUDIT_FEEDBACK_PROMOTED = "FEEDBACK_PROMOTED"

#: Suite that collects cases born from complaints.
DEFAULT_FEEDBACK_SUITE = "FEEDBACK_GOLDEN"


@dataclass(frozen=True)
class FeedbackSettings:
    """Configuration-driven defaults (Master Specification §42)."""

    enabled: bool = True
    promotionThreshold: int = 2
    requireCorrection: bool = True
    requireReason: bool = True
    negativeRatingCeiling: int = 2
    minimumSatisfaction: float = 0.6
    trendTolerance: float = 0.05
    trendWindowDays: int = 7
    autoPromote: bool = False
    goldenSuiteCode: str = DEFAULT_FEEDBACK_SUITE
    retentionDays: int = 730

    def __post_init__(self) -> None:
        if self.trendWindowDays < 1:
            raise AIConfigurationError("aiFeedbackTrendWindowDays must be positive.")
        if self.retentionDays < 1:
            raise AIConfigurationError("aiFeedbackRetentionDays must be positive.")
        if not str(self.goldenSuiteCode or "").strip():
            raise AIConfigurationError("aiFeedbackGoldenSuite must not be empty.")
        # Building the policy here means an impossible configuration fails
        # at construction, not on the first promotion sweep.
        self.policy()

    def policy(self) -> FeedbackPolicy:
        return FeedbackPolicy(
            promotionThreshold=self.promotionThreshold,
            requireCorrection=self.requireCorrection,
            requireReason=self.requireReason,
            negativeRatingCeiling=self.negativeRatingCeiling,
            minimumSatisfaction=self.minimumSatisfaction,
            trendTolerance=self.trendTolerance,
        )

    @classmethod
    def fromDjangoSettings(cls) -> FeedbackSettings:
        return cls(
            enabled=bool(getattr(djangoSettings, "AI_FEEDBACK_ENABLED", True)),
            promotionThreshold=int(
                getattr(djangoSettings, "AI_FEEDBACK_PROMOTION_THRESHOLD", 2) or 2
            ),
            requireCorrection=bool(getattr(djangoSettings, "AI_FEEDBACK_REQUIRE_CORRECTION", True)),
            requireReason=bool(getattr(djangoSettings, "AI_FEEDBACK_REQUIRE_REASON", True)),
            negativeRatingCeiling=int(
                getattr(djangoSettings, "AI_FEEDBACK_NEGATIVE_RATING_CEILING", 2) or 2
            ),
            minimumSatisfaction=float(
                getattr(djangoSettings, "AI_FEEDBACK_MIN_SATISFACTION", 0.6) or 0.6
            ),
            trendTolerance=float(
                getattr(djangoSettings, "AI_FEEDBACK_TREND_TOLERANCE", 0.05) or 0.05
            ),
            trendWindowDays=int(getattr(djangoSettings, "AI_FEEDBACK_TREND_WINDOW_DAYS", 7) or 7),
            autoPromote=bool(getattr(djangoSettings, "AI_FEEDBACK_AUTO_PROMOTE", False)),
            goldenSuiteCode=str(
                getattr(djangoSettings, "AI_FEEDBACK_GOLDEN_SUITE", DEFAULT_FEEDBACK_SUITE)
                or DEFAULT_FEEDBACK_SUITE
            ),
            retentionDays=int(getattr(djangoSettings, "AI_FEEDBACK_RETENTION_DAYS", 730) or 730),
        )


@dataclass(frozen=True)
class SubmitFeedbackCommand:
    """One human signal about one AI answer (§V.5)."""

    requestId: uuid.UUID
    kind: str = "RATING"
    responseId: uuid.UUID | None = None
    userId: uuid.UUID | None = None
    rating: int | None = None
    sentiment: str = ""
    reason: str = ""
    comment: str = ""
    correction: str = ""
    question: str = ""
    modelCode: str = ""
    promptVersion: str = ""
    capabilityCode: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FeedbackDescriptor:
    """Safe read model of one signal."""

    feedbackId: uuid.UUID
    tenantId: uuid.UUID
    requestId: uuid.UUID
    responseId: uuid.UUID | None
    kind: str
    rating: int | None
    sentiment: str
    reason: str
    status: str
    targetKey: str
    modelCode: str
    promptVersion: str
    suggestedMetric: str
    promotedCaseCode: str
    rejectionReason: str
    hasCorrection: bool
    userId: uuid.UUID | None
    createdAt: datetime
    updatedAt: datetime

    @classmethod
    def of(cls, entry: AIFeedbackEntry) -> FeedbackDescriptor:
        return cls(
            feedbackId=entry.id,
            tenantId=entry.tenantId,
            requestId=entry.requestId,
            responseId=entry.responseId,
            kind=entry.kind,
            rating=entry.rating,
            sentiment=entry.sentiment,
            reason=entry.reason,
            status=entry.status,
            targetKey=entry.targetKey,
            modelCode=entry.modelCode,
            promptVersion=entry.promptVersion,
            suggestedMetric=entry.suggestedMetric(),
            promotedCaseCode=entry.promotedCaseCode,
            rejectionReason=entry.rejectionReason,
            hasCorrection=bool(entry.correction),
            userId=entry.userId,
            createdAt=entry.createdAt,
            updatedAt=entry.updatedAt,
        )


@dataclass(frozen=True)
class SubmissionResult:
    """Outcome of a submission: was it a new signal or a revision?"""

    feedback: FeedbackDescriptor
    created: bool
    revised: bool = False

    @property
    def isDuplicate(self) -> bool:
        return not self.created and not self.revised


@dataclass(frozen=True)
class PromotionResult:
    """What a promotion sweep produced (§V.8)."""

    promotedCases: tuple[str, ...]
    plan: PromotionPlan
    promotedFeedbackIds: tuple[uuid.UUID, ...] = ()

    @property
    def promotedCount(self) -> int:
        return len(self.promotedCases)


class FeedbackApplicationService:
    """Tenant-scoped facade for collecting, triaging, and promoting feedback."""

    def __init__(
        self,
        store: FeedbackStore,
        *,
        casePublisher: GoldenCasePublisher | None = None,
        settings: FeedbackSettings | None = None,
        auditLogger: FeedbackAuditLogger | None = None,
        aggregator: FeedbackAggregator | None = None,
        planner: PromotionPlanner | None = None,
        comparer: TrendComparer | None = None,
        now: Any = utcNow,
    ) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self.store = store
        self.casePublisher = casePublisher
        self.settings = settings or FeedbackSettings()
        self.auditLogger = auditLogger
        self.aggregator = aggregator or FeedbackAggregator()
        self.planner = planner or PromotionPlanner()
        self.comparer = comparer or TrendComparer()
        self._now = now

    # ------------------------------------------------------------------
    # Submission (§V.5)
    # ------------------------------------------------------------------
    def submitFeedback(
        self, tenantId: uuid.UUID | str, command: SubmitFeedbackCommand
    ) -> SubmissionResult:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(command, SubmitFeedbackCommand):
            raise AIFeedbackInvalid("Submitting requires a SubmitFeedbackCommand.")
        kind = ensureFeedbackKind(command.kind)
        fingerprint = feedbackFingerprint(
            command.requestId, command.userId, kind, responseId=command.responseId
        )
        moment = self._now()

        existing = self.store.findByFingerprint(tenant, fingerprint)
        if existing is not None:
            if existing.isTerminal:
                return SubmissionResult(
                    feedback=FeedbackDescriptor.of(existing), created=False, revised=False
                )
            before = (existing.rating, existing.sentiment, existing.reason, existing.correction)
            existing.revise(
                rating=command.rating,
                sentiment=command.sentiment,
                reason=command.reason,
                comment=command.comment,
                correction=command.correction,
                now=moment,
            )
            after = (existing.rating, existing.sentiment, existing.reason, existing.correction)
            if before == after:
                return SubmissionResult(
                    feedback=FeedbackDescriptor.of(existing), created=False, revised=False
                )
            stored = self.store.updateEntry(existing)
            self._audit(
                tenant,
                AUDIT_FEEDBACK_RECEIVED,
                outcome="UPDATED",
                actorId=stored.userId,
                contextSources=(stored.targetKey,),
                detail={"feedbackId": str(stored.id), "revision": True},
            )
            return SubmissionResult(
                feedback=FeedbackDescriptor.of(stored), created=False, revised=True
            )

        entry = AIFeedbackEntry(
            tenantId=tenant,
            requestId=command.requestId,
            kind=kind,
            responseId=command.responseId,
            userId=command.userId,
            rating=command.rating,
            sentiment=command.sentiment,
            reason=command.reason,
            comment=command.comment,
            correction=command.correction,
            question=command.question,
            modelCode=command.modelCode,
            promptVersion=command.promptVersion,
            capabilityCode=command.capabilityCode,
            suiteCode=self.settings.goldenSuiteCode,
            fingerprint=fingerprint,
            metadata=dict(command.metadata),
            createdAt=moment,
            updatedAt=moment,
        )
        stored = self.store.saveEntry(entry)
        self._audit(
            tenant,
            AUDIT_FEEDBACK_RECEIVED,
            outcome="RECORDED",
            actorId=stored.userId,
            contextSources=(stored.targetKey,),
            detail={
                "feedbackId": str(stored.id),
                "kind": stored.kind,
                "sentiment": stored.sentiment,
                "reason": stored.reason,
            },
        )
        return SubmissionResult(feedback=FeedbackDescriptor.of(stored), created=True)

    # ------------------------------------------------------------------
    # Triage (§V.6)
    # ------------------------------------------------------------------
    def acceptFeedback(
        self,
        tenantId: uuid.UUID | str,
        feedbackId: uuid.UUID | str,
        *,
        reviewerId: uuid.UUID | str | None = None,
    ) -> FeedbackDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        entry = self._requireEntry(tenant, feedbackId)
        entry.accept(reviewerId=reviewerId, now=self._now())
        stored = self.store.updateEntry(entry)
        self._auditTriage(tenant, stored, "ALLOWED")
        return FeedbackDescriptor.of(stored)

    def rejectFeedback(
        self,
        tenantId: uuid.UUID | str,
        feedbackId: uuid.UUID | str,
        reason: str,
        *,
        reviewerId: uuid.UUID | str | None = None,
    ) -> FeedbackDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        entry = self._requireEntry(tenant, feedbackId)
        entry.reject(reason, reviewerId=reviewerId, now=self._now())
        stored = self.store.updateEntry(entry)
        self._auditTriage(tenant, stored, "DENIED")
        return FeedbackDescriptor.of(stored)

    # ------------------------------------------------------------------
    # Promotion (§V.8)
    # ------------------------------------------------------------------
    def planPromotions(
        self, tenantId: uuid.UUID | str, *, knownQuestions: Sequence[str] = ()
    ) -> PromotionPlan:
        """Dry run: what would a sweep promote right now?"""

        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        entries = self.store.listEntries(
            tenant, statuses=("NEW", "TRIAGED", "ACCEPTED"), limit=1000
        )
        return self.planner.plan(
            entries,
            self.settings.policy(),
            suiteCode=self.settings.goldenSuiteCode,
            knownQuestions=knownQuestions,
        )

    def promoteFeedback(
        self,
        tenantId: uuid.UUID | str,
        feedbackId: uuid.UUID | str,
        *,
        caseCode: str = "",
        suiteCode: str = "",
    ) -> FeedbackDescriptor:
        """Promote one accepted signal into a golden case."""

        tenant = requireUuid(tenantId, "tenantId")
        entry = self._requireEntry(tenant, feedbackId)
        policy = self.settings.policy()
        if not entry.isPromotable(policy):
            raise AIFeedbackNotPromotable("This signal does not satisfy the promotion policy.")
        draft = entry.toGoldenCaseDraft(
            suiteCode=suiteCode or self.settings.goldenSuiteCode, caseCode=caseCode
        )
        self._publishCase(tenant, draft)
        entry.promote(draft["caseCode"], suiteCode=draft["suiteCode"], now=self._now())
        stored = self.store.updateEntry(entry)
        self._audit(
            tenant,
            AUDIT_FEEDBACK_PROMOTED,
            outcome="RECORDED",
            contextSources=(f"{draft['suiteCode']}:{draft['caseCode']}",),
            detail={
                "feedbackId": str(stored.id),
                "caseCode": stored.promotedCaseCode,
                "reason": stored.reason,
                "metric": stored.suggestedMetric(),
            },
        )
        return FeedbackDescriptor.of(stored)

    def runPromotionSweep(
        self, tenantId: uuid.UUID | str, *, knownQuestions: Sequence[str] = ()
    ) -> PromotionResult:
        """Promote every complaint that clears the policy, in one pass."""

        tenant = requireUuid(tenantId, "tenantId")
        plan = self.planPromotions(tenant, knownQuestions=knownQuestions)
        promotedCases: list[str] = []
        promotedIds: list[uuid.UUID] = []
        for draft in plan.drafts:
            self._publishCase(
                tenant,
                {
                    "suiteCode": draft.suiteCode,
                    "caseCode": draft.caseCode,
                    "question": draft.question,
                    "expectedTerms": draft.expectedTerms,
                    "metadata": dict(draft.metadata),
                },
            )
            promotedCases.append(draft.caseCode)
            for feedbackId in draft.feedbackIds:
                entry = self.store.getEntry(tenant, requireUuid(feedbackId, "feedbackId"))
                if entry is None or entry.isTerminal:
                    continue
                entry.promote(draft.caseCode, suiteCode=draft.suiteCode, now=self._now())
                self.store.updateEntry(entry)
                promotedIds.append(entry.id)
            self._audit(
                tenant,
                AUDIT_FEEDBACK_PROMOTED,
                outcome="RECORDED",
                contextSources=(f"{draft.suiteCode}:{draft.caseCode}",),
                detail={
                    "caseCode": draft.caseCode,
                    "occurrences": draft.occurrences,
                    "reason": draft.reason,
                    "metric": draft.metric,
                },
            )
        return PromotionResult(
            promotedCases=tuple(promotedCases),
            plan=plan,
            promotedFeedbackIds=tuple(promotedIds),
        )

    # ------------------------------------------------------------------
    # Reads and trends (§V.7)
    # ------------------------------------------------------------------
    def describeFeedback(
        self, tenantId: uuid.UUID | str, feedbackId: uuid.UUID | str
    ) -> FeedbackDescriptor:
        return FeedbackDescriptor.of(
            self._requireEntry(requireUuid(tenantId, "tenantId"), feedbackId)
        )

    def listFeedback(
        self,
        tenantId: uuid.UUID | str,
        *,
        statuses: tuple[str, ...] = (),
        sentiments: tuple[str, ...] = (),
        requestId: uuid.UUID | str | None = None,
        modelCode: str = "",
        limit: int = 200,
    ) -> tuple[FeedbackDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        entries = self.store.listEntries(
            tenant,
            statuses=tuple(ensureFeedbackStatus(value) for value in statuses),
            sentiments=tuple(ensureSentiment(value) for value in sentiments),
            requestId=None if requestId is None else requireUuid(requestId, "requestId"),
            modelCode=str(modelCode or "").strip().upper(),
            limit=limit,
        )
        return tuple(FeedbackDescriptor.of(entry) for entry in entries)

    def summarize(
        self,
        tenantId: uuid.UUID | str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        modelCode: str = "",
        limit: int = 1000,
    ) -> FeedbackSummary:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        entries = self.store.listEntries(
            tenant,
            since=since,
            until=until,
            modelCode=str(modelCode or "").strip().upper(),
            limit=limit,
        )
        return self.aggregator.summarize(entries)

    def compareWindows(
        self,
        tenantId: uuid.UUID | str,
        *,
        windowDays: int | None = None,
        now: datetime | None = None,
        modelCode: str = "",
    ) -> SatisfactionTrend:
        """Compare the last window against the one before it (§V.7)."""

        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        days = self.settings.trendWindowDays if windowDays is None else int(windowDays)
        if days < 1:
            raise AIFeedbackInvalid("The trend window must be at least one day.")
        moment = now or self._now()
        currentStart = moment - timedelta(days=days)
        baselineStart = currentStart - timedelta(days=days)
        baseline = self.aggregator.summarize(
            self.store.listEntries(
                tenant, since=baselineStart, until=currentStart, modelCode=modelCode, limit=1000
            )
        )
        candidate = self.aggregator.summarize(
            self.store.listEntries(
                tenant, since=currentStart, until=moment, modelCode=modelCode, limit=1000
            )
        )
        return self.comparer.compare(baseline, candidate, self.settings.policy())

    def triageBacklog(self, tenantId: uuid.UUID | str) -> dict[str, int]:
        """How much feedback is waiting in each state."""

        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        return self.store.countByStatus(tenant)

    def purgeFeedbackRetention(
        self,
        tenantId: uuid.UUID | str | None = None,
        *,
        retentionDays: int | None = None,
        now: datetime | None = None,
    ) -> int:
        """Delete settled signals older than the horizon (§46)."""

        self._requireEnabled()
        tenant = None if tenantId is None else requireUuid(tenantId, "tenantId")
        days = self.settings.retentionDays if retentionDays is None else int(retentionDays)
        if days < 1:
            raise AIConfigurationError("Feedback retention must be at least one day.")
        cutoff = (now or self._now()) - timedelta(days=days)
        return self.store.deleteEntriesBefore(tenant, cutoff)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _publishCase(self, tenant: uuid.UUID, draft: dict[str, Any]) -> None:
        if self.casePublisher is None:
            raise AIConfigurationError("Promoting feedback requires a golden case publisher.")
        from apps.ai.application.services.evaluationService import RegisterCaseCommand

        self.casePublisher.registerCase(
            tenant,
            RegisterCaseCommand(
                suiteCode=draft["suiteCode"],
                caseCode=draft["caseCode"],
                question=draft["question"],
                expectedTerms=tuple(draft["expectedTerms"]),
                metadata=dict(draft.get("metadata", {})),
                replace=True,
            ),
        )

    def _requireEntry(self, tenant: uuid.UUID, feedbackId: uuid.UUID | str) -> AIFeedbackEntry:
        self._requireEnabled()
        entry = self.store.getEntry(tenant, requireUuid(feedbackId, "feedbackId"))
        if entry is None or entry.tenantId != tenant:
            raise AIFeedbackNotFound(str(feedbackId))
        return entry

    def _requireEnabled(self) -> None:
        if not self.settings.enabled:
            raise AIConfigurationError("The AI feedback platform is disabled.")

    def _auditTriage(self, tenant: uuid.UUID, entry: AIFeedbackEntry, outcome: str) -> None:
        self._audit(
            tenant,
            AUDIT_FEEDBACK_TRIAGED,
            outcome=outcome,
            actorId=entry.triagedBy,
            contextSources=(entry.targetKey,),
            detail={
                "feedbackId": str(entry.id),
                "status": entry.status,
                "reason": entry.reason or entry.rejectionReason,
            },
        )

    def _audit(self, tenant: uuid.UUID, action: str, **kwargs: Any) -> None:
        if self.auditLogger is None:
            return
        self.auditLogger.logAudit(tenant, action, **kwargs)


class FeedbackPromotionJobHandler:
    """Phase 13-P handler for the ``FEEDBACK`` job kind (§V.13).

    Payload contract::

        {"knownQuestions": ["..."], "purge": false, "retentionDays": 730}

    The sweep is idempotent: a complaint already promoted is terminal and
    is skipped on the next pass.
    """

    JOB_KIND = "FEEDBACK"

    def __init__(self, service: FeedbackApplicationService) -> None:
        self.service = service

    def kind(self) -> str:
        return self.JOB_KIND

    def execute(self, job: Any) -> Any:
        from apps.ai.domain.services.jobQueue import JobOutcome

        payload = dict(getattr(job, "payload", {}) or {})
        rawQuestions = payload.get("knownQuestions", [])
        if not isinstance(rawQuestions, list):
            raise AIFeedbackInvalid("Feedback job knownQuestions must be a list.")
        result = self.service.runPromotionSweep(
            job.tenantId, knownQuestions=tuple(str(item) for item in rawQuestions)
        )
        purged = 0
        if bool(payload.get("purge", False)):
            purged = self.service.purgeFeedbackRetention(
                job.tenantId, retentionDays=payload.get("retentionDays")
            )
        return JobOutcome(
            outcome="SUCCEEDED",
            summary={
                "promoted": result.promotedCount,
                "cases": list(result.promotedCases),
                "skipped": result.plan.skippedCount,
                "purged": purged,
            },
        )


__all__ = [
    "AUDIT_FEEDBACK_PROMOTED",
    "AUDIT_FEEDBACK_RECEIVED",
    "AUDIT_FEEDBACK_TRIAGED",
    "DEFAULT_FEEDBACK_SUITE",
    "FeedbackApplicationService",
    "FeedbackDescriptor",
    "FeedbackPromotionJobHandler",
    "FeedbackSettings",
    "PromotionResult",
    "SubmissionResult",
    "SubmitFeedbackCommand",
]
