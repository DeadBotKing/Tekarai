"""Pure chunking and incremental index planning for Phase 13-R.

Two deterministic services, both fully offline:

- ``ChunkingService`` — turns a canonical text into ordered ``ChunkDraft``
  values under a ``ChunkingPolicy``. Word-granular packing keeps the split
  reproducible without a tokenizer: the same text and policy always yield
  byte-identical chunks (and therefore identical checksums), which is what
  makes incremental reindexing possible at all;
- ``IndexPlanner`` — compares a freshly chunked text against what is
  already stored and returns an ``IndexPlan``: unchanged chunks to reuse
  (their vectors stay valid), chunks to add, chunks to remove, and the
  action verdict (``CREATE`` / ``REINDEX`` / ``UNCHANGED``).

Reuse is keyed on the chunk checksum, not on the ordinal: inserting a
paragraph at the top of a document must not force re-embedding of every
chunk below it (§R.7, decision R-D3).

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from apps.ai.domain.entities.knowledgeRecords import (
    AIKnowledgeChunkRecord,
    AIKnowledgeSourceRecord,
)
from apps.ai.domain.exceptions import AIKnowledgeChunkInvalid, AIKnowledgeSourceInvalid
from apps.ai.domain.services.aiRules import estimateTokens
from apps.ai.domain.valueObjects.knowledgeTypes import (
    MAX_CHUNKS_PER_SOURCE,
    ChunkingPolicy,
    canonicalContent,
    chunkChecksum,
    contentChecksum,
    ensureIndexAction,
    splitParagraphs,
    splitSentences,
)


@dataclass(frozen=True)
class ChunkDraft:
    """One prospective chunk before it becomes a persisted record."""

    ordinal: int
    text: str
    checksum: str
    tokenCount: int
    startOffset: int
    endOffset: int

    def withOrdinal(self, ordinal: int) -> ChunkDraft:
        return ChunkDraft(
            ordinal=ordinal,
            text=self.text,
            checksum=self.checksum,
            tokenCount=self.tokenCount,
            startOffset=self.startOffset,
            endOffset=self.endOffset,
        )


@dataclass(frozen=True)
class WordSpan:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class ChunkingResult:
    """Everything the application layer needs after a split."""

    policy: ChunkingPolicy
    canonical: str
    checksum: str
    chunks: tuple[ChunkDraft, ...]

    @property
    def tokenCount(self) -> int:
        return sum(chunk.tokenCount for chunk in self.chunks)

    @property
    def checksums(self) -> tuple[str, ...]:
        return tuple(chunk.checksum for chunk in self.chunks)


class ChunkingService:
    """Deterministic text splitter (§R.5)."""

    def __init__(self, policy: ChunkingPolicy | None = None) -> None:
        self.policy = policy or ChunkingPolicy()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def split(self, content: str, *, policy: ChunkingPolicy | None = None) -> ChunkingResult:
        chosen = policy or self.policy
        if not isinstance(chosen, ChunkingPolicy):
            raise AIKnowledgeChunkInvalid("Chunking requires a ChunkingPolicy.")
        canonical = canonicalContent(content)
        if not canonical:
            raise AIKnowledgeChunkInvalid("Knowledge content cannot be empty.")
        checksum = contentChecksum(canonical)

        if chosen.strategy == "FIXED_TOKEN":
            segments: tuple[str, ...] = (canonical,)
        elif chosen.strategy == "PARAGRAPH":
            segments = splitParagraphs(canonical)
        else:
            segments = splitSentences(canonical)
        if not segments:
            segments = (canonical,)

        drafts = self._packSegments(canonical, segments, chosen)
        drafts = self._rebalanceShortTail(drafts, chosen)
        if len(drafts) > MAX_CHUNKS_PER_SOURCE:
            raise AIKnowledgeChunkInvalid(
                "Chunking produced more chunks than the platform ceiling allows."
            )
        return ChunkingResult(
            policy=chosen,
            canonical=canonical,
            checksum=checksum,
            chunks=tuple(draft.withOrdinal(index) for index, draft in enumerate(drafts)),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _words(self, canonical: str, segment: str, cursor: int) -> tuple[tuple[WordSpan, ...], int]:
        """Locate a segment's words with exact offsets into the canonical text."""

        start = canonical.find(segment, cursor)
        if start < 0:  # pragma: no cover - segments always come from canonical
            start = cursor
        words: list[WordSpan] = []
        offset = start
        for token in segment.split():
            found = canonical.find(token, offset)
            if found < 0:  # pragma: no cover - defensive
                found = offset
            words.append(WordSpan(text=token, start=found, end=found + len(token)))
            offset = found + len(token)
        return tuple(words), start + len(segment)

    def _packSegments(
        self, canonical: str, segments: Sequence[str], policy: ChunkingPolicy
    ) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        pending: list[WordSpan] = []
        cursor = 0
        for segment in segments:
            words, cursor = self._words(canonical, segment, cursor)
            if not words:
                continue
            if estimateTokens(segment) > policy.maxTokens:
                # An oversized paragraph/sentence is split by the fixed-token
                # rule rather than silently exceeding the budget.
                if pending:
                    drafts.extend(self._emit(pending, policy, carryOverlap=False))
                    pending = []
                drafts.extend(self._emit(list(words), policy, carryOverlap=True))
                continue
            candidate = pending + list(words)
            if pending and estimateTokens(self._join(candidate)) > policy.maxTokens:
                drafts.extend(self._emit(pending, policy, carryOverlap=False))
                pending = list(words)
            else:
                pending = candidate
        if pending:
            drafts.extend(self._emit(pending, policy, carryOverlap=False))
        return drafts

    def _emit(
        self, words: list[WordSpan], policy: ChunkingPolicy, *, carryOverlap: bool
    ) -> list[ChunkDraft]:
        """Emit one or more chunks from a word run, honouring the budget."""

        drafts: list[ChunkDraft] = []
        index = 0
        while index < len(words):
            window: list[WordSpan] = []
            while index < len(words):
                nextWindow = window + [words[index]]
                if window and estimateTokens(self._join(nextWindow)) > policy.maxTokens:
                    break
                window = nextWindow
                index += 1
            drafts.append(self._draft(window))
            if index >= len(words):
                break
            if carryOverlap and policy.overlapTokens:
                index = max(index - self._overlapWordCount(window, policy), index - len(window) + 1)
        return drafts

    @staticmethod
    def _overlapWordCount(window: Sequence[WordSpan], policy: ChunkingPolicy) -> int:
        """How many trailing words to repeat so the overlap budget is met."""

        count = 0
        tail: list[str] = []
        for word in reversed(window):
            tail.insert(0, word.text)
            if estimateTokens(" ".join(tail)) > policy.overlapTokens:
                break
            count += 1
        return min(count, max(0, len(window) - 1))

    @staticmethod
    def _join(words: Iterable[WordSpan]) -> str:
        return " ".join(word.text for word in words)

    def _draft(self, window: Sequence[WordSpan]) -> ChunkDraft:
        text = self._join(window)
        return ChunkDraft(
            ordinal=0,
            text=text,
            checksum=chunkChecksum(text),
            tokenCount=estimateTokens(text),
            startOffset=window[0].start,
            endOffset=window[-1].end,
        )

    def _rebalanceShortTail(
        self, drafts: list[ChunkDraft], policy: ChunkingPolicy
    ) -> list[ChunkDraft]:
        """Repair a final fragment that is shorter than ``minTokens``.

        A budget-forced split can leave a three-word orphan at the end,
        which is useless to retrieve. Rather than merging it back (the
        merged chunk would exceed the budget that caused the split in the
        first place), trailing words are moved from the predecessor into
        the tail until both sides clear ``minTokens``.

        The rebalance is skipped when it cannot succeed — when the
        predecessor would itself fall below ``minTokens`` — so a tiny
        source is never mangled and no text is ever dropped.
        """

        if len(drafts) < 2 or policy.minTokens <= 0:
            return drafts
        previous, tail = drafts[-2], drafts[-1]
        if tail.tokenCount >= policy.minTokens:
            return drafts

        previousWords = previous.text.split()
        tailWords = tail.text.split()
        moved = 0
        while moved < len(previousWords) - 1:
            candidateTail = previousWords[len(previousWords) - moved - 1 :] + tailWords
            candidatePrevious = previousWords[: len(previousWords) - moved - 1]
            if estimateTokens(" ".join(candidatePrevious)) < policy.minTokens:
                return drafts
            moved += 1
            if estimateTokens(" ".join(candidateTail)) >= policy.minTokens:
                break
        else:
            return drafts

        splitAt = len(previousWords) - moved
        newPreviousText = " ".join(previousWords[:splitAt])
        newTailText = " ".join(previousWords[splitAt:] + tailWords)
        if estimateTokens(newTailText) > policy.maxTokens:
            return drafts
        movedChars = len(" ".join(previousWords[splitAt:])) + 1
        drafts[-2] = ChunkDraft(
            ordinal=previous.ordinal,
            text=newPreviousText,
            checksum=chunkChecksum(newPreviousText),
            tokenCount=estimateTokens(newPreviousText),
            startOffset=previous.startOffset,
            endOffset=max(previous.startOffset, previous.endOffset - movedChars),
        )
        drafts[-1] = ChunkDraft(
            ordinal=tail.ordinal,
            text=newTailText,
            checksum=chunkChecksum(newTailText),
            tokenCount=estimateTokens(newTailText),
            startOffset=max(previous.startOffset, previous.endOffset - movedChars + 1),
            endOffset=tail.endOffset,
        )
        return drafts


@dataclass(frozen=True)
class IndexPlan:
    """Verdict of comparing fresh chunks against the stored index (§R.7)."""

    action: str
    checksum: str
    added: tuple[ChunkDraft, ...] = ()
    reused: tuple[tuple[AIKnowledgeChunkRecord, int], ...] = ()
    removed: tuple[AIKnowledgeChunkRecord, ...] = ()
    reason: str = ""
    totalChunks: int = 0
    totalTokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", ensureIndexAction(self.action))

    @property
    def isNoop(self) -> bool:
        return self.action == "UNCHANGED"

    @property
    def addedCount(self) -> int:
        return len(self.added)

    @property
    def reusedCount(self) -> int:
        return len(self.reused)

    @property
    def removedCount(self) -> int:
        return len(self.removed)


class IndexPlanner:
    """Decides the minimum work an ingestion must perform."""

    def plan(
        self,
        source: AIKnowledgeSourceRecord | None,
        result: ChunkingResult,
        existingChunks: Sequence[AIKnowledgeChunkRecord] = (),
        *,
        force: bool = False,
    ) -> IndexPlan:
        if not isinstance(result, ChunkingResult):
            raise AIKnowledgeSourceInvalid("Planning requires a ChunkingResult.")
        totalTokens = result.tokenCount
        if source is None:
            return IndexPlan(
                action="CREATE",
                checksum=result.checksum,
                added=result.chunks,
                reason="No prior index exists for this source.",
                totalChunks=len(result.chunks),
                totalTokens=totalTokens,
            )
        source.requireIngestable()

        contentUnchanged = not source.hasContentChanged(result.checksum)
        policyUnchanged = source.matchesPolicy(result.policy)
        chunkCountMatches = len(existingChunks) == len(result.chunks)
        if (
            contentUnchanged
            and policyUnchanged
            and chunkCountMatches
            and source.status == "READY"
            and not force
        ):
            return IndexPlan(
                action="UNCHANGED",
                checksum=result.checksum,
                reason="Checksum, policy, and chunk count are identical.",
                totalChunks=len(existingChunks),
                totalTokens=source.tokenCount,
            )

        byChecksum: dict[str, list[AIKnowledgeChunkRecord]] = {}
        for chunk in existingChunks:
            byChecksum.setdefault(chunk.checksum, []).append(chunk)

        added: list[ChunkDraft] = []
        reused: list[tuple[AIKnowledgeChunkRecord, int]] = []
        consumed: set[uuid.UUID] = set()
        for draft in result.chunks:
            candidates = byChecksum.get(draft.checksum) or []
            match = next((item for item in candidates if item.id not in consumed), None)
            if match is None:
                added.append(draft)
                continue
            consumed.add(match.id)
            reused.append((match, draft.ordinal))
        removed = tuple(chunk for chunk in existingChunks if chunk.id not in consumed)

        if force:
            reason = "Reindex forced by the caller."
        elif not contentUnchanged:
            reason = "Source content checksum changed."
        elif not policyUnchanged:
            reason = "Chunking policy changed."
        elif not chunkCountMatches:
            reason = "Stored chunk count does not match the fresh split."
        else:
            reason = f"Source status is {source.status}."
        return IndexPlan(
            action="REINDEX",
            checksum=result.checksum,
            added=tuple(added),
            reused=tuple(reused),
            removed=removed,
            reason=reason,
            totalChunks=len(result.chunks),
            totalTokens=totalTokens,
        )


def buildChunkRecords(
    tenantId: uuid.UUID,
    sourceId: uuid.UUID,
    drafts: Iterable[ChunkDraft],
    *,
    classification: str = "INTERNAL",
    metadata: dict[str, Any] | None = None,
    createdAt: Any = None,
) -> tuple[AIKnowledgeChunkRecord, ...]:
    """Turn drafts into persistable chunk records."""

    baseMetadata = dict(metadata or {})
    records: list[AIKnowledgeChunkRecord] = []
    for draft in drafts:
        record = AIKnowledgeChunkRecord(
            tenantId=tenantId,
            sourceId=sourceId,
            ordinal=draft.ordinal,
            text=draft.text,
            checksum=draft.checksum,
            tokenCount=draft.tokenCount,
            startOffset=draft.startOffset,
            endOffset=draft.endOffset,
            classification=classification,
            metadata=dict(baseMetadata),
        )
        if createdAt is not None:
            record.createdAt = createdAt
        records.append(record)
    return tuple(records)


__all__ = [
    "ChunkDraft",
    "ChunkingResult",
    "ChunkingService",
    "IndexPlan",
    "IndexPlanner",
    "buildChunkRecords",
]
