"""Application orchestration for Phase 13-S retrieval, RAG, and reranking.

``RetrievalApplicationService`` closes the pipeline the Master
Specification draws in §20::

    Query → Query Embedding → Candidate Retrieval → Permission Filtering
          → Ranking → Context Construction → AI

Every arrow is a real call here: the query is embedded by Phase 13-Q, the
candidates come from the vector store (and, for ``LEXICAL``/``HYBRID``,
from Phase 13-R chunk text), the chunk text is hydrated by R, the
permission filter is Phase 13-K's fail-closed engine, ranking is the pure
S reranker, and the assembled context feeds the provider through the
Phase 13-C surface.

Behaviour worth stating once:

- **Filtering precedes assembly, structurally.** The pipeline object
  refuses to assemble a context whose ``AUTHORIZE`` stage never ran, so
  the ordering is enforced by the type, not by reviewer discipline.
- **Fail-closed grounding.** When no authorized evidence survives and the
  policy requires grounding, S raises ``AIRagUngrounded`` instead of
  letting a model answer from thin air.
- **S stores nothing.** It is a read path; the auditable account of a run
  lives in the returned trace and in the Phase 13-O ledger (decision
  S-D5), so no new table and no new migration exist in this sub-phase.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings as djangoSettings

from apps.ai.domain.entities.aiRecords import newId, requireUuid, utcNow
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIRagUngrounded,
    AIRetrievalInvalid,
    AIRetrievalPolicyInvalid,
)
from apps.ai.domain.retrievalPorts import (
    CandidateSearcher,
    ChunkTextResolver,
    GroundedGenerator,
    RetrievalAuditLogger,
    SourcePermissionFilter,
)
from apps.ai.domain.services.contextEngine import ContextSourceCandidate
from apps.ai.domain.services.retrievalPipeline import (
    Citation,
    GroundedPrompt,
    Reranker,
    RetrievalCandidate,
    RetrievalPipeline,
    RetrievalTrace,
)
from apps.ai.domain.valueObjects.retrievalTypes import (
    RetrievalPolicy,
    lexicalOverlap,
)

#: Audit actions appended by S (registered in the Phase 13-O vocabulary).
AUDIT_RETRIEVAL_EXECUTED = "RETRIEVAL_EXECUTED"
AUDIT_RETRIEVAL_DENIED = "RETRIEVAL_DENIED"
AUDIT_RAG_ANSWERED = "RAG_ANSWERED"

#: The Phase 13-Q source type every knowledge chunk vector is stored under.
CHUNK_SOURCE_TYPE = "KNOWLEDGE_CHUNK"


@dataclass(frozen=True)
class RetrievalSettings:
    """Configuration-driven defaults (Master Specification §42)."""

    enabled: bool = True
    strategy: str = "HYBRID"
    topK: int = 5
    candidateLimit: int = 200
    minScore: float | None = None
    rerank: str = "LEXICAL_BOOST"
    lexicalWeight: float = 0.3
    mmrLambda: float = 0.7
    maxContextTokens: int = 4000
    maxContextSources: int = 10
    requireGrounding: bool = True
    lexicalScanLimit: int = 500
    answerModelCode: str = ""

    def __post_init__(self) -> None:
        if self.lexicalScanLimit < 1:
            raise AIConfigurationError("aiRetrievalLexicalScanLimit must be positive.")
        # Building the policy here means an impossible configuration fails
        # at construction, not on the first query.
        self.defaultPolicy()

    def defaultPolicy(self) -> RetrievalPolicy:
        return RetrievalPolicy(
            strategy=self.strategy,
            topK=self.topK,
            candidateLimit=self.candidateLimit,
            minScore=self.minScore,
            rerank=self.rerank,
            lexicalWeight=self.lexicalWeight,
            mmrLambda=self.mmrLambda,
            maxContextTokens=self.maxContextTokens,
            maxContextSources=self.maxContextSources,
            requireGrounding=self.requireGrounding,
        )

    @classmethod
    def fromDjangoSettings(cls) -> RetrievalSettings:
        rawMinScore = getattr(djangoSettings, "AI_RETRIEVAL_MIN_SCORE", "")
        return cls(
            enabled=bool(getattr(djangoSettings, "AI_RETRIEVAL_ENABLED", True)),
            strategy=str(getattr(djangoSettings, "AI_RETRIEVAL_STRATEGY", "HYBRID") or "HYBRID"),
            topK=int(getattr(djangoSettings, "AI_RETRIEVAL_TOP_K", 5) or 5),
            candidateLimit=int(getattr(djangoSettings, "AI_RETRIEVAL_CANDIDATE_LIMIT", 200) or 200),
            minScore=None if rawMinScore in ("", None) else float(rawMinScore),
            rerank=str(
                getattr(djangoSettings, "AI_RETRIEVAL_RERANK", "LEXICAL_BOOST") or "LEXICAL_BOOST"
            ),
            lexicalWeight=float(getattr(djangoSettings, "AI_RETRIEVAL_LEXICAL_WEIGHT", 0.3) or 0.3),
            mmrLambda=float(getattr(djangoSettings, "AI_RETRIEVAL_MMR_LAMBDA", 0.7) or 0.7),
            maxContextTokens=int(
                getattr(djangoSettings, "AI_RETRIEVAL_MAX_CONTEXT_TOKENS", 4000) or 4000
            ),
            maxContextSources=int(
                getattr(djangoSettings, "AI_RETRIEVAL_MAX_CONTEXT_SOURCES", 10) or 10
            ),
            requireGrounding=bool(getattr(djangoSettings, "AI_RAG_REQUIRE_GROUNDING", True)),
            lexicalScanLimit=int(
                getattr(djangoSettings, "AI_RETRIEVAL_LEXICAL_SCAN_LIMIT", 500) or 500
            ),
            answerModelCode=str(getattr(djangoSettings, "AI_RAG_ANSWER_MODEL", "") or ""),
        )


@dataclass(frozen=True)
class RetrievalRequest:
    """One retrieval run (§S.6)."""

    spaceCode: str
    question: str
    principal: Any
    policy: RetrievalPolicy | None = None
    sourceDomain: str = ""
    requestId: uuid.UUID | None = None
    correlationId: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RagRequest:
    """A grounded question: retrieval plus one generation step (§S.10)."""

    spaceCode: str
    question: str
    principal: Any
    policy: RetrievalPolicy | None = None
    sourceDomain: str = ""
    modelCode: str = ""
    instruction: str = ""
    requestId: uuid.UUID | None = None
    correlationId: str = ""


@dataclass(frozen=True)
class RetrievalResult:
    """Ranked, authorized evidence plus the auditable trace."""

    requestId: uuid.UUID
    spaceCode: str
    question: str
    prompt: GroundedPrompt
    candidates: tuple[RetrievalCandidate, ...]
    trace: RetrievalTrace
    candidateCount: int
    authorizedCount: int
    deniedCount: int

    @property
    def citations(self) -> tuple[Citation, ...]:
        return self.prompt.citations

    @property
    def isGrounded(self) -> bool:
        return self.prompt.isGrounded


@dataclass(frozen=True)
class RagAnswer:
    """A grounded answer that can always be traced back to its evidence."""

    requestId: uuid.UUID
    question: str
    answer: str
    citations: tuple[Citation, ...]
    modelCode: str
    retrieval: RetrievalResult

    @property
    def isGrounded(self) -> bool:
        return bool(self.citations)


class RetrievalApplicationService:
    """Tenant-scoped facade for retrieval and retrieval-augmented answers."""

    def __init__(
        self,
        searcher: CandidateSearcher,
        resolver: ChunkTextResolver,
        *,
        permissionFilter: SourcePermissionFilter | None = None,
        generator: GroundedGenerator | None = None,
        settings: RetrievalSettings | None = None,
        auditLogger: RetrievalAuditLogger | None = None,
        reranker: Reranker | None = None,
        now: Any = utcNow,
    ) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self.searcher = searcher
        self.resolver = resolver
        self.permissionFilter = permissionFilter
        self.generator = generator
        self.settings = settings or RetrievalSettings()
        self.auditLogger = auditLogger
        self.reranker = reranker or Reranker()
        self._now = now

    # ------------------------------------------------------------------
    # Retrieval (§S.6–§S.9)
    # ------------------------------------------------------------------
    def retrieve(self, tenantId: uuid.UUID | str, request: RetrievalRequest) -> RetrievalResult:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(request, RetrievalRequest):
            raise AIRetrievalInvalid("Retrieval requires a RetrievalRequest.")
        question = str(request.question or "").strip()
        if not question:
            raise AIRetrievalInvalid("A retrieval question is required.")
        policy = request.policy or self.settings.defaultPolicy()
        if not isinstance(policy, RetrievalPolicy):
            raise AIRetrievalPolicyInvalid("Retrieval policy must be a RetrievalPolicy.")
        principal = self._requirePrincipal(tenant, request.principal)
        requestId = request.requestId or newId()

        pipeline = RetrievalPipeline(policy, query=question, now=self._now)

        # 1. Candidate retrieval (vector and/or lexical).
        vectorCandidates = (
            self._vectorCandidates(tenant, request, policy, question, pipeline)
            if policy.usesVectors
            else ()
        )
        if not policy.usesVectors:
            pipeline.recordEmbedding(used=False, reason="lexical-only strategy")
        lexicalCandidates = (
            self._lexicalCandidates(tenant, request, question) if policy.usesLexical else ()
        )
        pipeline.withCandidates(vectorCandidates, lexicalCandidates)
        candidateCount = len(pipeline.candidates)
        pipeline.recordResolution(candidateCount)

        # 2. Permission filtering — before any context exists (§20).
        allowedKeys, deniedCount = self._applyPermissionFilter(
            tenant, principal, pipeline.candidates
        )
        pipeline.authorize(allowedKeys)
        authorizedCount = len(pipeline.candidates)

        # 3. Ranking, then context assembly.
        pipeline.rerank(question, reranker=self.reranker)
        prompt = pipeline.assembleContext(question=question)

        result = RetrievalResult(
            requestId=requestId,
            spaceCode=str(request.spaceCode or "").strip().upper(),
            question=question,
            prompt=prompt,
            candidates=pipeline.ranked,
            trace=pipeline.trace,
            candidateCount=candidateCount,
            authorizedCount=authorizedCount,
            deniedCount=deniedCount,
        )
        self._auditRetrieval(tenant, principal, result)
        return result

    # ------------------------------------------------------------------
    # RAG (§S.10)
    # ------------------------------------------------------------------
    def answerQuestion(self, tenantId: uuid.UUID | str, request: RagRequest) -> RagAnswer:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(request, RagRequest):
            raise AIRetrievalInvalid("Answering requires a RagRequest.")
        policy = request.policy or self.settings.defaultPolicy()
        retrieval = self.retrieve(
            tenant,
            RetrievalRequest(
                spaceCode=request.spaceCode,
                question=request.question,
                principal=request.principal,
                policy=policy,
                sourceDomain=request.sourceDomain,
                requestId=request.requestId,
                correlationId=request.correlationId,
            ),
        )
        if not retrieval.isGrounded and policy.requireGrounding:
            self._auditAnswer(tenant, request, retrieval, grounded=False)
            raise AIRagUngrounded("No authorized evidence was found for this question.")
        if self.generator is None:
            raise AIConfigurationError("No grounded generator is configured.")
        modelCode = (
            str(request.modelCode or self.settings.answerModelCode or "").strip() or "default"
        )
        prompt = retrieval.prompt
        if request.instruction:
            prompt = GroundedPrompt(
                instruction=request.instruction,
                question=prompt.question,
                contextText=prompt.contextText,
                citations=prompt.citations,
                tokenCount=prompt.tokenCount,
            )
        raw = self.generator.generate(prompt=prompt.render(), model=modelCode)
        answerText = self._extractText(raw)
        answer = RagAnswer(
            requestId=retrieval.requestId,
            question=retrieval.question,
            answer=answerText,
            citations=prompt.citations,
            modelCode=modelCode,
            retrieval=retrieval,
        )
        self._auditAnswer(tenant, request, retrieval, grounded=True)
        return answer

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _vectorCandidates(
        self,
        tenant: uuid.UUID,
        request: RetrievalRequest,
        policy: RetrievalPolicy,
        question: str,
        pipeline: RetrievalPipeline,
    ) -> tuple[RetrievalCandidate, ...]:
        from apps.ai.application.services.embeddingService import SimilaritySearchQuery

        found = self.searcher.searchSimilar(
            tenant,
            SimilaritySearchQuery(
                spaceCode=request.spaceCode,
                queryText=question,
                topK=policy.candidateLimit,
                minScore=None,
                sourceTypes=(CHUNK_SOURCE_TYPE,),
                candidateLimit=policy.candidateLimit,
            ),
        )
        matches = tuple(getattr(found, "matches", ()) or ())
        pipeline.recordEmbedding(
            used=bool(getattr(found, "usedQueryEmbedding", False)),
            reason=f"scanned={getattr(found, 'scanned', 0)}",
        )
        if not matches:
            return ()
        chunkIds = [match.sourceId for match in matches]
        resolved = {
            str(chunk.chunkId): chunk for chunk in self.resolver.resolveChunks(tenant, chunkIds)
        }
        candidates: list[RetrievalCandidate] = []
        for match in matches:
            chunk = resolved.get(str(match.sourceId))
            if chunk is None:
                continue  # purged mid-flight: degrade the set, never break
            candidates.append(
                self._toCandidate(chunk, match.metadata, vectorScore=float(match.score))
            )
        return tuple(candidates)

    def _lexicalCandidates(
        self, tenant: uuid.UUID, request: RetrievalRequest, question: str
    ) -> tuple[RetrievalCandidate, ...]:
        """Keyword pass over READY sources, bounded by the scan limit."""

        sources = self.resolver.listSources(
            tenant, statuses=("READY",), sourceDomain=request.sourceDomain or ""
        )
        candidates: list[RetrievalCandidate] = []
        scanned = 0
        for source in sources:
            for chunk in self.resolver.listChunks(tenant, source.sourceId):
                scanned += 1
                if scanned > self.settings.lexicalScanLimit:
                    break
                score = lexicalOverlap(question, chunk.text)
                if score <= 0.0:
                    continue
                candidates.append(
                    self._toCandidate(
                        chunk,
                        {"reference": source.reference},
                        lexicalScore=score,
                    )
                )
            if scanned > self.settings.lexicalScanLimit:
                break
        candidates.sort(key=lambda item: (-item.lexicalScore, item.sourceReference, item.key))
        return tuple(candidates)

    def _toCandidate(
        self,
        chunk: Any,
        metadata: dict[str, Any] | None,
        *,
        vectorScore: float = 0.0,
        lexicalScore: float = 0.0,
    ) -> RetrievalCandidate:
        payload = dict(metadata or {})
        reference = str(payload.get("reference") or "").strip()
        parts = reference.split(":") if reference else []
        sourceDomain = parts[0] if len(parts) == 3 else "CUSTOM"
        entityType = parts[1] if len(parts) == 3 else "KNOWLEDGE"
        entityId = parts[2] if len(parts) == 3 else str(chunk.sourceId)
        return RetrievalCandidate(
            chunkId=chunk.chunkId,
            sourceReference=reference or f"KNOWLEDGE:CHUNK:{chunk.chunkId}",
            text=chunk.text,
            vectorScore=vectorScore,
            lexicalScore=lexicalScore,
            classification=chunk.classification,
            ordinal=chunk.ordinal,
            tokenCount=chunk.tokenCount,
            sourceDomain=sourceDomain,
            sourceEntityType=entityType,
            sourceEntityId=entityId,
            metadata={"knowledgeSourceId": str(chunk.sourceId)},
        )

    def _applyPermissionFilter(
        self,
        tenant: uuid.UUID,
        principal: Any,
        candidates: Sequence[RetrievalCandidate],
    ) -> tuple[tuple[str, ...], int]:
        """Run the Phase 13-K filter and translate its verdict back.

        Fail-closed: with no filter wired, **nothing** is authorized. A
        retrieval path that silently skipped authorization would be exactly
        the leak §20 exists to prevent.
        """

        if not candidates:
            return ((), 0)
        if self.permissionFilter is None:
            raise AIConfigurationError(
                "Retrieval requires a permission filter; refusing to serve unfiltered context."
            )
        sources = tuple(
            ContextSourceCandidate(
                tenantId=tenant,
                sourceDomain=candidate.sourceDomain,
                sourceEntityType=candidate.sourceEntityType,
                sourceEntityId=candidate.sourceEntityId,
                content=candidate.text,
                classification=candidate.classification,
                metadata={"chunkId": candidate.key},
            )
            for candidate in candidates
        )
        verdict = self.permissionFilter.filterSources(principal, sources)
        allowedIdentities = {
            (source.sourceDomain, source.sourceEntityType, source.sourceEntityId)
            for source in getattr(verdict, "authorizedSources", ())
        }
        allowedKeys = tuple(
            candidate.key
            for candidate in candidates
            if (candidate.sourceDomain, candidate.sourceEntityType, candidate.sourceEntityId)
            in allowedIdentities
        )
        denied = len(candidates) - len(allowedKeys)
        return (allowedKeys, denied)

    def _requirePrincipal(self, tenant: uuid.UUID, principal: Any) -> Any:
        if principal is None:
            raise AIRetrievalInvalid("Retrieval requires an authenticated principal.")
        principalTenant = getattr(principal, "tenantId", None)
        if principalTenant is not None and requireUuid(principalTenant, "tenantId") != tenant:
            raise AIRetrievalInvalid("Principal belongs to another tenant.")
        return principal

    @staticmethod
    def _extractText(raw: Any) -> str:
        if isinstance(raw, str):
            return raw
        for attribute in ("content", "text", "output"):
            value = getattr(raw, attribute, None)
            if isinstance(value, str) and value:
                return value
        return str(raw)

    def _requireEnabled(self) -> None:
        if not self.settings.enabled:
            raise AIConfigurationError("The AI retrieval pipeline is disabled.")

    def _auditRetrieval(self, tenant: uuid.UUID, principal: Any, result: RetrievalResult) -> None:
        if self.auditLogger is None:
            return
        action = (
            AUDIT_RETRIEVAL_DENIED
            if result.authorizedCount == 0 and result.candidateCount > 0
            else AUDIT_RETRIEVAL_EXECUTED
        )
        self.auditLogger.logAudit(
            tenant,
            action,
            outcome="ALLOWED" if action == AUDIT_RETRIEVAL_EXECUTED else "DENIED",
            actorId=getattr(principal, "subjectId", None),
            contextSources=tuple(citation.sourceReference for citation in result.prompt.citations),
            detail={
                "spaceCode": result.spaceCode,
                "candidates": result.candidateCount,
                "authorized": result.authorizedCount,
                "denied": result.deniedCount,
                "cited": len(result.prompt.citations),
                "contextTokens": result.prompt.tokenCount,
                "trace": result.trace.summary(),
            },
        )

    def _auditAnswer(
        self,
        tenant: uuid.UUID,
        request: RagRequest,
        retrieval: RetrievalResult,
        *,
        grounded: bool,
    ) -> None:
        if self.auditLogger is None:
            return
        self.auditLogger.logAudit(
            tenant,
            AUDIT_RAG_ANSWERED,
            outcome="RECORDED" if grounded else "DENIED",
            actorId=getattr(request.principal, "subjectId", None),
            errorCode="" if grounded else "AI_RAG_UNGROUNDED",
            contextSources=tuple(
                citation.sourceReference for citation in retrieval.prompt.citations
            ),
            detail={
                "spaceCode": retrieval.spaceCode,
                "cited": len(retrieval.prompt.citations),
                "grounded": grounded,
            },
        )


__all__ = [
    "AUDIT_RAG_ANSWERED",
    "AUDIT_RETRIEVAL_DENIED",
    "AUDIT_RETRIEVAL_EXECUTED",
    "CHUNK_SOURCE_TYPE",
    "RagAnswer",
    "RagRequest",
    "RetrievalApplicationService",
    "RetrievalRequest",
    "RetrievalResult",
    "RetrievalSettings",
]
