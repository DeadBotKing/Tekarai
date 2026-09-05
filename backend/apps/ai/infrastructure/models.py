from __future__ import annotations
import uuid
from django.db import models

class BaseAiModel(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    tenantId=models.UUIDField(db_index=True)
    createdAt=models.DateTimeField(auto_now_add=True); updatedAt=models.DateTimeField(auto_now=True)
    class Meta: abstract=True

class AIProviderModel(BaseAiModel):
    code=models.CharField(max_length=80); name=models.CharField(max_length=160); providerType=models.CharField(max_length=40)
    configurationReference=models.CharField(max_length=255,blank=True); isActive=models.BooleanField(default=True); metadata=models.JSONField(default=dict,blank=True)
    class Meta: db_table='aiProviders'; unique_together=[('tenantId','code')]
class AIModelModel(BaseAiModel):
    provider=models.ForeignKey(AIProviderModel,on_delete=models.PROTECT,related_name='models'); code=models.CharField(max_length=120); name=models.CharField(max_length=160); modelType=models.CharField(max_length=40,default='LLM'); version=models.CharField(max_length=80,blank=True); contextWindow=models.PositiveIntegerField(default=8192); inputCapability=models.JSONField(default=list); outputCapability=models.JSONField(default=list); supportsStreaming=models.BooleanField(default=False); supportsTools=models.BooleanField(default=False); supportsEmbeddings=models.BooleanField(default=False); supportsVision=models.BooleanField(default=False); isActive=models.BooleanField(default=True); metadata=models.JSONField(default=dict,blank=True)
    # Phase 13-N billable rates, denominated in AI_USAGE_DEFAULT_CURRENCY.
    inputCostPer1k = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    outputCostPer1k = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    class Meta: db_table='aiModels'; unique_together=[('tenantId','code','version')]
class AICapabilityModel(BaseAiModel):
    code=models.CharField(max_length=100); name=models.CharField(max_length=160); description=models.TextField(blank=True); isActive=models.BooleanField(default=True); policy=models.JSONField(default=dict,blank=True)
    class Meta: db_table='aiCapabilities'; unique_together=[('tenantId','code')]
class AIPromptModel(BaseAiModel):
    code=models.CharField(max_length=160); name=models.CharField(max_length=160); description=models.TextField(blank=True); isActive=models.BooleanField(default=True)
    class Meta: db_table='aiPrompts'; unique_together=[('tenantId','code')]
class AIPromptVersionModel(BaseAiModel):
    prompt=models.ForeignKey(AIPromptModel,on_delete=models.PROTECT,related_name='versions'); version=models.PositiveIntegerField(); template=models.TextField(); systemInstruction=models.TextField(blank=True); variables=models.JSONField(default=list); outputSchema=models.JSONField(default=dict,blank=True); modelConstraints=models.JSONField(default=dict,blank=True); createdBy=models.UUIDField(null=True); isActive=models.BooleanField(default=False)
    class Meta: db_table='aiPromptVersions'; unique_together=[('prompt','version')]
class AIRequestModel(BaseAiModel):
    capability=models.ForeignKey(AICapabilityModel,on_delete=models.PROTECT); requestedBy=models.UUIDField(null=True); requestType=models.CharField(max_length=40); sourceDomain=models.CharField(max_length=100,blank=True); sourceEntityType=models.CharField(max_length=100,blank=True); sourceEntityId=models.CharField(max_length=100,blank=True); priority=models.CharField(max_length=20,default='NORMAL'); status=models.CharField(max_length=30,default='PENDING'); correlationId=models.CharField(max_length=128,db_index=True); traceId=models.CharField(max_length=128,blank=True); parentRequestId=models.UUIDField(null=True); inputData=models.JSONField(default=dict); startedAt=models.DateTimeField(null=True); completedAt=models.DateTimeField(null=True); errorCode=models.CharField(max_length=80,blank=True); idempotencyKey=models.CharField(max_length=160,blank=True)
    class Meta: db_table='aiRequests'; indexes=[models.Index(fields=['tenantId','status','createdAt'])]
class AIResponseModel(BaseAiModel):
    request=models.OneToOneField(AIRequestModel,on_delete=models.PROTECT,related_name='response'); model=models.ForeignKey(AIModelModel,on_delete=models.PROTECT); status=models.CharField(max_length=30); content=models.TextField(blank=True); structuredData=models.JSONField(default=dict,blank=True); inputTokens=models.PositiveIntegerField(default=0); outputTokens=models.PositiveIntegerField(default=0); totalTokens=models.PositiveIntegerField(default=0); latencyMs=models.PositiveIntegerField(default=0); outputClassification=models.CharField(max_length=30,default='ADVISORY'); promptVersion=models.ForeignKey(AIPromptVersionModel,null=True,on_delete=models.PROTECT); createdAt=models.DateTimeField(auto_now_add=True)
    class Meta: db_table='aiResponses'
class AIUsageModel(BaseAiModel):
    request=models.OneToOneField(AIRequestModel,on_delete=models.PROTECT); provider=models.ForeignKey(AIProviderModel,on_delete=models.PROTECT); model=models.ForeignKey(AIModelModel,on_delete=models.PROTECT); inputTokens=models.PositiveIntegerField(default=0); outputTokens=models.PositiveIntegerField(default=0); totalTokens=models.PositiveIntegerField(default=0); estimatedCost=models.DecimalField(max_digits=18,decimal_places=8,default=0); currency=models.CharField(max_length=3,default='USD'); queueTimeMs=models.PositiveIntegerField(default=0); contextBuildTimeMs=models.PositiveIntegerField(default=0); providerTimeMs=models.PositiveIntegerField(default=0); validationTimeMs=models.PositiveIntegerField(default=0); totalTimeMs=models.PositiveIntegerField(default=0)
    class Meta: db_table='aiUsage'
class AIFeedbackModel(BaseAiModel):
    request=models.ForeignKey(AIRequestModel,on_delete=models.PROTECT); response=models.ForeignKey(AIResponseModel,on_delete=models.PROTECT); userId=models.UUIDField(null=True); rating=models.PositiveSmallIntegerField(null=True); sentiment=models.CharField(max_length=20,blank=True); correction=models.TextField(blank=True); comment=models.TextField(blank=True)
    class Meta: db_table='aiFeedback'
class AIMemoryModel(BaseAiModel):
    userId=models.UUIDField(null=True); scope=models.CharField(max_length=40); key=models.CharField(max_length=160); value=models.JSONField(); version=models.PositiveIntegerField(default=1); isActive=models.BooleanField(default=True); expiresAt=models.DateTimeField(null=True)
    class Meta: db_table='aiMemory'; unique_together=[('tenantId','scope','key','version')]
class AIKnowledgeItemModel(BaseAiModel):
    sourceDomain=models.CharField(max_length=100); sourceEntityType=models.CharField(max_length=100); sourceEntityId=models.CharField(max_length=160); title=models.CharField(max_length=300); content=models.TextField(); classification=models.CharField(max_length=30,default='INTERNAL'); checksum=models.CharField(max_length=128); status=models.CharField(max_length=30,default='PENDING'); metadata=models.JSONField(default=dict)
    class Meta: db_table='aiKnowledgeItems'; unique_together=[('tenantId','sourceDomain','sourceEntityId','checksum')]
class AIKnowledgeChunkModel(BaseAiModel):
    item=models.ForeignKey(AIKnowledgeItemModel,on_delete=models.CASCADE,related_name='chunks'); ordinal=models.PositiveIntegerField(); content=models.TextField(); embedding=models.JSONField(null=True); tokenCount=models.PositiveIntegerField(default=0); metadata=models.JSONField(default=dict)
    class Meta: db_table='aiKnowledgeChunks'; unique_together=[('item','ordinal')]
class AIAuditRecordModel(BaseAiModel):
    request=models.ForeignKey(AIRequestModel,on_delete=models.PROTECT); action=models.CharField(max_length=60); actorId=models.UUIDField(null=True); providerCode=models.CharField(max_length=100,blank=True); modelCode=models.CharField(max_length=160,blank=True); promptVersion=models.CharField(max_length=80,blank=True); contextSources=models.JSONField(default=list); resultClassification=models.CharField(max_length=30,blank=True); metadata=models.JSONField(default=dict); redacted=models.BooleanField(default=True)
    class Meta: db_table='aiAuditRecords'
# Phase 13-N metering tables (clean style; the minified classes above are
# pre-existing debt documented in the Phase 13-L execution report §6).
class AIUsageAttemptModel(BaseAiModel):
    request = models.ForeignKey(AIRequestModel, on_delete=models.PROTECT, related_name="usageAttempts")
    operationId = models.UUIDField(null=True)
    attemptNumber = models.PositiveIntegerField(default=1)
    provider = models.ForeignKey(AIProviderModel, on_delete=models.PROTECT)
    model = models.ForeignKey(AIModelModel, on_delete=models.PROTECT)
    providerCode = models.CharField(max_length=100)
    modelCode = models.CharField(max_length=160)
    capabilityCode = models.CharField(max_length=100, blank=True)
    requestedBy = models.UUIDField(null=True)
    inputTokens = models.PositiveIntegerField(default=0)
    outputTokens = models.PositiveIntegerField(default=0)
    totalTokens = models.PositiveIntegerField(default=0)
    estimatedCost = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    currency = models.CharField(max_length=3, default="USD")
    queueTimeMs = models.PositiveIntegerField(default=0)
    contextBuildTimeMs = models.PositiveIntegerField(default=0)
    providerTimeMs = models.PositiveIntegerField(default=0)
    validationTimeMs = models.PositiveIntegerField(default=0)
    totalTimeMs = models.PositiveIntegerField(default=0)
    outcome = models.CharField(max_length=20, default="SUCCEEDED")
    errorCode = models.CharField(max_length=80, blank=True)
    idempotencyKey = models.CharField(max_length=160, blank=True, db_index=True)
    fingerprint = models.CharField(max_length=64, blank=True)
    correlationId = models.CharField(max_length=128, blank=True)
    traceId = models.CharField(max_length=128, blank=True)

    class Meta:
        db_table = "aiUsageAttempts"
        unique_together = [("tenantId", "request", "attemptNumber")]
        indexes = [
            models.Index(fields=["tenantId", "createdAt"]),
            models.Index(fields=["tenantId", "idempotencyKey"]),
        ]


class AIQuotaPolicyModel(BaseAiModel):
    scope = models.CharField(max_length=20)
    scopeReference = models.CharField(max_length=160, blank=True)
    dimension = models.CharField(max_length=20)
    window = models.CharField(max_length=20)
    limitValue = models.DecimalField(max_digits=18, decimal_places=8)
    currency = models.CharField(max_length=3, default="USD")
    description = models.TextField(blank=True)
    isActive = models.BooleanField(default=True)

    class Meta:
        db_table = "aiQuotaPolicies"
        unique_together = [("tenantId", "scope", "scopeReference", "dimension", "window")]


class AIQuotaCounterModel(BaseAiModel):
    policy = models.ForeignKey(AIQuotaPolicyModel, on_delete=models.PROTECT, related_name="counters")
    windowStart = models.DateTimeField(db_index=True)
    consumedRequests = models.BigIntegerField(default=0)
    consumedInputTokens = models.BigIntegerField(default=0)
    consumedOutputTokens = models.BigIntegerField(default=0)
    consumedCost = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    currency = models.CharField(max_length=3, default="USD")

    class Meta:
        db_table = "aiQuotaCounters"
        unique_together = [("policy", "windowStart")]
        indexes = [models.Index(fields=["tenantId", "windowStart"])]


# Phase 13-O audit trail and governance tables (clean style). Entity
# references are plain UUID columns with no foreign keys on purpose:
# retention purges of the referenced rows must never cascade into the
# audit ledger, and purge order stays irrelevant (contract §O.4.1).
class AIAuditTrailModel(BaseAiModel):
    occurredAt = models.DateTimeField()
    actorType = models.CharField(max_length=20, default="SYSTEM")
    actorId = models.UUIDField(null=True)
    action = models.CharField(max_length=40)
    requestId = models.UUIDField(null=True)
    attemptId = models.UUIDField(null=True)
    policyId = models.UUIDField(null=True)
    capabilityCode = models.CharField(max_length=100, blank=True)
    providerCode = models.CharField(max_length=100, blank=True)
    modelCode = models.CharField(max_length=160, blank=True)
    promptVersion = models.CharField(max_length=80, blank=True)
    classification = models.CharField(max_length=20, default="INTERNAL")
    outcome = models.CharField(max_length=20, default="RECORDED")
    errorCode = models.CharField(max_length=80, blank=True)
    correlationId = models.CharField(max_length=128, blank=True)
    traceId = models.CharField(max_length=128, blank=True)
    contextSources = models.JSONField(default=list)
    detail = models.JSONField(default=dict)
    prevHash = models.CharField(max_length=64, blank=True)
    hash = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "aiAuditTrail"
        indexes = [
            models.Index(fields=["tenantId", "occurredAt"]),
            models.Index(fields=["tenantId", "action"]),
        ]


class AIGovernancePolicyModel(BaseAiModel):
    name = models.CharField(max_length=160, default="default")
    allowedProviders = models.JSONField(default=list)
    allowedModels = models.JSONField(default=list)
    disabledCapabilities = models.JSONField(default=list)
    allowRestrictedToExternal = models.BooleanField(default=False)
    maxCostPerDay = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    currency = models.CharField(max_length=3, default="USD")
    description = models.TextField(blank=True)
    isActive = models.BooleanField(default=True)

    class Meta:
        db_table = "aiGovernancePolicies"
        constraints = [
            models.UniqueConstraint(fields=["tenantId"], name="unique_governance_policy_per_tenant")
        ]


class AIJobModel(BaseAiModel):
    """Durable async job ledger row (Phase 13-P, contract §P.8).

    ``requestId`` is a plain UUID with no foreign key: purging referenced
    rows must never cascade into the ledger (same pattern as the O audit
    trail). Tenant-scoped idempotency keys are unique; rows submitted
    without a key store a ``none:<jobId>`` sentinel (translated back to
    ``""`` by the repository), so the plain unique constraint also works
    on backends without partial-index support.
    """

    kind = models.CharField(max_length=40)
    requestId = models.UUIDField(null=True)
    payload = models.JSONField(default=dict)
    idempotencyKey = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=20, default="PENDING")
    priority = models.PositiveIntegerField(default=5)
    attempts = models.PositiveIntegerField(default=0)
    maxAttempts = models.PositiveIntegerField(default=3)
    runAt = models.DateTimeField()
    claimedBy = models.CharField(max_length=128, blank=True)
    leaseExpiresAt = models.DateTimeField(null=True)
    resultSummary = models.JSONField(default=dict)
    errorCode = models.CharField(max_length=80, blank=True)
    correlationId = models.CharField(max_length=128, blank=True)
    traceId = models.CharField(max_length=128, blank=True)

    class Meta:
        db_table = "aiJobs"
        unique_together = [("tenantId", "idempotencyKey")]
        indexes = [
            models.Index(fields=["tenantId", "status", "runAt"]),
            models.Index(fields=["tenantId", "createdAt"]),
        ]


# Phase 13-Q embedding foundation tables (clean style). Vectors are stored
# as JSON float arrays so the schema works unchanged on SQL Server, SQLite,
# and PostgreSQL without a vector extension or any new dependency
# (contract §Q.15 decision Q-D2). ``sourceId`` is a plain reference string:
# AI never owns the business row it points at, so no foreign key exists and
# purging a source can never cascade into another domain's tables.
class AIVectorSpaceModel(BaseAiModel):
    """Tenant-scoped registration of one comparable vector set (§Q.5)."""

    code = models.CharField(max_length=80)
    modelCode = models.CharField(max_length=120)
    modelVersion = models.CharField(max_length=80, blank=True)
    modelId = models.UUIDField(null=True)
    providerCode = models.CharField(max_length=80, blank=True)
    dimensions = models.PositiveIntegerField()
    metric = models.CharField(max_length=20, default="COSINE")
    normalization = models.CharField(max_length=10, default="L2")
    description = models.TextField(blank=True)
    isActive = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiVectorSpaces"
        unique_together = [("tenantId", "code")]
        indexes = [models.Index(fields=["tenantId", "isActive"])]


class AIStoredEmbeddingModel(BaseAiModel):
    """One durable vector bound to a business reference (§Q.4)."""

    spaceCode = models.CharField(max_length=80)
    sourceType = models.CharField(max_length=40)
    sourceId = models.CharField(max_length=160)
    chunkId = models.UUIDField(null=True)
    modelId = models.UUIDField(null=True)
    providerCode = models.CharField(max_length=80, blank=True)
    dimensions = models.PositiveIntegerField()
    vector = models.JSONField(default=list)
    contentHash = models.CharField(max_length=64)
    tokenCount = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiEmbeddingVectors"
        unique_together = [("tenantId", "spaceCode", "contentHash")]
        indexes = [
            models.Index(fields=["tenantId", "spaceCode", "sourceType", "sourceId"]),
            models.Index(fields=["tenantId", "spaceCode", "createdAt"]),
        ]
