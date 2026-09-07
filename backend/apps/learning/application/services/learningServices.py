"""Application orchestration for the complete Phase 16 learning lifecycle."""

from __future__ import annotations

import platform
import time
import uuid
from datetime import datetime
from typing import Any

from apps.learning.application.commands.learningCommands import (
    ArtifactActionCommand,
    BuildDatasetCommand,
    CreateDatasetCommand,
    CreateExperienceCommand,
    CreateExperimentCommand,
    DetectDriftCommand,
    LearningListQuery,
    ProcessLearningJobCommand,
    RecordFeedbackCommand,
    RecordMetricsCommand,
    RunExperimentCommand,
    ValidateDatasetCommand,
)
from apps.learning.domain.entities.learningRecords import (
    LearningArtifact,
    LearningDataset,
    LearningDeployment,
    LearningExperience,
    LearningExperiment,
)
from apps.learning.domain.repositories.learningRepositories import (
    DriftDetector,
    FeatureExtractor,
    LearningEngine,
    LearningJobQueue,
    LearningStore,
    ModelStorage,
)
from apps.learning.domain.valueObjects import learningTypes as t
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import UseCase
from apps.sharedKernel.domain.errors import (
    ConflictError,
    EntityNotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid


def actorContext() -> tuple[uuid.UUID, uuid.UUID]:
    context = currentContext()
    return asUuid(context.actorId), asUuid(context.actorTenantId)


def entityDto(entity) -> dict[str, Any]:
    return {
        key: (
            str(value)
            if isinstance(value, uuid.UUID)
            else value.isoformat()
            if isinstance(value, datetime)
            else value
        )
        for key, value in vars(entity).items()
        if not key.startswith("_")
    }


class LearningUseCase(UseCase):
    def __init__(self, store: LearningStore, **kernel: Any) -> None:
        super().__init__(**kernel)
        self.store = store

    def audited(self, action, targetType, targetId, tenantId, *, before=None, after=None):
        actorId, _ = actorContext()
        self.audit(action, targetType, targetId, tenantId, before=before, after=after)
        auditMethod = getattr(self.store, "audit", None)
        if auditMethod:
            auditMethod(
                tenantId,
                actorId,
                action,
                targetType,
                targetId,
                previousState=before,
                newState=after,
            )


class CreateExperienceService(LearningUseCase):
    requiredAction = "learning.observe"

    def perform(self, command: CreateExperienceCommand):
        actorId, tenantId = actorContext()
        experience = LearningExperience.create(
            tenantId,
            command.source,
            command.context,
            command.input,
            command.action,
            command.expectedOutcome,
            command.actualOutcome,
            self.clock.nowUtc(),
            reward=command.reward,
            success=command.success,
            metadata=command.metadata,
            traceId=command.traceId,
        )
        self.store.saveExperience(experience)
        self.collectEventsFrom(experience)
        self.audited(
            "CREATE",
            "LearningExperience",
            str(experience.id),
            tenantId,
            after={
                "source": experience.source,
                "traceId": experience.traceId,
                "actorId": str(actorId),
            },
        )
        return entityDto(experience)


class CreateDatasetService(LearningUseCase):
    requiredAction = "learning.manage"

    def perform(self, command: CreateDatasetCommand):
        actorId, tenantId = actorContext()
        if not command.name.strip() or not command.source.strip():
            raise ValidationFailedError("Dataset name and source are required.")
        dataset = LearningDataset(
            uuid.uuid4(),
            tenantId,
            command.name.strip(),
            t.requireSemVer(command.version),
            command.description.strip(),
            command.source.strip(),
            "DRAFT",
            0,
            "",
            self.clock.nowUtc(),
            actorId,
            t.safePayload(command.metadata),
        )
        self.store.saveDataset(dataset)
        self.audited(
            "CREATE",
            "LearningDataset",
            str(dataset.id),
            tenantId,
            after={"name": dataset.name, "version": dataset.version},
        )
        return entityDto(dataset)


class BuildDatasetService(LearningUseCase):
    requiredAction = "learning.manage"

    def perform(self, command: BuildDatasetCommand):
        _actorId, tenantId = actorContext()
        datasetId = asUuid(command.datasetId)
        dataset = self.store.getDataset(tenantId, datasetId)
        if not dataset:
            raise EntityNotFoundError("LearningDataset", command.datasetId)
        if len(command.samples) > 100_000:
            raise ValidationFailedError("A dataset build is limited to 100,000 samples.")
        clean = []
        for sample in command.samples:
            if not sample.get("sourceExperienceId"):
                raise ValidationFailedError("Every sample requires sourceExperienceId.")
            weight = float(sample.get("weight", 1.0))
            if weight <= 0 or weight > 100:
                raise ValidationFailedError("Sample weight must be greater than 0 and at most 100.")
            clean.append(
                {
                    "input": t.safePayload(sample.get("input", {})),
                    "target": t.safePayload(sample.get("target", {})),
                    "context": t.safePayload(sample.get("context", {})),
                    "sourceExperienceId": sample["sourceExperienceId"],
                    "weight": weight,
                    "metadata": t.safePayload(sample.get("metadata", {})),
                }
            )
        count = self.store.addSamples(tenantId, datasetId, tuple(clean))
        updated = self.store.getDataset(tenantId, datasetId)
        if updated is None:  # repository invariant; fail closed if persistence vanished
            raise EntityNotFoundError("LearningDataset", command.datasetId)
        self.audited(
            "BUILD",
            "LearningDataset",
            command.datasetId,
            tenantId,
            before={"sampleCount": dataset.sampleCount},
            after={"sampleCount": count, "datasetHash": updated.datasetHash},
        )
        return entityDto(updated)


class ValidateDatasetService(LearningUseCase):
    requiredAction = "learning.manage"

    def perform(self, command: ValidateDatasetCommand):
        _actorId, tenantId = actorContext()
        dataset = self.store.getDataset(tenantId, asUuid(command.datasetId))
        if not dataset:
            raise EntityNotFoundError("LearningDataset", command.datasetId)
        if command.minimumSamples < 1:
            raise ValidationFailedError("minimumSamples must be positive.")
        if dataset.status != "READY":
            raise ConflictError("Only a ready dataset can be validated.")
        dataset.moveTo("VALIDATING", self.clock.nowUtc())
        dataset.moveTo(
            "APPROVED" if dataset.sampleCount >= command.minimumSamples else "FAILED",
            self.clock.nowUtc(),
        )
        self.store.saveDataset(dataset)
        self.collectEventsFrom(dataset)
        self.audited(
            "VALIDATE",
            "LearningDataset",
            command.datasetId,
            tenantId,
            after={"status": dataset.status, "sampleCount": dataset.sampleCount},
        )
        return entityDto(dataset)


class CreateExperimentService(LearningUseCase):
    requiredAction = "learning.manage"

    def perform(self, command: CreateExperimentCommand):
        actorId, tenantId = actorContext()
        dataset = self.store.getDataset(tenantId, asUuid(command.datasetId))
        if not dataset:
            raise EntityNotFoundError("LearningDataset", command.datasetId)
        if dataset.status != "APPROVED":
            raise ConflictError("Experiment requires an approved dataset version.")
        if not command.name.strip() or not command.algorithm.strip():
            raise ValidationFailedError("Experiment name and algorithm are required.")
        baselineId = asUuid(command.baselineArtifactId) if command.baselineArtifactId else None
        if baselineId and not self.store.getArtifact(tenantId, baselineId):
            raise EntityNotFoundError("LearningArtifact", command.baselineArtifactId)
        experiment = LearningExperiment(
            uuid.uuid4(),
            tenantId,
            command.name.strip(),
            command.description.strip(),
            dataset.id,
            dataset.version,
            command.algorithm.strip(),
            t.safePayload(command.configuration),
            baselineId,
            "CREATED",
            self.clock.nowUtc(),
            None,
            actorId,
        )
        self.store.saveExperiment(experiment)
        self.audited(
            "CREATE",
            "LearningExperiment",
            str(experiment.id),
            tenantId,
            after={"datasetVersion": dataset.version, "algorithm": experiment.algorithm},
        )
        return entityDto(experiment)


class QueueExperimentService(LearningUseCase):
    requiredAction = "learning.run"

    def __init__(self, store: LearningStore, queue: LearningJobQueue, **kernel):
        super().__init__(store, **kernel)
        self.queue = queue

    def perform(self, command: RunExperimentCommand):
        actorId, tenantId = actorContext()
        experiment = self.store.getExperiment(tenantId, asUuid(command.experimentId))
        if not experiment:
            raise EntityNotFoundError("LearningExperiment", command.experimentId)
        if experiment.status not in ("CREATED", "FAILED"):
            raise ConflictError("Experiment is not eligible to run.")
        if len(command.idempotencyKey.strip()) < 8:
            raise ValidationFailedError(
                "A stable idempotencyKey of at least 8 characters is required."
            )
        priority = command.priority.strip().upper()
        if priority not in ("LOW", "NORMAL", "HIGH"):
            raise ValidationFailedError("Job priority is invalid.")
        job = self.store.createJob(
            tenantId,
            experiment.id,
            actorId,
            priority,
            command.idempotencyKey.strip(),
            self.clock.nowUtc(),
        )
        if job["created"]:
            self.queue.publish(job["id"])
            self.audited(
                "QUEUE",
                "LearningJob",
                job["id"],
                tenantId,
                after={"experimentId": str(experiment.id), "priority": priority},
            )
        return job


class ProcessLearningJobService:
    """Worker use case. Job state provides tenant/actor context; no HTTP dependency."""

    def __init__(
        self,
        store: LearningStore,
        storage: ModelStorage,
        extractor: FeatureExtractor,
        engine: LearningEngine,
        clock,
        codeVersion: str = "0.16.0",
    ) -> None:
        self.store, self.storage, self.extractor, self.engine, self.clock = (
            store,
            storage,
            extractor,
            engine,
            clock,
        )
        self.codeVersion = codeVersion

    def execute(self, command: ProcessLearningJobCommand):
        jobId = asUuid(command.jobId)
        job = self.store.findJob(jobId)
        if not job:
            raise EntityNotFoundError("LearningJob", command.jobId)
        tenantId, experimentId = asUuid(job["tenantId"]), asUuid(job["experimentId"])
        if job["status"] == "COMPLETED":
            return job
        if job["status"] == "RUNNING":
            raise ConflictError("Learning job is already running.")
        now = self.clock.nowUtc()
        experiment = self.store.getExperiment(tenantId, experimentId)
        if not experiment:
            raise EntityNotFoundError("LearningExperiment", str(experimentId))
        dataset = self.store.getDataset(tenantId, experiment.datasetId)
        if not dataset or dataset.status != "APPROVED":
            raise ConflictError("Learning job dataset is not approved.")
        seed = int(experiment.configuration.get("randomSeed", 42))
        runDetails = {
            "status": "RUNNING",
            "startedAt": now,
            "parameters": experiment.configuration,
            "environment": {"python": platform.python_version(), "platform": platform.system()},
            "dependencyVersions": {
                "python": platform.python_version(),
                "engine": type(self.engine).__module__ + "." + type(self.engine).__name__,
            },
            "datasetHash": dataset.datasetHash,
            "codeVersion": self.codeVersion,
            "randomSeed": seed,
        }
        run = self.store.createRun(tenantId, experiment.id, runDetails)
        runId = asUuid(run["id"])
        experiment.start(now)
        self.store.saveExperiment(experiment)
        self.store.updateJob(tenantId, jobId, status="RUNNING", startedAt=now)
        started = time.monotonic()
        try:
            samples = self.extractor.extract(self.store.datasetSamples(tenantId, dataset.id))
            content, trainingMetrics = self.engine.train(
                samples=samples,
                algorithm=experiment.algorithm,
                configuration=experiment.configuration,
                seed=seed,
            )
            version = t.requireSemVer(str(experiment.configuration.get("artifactVersion", "1.0.0")))
            artifactName = str(
                experiment.configuration.get("artifactName", experiment.name)
            ).strip()
            existingVersion = self.store.latestArtifactVersion(tenantId, artifactName)
            if existingVersion == version:
                raise ConflictError("Artifact version is immutable and already exists.")
            uri, checksum = self.storage.putImmutable(tenantId, artifactName, version, content)
            artifact = LearningArtifact(
                uuid.uuid4(),
                tenantId,
                str(experiment.configuration.get("artifactType", "MODEL")),
                artifactName,
                version,
                uri,
                checksum,
                runId,
                "CREATED",
                {
                    "experimentId": str(experiment.id),
                    "datasetId": str(dataset.id),
                    "datasetVersion": dataset.version,
                    "datasetHash": dataset.datasetHash,
                    "trainingMetrics": trainingMetrics,
                    "creatorId": str(experiment.createdById),
                    "randomSeed": seed,
                    "codeVersion": self.codeVersion,
                    "configurationHash": t.integrityHash(experiment.configuration),
                    "baselineArtifactId": (
                        str(experiment.baselineArtifactId)
                        if experiment.baselineArtifactId
                        else None
                    ),
                },
                now,
            )
            self.store.saveArtifact(artifact)
            finished = self.clock.nowUtc()
            elapsed = int((time.monotonic() - started) * 1000)
            self.store.updateRun(
                tenantId,
                runId,
                status="COMPLETED",
                finishedAt=finished,
                artifactId=artifact.id,
                metrics=trainingMetrics,
                logs=[{"event": "completed", "durationMs": elapsed}],
            )
            experiment.complete(finished)
            self.store.saveExperiment(experiment)
            self.store.updateJob(
                tenantId,
                jobId,
                status="COMPLETED",
                completedAt=finished,
                metadata={"runId": str(runId), "artifactId": str(artifact.id)},
            )
            self.store.appendEvent(
                tenantId,
                "LearningArtifactCreated",
                "LearningArtifact",
                str(artifact.id),
                {"checksum": checksum},
                finished,
            )
            audit = getattr(self.store, "audit", None)
            if audit:
                audit(
                    tenantId,
                    asUuid(job["requestedById"]),
                    "RUN",
                    "LearningExperiment",
                    str(experiment.id),
                    newState={"runId": str(runId), "artifactId": str(artifact.id)},
                )
            return {
                "jobId": str(jobId),
                "runId": str(runId),
                "artifact": entityDto(artifact),
                "status": "COMPLETED",
            }
        except Exception as exc:
            failed = self.clock.nowUtc()
            code = type(exc).__name__[:80]
            self.store.updateRun(
                tenantId,
                runId,
                status="FAILED",
                finishedAt=failed,
                errorCode=code,
                errorMessage=str(exc)[:500],
            )
            experiment.fail(failed, code)
            self.store.saveExperiment(experiment)
            self.store.updateJob(
                tenantId,
                jobId,
                status="FAILED",
                completedAt=failed,
                retryCount=int(job.get("retryCount", 0)) + 1,
                errorCode=code,
                errorMessage=str(exc)[:500],
            )
            self.store.appendEvent(
                tenantId,
                "LearningExperimentFailed",
                "LearningExperiment",
                str(experiment.id),
                {"errorCode": code},
                failed,
            )
            raise


class ArtifactLifecycleService(LearningUseCase):
    def __init__(self, store, storage, evaluator, validator, deploymentEngine, **kernel):
        super().__init__(store, **kernel)
        self.storage, self.evaluator, self.validator, self.deploymentEngine = (
            storage,
            evaluator,
            validator,
            deploymentEngine,
        )

    def checkAuthorization(self, command):
        actions = {
            "evaluate": "learning.manage",
            "validate": "learning.manage",
            "approve": "learning.approve",
            "reject": "learning.approve",
            "deploy": "learning.deploy",
            "rollback": "learning.deploy",
        }
        required = actions.get(command.action.lower())
        if not required:
            raise ValidationFailedError("Artifact action is invalid.")
        actorId, tenantId = actorContext()
        if not self.permissionGate.hasPermission(actorId, required, tenantId=tenantId):
            raise PermissionDeniedError(action=required)

    def perform(self, command: ArtifactActionCommand):
        actorId, tenantId = actorContext()
        artifact = self.store.getArtifact(tenantId, asUuid(command.artifactId))
        if not artifact:
            raise EntityNotFoundError("LearningArtifact", command.artifactId)
        action, now = command.action.lower(), self.clock.nowUtc()
        before = {"status": artifact.status}
        if action == "evaluate":
            if not self.storage.verify(artifact.storageUri, artifact.checksum):
                raise ConflictError("Artifact integrity verification failed.")
            metadata = artifact.metadata
            dataset = self.store.getDataset(tenantId, asUuid(metadata["datasetId"]))
            if dataset is None:
                raise ConflictError("Artifact dataset version is unavailable.")
            samples = self.store.datasetSamples(tenantId, dataset.id)
            started = time.monotonic()
            metrics = self.evaluator.evaluate(
                artifactContent=self.storage.read(artifact.storageUri),
                samples=samples,
                trainingMetrics=metadata.get("trainingMetrics", {}),
            )
            baselineMetrics: dict[str, float] = {}
            baselineId = command.policy.get("baselineArtifactId") or metadata.get(
                "baselineArtifactId"
            )
            if baselineId:
                evaluation = self.store.latestEvaluation(tenantId, asUuid(baselineId))
                baselineMetrics = evaluation["metrics"] if evaluation else {}
            result = self.store.saveEvaluation(
                tenantId,
                artifact.id,
                {
                    "datasetId": dataset.id,
                    "datasetVersion": dataset.version,
                    "metrics": t.normalizedMetrics(metrics),
                    "businessMetrics": t.normalizedMetrics(
                        command.policy.get("businessMetrics", {})
                    ),
                    "baselineArtifactId": asUuid(baselineId) if baselineId else None,
                    "baselineComparison": {
                        key: metrics[key] - baselineMetrics.get(key, metrics[key])
                        for key in metrics
                    },
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "evaluatorVersion": "deterministic-v1",
                },
            )
            artifact.evaluated()
            response = result
        elif action == "validate":
            evaluation = self.store.latestEvaluation(tenantId, artifact.id)
            if not evaluation:
                raise ConflictError("Artifact has no evaluation result.")
            policy = t.safePayload(command.policy)
            baselineMetrics = {}
            if evaluation.get("baselineArtifactId"):
                baseline = self.store.latestEvaluation(
                    tenantId, asUuid(evaluation["baselineArtifactId"])
                )
                baselineMetrics = baseline["metrics"] if baseline else {}
            passed, failures = self.validator.validate(
                candidate=evaluation["metrics"],
                baseline=baselineMetrics,
                policy=policy,
                integrityValid=self.storage.verify(artifact.storageUri, artifact.checksum),
            )
            checks = [
                "minimum-performance",
                "regression",
                "artifact-integrity",
                "data-leakage",
                "reproducibility",
                "compatibility",
                "latency",
                "resource-usage",
                "business-constraints",
            ]
            reproducibility = t.integrityHash(
                {
                    "artifact": artifact.checksum,
                    "dataset": artifact.metadata.get("datasetHash"),
                    "seed": artifact.metadata.get("randomSeed"),
                    "code": artifact.metadata.get("codeVersion"),
                    "configuration": artifact.metadata.get("configurationHash"),
                }
            )
            result = self.store.saveValidation(
                tenantId,
                artifact.id,
                {
                    "evaluationId": asUuid(evaluation["id"]),
                    "decision": "PASSED" if passed else "FAILED",
                    "checks": checks,
                    "failures": failures,
                    "policySnapshot": policy,
                    "reproducibilityHash": reproducibility,
                    "validatorVersion": "policy-v1",
                },
            )
            artifact.validated(passed)
            response = result
        elif action in ("approve", "reject"):
            validation = self.store.latestValidation(tenantId, artifact.id)
            if not validation or validation["decision"] != "PASSED":
                raise ConflictError("Approval requires a passed validation.")
            if str(actorId) == str(artifact.metadata.get("creatorId")):
                raise ConflictError(
                    "Artifact creator cannot approve or reject their own candidate."
                )
            if len(command.reason.strip()) < 3:
                raise ValidationFailedError("Review reason is required.")
            approved = action == "approve"
            response = self.store.saveApproval(
                tenantId,
                artifact.id,
                actorId,
                "APPROVED" if approved else "REJECTED",
                command.reason.strip(),
                now,
            )
            artifact.decide(approved)
        elif action == "deploy":
            deploymentPolicy = t.safePayload(command.policy)
            validation = self.store.latestValidation(tenantId, artifact.id)
            if not validation or validation["decision"] != "PASSED":
                raise ConflictError("Deployment requires passed validation.")
            if artifact.status not in ("APPROVED", "CANARY", "STAGED"):
                raise ConflictError("Deployment requires approved artifact state.")
            environment = command.environment.strip().upper()
            active = self.store.activeDeployment(tenantId, environment, artifact.name)
            if active and active["artifactId"] == str(artifact.id):
                deployment = self.store.getDeployment(tenantId, asUuid(active["id"]))
                if deployment is None:
                    raise ConflictError("Active deployment record is unavailable.")
                canaryMetrics = self.store.latestMetrics(tenantId, artifact.id)
                if not canaryMetrics:
                    raise ConflictError(
                        "Canary advancement requires observed metrics from the current stage."
                    )
                canAdvance, canaryFailures = t.compareMetrics(
                    canaryMetrics,
                    deploymentPolicy.get("baselineMetrics", canaryMetrics),
                    minimums=deploymentPolicy.get("minimums", {}),
                    maximumRegression=deploymentPolicy.get("maximumRegression", {}),
                )
                for metricName, maximum in deploymentPolicy.get("maximums", {}).items():
                    actual = canaryMetrics.get(metricName)
                    if actual is None or actual > float(maximum):
                        canAdvance = False
                        canaryFailures.append(
                            {
                                "metric": metricName,
                                "rule": "maximum",
                                "expected": maximum,
                                "actual": actual,
                            }
                        )
                if not canAdvance:
                    raise ConflictError(f"Canary metric gate failed: {canaryFailures}")
                expected = t.nextCanaryStage(deployment.trafficPercentage)
                requested = command.trafficPercentage or expected
                if requested != expected:
                    raise ConflictError(f"Next canary stage must be {expected} percent.")
                deployment.advance(now)
            else:
                requested = command.trafficPercentage or 5
                if requested != 5:
                    raise ConflictError("A new production deployment must start at 5 percent.")
                deployment = LearningDeployment(
                    uuid.uuid4(),
                    tenantId,
                    artifact.id,
                    artifact.version,
                    environment,
                    "STAGED",
                    0,
                    asUuid(active["id"]) if active else None,
                    now,
                    None,
                    actorId,
                )
                deployment.advance(now)
                self.store.snapshot(
                    tenantId,
                    deployment.id,
                    {"previousDeployment": active, "artifact": entityDto(artifact)},
                    t.integrityHash({"previous": active, "artifact": artifact.checksum}),
                    now,
                )
            self.deploymentEngine.apply(
                artifactUri=artifact.storageUri,
                environment=environment,
                trafficPercentage=deployment.trafficPercentage,
            )
            artifact.deploy(deployment.trafficPercentage)
            self.store.saveDeployment(deployment)
            if deployment.status == "ACTIVE" and deployment.previousDeploymentId:
                previousDeployment = self.store.getDeployment(
                    tenantId, deployment.previousDeploymentId
                )
                self.store.markDeploymentStatus(
                    tenantId, deployment.previousDeploymentId, "SUPERSEDED", completedAt=now
                )
                if previousDeployment:
                    previousArtifact = self.store.getArtifact(
                        tenantId, previousDeployment.artifactId
                    )
                    if previousArtifact:
                        previousArtifact.status = "ARCHIVED"
                        self.store.saveArtifact(previousArtifact)
            response = entityDto(deployment)
        else:  # rollback
            if len(command.reason.strip()) < 3:
                raise ValidationFailedError("Rollback reason is required.")
            active = self.store.activeDeployment(
                tenantId, command.environment.strip().upper(), artifact.name
            )
            if not active or active["artifactId"] != str(artifact.id):
                raise ConflictError("Artifact has no active/canary deployment to rollback.")
            if not active["previousDeploymentId"]:
                raise ConflictError("No stable previous deployment exists.")
            deployment = self.store.getDeployment(tenantId, asUuid(active["id"]))
            if deployment is None:
                raise ConflictError("Current deployment record is unavailable.")
            previous = self.store.getDeployment(tenantId, asUuid(active["previousDeploymentId"]))
            if not previous:
                raise ConflictError("Previous stable deployment is unavailable.")
            previousArtifact = self.store.getArtifact(tenantId, previous.artifactId)
            if not previousArtifact:
                raise ConflictError("Previous stable artifact is unavailable.")
            self.deploymentEngine.deactivate(
                artifactUri=artifact.storageUri, environment=deployment.environment
            )
            self.deploymentEngine.apply(
                artifactUri=previousArtifact.storageUri,
                environment=previous.environment,
                trafficPercentage=100,
            )
            deployment.rollback(now)
            self.store.saveDeployment(deployment)
            self.store.markDeploymentStatus(
                tenantId,
                deployment.id,
                "ROLLED_BACK",
                completedAt=now,
                rollbackReason=command.reason.strip(),
            )
            self.store.markDeploymentStatus(tenantId, previous.id, "ACTIVE", completedAt=now)
            artifact.rollback()
            previousArtifact.status = "ACTIVE"
            self.store.saveArtifact(previousArtifact)
            response = {
                "rolledBackDeploymentId": str(deployment.id),
                "restoredDeploymentId": str(previous.id),
                "restoredArtifactId": str(previousArtifact.id),
            }
        self.store.saveArtifact(artifact)
        eventName = {
            "evaluate": "EvaluationCompleted",
            "validate": "ValidationPassed"
            if artifact.status == "VALIDATED"
            else "ValidationFailed",
            "approve": "LearningArtifactApproved",
            "reject": "LearningArtifactRejected",
            "deploy": "DeploymentCompleted",
            "rollback": "RollbackCompleted",
        }[action]
        self.store.appendEvent(
            tenantId,
            eventName,
            "LearningArtifact",
            str(artifact.id),
            {"status": artifact.status},
            now,
        )
        self.audited(
            action.upper(),
            "LearningArtifact",
            str(artifact.id),
            tenantId,
            before=before,
            after={"status": artifact.status},
        )
        return response


class RecordFeedbackService(LearningUseCase):
    requiredAction = "learning.feedback"

    def perform(self, command: RecordFeedbackCommand):
        actorId, tenantId = actorContext()
        if not command.source.strip():
            raise ValidationFailedError("Feedback source is required.")
        feedbackType = t.requireChoice(command.feedbackType, t.FEEDBACK_TYPES, "feedbackType")
        humanAction = command.humanAction.strip().upper()
        if humanAction:
            humanAction = t.requireChoice(humanAction, t.HUMAN_ACTIONS, "humanAction")
        identifiers = [command.experienceId, command.deploymentId, command.artifactId]
        if not any(identifiers):
            raise ValidationFailedError(
                "Feedback requires an experience, deployment or artifact source."
            )
        if command.score is not None and not -1 <= command.score <= 1:
            raise ValidationFailedError("Feedback score must be between -1 and 1.")
        if command.experienceId and not self.store.experienceExists(
            tenantId, asUuid(command.experienceId)
        ):
            raise EntityNotFoundError("LearningExperience", command.experienceId)
        if command.deploymentId and not self.store.getDeployment(
            tenantId, asUuid(command.deploymentId)
        ):
            raise EntityNotFoundError("LearningDeployment", command.deploymentId)
        if command.artifactId and not self.store.getArtifact(tenantId, asUuid(command.artifactId)):
            raise EntityNotFoundError("LearningArtifact", command.artifactId)
        result = self.store.saveFeedback(
            tenantId,
            actorId,
            {
                "experienceId": asUuid(command.experienceId) if command.experienceId else None,
                "deploymentId": asUuid(command.deploymentId) if command.deploymentId else None,
                "artifactId": asUuid(command.artifactId) if command.artifactId else None,
                "feedbackType": feedbackType,
                "humanAction": humanAction,
                "score": command.score,
                "source": command.source.strip(),
                "comment": command.comment[:2000],
                "metadata": t.safePayload(command.metadata),
            },
        )
        self.store.appendEvent(
            tenantId,
            "LearningFeedbackReceived",
            "LearningFeedback",
            result["id"],
            {"type": feedbackType},
            self.clock.nowUtc(),
        )
        self.audited(
            "FEEDBACK",
            "LearningFeedback",
            result["id"],
            tenantId,
            after={"type": feedbackType, "source": command.source},
        )
        return result


class MonitoringService(LearningUseCase):
    requiredAction = "learning.monitor"

    def __init__(self, store, detector: DriftDetector, **kernel):
        super().__init__(store, **kernel)
        self.detector = detector

    def perform(self, command):
        _actorId, tenantId = actorContext()
        if isinstance(command, RecordMetricsCommand):
            artifactId = asUuid(command.artifactId)
            if not self.store.getArtifact(tenantId, artifactId):
                raise EntityNotFoundError("LearningArtifact", command.artifactId)
            deploymentId = asUuid(command.deploymentId) if command.deploymentId else None
            if deploymentId:
                deployment = self.store.getDeployment(tenantId, deploymentId)
                if not deployment or deployment.artifactId != artifactId:
                    raise ValidationFailedError(
                        "Metric deployment must belong to the selected artifact."
                    )
            return self.store.recordMetrics(
                tenantId,
                artifactId,
                deploymentId,
                t.normalizedMetrics(command.metrics),
                self.clock.nowUtc(),
            )
        if isinstance(command, DetectDriftCommand):
            artifactId = asUuid(command.artifactId)
            driftType = t.requireChoice(command.driftType, t.DRIFT_TYPES, "driftType")
            current = self.store.latestMetrics(tenantId, artifactId)
            if not current:
                raise ConflictError("Drift detection requires observed production metrics.")
            detected, changes = self.detector.detect(
                baseline=t.normalizedMetrics(command.baselineMetrics),
                current=current,
                thresholds=t.normalizedMetrics(command.thresholds),
            )
            result = {
                "artifactId": str(artifactId),
                "driftType": driftType,
                "detected": detected,
                "changes": changes,
                "current": current,
            }
            if detected:
                self.store.appendEvent(
                    tenantId,
                    "DriftDetected",
                    "LearningArtifact",
                    str(artifactId),
                    result,
                    self.clock.nowUtc(),
                )
                self.audited("DRIFT", "LearningArtifact", str(artifactId), tenantId, after=result)
            return result
        return self.store.metricSummary(tenantId)


class LearningQueryService(LearningUseCase):
    requiredAction = "learning.view"

    def perform(self, query: LearningListQuery):
        _actorId, tenantId = actorContext()
        if query.limit < 1 or query.limit > 500:
            raise ValidationFailedError("List limit must be between 1 and 500.")
        resource = query.resource.lower()
        if resource == "experiences":
            return self.store.listExperiences(tenantId, limit=query.limit)
        if resource == "datasets":
            return self.store.listDatasets(tenantId)
        if resource == "experiments":
            return self.store.listExperiments(tenantId)
        if resource == "artifacts":
            if query.identifier:
                artifact = self.store.getArtifact(tenantId, asUuid(query.identifier))
                if not artifact:
                    raise EntityNotFoundError("LearningArtifact", query.identifier)
                return entityDto(artifact)
            return self.store.listArtifacts(tenantId)
        if resource == "deployments":
            return self.store.listDeployments(tenantId)
        if resource == "jobs":
            job = self.store.getJob(tenantId, asUuid(query.identifier))
            if not job:
                raise EntityNotFoundError("LearningJob", query.identifier)
            return job
        if resource == "metrics":
            return self.store.metricSummary(tenantId)
        raise ValidationFailedError("Learning resource is invalid.")
