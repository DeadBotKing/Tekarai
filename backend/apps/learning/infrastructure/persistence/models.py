"""Django persistence for the Phase 16 Self-Learning Platform."""

from __future__ import annotations

import uuid

from django.db import models


def uuidPk():
    return models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


class TenantRecord(models.Model):
    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class LearningExperienceModel(TenantRecord):
    source = models.CharField(max_length=120)
    context = models.JSONField(default=dict)
    inputData = models.JSONField(default=dict)
    action = models.CharField(max_length=160)
    expectedOutcome = models.JSONField(default=dict)
    actualOutcome = models.JSONField(default=dict)
    reward = models.FloatField(null=True, blank=True)
    success = models.BooleanField(null=True, blank=True)
    occurredAt = models.DateTimeField(db_index=True)
    metadata = models.JSONField(default=dict)
    traceId = models.CharField(max_length=160, db_index=True)
    integrityHash = models.CharField(max_length=64)

    class Meta:
        db_table = "learningExperiences"
        constraints = [
            models.UniqueConstraint(fields=["tenantId", "traceId"], name="UQ_LearnExp_t_trace")
        ]
        indexes = [models.Index(fields=["tenantId", "occurredAt"], name="IX_LearnExp_t_time")]


class LearningDatasetModel(TenantRecord):
    name = models.CharField(max_length=160)
    version = models.CharField(max_length=48)
    description = models.TextField(blank=True)
    source = models.CharField(max_length=120)
    status = models.CharField(max_length=20, db_index=True)
    sampleCount = models.PositiveIntegerField(default=0)
    datasetHash = models.CharField(max_length=64, blank=True)
    createdById = models.UUIDField()
    metadata = models.JSONField(default=dict)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "learningDatasets"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "name", "version"], name="UQ_LearnData_t_name_ver"
            )
        ]
        indexes = [
            models.Index(fields=["tenantId", "status", "createdAt"], name="IX_LearnData_t_status")
        ]


class LearningSampleModel(TenantRecord):
    datasetId = models.UUIDField(db_index=True)
    inputData = models.JSONField(default=dict)
    target = models.JSONField(default=dict)
    context = models.JSONField(default=dict)
    sourceExperienceId = models.UUIDField(db_index=True)
    weight = models.FloatField(default=1.0)
    metadata = models.JSONField(default=dict)
    sampleHash = models.CharField(max_length=64)

    class Meta:
        db_table = "learningSamples"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "datasetId", "sampleHash"], name="UQ_LearnSample_t_data_hash"
            )
        ]
        indexes = [
            models.Index(
                fields=["tenantId", "datasetId", "createdAt"], name="IX_LearnSample_t_data"
            )
        ]


class LearningExperimentModel(TenantRecord):
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    datasetId = models.UUIDField(db_index=True)
    datasetVersion = models.CharField(max_length=48)
    algorithm = models.CharField(max_length=120)
    configuration = models.JSONField(default=dict)
    baselineArtifactId = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, db_index=True)
    completedAt = models.DateTimeField(null=True, blank=True)
    createdById = models.UUIDField()

    class Meta:
        db_table = "learningExperiments"
        constraints = [
            models.UniqueConstraint(fields=["tenantId", "name"], name="UQ_LearnExperiment_t_name")
        ]
        indexes = [
            models.Index(
                fields=["tenantId", "status", "createdAt"], name="IX_LearnExperiment_t_status"
            )
        ]


class LearningRunModel(TenantRecord):
    experimentId = models.UUIDField(db_index=True)
    startedAt = models.DateTimeField(null=True, blank=True)
    finishedAt = models.DateTimeField(null=True, blank=True)
    parameters = models.JSONField(default=dict)
    environment = models.JSONField(default=dict)
    dependencyVersions = models.JSONField(default=dict)
    datasetHash = models.CharField(max_length=64)
    codeVersion = models.CharField(max_length=80)
    artifactId = models.UUIDField(null=True, blank=True)
    metrics = models.JSONField(default=dict)
    logs = models.JSONField(default=list)
    randomSeed = models.BigIntegerField()
    status = models.CharField(max_length=20, db_index=True)
    errorCode = models.CharField(max_length=80, blank=True)
    errorMessage = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "learningRuns"
        indexes = [
            models.Index(fields=["tenantId", "experimentId", "createdAt"], name="IX_LearnRun_t_exp")
        ]


class LearningArtifactModel(TenantRecord):
    artifactType = models.CharField(max_length=24)
    name = models.CharField(max_length=160)
    version = models.CharField(max_length=48)
    storageUri = models.CharField(max_length=1000)
    checksum = models.CharField(max_length=64, db_index=True)
    createdByRunId = models.UUIDField(db_index=True)
    status = models.CharField(max_length=24, db_index=True)
    metadata = models.JSONField(default=dict)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "learningArtifacts"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "name", "version"], name="UQ_LearnArtifact_t_name_ver"
            ),
            models.UniqueConstraint(
                fields=["tenantId", "checksum"], name="UQ_LearnArtifact_t_checksum"
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenantId", "status", "createdAt"], name="IX_LearnArtifact_t_status"
            )
        ]


class ModelVersionModel(TenantRecord):
    artifactId = models.UUIDField(db_index=True)
    modelName = models.CharField(max_length=160)
    version = models.CharField(max_length=48)
    checksum = models.CharField(max_length=64)

    class Meta:
        db_table = "modelVersions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "modelName", "version"], name="UQ_ModelVersion_t_name_ver"
            )
        ]


class PolicyVersionModel(TenantRecord):
    artifactId = models.UUIDField(db_index=True)
    policyName = models.CharField(max_length=160)
    version = models.CharField(max_length=48)
    policy = models.JSONField(default=dict)
    checksum = models.CharField(max_length=64)

    class Meta:
        db_table = "policyVersions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "policyName", "version"], name="UQ_PolicyVersion_t_name_ver"
            )
        ]


class EvaluationResultModel(TenantRecord):
    artifactId = models.UUIDField(db_index=True)
    datasetId = models.UUIDField()
    datasetVersion = models.CharField(max_length=48)
    metrics = models.JSONField(default=dict)
    businessMetrics = models.JSONField(default=dict)
    baselineArtifactId = models.UUIDField(null=True, blank=True)
    baselineComparison = models.JSONField(default=dict)
    durationMs = models.PositiveIntegerField(default=0)
    evaluatorVersion = models.CharField(max_length=80)

    class Meta:
        db_table = "evaluationResults"
        indexes = [
            models.Index(fields=["tenantId", "artifactId", "createdAt"], name="IX_LearnEval_t_art")
        ]


class ValidationResultModel(TenantRecord):
    artifactId = models.UUIDField(db_index=True)
    evaluationId = models.UUIDField()
    decision = models.CharField(max_length=12, db_index=True)
    checks = models.JSONField(default=list)
    failures = models.JSONField(default=list)
    policySnapshot = models.JSONField(default=dict)
    reproducibilityHash = models.CharField(max_length=64)
    validatorVersion = models.CharField(max_length=80)

    class Meta:
        db_table = "validationResults"
        indexes = [
            models.Index(fields=["tenantId", "artifactId", "createdAt"], name="IX_LearnValid_t_art")
        ]


class LearningApprovalModel(TenantRecord):
    artifactId = models.UUIDField(db_index=True)
    reviewerId = models.UUIDField()
    decision = models.CharField(max_length=12)
    reason = models.TextField()
    decidedAt = models.DateTimeField()

    class Meta:
        db_table = "learningApprovals"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "artifactId", "reviewerId"], name="UQ_LearnApproval_t_art_user"
            )
        ]


class LearningDeploymentModel(TenantRecord):
    artifactId = models.UUIDField(db_index=True)
    artifactVersion = models.CharField(max_length=48)
    artifactName = models.CharField(max_length=160)
    environment = models.CharField(max_length=80)
    status = models.CharField(max_length=24, db_index=True)
    trafficPercentage = models.PositiveSmallIntegerField(default=0)
    previousDeploymentId = models.UUIDField(null=True, blank=True)
    startedAt = models.DateTimeField()
    completedAt = models.DateTimeField(null=True, blank=True)
    deployedById = models.UUIDField()
    rollbackReason = models.TextField(blank=True)

    class Meta:
        db_table = "learningDeployments"
        indexes = [
            models.Index(fields=["tenantId", "environment", "status"], name="IX_LearnDeploy_t_env")
        ]


class LearningFeedbackModel(TenantRecord):
    experienceId = models.UUIDField(null=True, blank=True, db_index=True)
    deploymentId = models.UUIDField(null=True, blank=True, db_index=True)
    artifactId = models.UUIDField(null=True, blank=True, db_index=True)
    feedbackType = models.CharField(max_length=16)
    humanAction = models.CharField(max_length=16, blank=True)
    score = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=120)
    comment = models.TextField(blank=True)
    createdById = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "learningFeedback"
        indexes = [
            models.Index(
                fields=["tenantId", "artifactId", "createdAt"], name="IX_LearnFeedback_t_art"
            )
        ]


class LearningMetricModel(TenantRecord):
    artifactId = models.UUIDField(db_index=True)
    deploymentId = models.UUIDField(null=True, blank=True)
    metricName = models.CharField(max_length=120)
    metricValue = models.FloatField()
    observedAt = models.DateTimeField(db_index=True)
    dimensions = models.JSONField(default=dict)

    class Meta:
        db_table = "learningMetrics"
        indexes = [
            models.Index(
                fields=["tenantId", "artifactId", "metricName", "observedAt"],
                name="IX_LearnMetric_t_art_name",
            )
        ]


class LearningEventModel(TenantRecord):
    eventType = models.CharField(max_length=80, db_index=True)
    targetType = models.CharField(max_length=48)
    targetId = models.CharField(max_length=120)
    data = models.JSONField(default=dict)
    occurredAt = models.DateTimeField(db_index=True)
    eventHash = models.CharField(max_length=64)

    class Meta:
        db_table = "learningEvents"
        indexes = [models.Index(fields=["tenantId", "occurredAt"], name="IX_LearnEvent_t_time")]


class LearningSnapshotModel(TenantRecord):
    deploymentId = models.UUIDField(db_index=True)
    state = models.JSONField(default=dict)
    checksum = models.CharField(max_length=64)

    class Meta:
        db_table = "learningSnapshots"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "deploymentId", "checksum"], name="UQ_LearnSnap_t_dep_hash"
            )
        ]


class LearningJobModel(TenantRecord):
    jobType = models.CharField(max_length=48, default="EXPERIMENT_RUN")
    experimentId = models.UUIDField(db_index=True)
    status = models.CharField(max_length=20, db_index=True)
    priority = models.CharField(max_length=16)
    requestedById = models.UUIDField()
    idempotencyKey = models.CharField(max_length=160)
    startedAt = models.DateTimeField(null=True, blank=True)
    completedAt = models.DateTimeField(null=True, blank=True)
    retryCount = models.PositiveIntegerField(default=0)
    errorCode = models.CharField(max_length=80, blank=True)
    errorMessage = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "learningJobs"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "idempotencyKey"], name="UQ_LearnJob_t_idem"
            )
        ]
        indexes = [
            models.Index(fields=["tenantId", "status", "createdAt"], name="IX_LearnJob_t_status")
        ]


class LearningAuditModel(TenantRecord):
    actorId = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=64, db_index=True)
    targetType = models.CharField(max_length=48)
    targetId = models.CharField(max_length=120)
    previousState = models.JSONField(default=dict)
    newState = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    auditHash = models.CharField(max_length=64)

    class Meta:
        db_table = "learningAudits"
        indexes = [models.Index(fields=["tenantId", "createdAt"], name="IX_LearnAudit_t_time")]
