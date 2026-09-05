"""Application orchestration for the Phase 13-R knowledge platform.

``KnowledgeApplicationService`` wires the pure chunker and index planner to
persistence, to the Phase 13-Q embedding foundation, and to the Phase 13-O
audit ledger. It owns no splitting rule and no diff rule itself: both live
in ``apps.ai.domain.services.knowledgeChunker``.

Behaviour worth stating once:

- **AI stores no source content.** The register keeps the owning-domain
  reference, the content checksum, and the derived chunks — never the
  original row (Master Specification §37). Chunks are a rebuildable index.
- **Ingestion is idempotent.** Re-ingesting unchanged content under the
  same policy performs no write, no embedding call, and no revision bump.
- **Reindexing is incremental.** Chunks whose checksum survives are reused
  (their vectors stay valid) and merely reordered; only genuinely new
  chunks are embedded and only orphaned chunks (and their vectors) are
  deleted.
- **Failure is explicit.** A failed run leaves the source in ``FAILED``
  with a stable error code — never half ``READY``.
- **No authorization here.** Chunks carry the classification inherited
  from their source so the Phase 13-K engine can filter them in the S
  retrieval pipeline; R itself enforces tenant isolation only.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings as djangoSettings

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.knowledgeRecords import (
    AIKnowledgeChunkRecord,
    AIKnowledgeSourceRecord,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIKnowledgeChunkNotFound,
    AIKnowledgeIngestionFailed,
    AIKnowledgeSourceArchived,
    AIKnowledgeSourceInvalid,
    AIKnowledgeSourceNotFound,
)
from apps.ai.domain.knowledgePorts import (
    ChunkEmbedder,
    KnowledgeAuditLogger,
    KnowledgeChunkStore,
    KnowledgeSourceStore,
)
from apps.ai.domain.services.knowledgeChunker import (
    ChunkingService,
    IndexPlan,
    IndexPlanner,
    buildChunkRecords,
)
from apps.ai.domain.valueObjects.aiTypes import DATA_CLASSIFICATIONS, ensureEnum
from apps.ai.domain.valueObjects.knowledgeTypes import (
    MAX_CHUNKS_PER_SOURCE,
    ChunkingPolicy,
    ensureSourceDomain,
)

#: Audit actions appended by R (registered in the Phase 13-O vocabulary).
AUDIT_KNOWLEDGE_INGESTED = "KNOWLEDGE_INGESTED"
AUDIT_KNOWLEDGE_REINDEXED = "KNOWLEDGE_REINDEXED"
AUDIT_KNOWLEDGE_ARCHIVED = "KNOWLEDGE_ARCHIVED"
AUDIT_KNOWLEDGE_PURGED = "KNOWLEDGE_PURGED"

#: The Phase 13-Q source type every chunk vector is stored under.
CHUNK_SOURCE_TYPE = "KNOWLEDGE_CHUNK"


@dataclass(frozen=True)
class KnowledgeSettings:
    """Configuration-driven defaults (Master Specification §42)."""

    enabled: bool = True
    strategy: str = "PARAGRAPH"
    chunkTokens: int = 512
    overlapTokens: int = 64
    minChunkTokens: int = 32
    autoEmbed: bool = True
    embedBatchSize: int = 32
    maxChunksPerSource: int = 500
    retentionDays: int = 730

    def __post_init__(self) -> None:
        if self.embedBatchSize < 1:
            raise AIConfigurationError("aiKnowledgeEmbedBatchSize must be positive.")
        if self.maxChunksPerSource < 1 or self.maxChunksPerSource > MAX_CHUNKS_PER_SOURCE:
            raise AIConfigurationError("aiKnowledgeMaxChunksPerSource is out of range.")
        if self.retentionDays < 1:
            raise AIConfigurationError("aiKnowledgeRetentionDays must be positive.")
        # Validating the policy here means an impossible configuration fails
        # at construction, not on the first ingestion.
        self.defaultPolicy()

    def defaultPolicy(self) -> ChunkingPolicy:
        return ChunkingPolicy(
            strategy=self.strategy,
            maxTokens=self.chunkTokens,
            overlapTokens=self.overlapTokens,
            minTokens=self.minChunkTokens,
        )

    @classmethod
    def fromDjangoSettings(cls) -> KnowledgeSettings:
        return cls(
            enabled=bool(getattr(djangoSettings, "AI_KNOWLEDGE_ENABLED", True)),
            strategy=str(
                getattr(djangoSettings, "AI_KNOWLEDGE_CHUNK_STRATEGY", "PARAGRAPH") or "PARAGRAPH"
            ),
            chunkTokens=int(getattr(djangoSettings, "AI_KNOWLEDGE_CHUNK_TOKENS", 512) or 512),
            overlapTokens=int(
                getattr(djangoSettings, "AI_KNOWLEDGE_CHUNK_OVERLAP_TOKENS", 64) or 64
            ),
            minChunkTokens=int(getattr(djangoSettings, "AI_KNOWLEDGE_MIN_CHUNK_TOKENS", 32) or 32),
            autoEmbed=bool(getattr(djangoSettings, "AI_KNOWLEDGE_AUTO_EMBED", True)),
            embedBatchSize=int(getattr(djangoSettings, "AI_KNOWLEDGE_EMBED_BATCH_SIZE", 32) or 32),
            maxChunksPerSource=int(
                getattr(djangoSettings, "AI_KNOWLEDGE_MAX_CHUNKS_PER_SOURCE", 500) or 500
            ),
            retentionDays=int(getattr(djangoSettings, "AI_KNOWLEDGE_RETENTION_DAYS", 730) or 730),
        )


@dataclass(frozen=True)
class IngestKnowledgeCommand:
    """Publish or refresh one business row in the knowledge index (§R.8)."""

    sourceDomain: str
    sourceEntityType: str
    sourceEntityId: str
    title: str
    content: str
    classification: str = "INTERNAL"
    spaceCode: str = ""
    policy: ChunkingPolicy | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    force: bool = False
    autoEmbed: bool | None = None
    attribution: Any = None


@dataclass(frozen=True)
class KnowledgeSourceDescriptor:
    """Safe read model of a registered source."""

    sourceId: uuid.UUID
    tenantId: uuid.UUID
    reference: str
    sourceDomain: str
    sourceEntityType: str
    sourceEntityId: str
    title: str
    classification: str
    status: str
    checksum: str
    spaceCode: str
    policySignature: str
    revision: int
    chunkCount: int
    tokenCount: int
    errorCode: str
    lastIndexedAt: datetime | None
    createdAt: datetime

    @classmethod
    def of(cls, source: AIKnowledgeSourceRecord) -> KnowledgeSourceDescriptor:
        return cls(
            sourceId=source.id,
            tenantId=source.tenantId,
            reference=source.reference(),
            sourceDomain=source.sourceDomain,
            sourceEntityType=source.sourceEntityType,
            sourceEntityId=source.sourceEntityId,
            title=source.title,
            classification=source.classification,
            status=source.status,
            checksum=source.checksum,
            spaceCode=source.spaceCode,
            policySignature=source.policySignature,
            revision=source.revision,
            chunkCount=source.chunkCount,
            tokenCount=source.tokenCount,
            errorCode=source.errorCode,
            lastIndexedAt=source.lastIndexedAt,
            createdAt=source.createdAt,
        )


@dataclass(frozen=True)
class ChunkDescriptor:
    """Read model of one chunk — text included, because S needs it."""

    chunkId: uuid.UUID
    sourceId: uuid.UUID
    ordinal: int
    text: str
    checksum: str
    tokenCount: int
    classification: str
    startOffset: int
    endOffset: int

    @classmethod
    def of(cls, chunk: AIKnowledgeChunkRecord) -> ChunkDescriptor:
        return cls(
            chunkId=chunk.id,
            sourceId=chunk.sourceId,
            ordinal=chunk.ordinal,
            text=chunk.text,
            checksum=chunk.checksum,
            tokenCount=chunk.tokenCount,
            classification=chunk.classification,
            startOffset=chunk.startOffset,
            endOffset=chunk.endOffset,
        )


@dataclass(frozen=True)
class IngestionResult:
    """Outcome of one ingestion run (§R.8)."""

    source: KnowledgeSourceDescriptor
    action: str
    reason: str
    chunksAdded: int
    chunksReused: int
    chunksRemoved: int
    embeddingsCreated: int
    embeddingsReused: int
    embeddingsDeleted: int

    @property
    def isNoop(self) -> bool:
        return self.action == "UNCHANGED"


class KnowledgeApplicationService:
    """Tenant-scoped facade for ingestion, chunking, and indexing."""

    def __init__(
        self,
        sourceStore: KnowledgeSourceStore,
        chunkStore: KnowledgeChunkStore,
        *,
        embedder: ChunkEmbedder | None = None,
        settings: KnowledgeSettings | None = None,
        auditLogger: KnowledgeAuditLogger | None = None,
        chunker: ChunkingService | None = None,
        planner: IndexPlanner | None = None,
        now: Any = utcNow,
    ) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self.sourceStore = sourceStore
        self.chunkStore = chunkStore
        self.embedder = embedder
        self.settings = settings or KnowledgeSettings()
        self.auditLogger = auditLogger
        self.chunker = chunker or ChunkingService(self.settings.defaultPolicy())
        self.planner = planner or IndexPlanner()
        self._now = now

    # ------------------------------------------------------------------
    # Ingestion (§R.8)
    # ------------------------------------------------------------------
    def ingestSource(
        self, tenantId: uuid.UUID | str, command: IngestKnowledgeCommand
    ) -> IngestionResult:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(command, IngestKnowledgeCommand):
            raise AIKnowledgeSourceInvalid("Ingestion requires an IngestKnowledgeCommand.")
        policy = command.policy or self.settings.defaultPolicy()
        classification = ensureEnum(command.classification, DATA_CLASSIFICATIONS, "classification")
        domain = ensureSourceDomain(command.sourceDomain)

        result = self.chunker.split(command.content, policy=policy)
        if len(result.chunks) > self.settings.maxChunksPerSource:
            raise AIKnowledgeSourceInvalid(
                "Source produces more chunks than the configured ceiling allows."
            )

        source = self.sourceStore.findByNaturalKey(
            tenant, domain, command.sourceEntityType, command.sourceEntityId
        )
        if source is not None and source.status == "ARCHIVED":
            raise AIKnowledgeSourceArchived("An archived knowledge source cannot be re-ingested.")
        existingChunks = () if source is None else self.chunkStore.listChunks(tenant, source.id)
        plan = self.planner.plan(source, result, existingChunks, force=command.force)

        if plan.isNoop:
            assert source is not None
            return IngestionResult(
                source=KnowledgeSourceDescriptor.of(source),
                action=plan.action,
                reason=plan.reason,
                chunksAdded=0,
                chunksReused=len(existingChunks),
                chunksRemoved=0,
                embeddingsCreated=0,
                embeddingsReused=0,
                embeddingsDeleted=0,
            )

        moment = self._now()
        created = source is None
        if source is None:
            source = AIKnowledgeSourceRecord(
                tenantId=tenant,
                sourceDomain=domain,
                sourceEntityType=command.sourceEntityType,
                sourceEntityId=command.sourceEntityId,
                title=command.title,
                checksum=result.checksum,
                classification=classification,
                spaceCode=command.spaceCode,
                metadata=dict(command.metadata),
                createdAt=moment,
                updatedAt=moment,
            )
            source = self.sourceStore.saveSource(source)
        else:
            source.title = str(command.title or source.title).strip()
            source.classification = classification
            if command.spaceCode:
                source.spaceCode = command.spaceCode.strip().upper()
            if command.metadata:
                source.metadata = dict(command.metadata)

        source.transitionTo("INDEXING", now=moment)
        self.sourceStore.updateSource(source)

        try:
            outcome = self._applyPlan(tenant, source, plan, classification, command, moment)
        except Exception as error:  # noqa: BLE001 - re-raised after bookkeeping
            source.markFailed(getattr(error, "code", "AI_KNOWLEDGE_INGESTION_FAILED"), now=moment)
            self.sourceStore.updateSource(source)
            self._audit(
                tenant,
                AUDIT_KNOWLEDGE_REINDEXED,
                outcome="FAILED",
                classification=classification,
                errorCode=str(getattr(error, "code", "AI_KNOWLEDGE_INGESTION_FAILED")),
                contextSources=(source.reference(),),
                detail={"reason": plan.reason},
            )
            if isinstance(error, AIKnowledgeIngestionFailed):
                raise
            raise AIKnowledgeIngestionFailed(str(error) or "Knowledge ingestion failed.") from error

        source.markIndexed(
            checksum=plan.checksum,
            chunkCount=plan.totalChunks,
            tokenCount=plan.totalTokens,
            policy=policy,
            spaceCode=command.spaceCode,
            now=moment,
        )
        stored = self.sourceStore.updateSource(source)
        self._audit(
            tenant,
            AUDIT_KNOWLEDGE_INGESTED if created else AUDIT_KNOWLEDGE_REINDEXED,
            outcome="RECORDED",
            classification=classification,
            contextSources=(stored.reference(),),
            detail={
                "action": plan.action,
                "reason": plan.reason,
                "chunksAdded": plan.addedCount,
                "chunksReused": plan.reusedCount,
                "chunksRemoved": plan.removedCount,
                "revision": stored.revision,
            },
        )
        return IngestionResult(
            source=KnowledgeSourceDescriptor.of(stored),
            action=plan.action,
            reason=plan.reason,
            chunksAdded=plan.addedCount,
            chunksReused=plan.reusedCount,
            chunksRemoved=plan.removedCount,
            embeddingsCreated=outcome["embeddingsCreated"],
            embeddingsReused=outcome["embeddingsReused"],
            embeddingsDeleted=outcome["embeddingsDeleted"],
        )

    def reindexSource(
        self,
        tenantId: uuid.UUID | str,
        sourceId: uuid.UUID | str,
        content: str,
        *,
        policy: ChunkingPolicy | None = None,
        force: bool = True,
    ) -> IngestionResult:
        """Re-run ingestion for a known source with fresh content."""

        tenant = requireUuid(tenantId, "tenantId")
        source = self._requireSource(tenant, sourceId)
        return self.ingestSource(
            tenant,
            IngestKnowledgeCommand(
                sourceDomain=source.sourceDomain,
                sourceEntityType=source.sourceEntityType,
                sourceEntityId=source.sourceEntityId,
                title=source.title,
                content=content,
                classification=source.classification,
                spaceCode=source.spaceCode,
                policy=policy,
                force=force,
            ),
        )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def describeSource(
        self, tenantId: uuid.UUID | str, sourceId: uuid.UUID | str
    ) -> KnowledgeSourceDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        return KnowledgeSourceDescriptor.of(self._requireSource(tenant, sourceId))

    def findSource(
        self,
        tenantId: uuid.UUID | str,
        sourceDomain: str,
        sourceEntityType: str,
        sourceEntityId: str,
    ) -> KnowledgeSourceDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        source = self.sourceStore.findByNaturalKey(
            tenant, ensureSourceDomain(sourceDomain), sourceEntityType, sourceEntityId
        )
        if source is None:
            raise AIKnowledgeSourceNotFound(f"{sourceDomain}:{sourceEntityType}:{sourceEntityId}")
        return KnowledgeSourceDescriptor.of(source)

    def listSources(
        self,
        tenantId: uuid.UUID | str,
        *,
        statuses: tuple[str, ...] = (),
        sourceDomain: str = "",
    ) -> tuple[KnowledgeSourceDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        domain = ensureSourceDomain(sourceDomain) if sourceDomain else ""
        rows = self.sourceStore.listSources(tenant, statuses=statuses, sourceDomain=domain)
        return tuple(KnowledgeSourceDescriptor.of(row) for row in rows)

    def listChunks(
        self, tenantId: uuid.UUID | str, sourceId: uuid.UUID | str
    ) -> tuple[ChunkDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        source = self._requireSource(tenant, sourceId)
        rows = self.chunkStore.listChunks(tenant, source.id)
        return tuple(ChunkDescriptor.of(row) for row in rows)

    def describeChunk(self, tenantId: uuid.UUID | str, chunkId: uuid.UUID | str) -> ChunkDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        chunk = self.chunkStore.getChunk(tenant, requireUuid(chunkId, "chunkId"))
        if chunk is None:
            raise AIKnowledgeChunkNotFound(str(chunkId))
        return ChunkDescriptor.of(chunk)

    def resolveChunks(
        self, tenantId: uuid.UUID | str, chunkIds: Sequence[uuid.UUID | str]
    ) -> tuple[ChunkDescriptor, ...]:
        """Hydrate ranked search hits back into chunk text for S.

        Unknown or foreign identifiers are skipped rather than raising: a
        retrieval hit whose chunk was purged mid-flight must degrade the
        result set, not break the whole answer.
        """

        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        resolved: list[ChunkDescriptor] = []
        for candidate in chunkIds:
            try:
                identifier = requireUuid(candidate, "chunkId")
            except ValueError:
                continue
            chunk = self.chunkStore.getChunk(tenant, identifier)
            if chunk is not None:
                resolved.append(ChunkDescriptor.of(chunk))
        return tuple(resolved)

    # ------------------------------------------------------------------
    # Lifecycle (§R.11)
    # ------------------------------------------------------------------
    def archiveSource(
        self, tenantId: uuid.UUID | str, sourceId: uuid.UUID | str
    ) -> KnowledgeSourceDescriptor:
        """Archive a source: chunks and their vectors are dropped, the
        register row survives as an auditable tombstone."""

        tenant = requireUuid(tenantId, "tenantId")
        source = self._requireSource(tenant, sourceId)
        chunks = self.chunkStore.listChunks(tenant, source.id)
        deleted = self._deleteEmbeddings(tenant, source, chunks)
        self.chunkStore.deleteSourceChunks(tenant, source.id)
        source.archive(now=self._now())
        stored = self.sourceStore.updateSource(source)
        self._audit(
            tenant,
            AUDIT_KNOWLEDGE_ARCHIVED,
            outcome="UPDATED",
            classification=stored.classification,
            contextSources=(stored.reference(),),
            detail={"chunksRemoved": len(chunks), "embeddingsDeleted": deleted},
        )
        return KnowledgeSourceDescriptor.of(stored)

    def deleteSource(self, tenantId: uuid.UUID | str, sourceId: uuid.UUID | str) -> int:
        """Hard delete: register row, chunks, and vectors all disappear."""

        tenant = requireUuid(tenantId, "tenantId")
        source = self._requireSource(tenant, sourceId)
        chunks = self.chunkStore.listChunks(tenant, source.id)
        deleted = self._deleteEmbeddings(tenant, source, chunks)
        removedChunks = self.chunkStore.deleteSourceChunks(tenant, source.id)
        self.sourceStore.deleteSource(tenant, source.id)
        self._audit(
            tenant,
            AUDIT_KNOWLEDGE_PURGED,
            outcome="PURGED",
            classification=source.classification,
            contextSources=(source.reference(),),
            detail={"chunksRemoved": removedChunks, "embeddingsDeleted": deleted},
        )
        return removedChunks

    def purgeKnowledgeRetention(
        self,
        tenantId: uuid.UUID | str | None = None,
        *,
        retentionDays: int | None = None,
        now: datetime | None = None,
    ) -> int:
        """Delete archived/stale sources older than the retention horizon."""

        self._requireEnabled()
        tenant = None if tenantId is None else requireUuid(tenantId, "tenantId")
        days = self.settings.retentionDays if retentionDays is None else int(retentionDays)
        if days < 1:
            raise AIConfigurationError("Knowledge retention must be at least one day.")
        cutoff = (now or self._now()) - timedelta(days=days)
        removed = self.sourceStore.deleteSourcesBefore(tenant, cutoff)
        for sourceId in removed:
            if tenant is not None:
                self.chunkStore.deleteSourceChunks(tenant, sourceId)
        if removed and tenant is not None:
            self._audit(
                tenant,
                AUDIT_KNOWLEDGE_PURGED,
                outcome="PURGED",
                detail={"sourcesRemoved": len(removed), "retentionDays": days},
            )
        return len(removed)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _applyPlan(
        self,
        tenant: uuid.UUID,
        source: AIKnowledgeSourceRecord,
        plan: IndexPlan,
        classification: str,
        command: IngestKnowledgeCommand,
        moment: datetime,
    ) -> dict[str, int]:
        # 1. Reused chunks keep their identity (and their vectors) and are
        #    only moved to their new position.
        if plan.reused:
            self.chunkStore.reorderChunks(
                tenant, {chunk.id: ordinal for chunk, ordinal in plan.reused}
            )

        # 2. Orphaned chunks lose their vectors first, then themselves —
        #    an interrupted run leaves no vector pointing at a dead chunk.
        embeddingsDeleted = self._deleteEmbeddings(tenant, source, plan.removed)
        if plan.removed:
            self.chunkStore.deleteChunks(tenant, tuple(chunk.id for chunk in plan.removed))

        # 3. New chunks are persisted, then embedded.
        records = buildChunkRecords(
            tenant,
            source.id,
            plan.added,
            classification=classification,
            metadata={"reference": source.reference()},
            createdAt=moment,
        )
        storedChunks = self.chunkStore.saveChunks(records) if records else ()
        embeddingsCreated, embeddingsReused = self._embedChunks(
            tenant, source, storedChunks, command
        )
        return {
            "embeddingsCreated": embeddingsCreated,
            "embeddingsReused": embeddingsReused,
            "embeddingsDeleted": embeddingsDeleted,
        }

    def _embedChunks(
        self,
        tenant: uuid.UUID,
        source: AIKnowledgeSourceRecord,
        chunks: Sequence[AIKnowledgeChunkRecord],
        command: IngestKnowledgeCommand,
    ) -> tuple[int, int]:
        autoEmbed = self.settings.autoEmbed if command.autoEmbed is None else command.autoEmbed
        spaceCode = (command.spaceCode or source.spaceCode).strip().upper()
        if not chunks or not autoEmbed or not spaceCode:
            return (0, 0)
        if self.embedder is None:
            raise AIConfigurationError(
                "Knowledge auto-embedding is enabled but no embedder is configured."
            )
        from apps.ai.application.services.embeddingService import (
            EmbeddingItem,
            EmbedTextsCommand,
        )

        created = 0
        reused = 0
        batchSize = self.settings.embedBatchSize
        for start in range(0, len(chunks), batchSize):
            window = chunks[start : start + batchSize]
            items = tuple(
                EmbeddingItem(
                    text=chunk.text,
                    sourceType=CHUNK_SOURCE_TYPE,
                    sourceId=chunk.embeddingSourceId,
                    chunkId=chunk.id,
                    metadata={
                        "knowledgeSourceId": str(source.id),
                        "reference": source.reference(),
                        "ordinal": chunk.ordinal,
                        "classification": chunk.classification,
                    },
                )
                for chunk in window
            )
            result = self.embedder.embedTexts(
                tenant,
                EmbedTextsCommand(
                    spaceCode=spaceCode,
                    items=items,
                    attribution=command.attribution,
                ),
            )
            created += len(getattr(result, "created", ()))
            reused += len(getattr(result, "reused", ()))
        return (created, reused)

    def _deleteEmbeddings(
        self,
        tenant: uuid.UUID,
        source: AIKnowledgeSourceRecord,
        chunks: Sequence[AIKnowledgeChunkRecord],
    ) -> int:
        if not chunks or self.embedder is None or not source.spaceCode:
            return 0
        deleted = 0
        for chunk in chunks:
            deleted += int(
                self.embedder.deleteSourceEmbeddings(
                    tenant, source.spaceCode, CHUNK_SOURCE_TYPE, chunk.embeddingSourceId
                )
            )
        return deleted

    def _requireSource(
        self, tenant: uuid.UUID, sourceId: uuid.UUID | str
    ) -> AIKnowledgeSourceRecord:
        self._requireEnabled()
        source = self.sourceStore.getSource(tenant, requireUuid(sourceId, "sourceId"))
        if source is None or source.tenantId != tenant:
            raise AIKnowledgeSourceNotFound(str(sourceId))
        return source

    def _requireEnabled(self) -> None:
        if not self.settings.enabled:
            raise AIConfigurationError("The AI knowledge platform is disabled.")

    def _audit(self, tenant: uuid.UUID, action: str, **kwargs: Any) -> None:
        if self.auditLogger is None:
            return
        self.auditLogger.logAudit(tenant, action, **kwargs)


class KnowledgeIngestionJobHandler:
    """Phase 13-P handler for the ``INDEXING`` job kind (§R.14).

    Payload contract::

        {"sourceDomain": "DOCUMENTS", "sourceEntityType": "DOCUMENT",
         "sourceEntityId": "...", "title": "...", "content": "...",
         "classification": "INTERNAL", "spaceCode": "...", "force": false}
    """

    JOB_KIND = "INDEXING"

    def __init__(self, service: KnowledgeApplicationService) -> None:
        self.service = service

    def kind(self) -> str:
        return self.JOB_KIND

    def execute(self, job: Any) -> Any:
        from apps.ai.domain.services.jobQueue import JobOutcome

        payload = dict(getattr(job, "payload", {}) or {})
        required = ("sourceDomain", "sourceEntityType", "sourceEntityId", "title", "content")
        if any(not str(payload.get(key, "")).strip() for key in required):
            raise AIKnowledgeSourceInvalid("Knowledge ingestion job payload is invalid.")
        result = self.service.ingestSource(
            job.tenantId,
            IngestKnowledgeCommand(
                sourceDomain=str(payload["sourceDomain"]),
                sourceEntityType=str(payload["sourceEntityType"]),
                sourceEntityId=str(payload["sourceEntityId"]),
                title=str(payload["title"]),
                content=str(payload["content"]),
                classification=str(payload.get("classification", "INTERNAL") or "INTERNAL"),
                spaceCode=str(payload.get("spaceCode", "") or ""),
                metadata=dict(payload.get("metadata", {}) or {}),
                force=bool(payload.get("force", False)),
            ),
        )
        return JobOutcome(
            outcome="SUCCEEDED",
            summary={
                "action": result.action,
                "sourceId": str(result.source.sourceId),
                "revision": result.source.revision,
                "chunksAdded": result.chunksAdded,
                "chunksReused": result.chunksReused,
                "chunksRemoved": result.chunksRemoved,
                "embeddingsCreated": result.embeddingsCreated,
            },
        )


__all__ = [
    "AUDIT_KNOWLEDGE_ARCHIVED",
    "AUDIT_KNOWLEDGE_INGESTED",
    "AUDIT_KNOWLEDGE_PURGED",
    "AUDIT_KNOWLEDGE_REINDEXED",
    "CHUNK_SOURCE_TYPE",
    "ChunkDescriptor",
    "IngestKnowledgeCommand",
    "IngestionResult",
    "KnowledgeApplicationService",
    "KnowledgeIngestionJobHandler",
    "KnowledgeSettings",
    "KnowledgeSourceDescriptor",
]
