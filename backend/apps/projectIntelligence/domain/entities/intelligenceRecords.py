"""Phase 17 aggregates; intentionally independent from Django and I/O."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.projectIntelligence.domain.valueObjects import intelligenceTypes as t
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId
from apps.sharedKernel.domain.errors import ConflictError, ValidationFailedError


class ProjectSnapshot(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,
        tenantId: uuid.UUID,
        projectId: uuid.UUID,
        version: int,
        workspace: str,
        createdAt: datetime,
        files: tuple[dict[str, Any], ...],
        gitState: dict[str, Any],
        environment: dict[str, Any],
        analysisVersion: str,
        snapshotHash: str,
        artifactUri: str = "",
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.projectId = projectId
        self.version = version
        self.workspace = workspace
        self.createdAt = createdAt
        self.files = files
        self.gitState = gitState
        self.environment = environment
        self.analysisVersion = analysisVersion
        self.snapshotHash = snapshotHash
        self.artifactUri = artifactUri

    @staticmethod
    def create(
        tenantId: uuid.UUID,
        projectId: uuid.UUID,
        version: int,
        workspace: str,
        files: tuple[dict[str, Any], ...],
        gitState: dict[str, Any],
        environment: dict[str, Any],
        analysisVersion: str,
        now: datetime,
    ) -> ProjectSnapshot:
        logical = {
            "projectId": str(projectId),
            "workspace": workspace,
            "files": files,
            "gitState": gitState,
            "environment": environment,
            "analysisVersion": analysisVersion,
        }
        item = ProjectSnapshot(
            newId(),
            tenantId,
            projectId,
            version,
            workspace,
            now,
            files,
            gitState,
            environment,
            analysisVersion,
            t.integrityHash(logical),
        )
        item.recordEvent(
            DomainEvent(
                name="ProjectSnapshotCreated",
                occurredAt=now,
                tenantId=tenantId,
                payload={
                    "projectId": str(projectId),
                    "snapshotId": str(item.id),
                    "version": version,
                },
            )
        )
        return item


class ProjectState(AggregateRoot):
    transitions = {
        "INITIALIZING": ("SCANNING", "ERROR"),
        "SCANNING": ("ANALYZING", "CHANGED", "ERROR"),
        "ANALYZING": ("READY", "ERROR"),
        "READY": ("CHANGED", "STALE", "SCANNING", "ERROR"),
        "CHANGED": ("SCANNING", "ANALYZING", "ERROR"),
        "STALE": ("SCANNING", "ERROR"),
        "ERROR": ("SCANNING",),
    }

    def __init__(
        self,
        id: uuid.UUID,
        tenantId: uuid.UUID,
        projectId: uuid.UUID,
        status: str,
        updatedAt: datetime,
        snapshotId: uuid.UUID | None = None,
        error: str = "",
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.projectId = projectId
        self.status = t.requireChoice(status, t.PROJECT_STATES, "status")
        self.updatedAt = updatedAt
        self.snapshotId = snapshotId
        self.error = error

    def moveTo(
        self, status: str, now: datetime, *, snapshotId: uuid.UUID | None = None, error: str = ""
    ) -> None:
        target = t.requireChoice(status, t.PROJECT_STATES, "status")
        if target not in self.transitions[self.status]:
            raise ConflictError(f"Invalid project state transition {self.status} -> {target}.")
        self.status = target
        self.updatedAt = now
        self.snapshotId = snapshotId or self.snapshotId
        self.error = error[:1000]


class ProjectInsight(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,
        tenantId: uuid.UUID,
        projectId: uuid.UUID,
        knowledgeId: uuid.UUID,
        kind: str,
        title: str,
        severity: str,
        confidence: float,
        evidence: list[dict[str, Any]],
        source: str,
        impact: str,
        createdAt: datetime,
    ) -> None:
        if not evidence:
            raise ValidationFailedError("Insight evidence is required.")
        if not 0 <= confidence <= 1:
            raise ValidationFailedError("Insight confidence must be between 0 and 1.")
        super().__init__(id)
        self.tenantId = tenantId
        self.projectId = projectId
        self.knowledgeId = knowledgeId
        self.kind = kind
        self.title = title
        self.severity = t.requireChoice(severity, t.SEVERITIES, "severity")
        self.confidence = confidence
        self.evidence = evidence
        self.source = source
        self.impact = impact
        self.createdAt = createdAt


class ProjectRecommendation(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,
        tenantId: uuid.UUID,
        projectId: uuid.UUID,
        insightId: uuid.UUID,
        version: int,
        problem: str,
        recommendation: str,
        reason: str,
        evidence: list[dict[str, Any]],
        expectedBenefit: str,
        risk: str,
        priority: str,
        createdAt: datetime,
    ) -> None:
        if not evidence:
            raise ValidationFailedError("Recommendation evidence is required.")
        super().__init__(id)
        self.tenantId = tenantId
        self.projectId = projectId
        self.insightId = insightId
        self.version = version
        self.problem = problem
        self.recommendation = recommendation
        self.reason = reason
        self.evidence = evidence
        self.expectedBenefit = expectedBenefit
        self.risk = risk
        self.priority = t.requireChoice(priority, t.SEVERITIES, "priority")
        self.createdAt = createdAt


class ProjectDecision(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,
        tenantId: uuid.UUID,
        projectId: uuid.UUID,
        recommendationId: uuid.UUID,
        version: int,
        decision: str,
        evidence: list[dict[str, Any]],
        reason: str,
        createdAt: datetime,
    ) -> None:
        if not evidence:
            raise ValidationFailedError("Decision evidence is required.")
        super().__init__(id)
        self.tenantId = tenantId
        self.projectId = projectId
        self.recommendationId = recommendationId
        self.version = version
        self.decision = t.requireChoice(decision, t.DECISIONS, "decision")
        self.evidence = evidence
        self.reason = reason
        self.createdAt = createdAt
