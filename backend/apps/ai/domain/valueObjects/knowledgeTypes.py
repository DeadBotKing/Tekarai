"""Framework-free knowledge vocabularies and chunking policy for Phase 13-R.

This module owns the ingestion side of the knowledge platform:

- ``KNOWLEDGE_SOURCE_DOMAINS`` / ``KNOWLEDGE_ENTITY_KINDS`` — where a piece
  of knowledge comes from (§18: documents, projects, tasks, policies,
  meetings, messages, reports, manuals, external sources);
- ``CHUNK_STRATEGIES`` — how a text is split (§18 chunking);
- ``INDEX_ACTIONS`` — the verdict of an incremental index plan;
- ``ChunkingPolicy`` — the immutable, validated split configuration;
- ``contentChecksum`` / ``canonicalContent`` — the deterministic content
  identity used to decide whether anything actually changed.

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
Knowledge *status* keeps using the Phase 13-B ``KNOWLEDGE_STATUSES``
vocabulary; R adds no parallel lifecycle.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from apps.sharedKernel.domain.errors import ValidationFailedError

#: Owning domains allowed to publish knowledge into the AI platform (§18).
#: AI never becomes the source of truth for any of them (§37).
KNOWLEDGE_SOURCE_DOMAINS = (
    "DOCUMENTS",
    "PROJECTS",
    "TASKS",
    "POLICIES",
    "MEETINGS",
    "MESSAGES",
    "REPORTS",
    "MANUALS",
    "WORKFORCE",
    "ASSETS",
    "EXTERNAL",
    "CUSTOM",
)

#: How a source text is split into retrievable units (§18).
CHUNK_STRATEGIES = ("FIXED_TOKEN", "PARAGRAPH", "SENTENCE")

#: Verdict of an incremental index plan (§R.7).
INDEX_ACTIONS = ("CREATE", "REINDEX", "UNCHANGED", "ARCHIVE")

#: Absolute guards independent of configuration (§R.13).
MAX_CHUNK_TOKENS = 4096
MAX_CHUNKS_PER_SOURCE = 2000
MAX_CONTENT_CHARACTERS = 4_000_000

#: Sentence terminators covering Latin and Persian/Arabic punctuation.
_SENTENCE_TERMINATORS = ".!?؟۔…"
_SENTENCE_PATTERN = re.compile(
    rf"[^{re.escape(_SENTENCE_TERMINATORS)}]+[{re.escape(_SENTENCE_TERMINATORS)}]*"
)
_PARAGRAPH_PATTERN = re.compile(r"\n\s*\n+")


def ensureKnowledgeEnum(value: str, allowed: tuple[str, ...], fieldName: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise ValidationFailedError(
            "Unknown knowledge vocabulary value.", fieldErrors={fieldName: normalized}
        )
    return normalized


def ensureSourceDomain(value: str) -> str:
    return ensureKnowledgeEnum(value, KNOWLEDGE_SOURCE_DOMAINS, "sourceDomain")


def ensureChunkStrategy(value: str) -> str:
    return ensureKnowledgeEnum(value, CHUNK_STRATEGIES, "strategy")


def ensureIndexAction(value: str) -> str:
    return ensureKnowledgeEnum(value, INDEX_ACTIONS, "action")


def canonicalContent(value: str) -> str:
    """Canonical form of a source text.

    Unicode NFC, normalized line endings, trailing spaces per line removed,
    runs of blank lines collapsed to exactly one, and the edges trimmed.
    Paragraph structure survives (chunking depends on it) while cosmetic
    noise cannot produce a "changed" checksum.
    """

    if not isinstance(value, str):
        raise ValidationFailedError("Knowledge content must be a string.")
    if len(value) > MAX_CONTENT_CHARACTERS:
        raise ValidationFailedError(
            "Knowledge content exceeds the platform ceiling.",
            fieldErrors={"characters": str(len(value))},
        )
    text = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    collapsed: list[str] = []
    for line in lines:
        if not line and collapsed and not collapsed[-1]:
            continue
        collapsed.append(line)
    return "\n".join(collapsed).strip()


def contentChecksum(value: str) -> str:
    """SHA-256 of the canonical content — the change detector of R."""

    canonical = canonicalContent(value)
    if not canonical:
        raise ValidationFailedError("Knowledge content cannot be empty.")
    return hashlib.sha256(canonical.encode()).hexdigest()


def chunkChecksum(value: str) -> str:
    """SHA-256 of one chunk's text (used for incremental reuse)."""

    normalized = " ".join(unicodedata.normalize("NFC", str(value or "")).split())
    if not normalized:
        raise ValidationFailedError("Chunk text cannot be empty.")
    return hashlib.sha256(normalized.encode()).hexdigest()


def splitParagraphs(canonical: str) -> tuple[str, ...]:
    """Paragraphs of a canonical text (blank-line separated)."""

    return tuple(part.strip() for part in _PARAGRAPH_PATTERN.split(canonical) if part.strip())


def splitSentences(canonical: str) -> tuple[str, ...]:
    """Sentences of a canonical text, punctuation preserved."""

    sentences: list[str] = []
    for line in canonical.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        found = [match.group().strip() for match in _SENTENCE_PATTERN.finditer(stripped)]
        sentences.extend(part for part in found if part)
    return tuple(sentences)


@dataclass(frozen=True)
class ChunkingPolicy:
    """Immutable, validated split configuration (§R.5)."""

    strategy: str = "PARAGRAPH"
    maxTokens: int = 512
    overlapTokens: int = 64
    minTokens: int = 32

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategy", ensureChunkStrategy(self.strategy))
        for name in ("maxTokens", "overlapTokens", "minTokens"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValidationFailedError(
                    "Chunking policy values must be integers.", fieldErrors={name: str(value)}
                )
        if self.maxTokens < 1 or self.maxTokens > MAX_CHUNK_TOKENS:
            raise ValidationFailedError(
                "Chunk maxTokens is out of range.", fieldErrors={"maxTokens": str(self.maxTokens)}
            )
        if self.overlapTokens < 0 or self.overlapTokens >= self.maxTokens:
            raise ValidationFailedError(
                "Chunk overlap must be smaller than maxTokens.",
                fieldErrors={"overlapTokens": str(self.overlapTokens)},
            )
        if self.minTokens < 0 or self.minTokens > self.maxTokens:
            raise ValidationFailedError(
                "Chunk minTokens must not exceed maxTokens.",
                fieldErrors={"minTokens": str(self.minTokens)},
            )

    def signature(self) -> str:
        """Compact identity recorded on the source so a policy change is visible."""

        return f"{self.strategy}|{self.maxTokens}|{self.overlapTokens}|{self.minTokens}"


__all__ = [
    "CHUNK_STRATEGIES",
    "INDEX_ACTIONS",
    "KNOWLEDGE_SOURCE_DOMAINS",
    "MAX_CHUNKS_PER_SOURCE",
    "MAX_CHUNK_TOKENS",
    "MAX_CONTENT_CHARACTERS",
    "ChunkingPolicy",
    "canonicalContent",
    "chunkChecksum",
    "contentChecksum",
    "ensureChunkStrategy",
    "ensureIndexAction",
    "ensureKnowledgeEnum",
    "ensureSourceDomain",
    "splitParagraphs",
    "splitSentences",
]
