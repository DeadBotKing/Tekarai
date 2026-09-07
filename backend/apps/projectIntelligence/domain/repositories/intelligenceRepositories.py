"""Ports for Project Intelligence persistence, analysis, storage and jobs."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from apps.projectIntelligence.domain.entities.intelligenceRecords import (
    ProjectSnapshot,
    ProjectState,
)


class ProjectSnapshotRepository(Protocol):
    def nextSnapshotVersion(self, tenantId: uuid.UUID, projectId: uuid.UUID) -> int: ...
    def saveSnapshot(self, snapshot: ProjectSnapshot) -> None: ...
    def saveSnapshotBundle(self, snapshot: ProjectSnapshot) -> None: ...
    def latestSnapshot(self, tenantId: uuid.UUID, projectId: uuid.UUID) -> dict | None: ...
    def snapshotById(
        self, tenantId: uuid.UUID, projectId: uuid.UUID, snapshotId: uuid.UUID
    ) -> dict | None: ...


class ProjectAnalysisRepository(Protocol):
    def saveAnalysis(
        self, tenantId: uuid.UUID, projectId: uuid.UUID, snapshotId: uuid.UUID, data: dict
    ) -> dict: ...


class ProjectKnowledgeRepository(Protocol):
    def saveKnowledge(
        self, tenantId: uuid.UUID, projectId: uuid.UUID, analysisId: uuid.UUID, data: dict
    ) -> dict: ...


class ProjectInsightRepository(Protocol):
    def saveInsights(
        self, tenantId: uuid.UUID, projectId: uuid.UUID, knowledgeId: uuid.UUID, items: list[dict]
    ) -> list[dict]: ...


class ProjectRecommendationRepository(Protocol):
    def saveRecommendations(
        self, tenantId: uuid.UUID, projectId: uuid.UUID, items: list[dict]
    ) -> list[dict]: ...


class ProjectDecisionRepository(Protocol):
    def saveDecisions(
        self, tenantId: uuid.UUID, projectId: uuid.UUID, items: list[dict]
    ) -> list[dict]: ...


class ProjectContextRepository(Protocol):
    def saveContext(self, tenantId: uuid.UUID, projectId: uuid.UUID, data: dict) -> dict: ...


class ProjectStateRepository(Protocol):
    def getOrCreateState(
        self, tenantId: uuid.UUID, projectId: uuid.UUID, now: datetime
    ) -> ProjectState: ...
    def saveState(self, state: ProjectState) -> None: ...


class IntelligenceStore(
    ProjectSnapshotRepository,
    ProjectAnalysisRepository,
    ProjectKnowledgeRepository,
    ProjectInsightRepository,
    ProjectRecommendationRepository,
    ProjectDecisionRepository,
    ProjectContextRepository,
    ProjectStateRepository,
    Protocol,
):
    def saveFiles(self, snapshot: ProjectSnapshot) -> None: ...
    def saveChanges(
        self,
        tenantId: uuid.UUID,
        projectId: uuid.UUID,
        fromId: uuid.UUID | None,
        toId: uuid.UUID,
        data: dict,
    ) -> dict: ...
    def saveResume(self, tenantId: uuid.UUID, projectId: uuid.UUID, data: dict) -> dict: ...
    def createJob(
        self, tenantId: uuid.UUID, projectId: uuid.UUID, actorId: uuid.UUID, data: dict
    ) -> dict: ...
    def claimJob(self, jobId: uuid.UUID, now: datetime) -> dict | None: ...
    def finishJob(
        self, jobId: uuid.UUID, now: datetime, *, result: dict | None = None, error: str = ""
    ) -> dict: ...
    def retryJob(self, jobId: uuid.UUID, errorType: str) -> dict: ...
    def getJob(self, tenantId: uuid.UUID, jobId: uuid.UUID) -> dict | None: ...
    def projectData(self, tenantId: uuid.UUID, projectId: uuid.UUID, kind: str) -> Any: ...
    def audit(
        self,
        tenantId: uuid.UUID,
        actorId: uuid.UUID,
        projectId: uuid.UUID,
        action: str,
        metadata: dict,
    ) -> None: ...


class WorkspaceReader(Protocol):
    def resolve(self, relativePath: str) -> Path: ...
    def scan(
        self, relativePath: str, previousFiles: tuple[dict[str, Any], ...] = ()
    ) -> tuple[dict[str, Any], ...]: ...


class GitReader(Protocol):
    def inspect(self, workspace: Path) -> dict[str, Any]: ...


class SnapshotStorage(Protocol):
    def put(
        self, tenantId: uuid.UUID, projectId: uuid.UUID, snapshotId: uuid.UUID, payload: dict
    ) -> tuple[str, str]: ...
    def verify(self, uri: str, checksum: str) -> bool: ...


class AnalysisCache(Protocol):
    def get(self, key: str) -> dict | None: ...
    def put(self, key: str, value: dict) -> None: ...


class Analyzer(Protocol):
    name: str
    version: str

    def analyze(self, snapshot: dict[str, Any]) -> dict[str, Any]: ...


class IntelligenceJobQueue(Protocol):
    def publish(self, jobId: uuid.UUID) -> None: ...
