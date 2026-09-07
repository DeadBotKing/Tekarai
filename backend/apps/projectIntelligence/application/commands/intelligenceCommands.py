"""Immutable Phase 17 application messages."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateSnapshotCommand:
    projectId: str
    workspace: str = "."


@dataclass(frozen=True, slots=True)
class AnalyzeProjectCommand:
    projectId: str
    workspace: str = "."
    incremental: bool = False
    idempotencyKey: str = ""
    priority: int = 5


@dataclass(frozen=True, slots=True)
class ProcessIntelligenceJobCommand:
    jobId: uuid.UUID


@dataclass(frozen=True, slots=True)
class BuildContextCommand:
    projectId: str
    task: str
    tokenBudget: int = 4000


@dataclass(frozen=True, slots=True)
class CompareSnapshotsCommand:
    projectId: str
    fromSnapshotId: str
    toSnapshotId: str = ""


@dataclass(frozen=True, slots=True)
class IntelligenceQuery:
    projectId: str
    kind: str
