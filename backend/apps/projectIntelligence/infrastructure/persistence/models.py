"""Tenant-scoped persistence for the Phase 17 Project Intelligence Platform."""

from __future__ import annotations

import uuid

from django.db import models


def pk():
    return models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


class TenantRecord(models.Model):
    id = pk()
    tenantId = models.UUIDField(db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class ImmutableTenantRecord(TenantRecord):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError(f"{type(self).__name__} is immutable; create a new version.")
        return super().save(*args, **kwargs)


class ProjectSnapshotModel(ImmutableTenantRecord):
    projectId = models.UUIDField(db_index=True)
    version = models.PositiveIntegerField()
    workspace = models.CharField(max_length=1000)
    analysisVersion = models.CharField(max_length=40)
    snapshotHash = models.CharField(max_length=64)
    artifactUri = models.CharField(max_length=1200)
    artifactChecksum = models.CharField(max_length=64)
    environment = models.JSONField(default=dict)
    gitState = models.JSONField(default=dict)
    fileCount = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "projectSnapshots"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "projectId", "version"], name="UQ_PISnap_t_p_ver"
            ),
            models.UniqueConstraint(
                fields=["tenantId", "projectId", "snapshotHash"], name="UQ_PISnap_t_p_hash"
            ),
        ]
        indexes = [
            models.Index(fields=["tenantId", "projectId", "createdAt"], name="IX_PISnap_t_p_time")
        ]


class ProjectFileModel(ImmutableTenantRecord):
    snapshotId = models.UUIDField(db_index=True)
    projectId = models.UUIDField(db_index=True)
    path = models.CharField(max_length=1400)
    fileType = models.CharField(max_length=30)
    size = models.BigIntegerField()
    modifiedNs = models.BigIntegerField()
    binary = models.BooleanField()
    generated = models.BooleanField()
    ignored = models.BooleanField()
    temporary = models.BooleanField()
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "projectFiles"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "snapshotId", "path"], name="UQ_PIFile_t_s_path"
            )
        ]


class ProjectFileHashModel(ImmutableTenantRecord):
    snapshotId = models.UUIDField(db_index=True)
    projectId = models.UUIDField(db_index=True)
    path = models.CharField(max_length=1400)
    fileHash = models.CharField(max_length=64, db_index=True)

    class Meta:
        db_table = "projectFileHashes"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "snapshotId", "path"], name="UQ_PIHash_t_s_path"
            )
        ]


class ProjectAnalysisModel(ImmutableTenantRecord):
    projectId = models.UUIDField(db_index=True)
    snapshotId = models.UUIDField(db_index=True)
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=20)
    analysisHash = models.CharField(max_length=64)
    startedAt = models.DateTimeField()
    completedAt = models.DateTimeField(null=True)
    incremental = models.BooleanField(default=False)
    affectedFiles = models.JSONField(default=list)
    metrics = models.JSONField(default=dict)

    class Meta:
        db_table = "projectAnalyses"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "projectId", "version"], name="UQ_PIAnal_t_p_ver"
            )
        ]


class ProjectAnalysisResultModel(ImmutableTenantRecord):
    analysisId = models.UUIDField(db_index=True)
    projectId = models.UUIDField(db_index=True)
    analyzerName = models.CharField(max_length=80)
    analyzerVersion = models.CharField(max_length=30)
    status = models.CharField(max_length=20)
    findings = models.JSONField(default=list)
    metrics = models.JSONField(default=dict)
    errors = models.JSONField(default=list)
    metadata = models.JSONField(default=dict)
    resultHash = models.CharField(max_length=64)

    class Meta:
        db_table = "projectAnalysisResults"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "analysisId", "analyzerName"], name="UQ_PIResult_t_a_name"
            )
        ]


class ProjectDependencyModel(ImmutableTenantRecord):
    analysisId = models.UUIDField(db_index=True)
    projectId = models.UUIDField(db_index=True)
    source = models.CharField(max_length=1400)
    target = models.CharField(max_length=1400)
    dependencyType = models.CharField(max_length=30)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "projectDependencies"
        indexes = [
            models.Index(fields=["tenantId", "projectId", "source"], name="IX_PIDep_t_p_src")
        ]


class ProjectArchitectureModel(ImmutableTenantRecord):
    analysisId = models.UUIDField(db_index=True)
    projectId = models.UUIDField(db_index=True)
    version = models.PositiveIntegerField()
    model = models.JSONField(default=dict)
    violationCount = models.PositiveIntegerField(default=0)
    architectureHash = models.CharField(max_length=64)

    class Meta:
        db_table = "projectArchitectures"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "projectId", "version"], name="UQ_PIArch_t_p_ver"
            )
        ]


class ProjectKnowledgeModel(ImmutableTenantRecord):
    projectId = models.UUIDField(db_index=True)
    analysisId = models.UUIDField(db_index=True)
    snapshotId = models.UUIDField(db_index=True)
    version = models.PositiveIntegerField()
    knowledge = models.JSONField(default=dict)
    knowledgeHash = models.CharField(max_length=64)

    class Meta:
        db_table = "projectKnowledge"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "projectId", "version"], name="UQ_PIKnow_t_p_ver"
            )
        ]


class ProjectKnowledgeNodeModel(ImmutableTenantRecord):
    knowledgeId = models.UUIDField(db_index=True)
    projectId = models.UUIDField(db_index=True)
    nodeKey = models.CharField(max_length=1400)
    nodeType = models.CharField(max_length=40)
    properties = models.JSONField(default=dict)

    class Meta:
        db_table = "projectKnowledgeNodes"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "knowledgeId", "nodeKey"], name="UQ_PINode_t_k_key"
            )
        ]


class ProjectKnowledgeEdgeModel(ImmutableTenantRecord):
    knowledgeId = models.UUIDField(db_index=True)
    projectId = models.UUIDField(db_index=True)
    sourceKey = models.CharField(max_length=1400)
    targetKey = models.CharField(max_length=1400)
    edgeType = models.CharField(max_length=40)
    properties = models.JSONField(default=dict)

    class Meta:
        db_table = "projectKnowledgeEdges"
        indexes = [
            models.Index(fields=["tenantId", "knowledgeId", "sourceKey"], name="IX_PIEdge_t_k_src")
        ]


class ProjectInsightModel(ImmutableTenantRecord):
    projectId = models.UUIDField(db_index=True)
    knowledgeId = models.UUIDField(db_index=True)
    kind = models.CharField(max_length=80)
    title = models.CharField(max_length=300)
    severity = models.CharField(max_length=12)
    confidence = models.FloatField()
    evidence = models.JSONField(default=list)
    source = models.CharField(max_length=100)
    impact = models.TextField()

    class Meta:
        db_table = "projectInsights"
        indexes = [
            models.Index(fields=["tenantId", "projectId", "severity"], name="IX_PIInsight_t_p_sev")
        ]


class ProjectRecommendationModel(ImmutableTenantRecord):
    projectId = models.UUIDField(db_index=True)
    insightId = models.UUIDField(db_index=True)
    version = models.PositiveIntegerField()
    problem = models.TextField()
    recommendation = models.TextField()
    reason = models.TextField()
    evidence = models.JSONField(default=list)
    expectedBenefit = models.TextField()
    risk = models.TextField()
    priority = models.CharField(max_length=12)

    class Meta:
        db_table = "projectRecommendations"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "insightId", "version"], name="UQ_PIRec_t_i_ver"
            )
        ]


class ProjectDecisionModel(ImmutableTenantRecord):
    projectId = models.UUIDField(db_index=True)
    recommendationId = models.UUIDField(db_index=True)
    version = models.PositiveIntegerField()
    decision = models.CharField(max_length=20)
    evidence = models.JSONField(default=list)
    reason = models.TextField()
    decidedById = models.UUIDField(null=True)

    class Meta:
        db_table = "projectDecisions"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "recommendationId", "version"], name="UQ_PIDec_t_r_ver"
            )
        ]


class ProjectContextPackageModel(ImmutableTenantRecord):
    projectId = models.UUIDField(db_index=True)
    snapshotId = models.UUIDField()
    knowledgeId = models.UUIDField()
    version = models.PositiveIntegerField()
    generatorVersion = models.CharField(max_length=30)
    task = models.TextField()
    tokenBudget = models.PositiveIntegerField()
    includedFiles = models.JSONField(default=list)
    includedModules = models.JSONField(default=list)
    excludedFiles = models.JSONField(default=list)
    package = models.JSONField(default=dict)
    contextHash = models.CharField(max_length=64)

    class Meta:
        db_table = "projectContextPackages"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "projectId", "version"], name="UQ_PICtx_t_p_ver"
            )
        ]


class ProjectStateModel(TenantRecord):
    projectId = models.UUIDField()
    status = models.CharField(max_length=20)
    snapshotId = models.UUIDField(null=True)
    error = models.TextField(blank=True)
    updatedAt = models.DateTimeField()

    class Meta:
        db_table = "projectStates"
        constraints = [
            models.UniqueConstraint(fields=["tenantId", "projectId"], name="UQ_PIState_t_p")
        ]


class ProjectChangeModel(ImmutableTenantRecord):
    projectId = models.UUIDField(db_index=True)
    fromSnapshotId = models.UUIDField(null=True)
    toSnapshotId = models.UUIDField()
    added = models.JSONField(default=list)
    modified = models.JSONField(default=list)
    deleted = models.JSONField(default=list)
    renamed = models.JSONField(default=list)
    changeHash = models.CharField(max_length=64)

    class Meta:
        db_table = "projectChanges"
        indexes = [
            models.Index(fields=["tenantId", "projectId", "createdAt"], name="IX_PIChange_t_p_time")
        ]


class ProjectResumeModel(ImmutableTenantRecord):
    projectId = models.UUIDField(db_index=True)
    snapshotId = models.UUIDField()
    knowledgeId = models.UUIDField()
    version = models.PositiveIntegerField()
    resume = models.JSONField(default=dict)
    resumeHash = models.CharField(max_length=64)

    class Meta:
        db_table = "projectResume"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "projectId", "version"], name="UQ_PIResume_t_p_ver"
            )
        ]


class IntelligenceJobModel(TenantRecord):
    projectId = models.UUIDField(db_index=True)
    actorId = models.UUIDField()
    jobType = models.CharField(max_length=30)
    status = models.CharField(max_length=20)
    priority = models.PositiveSmallIntegerField(default=5)
    idempotencyKey = models.CharField(max_length=120)
    startedAt = models.DateTimeField(null=True)
    completedAt = models.DateTimeField(null=True)
    retryCount = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)
    result = models.JSONField(default=dict)

    class Meta:
        db_table = "projectIntelligenceJobs"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "projectId", "idempotencyKey"], name="UQ_PIJob_t_p_key"
            )
        ]


class IntelligenceAuditModel(ImmutableTenantRecord):
    actorId = models.UUIDField()
    projectId = models.UUIDField(db_index=True)
    action = models.CharField(max_length=80)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "projectIntelligenceAudit"
        indexes = [
            models.Index(fields=["tenantId", "projectId", "createdAt"], name="IX_PIAudit_t_p_time")
        ]


class IntelligenceEventModel(ImmutableTenantRecord):
    projectId = models.UUIDField(db_index=True)
    eventType = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    eventHash = models.CharField(max_length=64)

    class Meta:
        db_table = "projectIntelligenceEvents"
        indexes = [
            models.Index(fields=["tenantId", "eventType", "createdAt"], name="IX_PIEvent_t_type")
        ]


class AnalysisCacheModel(TenantRecord):
    cacheKey = models.CharField(max_length=64)
    value = models.JSONField(default=dict)
    expiresAt = models.DateTimeField(null=True)

    class Meta:
        db_table = "projectAnalysisCache"
        constraints = [
            models.UniqueConstraint(fields=["tenantId", "cacheKey"], name="UQ_PICache_t_key")
        ]
