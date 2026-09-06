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


# Phase 13-R knowledge ingestion tables (clean style). The register holds a
# *reference* to a business row plus the content checksum — never the source
# content itself (Master Specification §37). Chunks are a derived, purgeable
# index; they cascade from their source because they have no meaning without
# it, while vectors in `aiEmbeddingVectors` are unlinked on purpose and are
# removed explicitly by the application layer (contract §R.11).
class AIKnowledgeSourceModel(BaseAiModel):
    """Registered, indexable reference to a business row (§R.4)."""

    sourceDomain = models.CharField(max_length=40)
    sourceEntityType = models.CharField(max_length=100)
    sourceEntityId = models.CharField(max_length=160)
    title = models.CharField(max_length=300)
    checksum = models.CharField(max_length=64)
    classification = models.CharField(max_length=30, default="INTERNAL")
    status = models.CharField(max_length=30, default="PENDING")
    spaceCode = models.CharField(max_length=80, blank=True)
    policySignature = models.CharField(max_length=120, blank=True)
    revision = models.PositiveIntegerField(default=0)
    chunkCount = models.PositiveIntegerField(default=0)
    tokenCount = models.PositiveIntegerField(default=0)
    errorCode = models.CharField(max_length=80, blank=True)
    lastIndexedAt = models.DateTimeField(null=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiKnowledgeSources"
        unique_together = [("tenantId", "sourceDomain", "sourceEntityType", "sourceEntityId")]
        indexes = [
            models.Index(fields=["tenantId", "status", "updatedAt"]),
            models.Index(fields=["tenantId", "sourceDomain"]),
        ]


class AIKnowledgeChunkRecordModel(BaseAiModel):
    """One retrievable unit derived from a source's content (§R.5)."""

    source = models.ForeignKey(
        AIKnowledgeSourceModel, on_delete=models.CASCADE, related_name="chunkRecords"
    )
    ordinal = models.PositiveIntegerField()
    text = models.TextField()
    checksum = models.CharField(max_length=64)
    tokenCount = models.PositiveIntegerField(default=0)
    startOffset = models.PositiveIntegerField(default=0)
    endOffset = models.PositiveIntegerField(default=0)
    classification = models.CharField(max_length=30, default="INTERNAL")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiKnowledgeChunkRecords"
        indexes = [
            models.Index(fields=["tenantId", "source", "ordinal"]),
            models.Index(fields=["tenantId", "checksum"]),
        ]


# Phase 13-T memory table (clean style). The legacy `aiMemory` table from
# the Phase 13-B skeleton is left untouched: it lacks the version lineage,
# checksum, size accounting, classification, and expiry bookkeeping §17
# requires, and rewriting it in place would break the B-era rows. Versions
# are immutable rows; a write supersedes rather than edits (contract §T.5).
class AIMemoryEntryModel(BaseAiModel):
    """One immutable version of one memory slot (§T.4)."""

    scope = models.CharField(max_length=40)
    memoryKey = models.CharField(max_length=160)
    kind = models.CharField(max_length=30, default="FACT")
    userId = models.UUIDField(null=True)
    # Non-null projection of ``userId`` ("tenant" when the slot belongs to
    # the whole tenant). SQL treats two NULLs as distinct, so a nullable
    # column in the unique key would silently allow duplicate versions of a
    # tenant-wide slot — the same sentinel trick the Phase 13-P ledger uses.
    ownerKey = models.CharField(max_length=64, default="tenant")
    conversationId = models.CharField(max_length=160, blank=True)
    classification = models.CharField(max_length=30, default="INTERNAL")
    value = models.JSONField(default=dict)
    checksum = models.CharField(max_length=64)
    sizeBytes = models.PositiveIntegerField(default=0)
    version = models.PositiveIntegerField(default=1)
    isActive = models.BooleanField(default=True)
    expiresAt = models.DateTimeField(null=True)
    supersededAt = models.DateTimeField(null=True)
    sourceReference = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiMemoryEntries"
        unique_together = [("tenantId", "scope", "memoryKey", "ownerKey", "version")]
        indexes = [
            models.Index(fields=["tenantId", "scope", "memoryKey", "isActive"]),
            models.Index(fields=["tenantId", "isActive", "createdAt"]),
            models.Index(fields=["tenantId", "conversationId"]),
        ]


# Phase 13-U evaluation tables (clean style). Runs and their results are
# append-only history: a run is never edited after it settles, so quality
# over time stays comparable and a regression can always be attributed to
# a specific run (contract §U.7). ``caseCode`` is duplicated onto the
# result row on purpose — deleting a golden case must not erase the record
# of how it once scored.
class AIEvaluationCaseModel(BaseAiModel):
    """One golden case of one suite (§U.4)."""

    suiteCode = models.CharField(max_length=80)
    caseCode = models.CharField(max_length=80)
    question = models.TextField()
    expectedTerms = models.JSONField(default=list, blank=True)
    forbiddenTerms = models.JSONField(default=list, blank=True)
    expectedSchema = models.JSONField(default=dict, blank=True)
    minimumCitations = models.PositiveIntegerField(default=0)
    latencyBudgetMs = models.PositiveIntegerField(default=0)
    costBudget = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    spaceCode = models.CharField(max_length=80, blank=True)
    isActive = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiEvaluationCases"
        unique_together = [("tenantId", "suiteCode", "caseCode")]
        indexes = [models.Index(fields=["tenantId", "suiteCode", "isActive"])]


class AIEvaluationRunModel(BaseAiModel):
    """One execution of one suite (§U.7)."""

    suiteCode = models.CharField(max_length=80)
    method = models.CharField(max_length=20, default="AUTOMATIC")
    criteriaSignature = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, default="PENDING")
    verdict = models.CharField(max_length=10, default="PASS")
    caseCount = models.PositiveIntegerField(default=0)
    passedCount = models.PositiveIntegerField(default=0)
    warnedCount = models.PositiveIntegerField(default=0)
    failedCount = models.PositiveIntegerField(default=0)
    overallScore = models.DecimalField(max_digits=9, decimal_places=6, default=0)
    baselineRunId = models.UUIDField(null=True)
    triggeredBy = models.UUIDField(null=True)
    errorCode = models.CharField(max_length=80, blank=True)
    startedAt = models.DateTimeField(null=True)
    completedAt = models.DateTimeField(null=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiEvaluationRuns"
        indexes = [
            models.Index(fields=["tenantId", "suiteCode", "createdAt"]),
            models.Index(fields=["tenantId", "status"]),
        ]


class AIEvaluationResultModel(BaseAiModel):
    """One case outcome inside one run (§U.8)."""

    run = models.ForeignKey(
        AIEvaluationRunModel, on_delete=models.CASCADE, related_name="results"
    )
    caseCode = models.CharField(max_length=80)
    verdict = models.CharField(max_length=10, default="PASS")
    score = models.DecimalField(max_digits=9, decimal_places=6, default=0)
    scores = models.JSONField(default=list)
    latencyMs = models.PositiveIntegerField(default=0)
    totalTokens = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    citationCount = models.PositiveIntegerField(default=0)
    answerFingerprint = models.CharField(max_length=64, blank=True)
    requestId = models.UUIDField(null=True)
    errorCode = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiEvaluationResults"
        unique_together = [("run", "caseCode")]
        indexes = [models.Index(fields=["tenantId", "caseCode", "createdAt"])]


# Phase 13-V feedback table (clean style). The legacy `aiFeedback` table
# from the Phase 13-B skeleton stays untouched: it has no triage lifecycle,
# no reason vocabulary, no provenance (model + prompt version, §33) and no
# promotion link, and rewriting it in place would break the B-era rows.
# The fingerprint column is unique per tenant so one human leaves one
# signal of one kind per response (contract §V.5).
class AIFeedbackEntryModel(BaseAiModel):
    """One human signal about one AI answer (§V.4)."""

    requestId = models.UUIDField(db_index=True)
    responseId = models.UUIDField(null=True)
    userId = models.UUIDField(null=True)
    kind = models.CharField(max_length=20, default="RATING")
    rating = models.PositiveSmallIntegerField(null=True)
    sentiment = models.CharField(max_length=20, default="NEUTRAL")
    reason = models.CharField(max_length=30, blank=True)
    comment = models.TextField(blank=True)
    correction = models.TextField(blank=True)
    question = models.TextField(blank=True)
    modelCode = models.CharField(max_length=160, blank=True)
    promptVersion = models.CharField(max_length=80, blank=True)
    capabilityCode = models.CharField(max_length=100, blank=True)
    suiteCode = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, default="NEW")
    promotedCaseCode = models.CharField(max_length=80, blank=True)
    rejectionReason = models.CharField(max_length=500, blank=True)
    triagedBy = models.UUIDField(null=True)
    triagedAt = models.DateTimeField(null=True)
    fingerprint = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiFeedbackEntries"
        unique_together = [("tenantId", "fingerprint")]
        indexes = [
            models.Index(fields=["tenantId", "status", "createdAt"]),
            models.Index(fields=["tenantId", "sentiment", "createdAt"]),
            models.Index(fields=["tenantId", "modelCode"]),
        ]


# Phase 13-W observability tables (clean style). Snapshots are immutable
# roll-ups of one collection window: keeping them means a dashboard can
# still answer "what did last month look like?" after the raw attempt and
# job rows have aged out under their own retention (contract §W.6).
# Alerts are events, not flags, so a rule that fires twice leaves two rows.
class AIMetricSnapshotModel(BaseAiModel):
    """Frozen metrics of one collection window (§W.6)."""

    windowStart = models.DateTimeField()
    windowEnd = models.DateTimeField()
    metrics = models.JSONField(default=dict)
    labels = models.JSONField(default=dict, blank=True)
    sampleCount = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiMetricSnapshots"
        indexes = [
            models.Index(fields=["tenantId", "windowEnd"]),
            models.Index(fields=["tenantId", "createdAt"]),
        ]


class AIAlertEventModel(BaseAiModel):
    """One firing of one alert rule (§W.8)."""

    ruleCode = models.CharField(max_length=80)
    metric = models.CharField(max_length=80)
    severity = models.CharField(max_length=20, default="WARNING")
    state = models.CharField(max_length=20, default="FIRING")
    observedValue = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    threshold = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    message = models.CharField(max_length=500, blank=True)
    firedAt = models.DateTimeField()
    resolvedAt = models.DateTimeField(null=True)
    acknowledgedAt = models.DateTimeField(null=True)
    acknowledgedBy = models.UUIDField(null=True)
    snapshotId = models.UUIDField(null=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiAlertEvents"
        indexes = [
            models.Index(fields=["tenantId", "state", "firedAt"]),
            models.Index(fields=["tenantId", "ruleCode", "firedAt"]),
        ]


# Phase 13-X tool registry tables (clean style). The legacy `aiTools` /
# `aiToolExecutions` shape from the Phase 13-B skeleton is superseded here:
# it had no version lineage, no risk level, no registry lifecycle and no
# approval link, and §30 needs all four. Definitions are immutable per
# version, so an invocation recorded last month can still be read against
# the contract it actually used (contract §X.5).
class AIToolDefinitionModel(BaseAiModel):
    """One immutable version of one registered tool (§X.4)."""

    code = models.CharField(max_length=80)
    version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=160)
    description = models.TextField()
    effect = models.CharField(max_length=20, default="READ_ONLY")
    riskLevel = models.CharField(max_length=20, default="LOW")
    inputSchema = models.JSONField(default=dict, blank=True)
    outputSchema = models.JSONField(default=dict, blank=True)
    requiredPermission = models.CharField(max_length=100, blank=True)
    declaredApprovalMode = models.CharField(max_length=20, blank=True)
    timeoutSeconds = models.PositiveIntegerField(default=30)
    maxCallsPerRequest = models.PositiveIntegerField(default=5)
    status = models.CharField(max_length=20, default="DRAFT")
    approvedBy = models.UUIDField(null=True)
    approvedAt = models.DateTimeField(null=True)
    retiredAt = models.DateTimeField(null=True)
    rejectionReason = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiToolDefinitions"
        unique_together = [("tenantId", "code", "version")]
        indexes = [
            models.Index(fields=["tenantId", "code", "status"]),
            models.Index(fields=["tenantId", "status"]),
        ]


class AIToolApprovalModel(BaseAiModel):
    """One human decision about one proposed call (§X.7)."""

    toolCode = models.CharField(max_length=80)
    toolVersion = models.PositiveIntegerField(default=1)
    argumentFingerprint = models.CharField(max_length=64)
    mode = models.CharField(max_length=20, default="HUMAN_REQUIRED")
    decision = models.CharField(max_length=20, default="PENDING")
    requiredApprovals = models.PositiveSmallIntegerField(default=1)
    approvals = models.JSONField(default=list)
    requestedBy = models.UUIDField(null=True)
    invocationId = models.UUIDField(null=True)
    reason = models.CharField(max_length=500, blank=True)
    expiresAt = models.DateTimeField(null=True)
    decidedAt = models.DateTimeField(null=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiToolApprovals"
        indexes = [
            models.Index(fields=["tenantId", "toolCode", "argumentFingerprint"]),
            models.Index(fields=["tenantId", "decision", "createdAt"]),
        ]


class AIToolInvocationModel(BaseAiModel):
    """One proposed call and what happened to it (§X.8)."""

    toolCode = models.CharField(max_length=80)
    toolVersion = models.PositiveIntegerField(default=1)
    toolId = models.UUIDField(null=True)
    requestId = models.UUIDField(null=True, db_index=True)
    actorId = models.UUIDField(null=True)
    approvalId = models.UUIDField(null=True)
    arguments = models.JSONField(default=dict)
    fingerprint = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=20, default="PENDING")
    result = models.JSONField(default=dict, blank=True)
    errorCode = models.CharField(max_length=80, blank=True)
    startedAt = models.DateTimeField(null=True)
    completedAt = models.DateTimeField(null=True)
    latencyMs = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiToolInvocations"
        indexes = [
            models.Index(fields=["tenantId", "toolCode", "createdAt"]),
            models.Index(fields=["tenantId", "status", "createdAt"]),
        ]

# Phase 13-Y agent tables. The registry is versioned and immutable-per-
# version (mirror of X); runs and steps are append-only history: a run is
# settled once, and every step row — including denied tool calls — stays,
# so "what did the agent try?" always has an answer (contract §Y.8, Y-D7).
class AIAgentDefinitionModel(BaseAiModel):
    """One immutable version of one registered agent (§Y.4)."""

    code = models.CharField(max_length=80)
    version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    instructions = models.TextField()
    accessLevel = models.CharField(max_length=20, default="ADVISORY")
    riskLevel = models.CharField(max_length=20, default="LOW")
    capabilityCodes = models.JSONField(default=list)
    toolCodes = models.JSONField(default=list)
    outputSchema = models.JSONField(default=dict, blank=True)
    contextPolicy = models.JSONField(default=dict, blank=True)
    modelPolicy = models.JSONField(default=dict, blank=True)
    permissionPolicy = models.JSONField(default=dict, blank=True)
    executionPolicy = models.JSONField(default=dict, blank=True)
    declaredApprovalMode = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, default="DRAFT")
    approvedBy = models.UUIDField(null=True)
    approvedAt = models.DateTimeField(null=True)
    retiredAt = models.DateTimeField(null=True)
    rejectionReason = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiAgentDefinitions"
        unique_together = [("tenantId", "code", "version")]
        indexes = [
            models.Index(fields=["tenantId", "code", "status"]),
            models.Index(fields=["tenantId", "status"]),
        ]


class AIAgentApprovalModel(BaseAiModel):
    """One human decision about one requested run (§Y.7)."""

    agentCode = models.CharField(max_length=80)
    agentVersion = models.PositiveIntegerField(default=1)
    inputFingerprint = models.CharField(max_length=64)
    mode = models.CharField(max_length=20, default="HUMAN_REQUIRED")
    decision = models.CharField(max_length=20, default="PENDING")
    requiredApprovals = models.PositiveSmallIntegerField(default=1)
    approvals = models.JSONField(default=list)
    requestedBy = models.UUIDField(null=True)
    executionId = models.UUIDField(null=True)
    reason = models.CharField(max_length=500, blank=True)
    expiresAt = models.DateTimeField(null=True)
    decidedAt = models.DateTimeField(null=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiAgentApprovals"
        indexes = [
            models.Index(fields=["tenantId", "agentCode", "inputFingerprint"]),
            models.Index(fields=["tenantId", "decision", "createdAt"]),
        ]


class AIAgentRunModel(BaseAiModel):
    """One requested run and what happened to it (§Y.8)."""

    agentId = models.UUIDField()
    agentCode = models.CharField(max_length=80)
    agentVersion = models.PositiveIntegerField(default=1)
    requestedBy = models.UUIDField(null=True)
    input = models.JSONField(default=dict)
    inputFingerprint = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=20, default="PENDING")
    answer = models.TextField(blank=True)
    output = models.JSONField(default=dict, blank=True)
    errorCode = models.CharField(max_length=80, blank=True)
    approvalId = models.UUIDField(null=True)
    startedAt = models.DateTimeField(null=True)
    completedAt = models.DateTimeField(null=True)
    latencyMs = models.PositiveIntegerField(default=0)
    modelCallCount = models.PositiveIntegerField(default=0)
    toolCallCount = models.PositiveIntegerField(default=0)
    inputTokens = models.PositiveIntegerField(default=0)
    outputTokens = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "aiAgentRuns"
        indexes = [
            models.Index(fields=["tenantId", "agentCode", "createdAt"]),
            models.Index(fields=["tenantId", "status", "createdAt"]),
        ]


class AIAgentStepModel(BaseAiModel):
    """One step of the plan-act loop — a model call or a tool call."""

    runId = models.UUIDField(db_index=True)
    ordinal = models.PositiveIntegerField()
    kind = models.CharField(max_length=10)
    status = models.CharField(max_length=20)
    toolCode = models.CharField(max_length=80, blank=True)
    toolVersion = models.PositiveIntegerField(default=0)
    arguments = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    tokensIn = models.PositiveIntegerField(default=0)
    tokensOut = models.PositiveIntegerField(default=0)
    latencyMs = models.PositiveIntegerField(default=0)
    errorCode = models.CharField(max_length=80, blank=True)

    class Meta:
        db_table = "aiAgentSteps"
        unique_together = [("runId", "ordinal")]
        indexes = [
            models.Index(fields=["runId", "kind"]),
            models.Index(fields=["tenantId", "createdAt"]),
        ]
