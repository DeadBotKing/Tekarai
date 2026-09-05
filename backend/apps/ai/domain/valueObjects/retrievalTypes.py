"""Framework-free retrieval vocabularies and scoring math for Phase 13-S.

This module owns the read side of the knowledge platform:

- ``RETRIEVAL_STRATEGIES`` — how candidates are produced (§20);
- ``RERANK_STRATEGIES`` — how the authorized set is ordered (§20 ranking);
- ``RETRIEVAL_STAGES`` — the fixed pipeline order, which is what makes the
  "permission filtering happens before context construction" rule
  structural rather than a convention (§20, §40);
- ``RetrievalPolicy`` — the immutable, validated read configuration;
- deterministic lexical helpers (``tokenize``, ``lexicalOverlap``) and
  ``reciprocalRankFusion`` for hybrid retrieval.

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
Lexical scoring is intentionally tokenizer-free and language-neutral: it
splits on non-alphanumeric boundaries so Persian, Arabic, and Latin text
behave the same, and it never depends on a model being reachable.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from apps.sharedKernel.domain.errors import ValidationFailedError

#: How the candidate set is produced before authorization.
RETRIEVAL_STRATEGIES = ("VECTOR", "LEXICAL", "HYBRID")

#: How the authorized set is ordered before context assembly.
RERANK_STRATEGIES = ("NONE", "LEXICAL_BOOST", "MMR")

#: The fixed pipeline order (§S.5). Every stage is recorded in the trace,
#: and ``CONTEXT`` can never be reached without ``AUTHORIZE``.
RETRIEVAL_STAGES = (
    "EMBED",
    "CANDIDATES",
    "RESOLVE",
    "AUTHORIZE",
    "RERANK",
    "CONTEXT",
    "ANSWER",
)

#: Absolute guards independent of configuration (§S.12).
MAX_TOP_K = 100
MAX_CANDIDATE_LIMIT = 5000
MAX_CONTEXT_TOKENS = 32_000

#: Rank-fusion constant; 60 is the value from the original RRF paper and is
#: fixed here so hybrid scores stay reproducible across deployments.
RRF_CONSTANT = 60

#: Scores are rounded before comparison so ranking is reproducible.
SCORE_PRECISION = 9

_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


def ensureRetrievalEnum(value: str, allowed: tuple[str, ...], fieldName: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise ValidationFailedError(
            "Unknown retrieval vocabulary value.", fieldErrors={fieldName: normalized}
        )
    return normalized


def ensureStrategy(value: str) -> str:
    return ensureRetrievalEnum(value, RETRIEVAL_STRATEGIES, "strategy")


def ensureRerankStrategy(value: str) -> str:
    return ensureRetrievalEnum(value, RERANK_STRATEGIES, "rerank")


def ensureStage(value: str) -> str:
    return ensureRetrievalEnum(value, RETRIEVAL_STAGES, "stage")


def tokenize(value: str) -> tuple[str, ...]:
    """Language-neutral token sequence used by every lexical score."""

    if not isinstance(value, str):
        raise ValidationFailedError("Text to tokenize must be a string.")
    normalized = unicodedata.normalize("NFC", value).casefold()
    return tuple(match.group() for match in _TOKEN_PATTERN.finditer(normalized))


def lexicalOverlap(query: str, text: str) -> float:
    """Fraction of distinct query tokens present in ``text`` — in ``[0, 1]``.

    Query coverage, not document similarity: a long document is not
    rewarded merely for being long, and an empty query scores zero rather
    than raising, so a vector-only search never fails on this path.
    """

    queryTokens = set(tokenize(query))
    if not queryTokens:
        return 0.0
    textTokens = set(tokenize(text))
    if not textTokens:
        return 0.0
    return round(len(queryTokens & textTokens) / len(queryTokens), SCORE_PRECISION)


def jaccardSimilarity(left: str, right: str) -> float:
    """Symmetric text similarity used by MMR diversity (``[0, 1]``)."""

    leftTokens = set(tokenize(left))
    rightTokens = set(tokenize(right))
    if not leftTokens or not rightTokens:
        return 0.0
    union = leftTokens | rightTokens
    return round(len(leftTokens & rightTokens) / len(union), SCORE_PRECISION)


def reciprocalRankFusion(
    rankings: Sequence[Sequence[str]], *, constant: int = RRF_CONSTANT
) -> dict[str, float]:
    """Fuse several ranked identifier lists into one score map.

    ``score(d) = Σ 1 / (constant + rank(d))`` over the lists containing
    ``d``. Rank-based fusion needs no score normalization, which matters
    because a cosine score and a lexical coverage score are not on the
    same scale.
    """

    if constant < 1:
        raise ValidationFailedError("Rank fusion constant must be positive.")
    fused: dict[str, float] = {}
    for ranking in rankings:
        for position, identifier in enumerate(ranking, start=1):
            key = str(identifier)
            fused[key] = round(fused.get(key, 0.0) + 1.0 / (constant + position), SCORE_PRECISION)
    return fused


def normalizeScores(values: Iterable[float]) -> tuple[float, ...]:
    """Min-max normalize a score series into ``[0, 1]`` (flat series → 1.0)."""

    materialized = [float(value) for value in values]
    if not materialized:
        return ()
    lowest = min(materialized)
    highest = max(materialized)
    if highest - lowest <= 0.0:
        return tuple(1.0 for _ in materialized)
    span = highest - lowest
    return tuple(round((value - lowest) / span, SCORE_PRECISION) for value in materialized)


@dataclass(frozen=True)
class RetrievalPolicy:
    """Immutable, validated read configuration (§S.4)."""

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
    dedupeBySource: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategy", ensureStrategy(self.strategy))
        object.__setattr__(self, "rerank", ensureRerankStrategy(self.rerank))
        if not isinstance(self.topK, int) or isinstance(self.topK, bool):
            raise ValidationFailedError("topK must be an integer.")
        if self.topK < 1 or self.topK > MAX_TOP_K:
            raise ValidationFailedError(
                "topK is out of range.", fieldErrors={"topK": str(self.topK)}
            )
        if self.candidateLimit < self.topK or self.candidateLimit > MAX_CANDIDATE_LIMIT:
            raise ValidationFailedError(
                "candidateLimit must be at least topK and within the platform ceiling.",
                fieldErrors={"candidateLimit": str(self.candidateLimit)},
            )
        if self.minScore is not None and not (-1.0 <= float(self.minScore) <= 1.0):
            raise ValidationFailedError("minScore must lie in [-1, 1].")
        if not 0.0 <= float(self.lexicalWeight) <= 1.0:
            raise ValidationFailedError("lexicalWeight must lie in [0, 1].")
        if not 0.0 <= float(self.mmrLambda) <= 1.0:
            raise ValidationFailedError("mmrLambda must lie in [0, 1].")
        if self.maxContextTokens < 1 or self.maxContextTokens > MAX_CONTEXT_TOKENS:
            raise ValidationFailedError("maxContextTokens is out of range.")
        if self.maxContextSources < 1:
            raise ValidationFailedError("maxContextSources must be positive.")
        for name in ("requireGrounding", "dedupeBySource"):
            if not isinstance(getattr(self, name), bool):
                raise ValidationFailedError(f"{name} must be boolean.")

    @property
    def usesVectors(self) -> bool:
        return self.strategy in ("VECTOR", "HYBRID")

    @property
    def usesLexical(self) -> bool:
        return self.strategy in ("LEXICAL", "HYBRID")

    def signature(self) -> str:
        return (
            f"{self.strategy}|{self.topK}|{self.candidateLimit}|{self.rerank}|"
            f"{self.lexicalWeight}|{self.mmrLambda}|{self.maxContextTokens}"
        )


__all__ = [
    "MAX_CANDIDATE_LIMIT",
    "MAX_CONTEXT_TOKENS",
    "MAX_TOP_K",
    "RERANK_STRATEGIES",
    "RETRIEVAL_STAGES",
    "RETRIEVAL_STRATEGIES",
    "RRF_CONSTANT",
    "SCORE_PRECISION",
    "RetrievalPolicy",
    "ensureRerankStrategy",
    "ensureRetrievalEnum",
    "ensureStage",
    "ensureStrategy",
    "jaccardSimilarity",
    "lexicalOverlap",
    "normalizeScores",
    "reciprocalRankFusion",
    "tokenize",
]
