"""Pure retrieval pipeline, reranking, and grounded prompt assembly (13-S).

The pipeline is a small explicit state machine, and that is the point: the
Master Specification (§20) requires permission filtering to happen *before*
the context is built, so ``assembleContext`` refuses to run unless the
``AUTHORIZE`` stage has been recorded. The ordering guarantee is therefore
structural — a future caller cannot "forget" to filter, they get
``AIRetrievalStageViolation`` instead of a leak.

Contents:

- ``RetrievalCandidate`` — one scored chunk reference plus its text;
- ``StageRecord`` / ``RetrievalTrace`` — the auditable stage-by-stage
  account of what entered, what survived, and why things were dropped;
- ``Reranker`` — ``NONE``, ``LEXICAL_BOOST`` and ``MMR`` strategies;
- ``RetrievalPipeline`` — the ordered stages, ending in an assembled
  context and its citations;
- ``Citation`` / ``GroundedPrompt`` — the RAG payload with numbered
  evidence, so an answer can always be traced back to its sources.

The module has no Django, HTTP, ORM, queue, network, or vendor dependency
and performs no I/O: candidates, chunk text, and authorization verdicts are
all supplied by the application layer.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.aiRecords import utcNow
from apps.ai.domain.exceptions import (
    AIRetrievalInvalid,
    AIRetrievalPolicyInvalid,
    AIRetrievalStageViolation,
)
from apps.ai.domain.services.aiRules import estimateTokens
from apps.ai.domain.valueObjects.retrievalTypes import (
    SCORE_PRECISION,
    RetrievalPolicy,
    ensureStage,
    jaccardSimilarity,
    lexicalOverlap,
    normalizeScores,
    reciprocalRankFusion,
)

#: Default instruction prepended to a grounded prompt. Kept here (not in a
#: provider adapter) so every provider receives the same grounding rule.
DEFAULT_GROUNDING_INSTRUCTION = (
    "Answer using only the numbered context blocks below. "
    "Cite the blocks you used as [1], [2] and so on. "
    "If the context does not contain the answer, say that it is not available."
)


@dataclass(frozen=True)
class RetrievalCandidate:
    """One scored chunk reference with the text needed to rank and cite it."""

    chunkId: uuid.UUID
    sourceReference: str
    text: str
    vectorScore: float = 0.0
    lexicalScore: float = 0.0
    fusedScore: float = 0.0
    finalScore: float = 0.0
    classification: str = "INTERNAL"
    ordinal: int = 0
    tokenCount: int = 0
    sourceDomain: str = "CUSTOM"
    sourceEntityType: str = "KNOWLEDGE"
    sourceEntityId: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise AIRetrievalInvalid("Retrieval candidate text is required.")
        object.__setattr__(self, "text", self.text.strip())
        object.__setattr__(self, "sourceReference", str(self.sourceReference or "").strip())
        if not self.sourceReference:
            raise AIRetrievalInvalid("Retrieval candidate needs a source reference.")
        if not self.sourceEntityId:
            object.__setattr__(self, "sourceEntityId", str(self.chunkId))
        if not self.tokenCount:
            object.__setattr__(self, "tokenCount", estimateTokens(self.text))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def scored(self, **scores: float) -> RetrievalCandidate:
        """Return a copy with updated score fields (candidates are frozen)."""

        payload = {
            "chunkId": self.chunkId,
            "sourceReference": self.sourceReference,
            "text": self.text,
            "vectorScore": self.vectorScore,
            "lexicalScore": self.lexicalScore,
            "fusedScore": self.fusedScore,
            "finalScore": self.finalScore,
            "classification": self.classification,
            "ordinal": self.ordinal,
            "tokenCount": self.tokenCount,
            "sourceDomain": self.sourceDomain,
            "sourceEntityType": self.sourceEntityType,
            "sourceEntityId": self.sourceEntityId,
            "metadata": dict(self.metadata),
        }
        payload.update({key: round(float(value), SCORE_PRECISION) for key, value in scores.items()})
        return RetrievalCandidate(**payload)  # type: ignore[arg-type]

    @property
    def key(self) -> str:
        return str(self.chunkId)


@dataclass(frozen=True)
class StageRecord:
    """What one pipeline stage received, produced, and discarded."""

    stage: str
    inputCount: int
    outputCount: int
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", ensureStage(self.stage))

    @property
    def droppedCount(self) -> int:
        return max(0, self.inputCount - self.outputCount)


@dataclass(frozen=True)
class RetrievalTrace:
    """Auditable, content-free account of one retrieval run (§S.9)."""

    query: str
    policySignature: str
    stages: tuple[StageRecord, ...] = ()
    startedAt: datetime | None = None

    def withStage(self, record: StageRecord) -> RetrievalTrace:
        return RetrievalTrace(
            query=self.query,
            policySignature=self.policySignature,
            stages=self.stages + (record,),
            startedAt=self.startedAt,
        )

    def has(self, stage: str) -> bool:
        wanted = ensureStage(stage)
        return any(record.stage == wanted for record in self.stages)

    def countFor(self, stage: str) -> int:
        wanted = ensureStage(stage)
        for record in self.stages:
            if record.stage == wanted:
                return record.outputCount
        return 0

    def summary(self) -> dict[str, Any]:
        """Compact, non-sensitive summary suitable for the audit ledger."""

        return {
            "policy": self.policySignature,
            "stages": [
                {
                    "stage": record.stage,
                    "in": record.inputCount,
                    "out": record.outputCount,
                    "dropped": record.droppedCount,
                    "reason": record.reason,
                }
                for record in self.stages
            ],
        }


@dataclass(frozen=True)
class Citation:
    """One numbered piece of evidence behind an answer."""

    index: int
    chunkId: uuid.UUID
    sourceReference: str
    ordinal: int
    score: float


@dataclass(frozen=True)
class GroundedPrompt:
    """Prompt payload plus the citations that justify it."""

    instruction: str
    question: str
    contextText: str
    citations: tuple[Citation, ...]
    tokenCount: int

    @property
    def isGrounded(self) -> bool:
        return bool(self.citations)

    def render(self) -> str:
        blocks = self.contextText or "(no authorized context)"
        return f"{self.instruction}\n\nContext:\n{blocks}\n\nQuestion: {self.question}"


class Reranker:
    """Ordering strategies applied to the *authorized* candidate set."""

    def rank(
        self,
        query: str,
        candidates: Sequence[RetrievalCandidate],
        policy: RetrievalPolicy,
    ) -> tuple[RetrievalCandidate, ...]:
        if not isinstance(policy, RetrievalPolicy):
            raise AIRetrievalPolicyInvalid("Reranking requires a RetrievalPolicy.")
        if not candidates:
            return ()
        if policy.rerank == "NONE":
            scored = tuple(
                item.scored(finalScore=item.fusedScore or item.vectorScore) for item in candidates
            )
            return self._sorted(scored)
        if policy.rerank == "LEXICAL_BOOST":
            return self._sorted(self._lexicalBoost(query, candidates, policy))
        return self._maximalMarginalRelevance(query, candidates, policy)

    # -- strategies -----------------------------------------------------
    def _lexicalBoost(
        self,
        query: str,
        candidates: Sequence[RetrievalCandidate],
        policy: RetrievalPolicy,
    ) -> tuple[RetrievalCandidate, ...]:
        """Blend the retrieval score with query-token coverage.

        Both series are min-max normalized first: a cosine score and a
        coverage ratio are not on the same scale, and blending raw values
        would let whichever happens to have the wider spread dominate.
        """

        base = normalizeScores([item.fusedScore or item.vectorScore for item in candidates])
        lexical = normalizeScores([lexicalOverlap(query, item.text) for item in candidates])
        weight = policy.lexicalWeight
        return tuple(
            item.scored(
                lexicalScore=lexicalOverlap(query, item.text),
                finalScore=(1.0 - weight) * base[index] + weight * lexical[index],
            )
            for index, item in enumerate(candidates)
        )

    def _maximalMarginalRelevance(
        self,
        query: str,
        candidates: Sequence[RetrievalCandidate],
        policy: RetrievalPolicy,
    ) -> tuple[RetrievalCandidate, ...]:
        """Greedy MMR: relevance minus redundancy against what is selected.

        Similarity between candidates is measured on their *text* (Jaccard
        over tokens) rather than on vectors: Q's vectors never leave the
        embedding store, and a text measure keeps S independent of the
        vector space geometry.
        """

        pool = list(self._lexicalBoost(query, candidates, policy))
        pool.sort(key=lambda item: (-item.finalScore, item.sourceReference, item.key))
        selected: list[RetrievalCandidate] = []
        lambdaValue = policy.mmrLambda
        while pool:
            best: RetrievalCandidate | None = None
            bestScore = float("-inf")
            for item in pool:
                redundancy = max(
                    (jaccardSimilarity(item.text, chosen.text) for chosen in selected),
                    default=0.0,
                )
                score = lambdaValue * item.finalScore - (1.0 - lambdaValue) * redundancy
                if score > bestScore:
                    best = item
                    bestScore = score
            assert best is not None
            pool.remove(best)
            selected.append(best.scored(finalScore=round(bestScore, SCORE_PRECISION)))
        return tuple(selected)

    @staticmethod
    def _sorted(candidates: Iterable[RetrievalCandidate]) -> tuple[RetrievalCandidate, ...]:
        """Deterministic ordering: score desc, then reference, then id."""

        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    -round(item.finalScore, SCORE_PRECISION),
                    item.sourceReference,
                    item.key,
                ),
            )
        )


class RetrievalPipeline:
    """Ordered, auditable retrieval run (§S.5).

    Usage is deliberately linear::

        pipeline = RetrievalPipeline(policy)
        pipeline.recordEmbedding(used=True)
        pipeline.withCandidates(vectorHits, lexicalHits)
        pipeline.authorize(allowedKeys, deniedCount)
        pipeline.rerank(query)
        result = pipeline.assembleContext()

    Any attempt to assemble before ``authorize`` raises
    ``AIRetrievalStageViolation``.
    """

    def __init__(self, policy: RetrievalPolicy, *, query: str = "", now: Any = utcNow) -> None:
        if not isinstance(policy, RetrievalPolicy):
            raise AIRetrievalPolicyInvalid("The pipeline requires a RetrievalPolicy.")
        self.policy = policy
        self.query = str(query or "")
        self._now = now
        self._candidates: tuple[RetrievalCandidate, ...] = ()
        self._ranked: tuple[RetrievalCandidate, ...] = ()
        self._authorized = False
        self.trace = RetrievalTrace(
            query=self.query, policySignature=policy.signature(), startedAt=now()
        )

    # -- stages ---------------------------------------------------------
    def recordEmbedding(self, *, used: bool, reason: str = "") -> RetrievalPipeline:
        self.trace = self.trace.withStage(
            StageRecord(
                stage="EMBED",
                inputCount=1 if used else 0,
                outputCount=1 if used else 0,
                reason=reason or ("query embedded" if used else "vector search skipped"),
            )
        )
        return self

    def withCandidates(
        self,
        vectorCandidates: Sequence[RetrievalCandidate] = (),
        lexicalCandidates: Sequence[RetrievalCandidate] = (),
    ) -> RetrievalPipeline:
        """Merge (and for ``HYBRID``, rank-fuse) the raw candidate sets."""

        merged: dict[str, RetrievalCandidate] = {}
        for item in list(vectorCandidates) + list(lexicalCandidates):
            if not isinstance(item, RetrievalCandidate):
                raise AIRetrievalInvalid("Candidates must be RetrievalCandidate values.")
            merged.setdefault(item.key, item)

        if self.policy.strategy == "HYBRID" and vectorCandidates and lexicalCandidates:
            fused = reciprocalRankFusion(
                [
                    [item.key for item in vectorCandidates],
                    [item.key for item in lexicalCandidates],
                ]
            )
            candidates = tuple(merged[key].scored(fusedScore=score) for key, score in fused.items())
        else:
            candidates = tuple(
                item.scored(fusedScore=item.vectorScore or item.lexicalScore)
                for item in merged.values()
            )

        limited = tuple(
            sorted(
                candidates,
                key=lambda item: (-item.fusedScore, item.sourceReference, item.key),
            )
        )[: self.policy.candidateLimit]
        self._candidates = limited
        self.trace = self.trace.withStage(
            StageRecord(
                stage="CANDIDATES",
                inputCount=len(vectorCandidates) + len(lexicalCandidates),
                outputCount=len(limited),
                reason=f"strategy={self.policy.strategy}",
            )
        )
        return self

    def recordResolution(self, resolvedCount: int, *, reason: str = "") -> RetrievalPipeline:
        self.trace = self.trace.withStage(
            StageRecord(
                stage="RESOLVE",
                inputCount=len(self._candidates),
                outputCount=resolvedCount,
                reason=reason or "chunk text resolved",
            )
        )
        return self

    def authorize(
        self, allowedKeys: Iterable[str], *, reason: str = "permission filter applied"
    ) -> RetrievalPipeline:
        """Keep only the candidates the permission filter allowed.

        This is the gate: nothing downstream can see a candidate that did
        not survive here, and ``assembleContext`` refuses to run at all if
        this stage was never executed.
        """

        allowed = {str(key) for key in allowedKeys}
        survivors = tuple(item for item in self._candidates if item.key in allowed)
        self.trace = self.trace.withStage(
            StageRecord(
                stage="AUTHORIZE",
                inputCount=len(self._candidates),
                outputCount=len(survivors),
                reason=reason,
            )
        )
        self._candidates = survivors
        self._ranked = survivors
        self._authorized = True
        return self

    def rerank(self, query: str = "", *, reranker: Reranker | None = None) -> RetrievalPipeline:
        self._requireAuthorized("Reranking")
        engine = reranker or Reranker()
        ranked = engine.rank(query or self.query, self._candidates, self.policy)
        if self.policy.minScore is not None:
            ranked = tuple(item for item in ranked if item.finalScore >= self.policy.minScore)
        topK = ranked[: self.policy.topK]
        self.trace = self.trace.withStage(
            StageRecord(
                stage="RERANK",
                inputCount=len(self._candidates),
                outputCount=len(topK),
                reason=f"rerank={self.policy.rerank}",
            )
        )
        self._ranked = topK
        return self

    def assembleContext(self, *, instruction: str = "", question: str = "") -> GroundedPrompt:
        """Pack the authorized, ranked evidence into a budgeted prompt."""

        self._requireAuthorized("Context assembly")
        selected: list[RetrievalCandidate] = []
        usedTokens = 0
        seenSources: set[str] = set()
        for candidate in self._ranked:
            if len(selected) >= self.policy.maxContextSources:
                break
            if self.policy.dedupeBySource and candidate.sourceReference in seenSources:
                continue
            projected = usedTokens + candidate.tokenCount
            if selected and projected > self.policy.maxContextTokens:
                continue
            selected.append(candidate)
            seenSources.add(candidate.sourceReference)
            usedTokens = projected

        citations = tuple(
            Citation(
                index=position,
                chunkId=candidate.chunkId,
                sourceReference=candidate.sourceReference,
                ordinal=candidate.ordinal,
                score=round(candidate.finalScore, SCORE_PRECISION),
            )
            for position, candidate in enumerate(selected, start=1)
        )
        blocks = "\n\n".join(
            f"[{citation.index}] ({citation.sourceReference}) {candidate.text}"
            for citation, candidate in zip(citations, selected, strict=True)
        )
        self.trace = self.trace.withStage(
            StageRecord(
                stage="CONTEXT",
                inputCount=len(self._ranked),
                outputCount=len(selected),
                reason=f"tokens={usedTokens}/{self.policy.maxContextTokens}",
            )
        )
        self._ranked = tuple(selected)
        return GroundedPrompt(
            instruction=instruction or DEFAULT_GROUNDING_INSTRUCTION,
            question=question or self.query,
            contextText=blocks,
            citations=citations,
            tokenCount=usedTokens,
        )

    def recordAnswer(self, *, grounded: bool, reason: str = "") -> RetrievalPipeline:
        self.trace = self.trace.withStage(
            StageRecord(
                stage="ANSWER",
                inputCount=len(self._ranked),
                outputCount=1 if grounded else 0,
                reason=reason or ("answer generated" if grounded else "answer refused"),
            )
        )
        return self

    # -- reads ----------------------------------------------------------
    @property
    def candidates(self) -> tuple[RetrievalCandidate, ...]:
        return self._candidates

    @property
    def ranked(self) -> tuple[RetrievalCandidate, ...]:
        return self._ranked

    @property
    def isAuthorized(self) -> bool:
        return self._authorized

    def _requireAuthorized(self, operation: str) -> None:
        if not self._authorized:
            raise AIRetrievalStageViolation(
                f"{operation} requires the permission filter to run first."
            )


__all__ = [
    "DEFAULT_GROUNDING_INSTRUCTION",
    "Citation",
    "GroundedPrompt",
    "Reranker",
    "RetrievalCandidate",
    "RetrievalPipeline",
    "RetrievalTrace",
    "StageRecord",
]
