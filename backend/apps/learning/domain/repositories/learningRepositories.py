"""Phase 16 repository and engine ports."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from apps.learning.domain.entities.learningRecords import (
    LearningArtifact,
    LearningDataset,
    LearningDeployment,
    LearningExperience,
    LearningExperiment,
)


# Fine-grained ports named by the Phase 16 contract. ``LearningStore`` below
# is the transactional composition used by application services; alternative
# infrastructures may implement these ports separately.
class ExperienceRepository(Protocol):
    def saveExperience(self, experience: LearningExperience) -> None: ...


class DatasetRepository(Protocol):
    def saveDataset(self, dataset: LearningDataset) -> None: ...


class ExperimentRepository(Protocol):
    def saveExperiment(self, experiment: LearningExperiment) -> None: ...


class ArtifactRepository(Protocol):
    def saveArtifact(self, artifact: LearningArtifact) -> None: ...


class EvaluationRepository(Protocol):
    def saveEvaluation(self, tenantId: uuid.UUID, artifactId: uuid.UUID, result: dict) -> dict: ...


class ValidationRepository(Protocol):
    def saveValidation(self, tenantId: uuid.UUID, artifactId: uuid.UUID, result: dict) -> dict: ...


class DeploymentRepository(Protocol):
    def saveDeployment(self, deployment: LearningDeployment) -> None: ...


class FeedbackRepository(Protocol):
    def saveFeedback(self, tenantId: uuid.UUID, actorId: uuid.UUID | None, data: dict) -> dict: ...


class DatasetStorage(Protocol):
    def putDataset(
        self, tenantId: uuid.UUID, datasetId: uuid.UUID, version: str, content: bytes
    ) -> tuple[str, str]: ...


class MetricCollector(Protocol):
    def recordMetrics(
        self,
        tenantId: uuid.UUID,
        artifactId: uuid.UUID,
        deploymentId: uuid.UUID | None,
        metrics: dict[str, float],
        now: datetime,
    ) -> dict: ...


class LearningStore(Protocol):
    def saveExperience(self, experience: LearningExperience) -> None: ...
    def listExperiences(self, tenantId: uuid.UUID, *, limit: int = 100) -> tuple[dict, ...]: ...
    def experienceExists(self, tenantId: uuid.UUID, experienceId: uuid.UUID) -> bool: ...
    def saveDataset(self, dataset: LearningDataset) -> None: ...
    def getDataset(self, tenantId: uuid.UUID, datasetId: uuid.UUID) -> LearningDataset | None: ...
    def listDatasets(self, tenantId: uuid.UUID) -> tuple[dict, ...]: ...
    def addSamples(
        self, tenantId: uuid.UUID, datasetId: uuid.UUID, samples: tuple[dict, ...]
    ) -> int: ...
    def datasetSamples(self, tenantId: uuid.UUID, datasetId: uuid.UUID) -> tuple[dict, ...]: ...
    def saveExperiment(self, experiment: LearningExperiment) -> None: ...
    def getExperiment(
        self, tenantId: uuid.UUID, experimentId: uuid.UUID
    ) -> LearningExperiment | None: ...
    def listExperiments(self, tenantId: uuid.UUID) -> tuple[dict, ...]: ...
    def createRun(self, tenantId: uuid.UUID, experimentId: uuid.UUID, details: dict) -> dict: ...
    def updateRun(self, tenantId: uuid.UUID, runId: uuid.UUID, **changes: Any) -> None: ...
    def saveArtifact(self, artifact: LearningArtifact) -> None: ...
    def getArtifact(
        self, tenantId: uuid.UUID, artifactId: uuid.UUID
    ) -> LearningArtifact | None: ...
    def listArtifacts(self, tenantId: uuid.UUID) -> tuple[dict, ...]: ...
    def latestArtifactVersion(self, tenantId: uuid.UUID, name: str) -> str | None: ...
    def saveEvaluation(self, tenantId: uuid.UUID, artifactId: uuid.UUID, result: dict) -> dict: ...
    def latestEvaluation(self, tenantId: uuid.UUID, artifactId: uuid.UUID) -> dict | None: ...
    def saveValidation(self, tenantId: uuid.UUID, artifactId: uuid.UUID, result: dict) -> dict: ...
    def latestValidation(self, tenantId: uuid.UUID, artifactId: uuid.UUID) -> dict | None: ...
    def saveApproval(
        self,
        tenantId: uuid.UUID,
        artifactId: uuid.UUID,
        reviewerId: uuid.UUID,
        decision: str,
        reason: str,
        now: datetime,
    ) -> dict: ...
    def saveDeployment(self, deployment: LearningDeployment) -> None: ...
    def getDeployment(
        self, tenantId: uuid.UUID, deploymentId: uuid.UUID
    ) -> LearningDeployment | None: ...
    def activeDeployment(
        self, tenantId: uuid.UUID, environment: str, artifactName: str
    ) -> dict | None: ...
    def listDeployments(self, tenantId: uuid.UUID) -> tuple[dict, ...]: ...
    def markDeploymentStatus(
        self,
        tenantId: uuid.UUID,
        deploymentId: uuid.UUID,
        status: str,
        completedAt: datetime | None = None,
        rollbackReason: str = "",
    ) -> None: ...
    def saveFeedback(self, tenantId: uuid.UUID, actorId: uuid.UUID | None, data: dict) -> dict: ...
    def recordMetrics(
        self,
        tenantId: uuid.UUID,
        artifactId: uuid.UUID,
        deploymentId: uuid.UUID | None,
        metrics: dict[str, float],
        now: datetime,
    ) -> dict: ...
    def latestMetrics(self, tenantId: uuid.UUID, artifactId: uuid.UUID) -> dict[str, float]: ...
    def metricSummary(self, tenantId: uuid.UUID) -> dict: ...
    def createJob(
        self,
        tenantId: uuid.UUID,
        experimentId: uuid.UUID,
        actorId: uuid.UUID,
        priority: str,
        idempotencyKey: str,
        now: datetime,
    ) -> dict: ...
    def getJob(self, tenantId: uuid.UUID, jobId: uuid.UUID) -> dict | None: ...
    def findJob(self, jobId: uuid.UUID) -> dict | None: ...
    def updateJob(self, tenantId: uuid.UUID, jobId: uuid.UUID, **changes: Any) -> None: ...
    def appendEvent(
        self,
        tenantId: uuid.UUID,
        eventType: str,
        targetType: str,
        targetId: str,
        data: dict,
        now: datetime,
    ) -> None: ...
    def snapshot(
        self,
        tenantId: uuid.UUID,
        deploymentId: uuid.UUID,
        state: dict,
        checksum: str,
        now: datetime,
    ) -> dict: ...


class ModelStorage(Protocol):
    def putImmutable(
        self, tenantId: uuid.UUID, name: str, version: str, content: bytes
    ) -> tuple[str, str]: ...
    def verify(self, uri: str, checksum: str) -> bool: ...
    def read(self, uri: str) -> bytes: ...


class FeatureExtractor(Protocol):
    def extract(self, samples: tuple[dict, ...]) -> tuple[dict, ...]: ...


class LearningEngine(Protocol):
    def train(
        self, *, samples: tuple[dict, ...], algorithm: str, configuration: dict, seed: int
    ) -> tuple[bytes, dict[str, float]]: ...


class EvaluationEngine(Protocol):
    def evaluate(
        self,
        *,
        artifactContent: bytes,
        samples: tuple[dict, ...],
        trainingMetrics: dict[str, float],
    ) -> dict[str, float]: ...


class ValidationEngine(Protocol):
    def validate(
        self,
        *,
        candidate: dict[str, float],
        baseline: dict[str, float],
        policy: dict,
        integrityValid: bool,
    ) -> tuple[bool, list[dict[str, Any]]]: ...


class DeploymentEngine(Protocol):
    def apply(self, *, artifactUri: str, environment: str, trafficPercentage: int) -> None: ...
    def deactivate(self, *, artifactUri: str, environment: str) -> None: ...


class DriftDetector(Protocol):
    def detect(
        self, *, baseline: dict[str, float], current: dict[str, float], thresholds: dict[str, float]
    ) -> tuple[bool, dict[str, float]]: ...


class LearningJobQueue(Protocol):
    def publish(self, jobId: str) -> None: ...
