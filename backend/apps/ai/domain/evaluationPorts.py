"""Evaluation port interfaces for Phase 13-U.

Minimal contracts the application layer depends on:

- ``EvaluationCaseStore`` / ``EvaluationRunStore`` — persistence of the
  golden cases and of the runs and their per-case results;
- ``AnswerProducer`` — the thing under test. Any callable object that can
  turn a case into a ``CaseObservation`` satisfies it, which is what lets
  the same suite grade a RAG pipeline (Phase 13-S), a bare provider call,
  or a future agent without U knowing about any of them;
- ``EvaluationAuditLogger`` — the single Phase 13-O ledger append.

``datetime`` and ``uuid`` are typing-only; the module has no Django, ORM,
HTTP, provider SDK, Redis, queue, or network dependency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from apps.ai.domain.entities.evaluationRecords import (
    AIEvaluationCase,
    AIEvaluationResult,
    AIEvaluationRun,
)


class EvaluationCaseStore(Protocol):
    """Persistence contract for golden cases."""

    def saveCase(self, case: AIEvaluationCase) -> AIEvaluationCase: ...
    def updateCase(self, case: AIEvaluationCase) -> AIEvaluationCase: ...
    def getCase(self, tenantId: UUID, caseId: UUID) -> AIEvaluationCase | None: ...
    def findCase(
        self, tenantId: UUID, suiteCode: str, caseCode: str
    ) -> AIEvaluationCase | None: ...
    def listCases(
        self, tenantId: UUID, suiteCode: str = "", *, activeOnly: bool = True
    ) -> tuple[AIEvaluationCase, ...]: ...
    def listSuites(self, tenantId: UUID) -> tuple[str, ...]: ...
    def deleteCase(self, tenantId: UUID, caseId: UUID) -> int: ...


class EvaluationRunStore(Protocol):
    """Persistence contract for runs and their results."""

    def saveRun(self, run: AIEvaluationRun) -> AIEvaluationRun: ...
    def updateRun(self, run: AIEvaluationRun) -> AIEvaluationRun: ...
    def getRun(self, tenantId: UUID, runId: UUID) -> AIEvaluationRun | None: ...
    def listRuns(
        self, tenantId: UUID, suiteCode: str = "", *, limit: int = 50
    ) -> tuple[AIEvaluationRun, ...]: ...
    def latestRun(
        self, tenantId: UUID, suiteCode: str, *, excludeRunId: UUID | None = None
    ) -> AIEvaluationRun | None: ...
    def saveResults(
        self, results: tuple[AIEvaluationResult, ...]
    ) -> tuple[AIEvaluationResult, ...]: ...
    def listResults(self, tenantId: UUID, runId: UUID) -> tuple[AIEvaluationResult, ...]: ...
    def deleteRunsBefore(self, tenantId: UUID | None, cutoff: datetime) -> int: ...


class AnswerProducer(Protocol):
    """The subject under evaluation: a case in, an observation out."""

    def produce(self, tenantId: Any, case: Any) -> Any: ...


class EvaluationAuditLogger(Protocol):
    """The single Phase 13-O entry point U needs (one ledger append)."""

    def logAudit(
        self,
        tenantId: Any,
        action: str,
        *,
        outcome: str = ...,
        errorCode: str = ...,
        actorId: Any = ...,
        contextSources: tuple[str, ...] | list[str] | None = ...,
        detail: dict[str, Any] | None = ...,
    ) -> Any: ...


__all__ = [
    "AnswerProducer",
    "EvaluationAuditLogger",
    "EvaluationCaseStore",
    "EvaluationRunStore",
]
