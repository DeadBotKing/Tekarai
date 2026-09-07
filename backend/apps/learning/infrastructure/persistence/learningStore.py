"""Tenant-scoped Django implementation of all Phase 16 repository ports."""

from __future__ import annotations

import uuid

from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Max

from apps.learning.domain.entities.learningRecords import (
    LearningArtifact,
    LearningDataset,
    LearningDeployment,
    LearningExperience,
    LearningExperiment,
)
from apps.learning.domain.valueObjects.learningTypes import integrityHash
from apps.learning.infrastructure.persistence.models import (
    EvaluationResultModel,
    LearningApprovalModel,
    LearningArtifactModel,
    LearningAuditModel,
    LearningDatasetModel,
    LearningDeploymentModel,
    LearningEventModel,
    LearningExperienceModel,
    LearningExperimentModel,
    LearningFeedbackModel,
    LearningJobModel,
    LearningMetricModel,
    LearningRunModel,
    LearningSampleModel,
    LearningSnapshotModel,
    ModelVersionModel,
    PolicyVersionModel,
    ValidationResultModel,
)
from apps.sharedKernel.domain.errors import ConflictError, EntityNotFoundError


def _iso(value):
    return value.isoformat() if value else None


def _dataset(row: LearningDatasetModel) -> LearningDataset:
    return LearningDataset(
        row.id,
        row.tenantId,
        row.name,
        row.version,
        row.description,
        row.source,
        row.status,
        row.sampleCount,
        row.datasetHash,
        row.createdAt,
        row.createdById,
        row.metadata,
    )


def _experiment(row: LearningExperimentModel) -> LearningExperiment:
    return LearningExperiment(
        row.id,
        row.tenantId,
        row.name,
        row.description,
        row.datasetId,
        row.datasetVersion,
        row.algorithm,
        row.configuration,
        row.baselineArtifactId,
        row.status,
        row.createdAt,
        row.completedAt,
        row.createdById,
    )


def _artifact(row: LearningArtifactModel) -> LearningArtifact:
    return LearningArtifact(
        row.id,
        row.tenantId,
        row.artifactType,
        row.name,
        row.version,
        row.storageUri,
        row.checksum,
        row.createdByRunId,
        row.status,
        row.metadata,
        row.createdAt,
    )


def _deployment(row: LearningDeploymentModel) -> LearningDeployment:
    return LearningDeployment(
        row.id,
        row.tenantId,
        row.artifactId,
        row.artifactVersion,
        row.environment,
        row.status,
        row.trafficPercentage,
        row.previousDeploymentId,
        row.startedAt,
        row.completedAt,
        row.deployedById,
    )


def _datasetDto(row):
    return {
        "id": str(row.id),
        "name": row.name,
        "version": row.version,
        "description": row.description,
        "source": row.source,
        "status": row.status,
        "sampleCount": row.sampleCount,
        "datasetHash": row.datasetHash,
        "createdById": str(row.createdById),
        "createdAt": _iso(row.createdAt),
        "metadata": row.metadata,
    }


def _experimentDto(row):
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "datasetId": str(row.datasetId),
        "datasetVersion": row.datasetVersion,
        "algorithm": row.algorithm,
        "configuration": row.configuration,
        "baselineArtifactId": str(row.baselineArtifactId) if row.baselineArtifactId else None,
        "status": row.status,
        "createdById": str(row.createdById),
        "createdAt": _iso(row.createdAt),
        "completedAt": _iso(row.completedAt),
    }


def _artifactDto(row):
    return {
        "id": str(row.id),
        "type": row.artifactType,
        "name": row.name,
        "version": row.version,
        "storageUri": row.storageUri,
        "checksum": row.checksum,
        "createdByRunId": str(row.createdByRunId),
        "status": row.status,
        "metadata": row.metadata,
        "createdAt": _iso(row.createdAt),
    }


def _deploymentDto(row):
    return {
        "id": str(row.id),
        "artifactId": str(row.artifactId),
        "artifactName": row.artifactName,
        "artifactVersion": row.artifactVersion,
        "environment": row.environment,
        "status": row.status,
        "trafficPercentage": row.trafficPercentage,
        "previousDeploymentId": str(row.previousDeploymentId) if row.previousDeploymentId else None,
        "startedAt": _iso(row.startedAt),
        "completedAt": _iso(row.completedAt),
        "deployedById": str(row.deployedById),
        "rollbackReason": row.rollbackReason,
    }


class DjangoLearningStore:
    def saveExperience(self, experience: LearningExperience) -> None:
        values = {
            "id": experience.id,
            "tenantId": experience.tenantId,
            "source": experience.source,
            "context": experience.context,
            "inputData": experience.inputData,
            "action": experience.action,
            "expectedOutcome": experience.expectedOutcome,
            "actualOutcome": experience.actualOutcome,
            "reward": experience.reward,
            "success": experience.success,
            "occurredAt": experience.occurredAt,
            "metadata": experience.metadata,
            "traceId": experience.traceId,
        }
        values["integrityHash"] = integrityHash(
            {key: value for key, value in values.items() if key not in ("id", "occurredAt")}
        )
        existing = LearningExperienceModel.objects.filter(
            tenantId=experience.tenantId, traceId=experience.traceId
        ).first()
        if existing:
            if existing.integrityHash != values["integrityHash"]:
                raise ConflictError("Experience traceId already exists with different data.")
            experience.id = existing.id
            return
        LearningExperienceModel.objects.create(**values)

    def listExperiences(self, tenantId, *, limit=100):
        return tuple(
            {
                "id": str(r.id),
                "source": r.source,
                "context": r.context,
                "input": r.inputData,
                "action": r.action,
                "expectedOutcome": r.expectedOutcome,
                "actualOutcome": r.actualOutcome,
                "reward": r.reward,
                "success": r.success,
                "traceId": r.traceId,
                "timestamp": _iso(r.occurredAt),
                "metadata": r.metadata,
            }
            for r in LearningExperienceModel.objects.filter(tenantId=tenantId).order_by(
                "-occurredAt"
            )[:limit]
        )

    def experienceExists(self, tenantId, experienceId):
        return LearningExperienceModel.objects.filter(tenantId=tenantId, id=experienceId).exists()

    def saveDataset(self, dataset):
        try:
            LearningDatasetModel.objects.update_or_create(
                id=dataset.id,
                tenantId=dataset.tenantId,
                defaults={
                    "name": dataset.name,
                    "version": dataset.version,
                    "description": dataset.description,
                    "source": dataset.source,
                    "status": dataset.status,
                    "sampleCount": dataset.sampleCount,
                    "datasetHash": dataset.datasetHash,
                    "createdById": dataset.createdById,
                    "metadata": dataset.metadata,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("Dataset name and version already exist.") from exc

    def getDataset(self, tenantId, datasetId):
        row = LearningDatasetModel.objects.filter(tenantId=tenantId, id=datasetId).first()
        return _dataset(row) if row else None

    def listDatasets(self, tenantId):
        return tuple(
            _datasetDto(r)
            for r in LearningDatasetModel.objects.filter(tenantId=tenantId).order_by("-createdAt")
        )

    @transaction.atomic
    def addSamples(self, tenantId, datasetId, samples):
        dataset = (
            LearningDatasetModel.objects.select_for_update()
            .filter(tenantId=tenantId, id=datasetId)
            .first()
        )
        if not dataset:
            raise EntityNotFoundError("LearningDataset", str(datasetId))
        if dataset.status not in ("DRAFT", "BUILDING", "FAILED"):
            raise ConflictError("Samples cannot be added to this dataset state.")
        rows = []
        for sample in samples:
            sourceId = uuid.UUID(str(sample["sourceExperienceId"]))
            if not LearningExperienceModel.objects.filter(tenantId=tenantId, id=sourceId).exists():
                raise EntityNotFoundError("LearningExperience", str(sourceId))
            digest = integrityHash(
                {
                    "input": sample["input"],
                    "target": sample["target"],
                    "context": sample.get("context", {}),
                    "source": str(sourceId),
                }
            )
            rows.append(
                LearningSampleModel(
                    tenantId=tenantId,
                    datasetId=datasetId,
                    inputData=sample["input"],
                    target=sample["target"],
                    context=sample.get("context", {}),
                    sourceExperienceId=sourceId,
                    weight=sample.get("weight", 1.0),
                    metadata=sample.get("metadata", {}),
                    sampleHash=digest,
                )
            )
        LearningSampleModel.objects.bulk_create(rows, ignore_conflicts=True, batch_size=500)
        hashes = list(
            LearningSampleModel.objects.filter(tenantId=tenantId, datasetId=datasetId)
            .order_by("sampleHash")
            .values_list("sampleHash", flat=True)
        )
        dataset.sampleCount = len(hashes)
        dataset.datasetHash = integrityHash(hashes)
        dataset.status = "READY" if hashes else "FAILED"
        dataset.save(update_fields=["sampleCount", "datasetHash", "status", "updatedAt"])
        return len(hashes)

    def datasetSamples(self, tenantId, datasetId):
        return tuple(
            {
                "id": str(r.id),
                "input": r.inputData,
                "target": r.target,
                "context": r.context,
                "sourceExperienceId": str(r.sourceExperienceId),
                "weight": r.weight,
                "metadata": r.metadata,
                "sampleHash": r.sampleHash,
            }
            for r in LearningSampleModel.objects.filter(
                tenantId=tenantId, datasetId=datasetId
            ).order_by("sampleHash")
        )

    def saveExperiment(self, experiment):
        try:
            LearningExperimentModel.objects.update_or_create(
                id=experiment.id,
                tenantId=experiment.tenantId,
                defaults={
                    "name": experiment.name,
                    "description": experiment.description,
                    "datasetId": experiment.datasetId,
                    "datasetVersion": experiment.datasetVersion,
                    "algorithm": experiment.algorithm,
                    "configuration": experiment.configuration,
                    "baselineArtifactId": experiment.baselineArtifactId,
                    "status": experiment.status,
                    "completedAt": experiment.completedAt,
                    "createdById": experiment.createdById,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("Experiment name already exists.") from exc

    def getExperiment(self, tenantId, experimentId):
        row = LearningExperimentModel.objects.filter(tenantId=tenantId, id=experimentId).first()
        return _experiment(row) if row else None

    def listExperiments(self, tenantId):
        return tuple(
            _experimentDto(r)
            for r in LearningExperimentModel.objects.filter(tenantId=tenantId).order_by(
                "-createdAt"
            )
        )

    def createRun(self, tenantId, experimentId, details):
        row = LearningRunModel.objects.create(
            tenantId=tenantId, experimentId=experimentId, **details
        )
        return {"id": str(row.id), "status": row.status}

    def updateRun(self, tenantId, runId, **changes):
        if not LearningRunModel.objects.filter(tenantId=tenantId, id=runId).update(**changes):
            raise EntityNotFoundError("LearningRun", str(runId))

    @transaction.atomic
    def saveArtifact(self, artifact):
        try:
            LearningArtifactModel.objects.update_or_create(
                id=artifact.id,
                tenantId=artifact.tenantId,
                defaults={
                    "artifactType": artifact.artifactType,
                    "name": artifact.name,
                    "version": artifact.version,
                    "storageUri": artifact.storageUri,
                    "checksum": artifact.checksum,
                    "createdByRunId": artifact.createdByRunId,
                    "status": artifact.status,
                    "metadata": artifact.metadata,
                },
            )
            versionDefaults = {"artifactId": artifact.id, "checksum": artifact.checksum}
            if artifact.artifactType == "MODEL":
                ModelVersionModel.objects.get_or_create(
                    tenantId=artifact.tenantId,
                    modelName=artifact.name,
                    version=artifact.version,
                    defaults=versionDefaults,
                )
            if artifact.artifactType == "POLICY":
                PolicyVersionModel.objects.get_or_create(
                    tenantId=artifact.tenantId,
                    policyName=artifact.name,
                    version=artifact.version,
                    defaults={**versionDefaults, "policy": artifact.metadata.get("policy", {})},
                )
        except IntegrityError as exc:
            raise ConflictError("Artifact version or checksum already exists.") from exc

    def getArtifact(self, tenantId, artifactId):
        row = LearningArtifactModel.objects.filter(tenantId=tenantId, id=artifactId).first()
        return _artifact(row) if row else None

    def listArtifacts(self, tenantId):
        return tuple(
            _artifactDto(r)
            for r in LearningArtifactModel.objects.filter(tenantId=tenantId).order_by("-createdAt")
        )

    def latestArtifactVersion(self, tenantId, name):
        return (
            LearningArtifactModel.objects.filter(tenantId=tenantId, name=name)
            .order_by("-createdAt")
            .values_list("version", flat=True)
            .first()
        )

    def saveEvaluation(self, tenantId, artifactId, result):
        row = EvaluationResultModel.objects.create(
            tenantId=tenantId, artifactId=artifactId, **result
        )
        return {
            "id": str(row.id),
            "artifactId": str(artifactId),
            "metrics": row.metrics,
            "businessMetrics": row.businessMetrics,
            "baselineComparison": row.baselineComparison,
            "createdAt": _iso(row.createdAt),
        }

    def latestEvaluation(self, tenantId, artifactId):
        row = (
            EvaluationResultModel.objects.filter(tenantId=tenantId, artifactId=artifactId)
            .order_by("-createdAt")
            .first()
        )
        return (
            {
                "id": str(row.id),
                "artifactId": str(row.artifactId),
                "datasetId": str(row.datasetId),
                "datasetVersion": row.datasetVersion,
                "metrics": row.metrics,
                "businessMetrics": row.businessMetrics,
                "baselineArtifactId": str(row.baselineArtifactId)
                if row.baselineArtifactId
                else None,
                "baselineComparison": row.baselineComparison,
                "createdAt": _iso(row.createdAt),
            }
            if row
            else None
        )

    def saveValidation(self, tenantId, artifactId, result):
        row = ValidationResultModel.objects.create(
            tenantId=tenantId, artifactId=artifactId, **result
        )
        return {
            "id": str(row.id),
            "artifactId": str(artifactId),
            "decision": row.decision,
            "checks": row.checks,
            "failures": row.failures,
            "reproducibilityHash": row.reproducibilityHash,
            "createdAt": _iso(row.createdAt),
        }

    def latestValidation(self, tenantId, artifactId):
        row = (
            ValidationResultModel.objects.filter(tenantId=tenantId, artifactId=artifactId)
            .order_by("-createdAt")
            .first()
        )
        return (
            {
                "id": str(row.id),
                "decision": row.decision,
                "checks": row.checks,
                "failures": row.failures,
                "policySnapshot": row.policySnapshot,
                "reproducibilityHash": row.reproducibilityHash,
            }
            if row
            else None
        )

    def saveApproval(self, tenantId, artifactId, reviewerId, decision, reason, now):
        try:
            row = LearningApprovalModel.objects.create(
                tenantId=tenantId,
                artifactId=artifactId,
                reviewerId=reviewerId,
                decision=decision,
                reason=reason,
                decidedAt=now,
            )
        except IntegrityError as exc:
            raise ConflictError("Reviewer has already decided this artifact.") from exc
        return {
            "id": str(row.id),
            "artifactId": str(artifactId),
            "reviewerId": str(reviewerId),
            "decision": decision,
            "reason": reason,
            "timestamp": _iso(now),
        }

    def saveDeployment(self, deployment):
        artifact = LearningArtifactModel.objects.get(
            tenantId=deployment.tenantId, id=deployment.artifactId
        )
        LearningDeploymentModel.objects.update_or_create(
            id=deployment.id,
            tenantId=deployment.tenantId,
            defaults={
                "artifactId": deployment.artifactId,
                "artifactVersion": deployment.artifactVersion,
                "artifactName": artifact.name,
                "environment": deployment.environment,
                "status": deployment.status,
                "trafficPercentage": deployment.trafficPercentage,
                "previousDeploymentId": deployment.previousDeploymentId,
                "startedAt": deployment.startedAt,
                "completedAt": deployment.completedAt,
                "deployedById": deployment.deployedById,
            },
        )

    def getDeployment(self, tenantId, deploymentId):
        row = LearningDeploymentModel.objects.filter(tenantId=tenantId, id=deploymentId).first()
        return _deployment(row) if row else None

    def activeDeployment(self, tenantId, environment, artifactName):
        row = (
            LearningDeploymentModel.objects.filter(
                tenantId=tenantId,
                environment=environment,
                artifactName=artifactName,
                status__in=("ACTIVE", "CANARY", "STAGED"),
            )
            .order_by("-createdAt")
            .first()
        )
        return _deploymentDto(row) if row else None

    def listDeployments(self, tenantId):
        return tuple(
            _deploymentDto(r)
            for r in LearningDeploymentModel.objects.filter(tenantId=tenantId).order_by(
                "-createdAt"
            )
        )

    def markDeploymentStatus(
        self, tenantId, deploymentId, status, completedAt=None, rollbackReason=""
    ):
        changes = {"status": status}
        if completedAt is not None:
            changes["completedAt"] = completedAt
        if rollbackReason:
            changes["rollbackReason"] = rollbackReason
        if not LearningDeploymentModel.objects.filter(tenantId=tenantId, id=deploymentId).update(
            **changes
        ):
            raise EntityNotFoundError("LearningDeployment", str(deploymentId))

    def saveFeedback(self, tenantId, actorId, data):
        row = LearningFeedbackModel.objects.create(tenantId=tenantId, createdById=actorId, **data)
        return {
            "id": str(row.id),
            "experienceId": str(row.experienceId) if row.experienceId else None,
            "deploymentId": str(row.deploymentId) if row.deploymentId else None,
            "artifactId": str(row.artifactId) if row.artifactId else None,
            "type": row.feedbackType,
            "humanAction": row.humanAction,
            "score": row.score,
            "source": row.source,
            "comment": row.comment,
            "createdAt": _iso(row.createdAt),
            "metadata": row.metadata,
        }

    def recordMetrics(self, tenantId, artifactId, deploymentId, metrics, now):
        LearningMetricModel.objects.bulk_create(
            [
                LearningMetricModel(
                    tenantId=tenantId,
                    artifactId=artifactId,
                    deploymentId=deploymentId,
                    metricName=name,
                    metricValue=value,
                    observedAt=now,
                )
                for name, value in metrics.items()
            ],
            batch_size=500,
        )
        return {
            "artifactId": str(artifactId),
            "deploymentId": str(deploymentId) if deploymentId else None,
            "metrics": metrics,
            "observedAt": _iso(now),
        }

    def latestMetrics(self, tenantId, artifactId):
        rows = (
            LearningMetricModel.objects.filter(tenantId=tenantId, artifactId=artifactId)
            .values("metricName")
            .annotate(latest=Max("observedAt"))
        )
        result = {}
        for item in rows:
            value = (
                LearningMetricModel.objects.filter(
                    tenantId=tenantId,
                    artifactId=artifactId,
                    metricName=item["metricName"],
                    observedAt=item["latest"],
                )
                .values_list("metricValue", flat=True)
                .first()
            )
            result[item["metricName"]] = float(value)
        return result

    def metricSummary(self, tenantId):
        jobs = dict(
            LearningJobModel.objects.filter(tenantId=tenantId)
            .values_list("status")
            .annotate(total=Count("id"))
        )
        deployments = dict(
            LearningDeploymentModel.objects.filter(tenantId=tenantId)
            .values_list("status")
            .annotate(total=Count("id"))
        )
        aggregate = LearningMetricModel.objects.filter(tenantId=tenantId).aggregate(
            count=Count("id"), average=Avg("metricValue")
        )
        runDurations = [
            (row.finishedAt - row.startedAt).total_seconds() * 1000
            for row in LearningRunModel.objects.filter(
                tenantId=tenantId, startedAt__isnull=False, finishedAt__isnull=False
            )
        ]
        deploymentDurations = [
            (row.completedAt - row.startedAt).total_seconds() * 1000
            for row in LearningDeploymentModel.objects.filter(
                tenantId=tenantId, completedAt__isnull=False
            )
        ]
        evaluation = EvaluationResultModel.objects.filter(tenantId=tenantId).aggregate(
            average=Avg("durationMs")
        )
        return {
            "jobs": jobs,
            "deployments": deployments,
            "metricCount": aggregate["count"],
            "metricAverage": aggregate["average"] or 0.0,
            "experimentDurationMs": sum(runDurations) / len(runDurations) if runDurations else 0.0,
            "trainingDurationMs": sum(runDurations) / len(runDurations) if runDurations else 0.0,
            "evaluationDurationMs": evaluation["average"] or 0.0,
            "deploymentDurationMs": (
                sum(deploymentDurations) / len(deploymentDurations) if deploymentDurations else 0.0
            ),
            "failureCount": jobs.get("FAILED", 0),
            "rollbackCount": deployments.get("ROLLED_BACK", 0),
            "driftCount": LearningEventModel.objects.filter(
                tenantId=tenantId, eventType="DriftDetected"
            ).count(),
        }

    def createJob(self, tenantId, experimentId, actorId, priority, idempotencyKey, now):
        row, created = LearningJobModel.objects.get_or_create(
            tenantId=tenantId,
            idempotencyKey=idempotencyKey,
            defaults={
                "experimentId": experimentId,
                "requestedById": actorId,
                "status": "QUEUED",
                "priority": priority,
            },
        )
        if not created and row.experimentId != experimentId:
            raise ConflictError("Idempotency key belongs to another experiment.")
        return {
            "id": str(row.id),
            "experimentId": str(row.experimentId),
            "status": row.status,
            "priority": row.priority,
            "created": created,
            "createdAt": _iso(row.createdAt),
        }

    def getJob(self, tenantId, jobId):
        row = LearningJobModel.objects.filter(tenantId=tenantId, id=jobId).first()
        return (
            {
                "id": str(row.id),
                "experimentId": str(row.experimentId),
                "status": row.status,
                "priority": row.priority,
                "requestedById": str(row.requestedById),
                "retryCount": row.retryCount,
                "errorCode": row.errorCode,
                "errorMessage": row.errorMessage,
                "createdAt": _iso(row.createdAt),
                "startedAt": _iso(row.startedAt),
                "completedAt": _iso(row.completedAt),
                "metadata": row.metadata,
            }
            if row
            else None
        )

    def findJob(self, jobId):
        row = LearningJobModel.objects.filter(id=jobId).first()
        return (
            {
                "id": str(row.id),
                "tenantId": str(row.tenantId),
                "experimentId": str(row.experimentId),
                "status": row.status,
                "requestedById": str(row.requestedById),
                "retryCount": row.retryCount,
            }
            if row
            else None
        )

    def updateJob(self, tenantId, jobId, **changes):
        if not LearningJobModel.objects.filter(tenantId=tenantId, id=jobId).update(**changes):
            raise EntityNotFoundError("LearningJob", str(jobId))

    def appendEvent(self, tenantId, eventType, targetType, targetId, data, now):
        event = {
            "eventType": eventType,
            "targetType": targetType,
            "targetId": targetId,
            "data": data,
            "occurredAt": _iso(now),
        }
        LearningEventModel.objects.create(
            tenantId=tenantId,
            eventType=eventType,
            targetType=targetType,
            targetId=targetId,
            data=data,
            occurredAt=now,
            eventHash=integrityHash(event),
        )

    def snapshot(self, tenantId, deploymentId, state, checksum, now):
        row, _ = LearningSnapshotModel.objects.get_or_create(
            tenantId=tenantId,
            deploymentId=deploymentId,
            checksum=checksum,
            defaults={"state": state},
        )
        return {
            "id": str(row.id),
            "deploymentId": str(deploymentId),
            "state": row.state,
            "checksum": row.checksum,
            "createdAt": _iso(row.createdAt),
        }

    def audit(
        self,
        tenantId,
        actorId,
        action,
        targetType,
        targetId,
        previousState=None,
        newState=None,
        metadata=None,
    ):
        data = {
            "actorId": str(actorId) if actorId else None,
            "action": action,
            "targetType": targetType,
            "targetId": targetId,
            "previousState": previousState or {},
            "newState": newState or {},
            "metadata": metadata or {},
        }
        LearningAuditModel.objects.create(
            tenantId=tenantId,
            actorId=actorId,
            action=action,
            targetType=targetType,
            targetId=targetId,
            previousState=previousState or {},
            newState=newState or {},
            metadata=metadata or {},
            auditHash=integrityHash(data),
        )
