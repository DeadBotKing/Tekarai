"""Transport-neutral Phase 16 commands and queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CreateExperienceCommand:
    source: str
    context: dict[str, Any]
    input: dict[str, Any]
    action: str
    expectedOutcome: dict[str, Any]
    actualOutcome: dict[str, Any]
    traceId: str
    reward: float | None = None
    success: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreateDatasetCommand:
    name: str
    version: str
    source: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildDatasetCommand:
    datasetId: str
    samples: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ValidateDatasetCommand:
    datasetId: str
    minimumSamples: int = 1


@dataclass(frozen=True)
class CreateExperimentCommand:
    name: str
    datasetId: str
    algorithm: str
    description: str = ""
    configuration: dict[str, Any] = field(default_factory=dict)
    baselineArtifactId: str = ""


@dataclass(frozen=True)
class RunExperimentCommand:
    experimentId: str
    idempotencyKey: str
    priority: str = "NORMAL"


@dataclass(frozen=True)
class ProcessLearningJobCommand:
    jobId: str


@dataclass(frozen=True)
class ArtifactActionCommand:
    artifactId: str
    action: str
    reason: str = ""
    environment: str = "PRODUCTION"
    trafficPercentage: int = 0
    policy: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecordFeedbackCommand:
    source: str
    feedbackType: str
    experienceId: str = ""
    deploymentId: str = ""
    artifactId: str = ""
    humanAction: str = ""
    score: float | None = None
    comment: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecordMetricsCommand:
    artifactId: str
    deploymentId: str = ""
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DetectDriftCommand:
    artifactId: str
    baselineMetrics: dict[str, float]
    thresholds: dict[str, float]
    driftType: str = "PERFORMANCE"


@dataclass(frozen=True)
class LearningListQuery:
    resource: str
    limit: int = 100
    identifier: str = ""
