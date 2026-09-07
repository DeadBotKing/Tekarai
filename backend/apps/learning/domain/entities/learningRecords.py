"""Phase 16 domain aggregates. No framework or infrastructure imports."""

from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any

from apps.learning.domain.valueObjects import learningTypes as t
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId
from apps.sharedKernel.domain.errors import ConflictError, ValidationFailedError


class LearningExperience(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,
        tenantId: uuid.UUID,
        source: str,
        context: dict[str, Any],
        inputData: dict[str, Any],
        action: str,
        expectedOutcome: dict[str, Any],
        actualOutcome: dict[str, Any],
        reward: float | None,
        success: bool | None,
        occurredAt: datetime,
        metadata: dict[str, Any],
        traceId: str,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.source = source
        self.context = context
        self.inputData = inputData
        self.action = action
        self.expectedOutcome = expectedOutcome
        self.actualOutcome = actualOutcome
        self.reward = reward
        self.success = success
        self.occurredAt = occurredAt
        self.metadata = metadata
        self.traceId = traceId

    @staticmethod
    def create(
        tenantId: uuid.UUID,
        source: str,
        context: dict[str, Any],
        inputData: dict[str, Any],
        action: str,
        expectedOutcome: dict[str, Any],
        actualOutcome: dict[str, Any],
        now: datetime,
        *,
        reward: float | None = None,
        success: bool | None = None,
        metadata: dict[str, Any] | None = None,
        traceId: str = "",
    ) -> LearningExperience:
        if not source.strip() or not action.strip() or not traceId.strip():
            raise ValidationFailedError("Experience source, action and traceId are required.")
        if reward is not None and not math.isfinite(float(reward)):
            raise ValidationFailedError("Experience reward must be finite.")
        experience = LearningExperience(
            newId(),
            tenantId,
            source.strip(),
            t.safePayload(context),
            t.safePayload(inputData),
            action.strip(),
            t.safePayload(expectedOutcome),
            t.safePayload(actualOutcome),
            reward,
            success,
            now,
            t.safePayload(metadata),
            traceId.strip(),
        )
        experience.recordEvent(
            DomainEvent(
                name="LearningExperienceCreated",
                occurredAt=now,
                tenantId=tenantId,
                payload={"experienceId": str(experience.id), "source": experience.source},
            )
        )
        return experience


class LearningDataset(AggregateRoot):
    transitions = {
        "DRAFT": ("BUILDING", "ARCHIVED"),
        "BUILDING": ("READY", "FAILED"),
        "READY": ("VALIDATING", "ARCHIVED"),
        "VALIDATING": ("APPROVED", "FAILED"),
        "APPROVED": ("ARCHIVED",),
        "FAILED": ("BUILDING", "ARCHIVED"),
        "ARCHIVED": (),
    }

    def __init__(
        self,
        id: uuid.UUID,
        tenantId: uuid.UUID,
        name: str,
        version: str,
        description: str,
        source: str,
        status: str,
        sampleCount: int,
        datasetHash: str,
        createdAt: datetime,
        createdById: uuid.UUID,
        metadata: dict[str, Any],
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.name = name
        self.version = t.requireSemVer(version)
        self.description = description
        self.source = source
        self.status = t.requireChoice(status, t.DATASET_STATUSES, "status")
        self.sampleCount = sampleCount
        self.datasetHash = datasetHash
        self.createdAt = createdAt
        self.createdById = createdById
        self.metadata = metadata

    def moveTo(self, target: str, now: datetime) -> None:
        target = t.requireChoice(target, t.DATASET_STATUSES, "status")
        if target not in self.transitions[self.status]:
            raise ConflictError(f"Dataset cannot move from {self.status} to {target}.")
        self.status = target
        eventName = "LearningDatasetReady" if target == "READY" else "LearningDatasetChanged"
        self.recordEvent(
            DomainEvent(
                name=eventName,
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"datasetId": str(self.id), "status": target},
            )
        )


class LearningExperiment(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,
        tenantId: uuid.UUID,
        name: str,
        description: str,
        datasetId: uuid.UUID,
        datasetVersion: str,
        algorithm: str,
        configuration: dict[str, Any],
        baselineArtifactId: uuid.UUID | None,
        status: str,
        createdAt: datetime,
        completedAt: datetime | None,
        createdById: uuid.UUID,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.name = name
        self.description = description
        self.datasetId = datasetId
        self.datasetVersion = datasetVersion
        self.algorithm = algorithm
        self.configuration = configuration
        self.baselineArtifactId = baselineArtifactId
        self.status = t.requireChoice(status, t.EXPERIMENT_STATUSES, "status")
        self.createdAt = createdAt
        self.completedAt = completedAt
        self.createdById = createdById

    def start(self, now: datetime) -> None:
        if self.status not in ("CREATED", "FAILED"):
            raise ConflictError("Only a created or failed experiment can run.")
        self.status = "RUNNING"
        self.recordEvent(
            DomainEvent(
                name="LearningExperimentStarted",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"experimentId": str(self.id)},
            )
        )

    def complete(self, now: datetime) -> None:
        if self.status != "RUNNING":
            raise ConflictError("Only a running experiment can complete.")
        self.status, self.completedAt = "COMPLETED", now
        self.recordEvent(
            DomainEvent(
                name="LearningExperimentCompleted",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"experimentId": str(self.id)},
            )
        )

    def fail(self, now: datetime, errorCode: str) -> None:
        if self.status != "RUNNING":
            raise ConflictError("Only a running experiment can fail.")
        self.status, self.completedAt = "FAILED", now
        self.recordEvent(
            DomainEvent(
                name="LearningExperimentFailed",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"experimentId": str(self.id), "errorCode": errorCode},
            )
        )


class LearningArtifact(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,
        tenantId: uuid.UUID,
        artifactType: str,
        name: str,
        version: str,
        storageUri: str,
        checksum: str,
        createdByRunId: uuid.UUID,
        status: str,
        metadata: dict[str, Any],
        createdAt: datetime,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.artifactType = t.requireChoice(artifactType, t.ARTIFACT_TYPES, "artifactType")
        self.name = name
        self.version = t.requireSemVer(version)
        self.storageUri = storageUri
        self.checksum = checksum
        self.createdByRunId = createdByRunId
        self.status = t.requireChoice(status, t.ARTIFACT_STATUSES, "status")
        self.metadata = metadata
        self.createdAt = createdAt

    def evaluated(self) -> None:
        if self.status not in ("CREATED", "EVALUATED"):
            raise ConflictError("Artifact is not eligible for evaluation.")
        self.status = "EVALUATED"

    def validated(self, passed: bool) -> None:
        if self.status != "EVALUATED":
            raise ConflictError("Artifact must be evaluated before validation.")
        self.status = "VALIDATED" if passed else "FAILED"

    def decide(self, approved: bool) -> None:
        if self.status != "VALIDATED":
            raise ConflictError("Only a validated artifact can be reviewed.")
        self.status = "APPROVED" if approved else "REJECTED"

    def deploy(self, percentage: int) -> None:
        if self.status not in ("APPROVED", "STAGED", "CANARY", "ACTIVE"):
            raise ConflictError("Only an approved artifact can be deployed.")
        if percentage not in t.CANARY_STAGES:
            raise ValidationFailedError("Deployment percentage must be a canary stage.")
        self.status = "ACTIVE" if percentage == 100 else "CANARY"

    def rollback(self) -> None:
        if self.status not in ("ACTIVE", "CANARY"):
            raise ConflictError("Only a deployed artifact can be rolled back.")
        self.status = "ROLLED_BACK"


class LearningDeployment(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,
        tenantId: uuid.UUID,
        artifactId: uuid.UUID,
        artifactVersion: str,
        environment: str,
        status: str,
        trafficPercentage: int,
        previousDeploymentId: uuid.UUID | None,
        startedAt: datetime,
        completedAt: datetime | None,
        deployedById: uuid.UUID,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.artifactId = artifactId
        self.artifactVersion = artifactVersion
        self.environment = environment
        self.status = t.requireChoice(status, t.DEPLOYMENT_STATUSES, "status")
        self.trafficPercentage = trafficPercentage
        self.previousDeploymentId = previousDeploymentId
        self.startedAt = startedAt
        self.completedAt = completedAt
        self.deployedById = deployedById

    def advance(self, now: datetime) -> None:
        if self.status not in ("STAGED", "CANARY"):
            raise ConflictError("Deployment cannot advance from its current state.")
        self.trafficPercentage = t.nextCanaryStage(self.trafficPercentage)
        self.status = "ACTIVE" if self.trafficPercentage == 100 else "CANARY"
        if self.status == "ACTIVE":
            self.completedAt = now

    def rollback(self, now: datetime) -> None:
        if self.status not in ("CANARY", "ACTIVE", "FAILED"):
            raise ConflictError("Deployment cannot be rolled back.")
        self.status, self.completedAt = "ROLLED_BACK", now


__all__ = [
    "LearningArtifact",
    "LearningDataset",
    "LearningDeployment",
    "LearningExperience",
    "LearningExperiment",
]
