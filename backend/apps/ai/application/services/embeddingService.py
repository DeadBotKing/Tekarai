"""Application orchestration for the Phase 13-Q embedding foundation.

``EmbeddingApplicationService`` wires the pure engine (planning, vector
validation, ranking) to persistence, the provider port from Phase 13-C,
the metering entry point from Phase 13-N, and the audit ledger from
Phase 13-O. It owns no vector math and no ranking rule itself: every
decision lives in ``apps.ai.domain.services.embeddingEngine``.

Behaviour worth stating once:

- **Fail-closed switch.** A disabled foundation refuses writes and reads
  instead of silently returning empty results (§Q.13).
- **Space first.** Every write resolves a registered, active space; every
  read resolves a registered space (inactive spaces stay readable so a
  migration can drain them). Vectors from two spaces never meet (§Q.5).
- **Cache before provider.** The fingerprint cache is consulted first, so
  re-embedding unchanged text costs nothing and stays idempotent (§Q.10).
- **Metering and audit are attributable extras.** Usage is recorded only
  when the caller supplies the request/model/provider identity Phase 13-N
  requires; audit entries are appended whenever a logger is wired. Neither
  is allowed to fabricate identifiers.
- **No authorization here.** Permission filtering belongs to Phase 13-K
  and is applied by the S retrieval pipeline before context assembly;
  Q enforces tenant and space integrity only (§Q.12).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from django.conf import settings as djangoSettings

from apps.ai.domain.embeddingPorts import (
    EmbeddingAuditLogger,
    EmbeddingStore,
    EmbeddingUsageRecorder,
    VectorSpaceStore,
)
from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.embeddingRecords import (
    AIStoredEmbedding,
    AIVectorSpaceDefinition,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIEmbeddingBatchTooLarge,
    AIEmbeddingInvalid,
    AIEmbeddingNotFound,
    AIVectorSpaceAlreadyRegistered,
    AIVectorSpaceInactive,
    AIVectorSpaceInvalid,
    AIVectorSpaceMismatch,
    AIVectorSpaceNotFound,
)
from apps.ai.domain.services.aiRules import estimateTokens
from apps.ai.domain.services.embeddingEngine import (
    EmbeddingEngine,
    EmbeddingItem,
    EmbeddingPlan,
    SimilarityMatch,
    rankBySimilarity,
)
from apps.ai.domain.valueObjects.embeddingTypes import (
    MAX_BATCH_SIZE,
    VectorSpace,
    ensureMetric,
    ensureNormalization,
    ensureSourceType,
)

#: Audit actions appended by Q (registered in the Phase 13-O vocabulary).
AUDIT_SPACE_DEFINED = "VECTOR_SPACE_DEFINED"
AUDIT_SPACE_DEACTIVATED = "VECTOR_SPACE_DEACTIVATED"
AUDIT_EMBEDDING_CREATED = "EMBEDDING_CREATED"
AUDIT_EMBEDDING_DELETED = "EMBEDDING_DELETED"


class EmbeddingProviderResolver(Protocol):
    """Resolves the adapter that serves one tenant's vector space.

    The composition root implements this over the Phase 13-D provider
    registry and the Phase 13-E model registry; Q never imports a vendor
    SDK or reads provider configuration itself.
    """

    def providerFor(self, tenantId: uuid.UUID, space: VectorSpace) -> Any: ...


@dataclass(frozen=True)
class EmbeddingSettings:
    """Configuration-driven defaults (Master Specification §42)."""

    enabled: bool = True
    maxBatchSize: int = 32
    maxInputTokens: int = 8192
    defaultMetric: str = "COSINE"
    defaultNormalization: str = "L2"
    cacheEnabled: bool = True
    searchCandidateLimit: int = 1000
    retentionDays: int = 365

    def __post_init__(self) -> None:
        if self.maxBatchSize < 1 or self.maxBatchSize > MAX_BATCH_SIZE:
            raise AIConfigurationError("aiEmbeddingMaxBatchSize is out of range.")
        if self.maxInputTokens < 1:
            raise AIConfigurationError("aiEmbeddingMaxInputTokens must be positive.")
        if self.searchCandidateLimit < 1:
            raise AIConfigurationError("aiEmbeddingSearchCandidateLimit must be positive.")
        if self.retentionDays < 1:
            raise AIConfigurationError("aiEmbeddingRetentionDays must be positive.")
        object.__setattr__(self, "defaultMetric", ensureMetric(self.defaultMetric))
        object.__setattr__(
            self, "defaultNormalization", ensureNormalization(self.defaultNormalization)
        )

    @classmethod
    def fromDjangoSettings(cls) -> EmbeddingSettings:
        return cls(
            enabled=bool(getattr(djangoSettings, "AI_EMBEDDING_ENABLED", True)),
            maxBatchSize=int(getattr(djangoSettings, "AI_EMBEDDING_MAX_BATCH_SIZE", 32) or 32),
            maxInputTokens=int(
                getattr(djangoSettings, "AI_EMBEDDING_MAX_INPUT_TOKENS", 8192) or 8192
            ),
            defaultMetric=str(
                getattr(djangoSettings, "AI_EMBEDDING_DEFAULT_METRIC", "COSINE") or "COSINE"
            ),
            defaultNormalization=str(
                getattr(djangoSettings, "AI_EMBEDDING_DEFAULT_NORMALIZATION", "L2") or "L2"
            ),
            cacheEnabled=bool(getattr(djangoSettings, "AI_EMBEDDING_CACHE_ENABLED", True)),
            searchCandidateLimit=int(
                getattr(djangoSettings, "AI_EMBEDDING_SEARCH_CANDIDATE_LIMIT", 1000) or 1000
            ),
            retentionDays=int(getattr(djangoSettings, "AI_EMBEDDING_RETENTION_DAYS", 365) or 365),
        )


@dataclass(frozen=True)
class DefineVectorSpaceCommand:
    """Register one comparable vector set for a tenant (§Q.5)."""

    code: str
    modelCode: str
    dimensions: int
    metric: str = ""
    normalization: str = ""
    modelVersion: str = ""
    modelId: uuid.UUID | None = None
    providerCode: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UsageAttribution:
    """Optional identity that makes an embedding call meterable by N."""

    requestId: uuid.UUID
    modelId: uuid.UUID
    providerId: uuid.UUID
    providerCode: str
    modelCode: str
    capabilityCode: str = "EMBEDDING"
    requestedBy: uuid.UUID | None = None
    correlationId: str = ""
    traceId: str = ""


@dataclass(frozen=True)
class EmbedTextsCommand:
    """Embed one or more texts into a registered space."""

    spaceCode: str
    items: tuple[EmbeddingItem, ...]
    attribution: UsageAttribution | None = None
    useCache: bool | None = None
    replaceExisting: bool = False


@dataclass(frozen=True)
class SimilaritySearchQuery:
    """Nearest-neighbour lookup inside one space."""

    spaceCode: str
    queryText: str = ""
    queryVector: tuple[float, ...] = ()
    topK: int = 10
    minScore: float | None = None
    sourceTypes: tuple[str, ...] = ()
    candidateLimit: int | None = None
    attribution: UsageAttribution | None = None


@dataclass(frozen=True)
class VectorSpaceDescriptor:
    """Safe, immutable read model of a registered space."""

    tenantId: uuid.UUID
    code: str
    modelCode: str
    modelVersion: str
    dimensions: int
    metric: str
    normalization: str
    isActive: bool
    providerCode: str
    description: str
    signature: str
    createdAt: datetime

    @classmethod
    def of(cls, definition: AIVectorSpaceDefinition) -> VectorSpaceDescriptor:
        space = definition.space
        return cls(
            tenantId=definition.tenantId,
            code=space.code,
            modelCode=space.modelCode,
            modelVersion=space.modelVersion,
            dimensions=space.dimensions,
            metric=space.metric,
            normalization=space.normalization,
            isActive=definition.isActive,
            providerCode=definition.providerCode,
            description=definition.description,
            signature=space.signature(),
            createdAt=definition.createdAt,
        )


@dataclass(frozen=True)
class EmbeddingDescriptor:
    """Safe read model of a stored vector — the vector itself stays home."""

    embeddingId: uuid.UUID
    tenantId: uuid.UUID
    spaceCode: str
    sourceType: str
    sourceId: str
    dimensions: int
    contentHash: str
    tokenCount: int
    providerCode: str
    chunkId: uuid.UUID | None
    createdAt: datetime

    @classmethod
    def of(cls, embedding: AIStoredEmbedding) -> EmbeddingDescriptor:
        return cls(
            embeddingId=embedding.id,
            tenantId=embedding.tenantId,
            spaceCode=embedding.space.code,
            sourceType=embedding.sourceType,
            sourceId=embedding.sourceId,
            dimensions=embedding.dimensions,
            contentHash=embedding.contentHash,
            tokenCount=embedding.tokenCount,
            providerCode=embedding.providerCode,
            chunkId=embedding.chunkId,
            createdAt=embedding.createdAt,
        )


@dataclass(frozen=True)
class EmbedResult:
    """Outcome of one embed call (§Q.10)."""

    spaceCode: str
    created: tuple[EmbeddingDescriptor, ...]
    reused: tuple[EmbeddingDescriptor, ...]
    duplicates: int
    providerCalls: int
    estimatedTokens: int

    @property
    def total(self) -> int:
        return len(self.created) + len(self.reused)


@dataclass(frozen=True)
class SearchResult:
    """Ranked matches plus how the candidate set was produced."""

    spaceCode: str
    matches: tuple[SimilarityMatch, ...]
    scanned: int
    usedQueryEmbedding: bool


class EmbeddingApplicationService:
    """Tenant-scoped facade for vector spaces, embeddings, and search."""

    def __init__(
        self,
        spaceStore: VectorSpaceStore,
        embeddingStore: EmbeddingStore,
        *,
        providerResolver: EmbeddingProviderResolver | None = None,
        settings: EmbeddingSettings | None = None,
        usageRecorder: EmbeddingUsageRecorder | None = None,
        auditLogger: EmbeddingAuditLogger | None = None,
        now: Any = utcNow,
    ) -> None:
        self.spaceStore = spaceStore
        self.embeddingStore = embeddingStore
        self.providerResolver = providerResolver
        self.settings = settings or EmbeddingSettings()
        self.usageRecorder = usageRecorder
        self.auditLogger = auditLogger
        self._now = now
        self.engine = EmbeddingEngine(
            maxBatchSize=self.settings.maxBatchSize,
            maxInputTokens=self.settings.maxInputTokens,
            now=now,
        )

    # ------------------------------------------------------------------
    # Vector spaces (§Q.5)
    # ------------------------------------------------------------------
    def defineVectorSpace(
        self,
        tenantId: uuid.UUID | str,
        command: DefineVectorSpaceCommand,
    ) -> VectorSpaceDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(command, DefineVectorSpaceCommand):
            raise AIVectorSpaceInvalid("Defining a space requires a DefineVectorSpaceCommand.")
        space = VectorSpace(
            code=command.code,
            modelCode=command.modelCode,
            dimensions=command.dimensions,
            metric=command.metric or self.settings.defaultMetric,
            normalization=command.normalization or self.settings.defaultNormalization,
            modelVersion=command.modelVersion,
        )
        if self.spaceStore.getSpace(tenant, space.code) is not None:
            raise AIVectorSpaceAlreadyRegistered(space.code)
        moment = self._now()
        definition = AIVectorSpaceDefinition(
            tenantId=tenant,
            space=space,
            modelId=command.modelId,
            providerCode=command.providerCode,
            description=command.description,
            metadata=dict(command.metadata),
            createdAt=moment,
            updatedAt=moment,
        )
        stored = self.spaceStore.saveSpace(definition)
        self._audit(
            tenant,
            AUDIT_SPACE_DEFINED,
            outcome="DEFINED",
            modelCode=space.modelCode,
            providerCode=stored.providerCode,
            detail={"spaceCode": space.code, "signature": space.signature()},
        )
        return VectorSpaceDescriptor.of(stored)

    def describeVectorSpace(
        self, tenantId: uuid.UUID | str, spaceCode: str
    ) -> VectorSpaceDescriptor:
        definition = self._requireSpace(requireUuid(tenantId, "tenantId"), spaceCode)
        return VectorSpaceDescriptor.of(definition)

    def listVectorSpaces(
        self, tenantId: uuid.UUID | str, *, activeOnly: bool = False
    ) -> tuple[VectorSpaceDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        definitions = self.spaceStore.listSpaces(tenant)
        chosen = [item for item in definitions if item.isActive or not activeOnly]
        return tuple(
            VectorSpaceDescriptor.of(item) for item in sorted(chosen, key=lambda row: row.code)
        )

    def deactivateVectorSpace(
        self, tenantId: uuid.UUID | str, spaceCode: str
    ) -> VectorSpaceDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireSpace(tenant, spaceCode)
        definition.deactivate(now=self._now())
        stored = self.spaceStore.updateSpace(definition)
        self._audit(
            tenant,
            AUDIT_SPACE_DEACTIVATED,
            outcome="UPDATED",
            modelCode=stored.space.modelCode,
            detail={"spaceCode": stored.space.code},
        )
        return VectorSpaceDescriptor.of(stored)

    def activateVectorSpace(
        self, tenantId: uuid.UUID | str, spaceCode: str
    ) -> VectorSpaceDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireSpace(tenant, spaceCode)
        definition.activate(now=self._now())
        return VectorSpaceDescriptor.of(self.spaceStore.updateSpace(definition))

    # ------------------------------------------------------------------
    # Embedding (§Q.9–§Q.10)
    # ------------------------------------------------------------------
    def embedTexts(self, tenantId: uuid.UUID | str, command: EmbedTextsCommand) -> EmbedResult:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(command, EmbedTextsCommand):
            raise AIEmbeddingInvalid("Embedding requires an EmbedTextsCommand.")
        if not command.items:
            raise AIEmbeddingInvalid("Embedding requires at least one item.")
        definition = self._requireSpace(tenant, command.spaceCode)
        if not definition.isActive:
            raise AIVectorSpaceInactive(
                "Vector space is inactive and cannot accept new embeddings."
            )
        space = definition.space

        if command.replaceExisting:
            for item in command.items:
                self.embeddingStore.deleteBySource(
                    tenant, space.code, item.sourceType, item.sourceId
                )

        useCache = self.settings.cacheEnabled if command.useCache is None else command.useCache
        cachedRows: dict[str, AIStoredEmbedding] = {}
        if useCache and not command.replaceExisting:
            fingerprints = tuple(item.fingerprint(space) for item in command.items)
            for row in self.embeddingStore.findByFingerprints(tenant, space.code, fingerprints):
                if not row.sameSpaceAs(space):
                    raise AIVectorSpaceMismatch("Cached embedding belongs to another space.")
                cachedRows[row.contentHash] = row

        plan = self.engine.plan(
            space,
            command.items,
            knownFingerprints=tuple(cachedRows),
            maxItems=self.settings.maxBatchSize if len(command.items) > MAX_BATCH_SIZE else None,
        )
        created = self._executePlan(tenant, definition, plan, command.attribution)
        reused = tuple(
            EmbeddingDescriptor.of(cachedRows[item.fingerprint(space)]) for item in plan.cached
        )
        return EmbedResult(
            spaceCode=space.code,
            created=created,
            reused=reused,
            duplicates=plan.duplicates,
            providerCalls=plan.providerCalls,
            estimatedTokens=plan.estimatedTokens,
        )

    def embedText(
        self,
        tenantId: uuid.UUID | str,
        spaceCode: str,
        text: str,
        *,
        sourceType: str = "CUSTOM",
        sourceId: str = "",
        chunkId: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
        attribution: UsageAttribution | None = None,
    ) -> EmbedResult:
        item = EmbeddingItem(
            text=text,
            sourceType=sourceType,
            sourceId=sourceId or "singleton",
            chunkId=chunkId,
            metadata=metadata or {},
        )
        return self.embedTexts(
            tenantId,
            EmbedTextsCommand(spaceCode=spaceCode, items=(item,), attribution=attribution),
        )

    # ------------------------------------------------------------------
    # Search (§Q.11)
    # ------------------------------------------------------------------
    def searchSimilar(
        self, tenantId: uuid.UUID | str, query: SimilaritySearchQuery
    ) -> SearchResult:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(query, SimilaritySearchQuery):
            raise AIEmbeddingInvalid("Search requires a SimilaritySearchQuery.")
        if query.topK < 1:
            raise AIEmbeddingInvalid("topK must be positive.")
        definition = self._requireSpace(tenant, query.spaceCode)
        space = definition.space
        sourceTypes = tuple(ensureSourceType(value) for value in query.sourceTypes)

        usedQueryEmbedding = False
        if query.queryVector:
            vector = space.prepare(query.queryVector)
        elif query.queryText.strip():
            item = self.engine.prepareQuery(space, query.queryText)
            vector = space.prepare(
                self._callProvider(tenant, definition, (item.text,), query.attribution)[0]
            )
            usedQueryEmbedding = True
        else:
            raise AIEmbeddingInvalid("Search requires either a query text or a query vector.")

        limit = query.candidateLimit or self.settings.searchCandidateLimit
        if limit < 1:
            raise AIEmbeddingInvalid("candidateLimit must be positive.")
        candidates = self.embeddingStore.scanCandidates(
            tenant, space.code, sourceTypes=sourceTypes, limit=limit
        )
        matches = rankBySimilarity(
            space, vector, candidates, topK=query.topK, minScore=query.minScore
        )
        return SearchResult(
            spaceCode=space.code,
            matches=matches,
            scanned=len(candidates),
            usedQueryEmbedding=usedQueryEmbedding,
        )

    # ------------------------------------------------------------------
    # Reads and lifecycle
    # ------------------------------------------------------------------
    def describeEmbedding(
        self, tenantId: uuid.UUID | str, embeddingId: uuid.UUID | str
    ) -> EmbeddingDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        row = self.embeddingStore.getEmbedding(tenant, requireUuid(embeddingId, "embeddingId"))
        if row is None:
            raise AIEmbeddingNotFound(str(embeddingId))
        return EmbeddingDescriptor.of(row)

    def listSourceEmbeddings(
        self, tenantId: uuid.UUID | str, spaceCode: str, sourceType: str, sourceId: str
    ) -> tuple[EmbeddingDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireSpace(tenant, spaceCode)
        rows = self.embeddingStore.listBySource(
            tenant, definition.space.code, ensureSourceType(sourceType), sourceId
        )
        return tuple(EmbeddingDescriptor.of(row) for row in rows)

    def countEmbeddings(self, tenantId: uuid.UUID | str, spaceCode: str) -> int:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireSpace(tenant, spaceCode)
        return self.embeddingStore.countForSpace(tenant, definition.space.code)

    def deleteSourceEmbeddings(
        self, tenantId: uuid.UUID | str, spaceCode: str, sourceType: str, sourceId: str
    ) -> int:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireSpace(tenant, spaceCode)
        removed = self.embeddingStore.deleteBySource(
            tenant, definition.space.code, ensureSourceType(sourceType), sourceId
        )
        if removed:
            self._audit(
                tenant,
                AUDIT_EMBEDDING_DELETED,
                outcome="PURGED",
                detail={
                    "spaceCode": definition.space.code,
                    "sourceType": ensureSourceType(sourceType),
                    "removed": removed,
                },
            )
        return removed

    def purgeVectorSpace(self, tenantId: uuid.UUID | str, spaceCode: str) -> int:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireSpace(tenant, spaceCode)
        removed = self.embeddingStore.deleteSpaceEmbeddings(tenant, definition.space.code)
        if removed:
            self._audit(
                tenant,
                AUDIT_EMBEDDING_DELETED,
                outcome="PURGED",
                detail={"spaceCode": definition.space.code, "removed": removed},
            )
        return removed

    def purgeEmbeddingRetention(
        self,
        tenantId: uuid.UUID | str | None = None,
        *,
        retentionDays: int | None = None,
        now: datetime | None = None,
    ) -> int:
        self._requireEnabled()
        tenant = None if tenantId is None else requireUuid(tenantId, "tenantId")
        days = self.settings.retentionDays if retentionDays is None else int(retentionDays)
        if days < 1:
            raise AIConfigurationError("Embedding retention must be at least one day.")
        cutoff = (now or self._now()) - timedelta(days=days)
        removed = self.embeddingStore.deleteEmbeddingsBefore(tenant, cutoff)
        if removed and tenant is not None:
            self._audit(
                tenant,
                AUDIT_EMBEDDING_DELETED,
                outcome="PURGED",
                detail={"removed": removed, "retentionDays": days},
            )
        return removed

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _executePlan(
        self,
        tenant: uuid.UUID,
        definition: AIVectorSpaceDefinition,
        plan: EmbeddingPlan,
        attribution: UsageAttribution | None,
    ) -> tuple[EmbeddingDescriptor, ...]:
        if plan.isEmpty:
            return ()
        space = definition.space
        stored: list[AIStoredEmbedding] = []
        for batch in plan.batches:
            vectors = self._callProvider(
                tenant, definition, tuple(item.text for item in batch), attribution
            )
            built = self.engine.buildBatch(
                tenant,
                space,
                batch,
                vectors,
                modelId=None if attribution is None else attribution.modelId,
                providerCode=(attribution.providerCode if attribution else definition.providerCode),
                createdAt=self._now(),
            )
            stored.extend(self.embeddingStore.saveMany(tuple(built)))
        if stored:
            self._audit(
                tenant,
                AUDIT_EMBEDDING_CREATED,
                outcome="RECORDED",
                modelCode=space.modelCode,
                providerCode=stored[0].providerCode,
                requestId=None if attribution is None else attribution.requestId,
                correlationId="" if attribution is None else attribution.correlationId,
                traceId="" if attribution is None else attribution.traceId,
                detail={
                    "spaceCode": space.code,
                    "created": len(stored),
                    "providerCalls": plan.providerCalls,
                },
            )
        return tuple(EmbeddingDescriptor.of(row) for row in stored)

    def _callProvider(
        self,
        tenant: uuid.UUID,
        definition: AIVectorSpaceDefinition,
        texts: Sequence[str],
        attribution: UsageAttribution | None,
    ) -> tuple[tuple[float, ...], ...]:
        if self.providerResolver is None:
            raise AIConfigurationError("No embedding provider resolver is configured.")
        provider = self.providerResolver.providerFor(tenant, definition.space)
        if provider is None:
            raise AIConfigurationError("Embedding provider resolution returned nothing.")
        modelCode = definition.space.modelCode
        started = self._now()
        if len(texts) == 1:
            raw: Iterable[Iterable[float]] = [provider.embed(text=texts[0], model=modelCode)]
        else:
            raw = provider.embedBatch(texts=list(texts), model=modelCode)
        vectors = tuple(tuple(float(value) for value in vector) for vector in raw)
        if len(vectors) != len(texts):
            raise AIEmbeddingInvalid("Provider returned a different number of vectors than inputs.")
        for vector in vectors:
            if len(vector) != definition.space.dimensions:
                raise AIVectorSpaceMismatch(
                    "Provider vector dimensionality does not match the vector space."
                )
        self._recordUsage(tenant, texts, attribution, started)
        return vectors

    def _recordUsage(
        self,
        tenant: uuid.UUID,
        texts: Sequence[str],
        attribution: UsageAttribution | None,
        started: datetime,
    ) -> None:
        """Meter one provider attempt through Phase 13-N when attributable."""

        if self.usageRecorder is None or attribution is None:
            return
        from apps.ai.application.services.usageService import RecordUsageAttemptCommand

        inputTokens = sum(estimateTokens(text) for text in texts)
        elapsed = self._now() - started
        latencyMs = max(0, int(elapsed.total_seconds() * 1000))
        self.usageRecorder.recordProviderAttempt(
            tenant,
            RecordUsageAttemptCommand(
                requestId=attribution.requestId,
                modelId=attribution.modelId,
                providerId=attribution.providerId,
                providerCode=attribution.providerCode,
                modelCode=attribution.modelCode,
                inputTokens=inputTokens,
                outputTokens=0,
                capabilityCode=attribution.capabilityCode or "EMBEDDING",
                requestedBy=attribution.requestedBy,
                providerTimeMs=latencyMs,
                latencyMs=latencyMs,
                correlationId=attribution.correlationId,
                traceId=attribution.traceId,
            ),
        )

    def _requireSpace(self, tenant: uuid.UUID, spaceCode: str) -> AIVectorSpaceDefinition:
        self._requireEnabled()
        code = str(spaceCode or "").strip().upper()
        if not code:
            raise AIVectorSpaceInvalid("A vector space code is required.")
        definition = self.spaceStore.getSpace(tenant, code)
        if definition is None:
            raise AIVectorSpaceNotFound(code)
        if definition.tenantId != tenant:
            raise AIVectorSpaceNotFound(code)
        return definition

    def _requireEnabled(self) -> None:
        if not self.settings.enabled:
            raise AIConfigurationError("The AI embedding foundation is disabled.")

    def _audit(self, tenant: uuid.UUID, action: str, **kwargs: Any) -> None:
        if self.auditLogger is None:
            return
        self.auditLogger.logAudit(tenant, action, **kwargs)


class EmbeddingJobHandler:
    """Phase 13-P handler for the ``EMBEDDING`` job kind (§Q.14).

    Payload contract::

        {"spaceCode": "...", "items": [{"text": "...", "sourceType": "...",
         "sourceId": "...", "metadata": {...}}], "replaceExisting": false}

    The handler owns no business rule: it validates the payload shape and
    delegates to ``EmbeddingApplicationService.embedTexts``.
    """

    JOB_KIND = "EMBEDDING"

    def __init__(self, service: EmbeddingApplicationService) -> None:
        self.service = service

    def kind(self) -> str:
        return self.JOB_KIND

    def execute(self, job: Any) -> Any:
        from apps.ai.domain.services.jobQueue import JobOutcome

        payload = dict(getattr(job, "payload", {}) or {})
        spaceCode = str(payload.get("spaceCode") or "").strip()
        rawItems = payload.get("items")
        if not spaceCode or not isinstance(rawItems, list) or not rawItems:
            raise AIEmbeddingInvalid("Embedding job payload is invalid.")
        if len(rawItems) > MAX_BATCH_SIZE:
            raise AIEmbeddingBatchTooLarge("Embedding job payload exceeds the batch ceiling.")
        items = tuple(
            EmbeddingItem(
                text=str(entry.get("text", "")),
                sourceType=str(entry.get("sourceType", "CUSTOM")),
                sourceId=str(entry.get("sourceId", "")),
                metadata=dict(entry.get("metadata", {}) or {}),
            )
            for entry in rawItems
            if isinstance(entry, dict)
        )
        if len(items) != len(rawItems):
            raise AIEmbeddingInvalid("Embedding job payload contains a non-object item.")
        result = self.service.embedTexts(
            job.tenantId,
            EmbedTextsCommand(
                spaceCode=spaceCode,
                items=items,
                replaceExisting=bool(payload.get("replaceExisting", False)),
            ),
        )
        return JobOutcome(
            outcome="SUCCEEDED",
            summary={
                "spaceCode": result.spaceCode,
                "created": len(result.created),
                "reused": len(result.reused),
                "duplicates": result.duplicates,
                "providerCalls": result.providerCalls,
            },
        )


__all__ = [
    "AUDIT_EMBEDDING_CREATED",
    "AUDIT_EMBEDDING_DELETED",
    "AUDIT_SPACE_DEACTIVATED",
    "AUDIT_SPACE_DEFINED",
    "DefineVectorSpaceCommand",
    "EmbedResult",
    "EmbedTextsCommand",
    "EmbeddingApplicationService",
    "EmbeddingDescriptor",
    "EmbeddingJobHandler",
    "EmbeddingProviderResolver",
    "EmbeddingSettings",
    "SearchResult",
    "SimilaritySearchQuery",
    "UsageAttribution",
    "VectorSpaceDescriptor",
]
