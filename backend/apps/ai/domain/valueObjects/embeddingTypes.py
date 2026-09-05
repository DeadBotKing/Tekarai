"""Framework-free embedding vocabularies and vector math for Phase 13-Q.

This module owns the *vector space* concept and the deterministic math the
embedding foundation needs:

- ``EMBEDDING_SOURCE_TYPES`` — what an embedding may describe;
- ``DISTANCE_METRICS`` — how two vectors are compared (§Q.6);
- ``NORMALIZATION_MODES`` — whether stored vectors are unit length;
- ``VectorSpace`` — the immutable identity of a comparable vector set
  (model + dimensions + metric + normalization). Two embeddings may only
  be compared when their spaces are identical (§Q.5, the central
  invariant of Q);
- pure vector helpers (``l2Norm``, ``normalizeVector``, similarity and
  distance functions, ``similarityFor``);
- ``contentFingerprint`` — the SHA-256 cache/idempotency key of a text.

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
Floats are validated for finiteness at the boundary so a provider can never
poison the store with ``nan``/``inf``.
"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from apps.ai.domain.valueObjects.aiTypes import validateCode
from apps.sharedKernel.domain.errors import ValidationFailedError

#: What the embedded text belongs to. ``QUERY`` is the transient search
#: side of the pipeline (never persisted by default); the rest are durable
#: sources owned by their domains — AI stores only the reference (§Q.3).
EMBEDDING_SOURCE_TYPES = (
    "KNOWLEDGE_CHUNK",
    "KNOWLEDGE_ITEM",
    "DOCUMENT",
    "MESSAGE",
    "TASK",
    "PROJECT",
    "MEMORY",
    "QUERY",
    "CUSTOM",
)

#: Comparison functions supported by the foundation (§Q.6).
DISTANCE_METRICS = ("COSINE", "DOT_PRODUCT", "EUCLIDEAN")

#: Whether vectors are stored unit-length. ``L2`` makes ``COSINE`` and
#: ``DOT_PRODUCT`` agree and keeps scores stable across providers.
NORMALIZATION_MODES = ("NONE", "L2")

#: Hard ceilings that protect the store from absurd input regardless of
#: configuration. Configuration may lower them, never raise them (§Q.13).
MAX_VECTOR_DIMENSIONS = 8192
MAX_BATCH_SIZE = 512

#: Scores are rounded before comparison so ranking is reproducible across
#: platforms and float error cannot reorder equal candidates (§Q.7).
SCORE_PRECISION = 9


def ensureEmbeddingEnum(value: str, allowed: tuple[str, ...], fieldName: str) -> str:
    """Normalize and validate a closed-vocabulary value."""

    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise ValidationFailedError(
            "Unknown embedding vocabulary value.", fieldErrors={fieldName: normalized}
        )
    return normalized


def ensureSourceType(value: str) -> str:
    return ensureEmbeddingEnum(value, EMBEDDING_SOURCE_TYPES, "sourceType")


def ensureMetric(value: str) -> str:
    return ensureEmbeddingEnum(value, DISTANCE_METRICS, "metric")


def ensureNormalization(value: str) -> str:
    return ensureEmbeddingEnum(value, NORMALIZATION_MODES, "normalization")


def ensureDimensions(value: int) -> int:
    """Reject non-positive or oversized dimensionality."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationFailedError(
            "Vector dimensions must be an integer.", fieldErrors={"dimensions": str(value)}
        )
    if value < 1 or value > MAX_VECTOR_DIMENSIONS:
        raise ValidationFailedError(
            "Vector dimensions are out of range.", fieldErrors={"dimensions": str(value)}
        )
    return value


def normalizeText(value: str) -> str:
    """Canonical text form used for fingerprints and token estimates.

    Unicode NFC + trimmed edges + collapsed internal whitespace, so the
    same logical text always produces the same cache key regardless of how
    a caller formatted it.
    """

    if not isinstance(value, str):
        raise ValidationFailedError("Embedding text must be a string.")
    return " ".join(unicodedata.normalize("NFC", value).split())


def contentFingerprint(text: str, space: VectorSpace | None = None) -> str:
    """Stable SHA-256 cache key for a text inside one vector space.

    The space code and dimensions are part of the digest: the same text
    embedded by a different model must never hit the same cache row.
    """

    canonical = normalizeText(text)
    if not canonical:
        raise ValidationFailedError("Embedding text cannot be empty.")
    prefix = "" if space is None else f"{space.code}:{space.dimensions}:"
    return hashlib.sha256(f"{prefix}{canonical}".encode()).hexdigest()


def validateVector(vector: Iterable[float], *, dimensions: int | None = None) -> tuple[float, ...]:
    """Coerce an iterable to a finite float tuple with an optional arity check."""

    try:
        values = tuple(float(item) for item in vector)
    except (TypeError, ValueError) as error:
        raise ValidationFailedError("Embedding vector must contain numbers only.") from error
    if not values:
        raise ValidationFailedError("Embedding vector cannot be empty.")
    if len(values) > MAX_VECTOR_DIMENSIONS:
        raise ValidationFailedError(
            "Embedding vector exceeds the maximum dimensionality.",
            fieldErrors={"dimensions": str(len(values))},
        )
    if any(not math.isfinite(item) for item in values):
        raise ValidationFailedError("Embedding vector contains a non-finite value.")
    if dimensions is not None and len(values) != dimensions:
        raise ValidationFailedError(
            "Embedding vector dimensionality does not match the vector space.",
            fieldErrors={"expected": str(dimensions), "actual": str(len(values))},
        )
    return values


def l2Norm(vector: Sequence[float]) -> float:
    """Euclidean length of a vector."""

    return math.sqrt(math.fsum(item * item for item in vector))


def normalizeVector(vector: Sequence[float]) -> tuple[float, ...]:
    """Return the unit-length form of ``vector``.

    A zero vector carries no direction and cannot be normalized; rejecting
    it here keeps ``COSINE`` total instead of returning a silent ``0.0``.
    """

    norm = l2Norm(vector)
    if norm <= 0.0:
        raise ValidationFailedError("A zero vector cannot be normalized.")
    return tuple(item / norm for item in vector)


def isUnitVector(vector: Sequence[float], *, tolerance: float = 1e-6) -> bool:
    return abs(l2Norm(vector) - 1.0) <= tolerance


def _assertComparable(left: Sequence[float], right: Sequence[float]) -> None:
    if len(left) != len(right):
        raise ValidationFailedError(
            "Vectors of different dimensionality cannot be compared.",
            fieldErrors={"left": str(len(left)), "right": str(len(right))},
        )
    if not left:
        raise ValidationFailedError("Vectors cannot be empty.")


def dotProduct(left: Sequence[float], right: Sequence[float]) -> float:
    _assertComparable(left, right)
    return math.fsum(a * b for a, b in zip(left, right, strict=True))


def cosineSimilarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity clamped to ``[-1.0, 1.0]``."""

    _assertComparable(left, right)
    leftNorm = l2Norm(left)
    rightNorm = l2Norm(right)
    if leftNorm <= 0.0 or rightNorm <= 0.0:
        raise ValidationFailedError("Cosine similarity is undefined for a zero vector.")
    raw = dotProduct(left, right) / (leftNorm * rightNorm)
    return max(-1.0, min(1.0, raw))


def euclideanDistance(left: Sequence[float], right: Sequence[float]) -> float:
    _assertComparable(left, right)
    return math.sqrt(math.fsum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def similarityFor(metric: str, left: Sequence[float], right: Sequence[float]) -> float:
    """Metric-aware score where **higher always means more similar**.

    ``EUCLIDEAN`` is a distance, so it is converted to ``1 / (1 + d)`` —
    a monotonically decreasing transform that keeps ranking identical to
    the raw distance while making every metric comparable in one API.
    """

    chosen = ensureMetric(metric)
    if chosen == "COSINE":
        score = cosineSimilarity(left, right)
    elif chosen == "DOT_PRODUCT":
        score = dotProduct(left, right)
    else:
        score = 1.0 / (1.0 + euclideanDistance(left, right))
    return round(score, SCORE_PRECISION)


@dataclass(frozen=True)
class VectorSpace:
    """Immutable identity of a set of mutually comparable vectors (§Q.5).

    Two embeddings belong to the same space only when the model code,
    model version, dimensionality, metric, and normalization all match.
    Comparing across spaces is a domain error, never a silent cast.
    """

    code: str
    modelCode: str
    dimensions: int
    metric: str = "COSINE"
    normalization: str = "L2"
    modelVersion: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", validateCode(self.code, "spaceCode"))
        object.__setattr__(self, "modelCode", validateCode(self.modelCode, "modelCode"))
        object.__setattr__(self, "dimensions", ensureDimensions(self.dimensions))
        object.__setattr__(self, "metric", ensureMetric(self.metric))
        object.__setattr__(self, "normalization", ensureNormalization(self.normalization))
        object.__setattr__(self, "modelVersion", str(self.modelVersion or "").strip())

    @property
    def isNormalized(self) -> bool:
        return self.normalization == "L2"

    def signature(self) -> str:
        """Compact comparable identity used in payloads and audit detail."""

        version = self.modelVersion or "-"
        return f"{self.code}|{self.modelCode}|{version}|{self.dimensions}|{self.metric}|{self.normalization}"

    def matches(self, other: VectorSpace) -> bool:
        return isinstance(other, VectorSpace) and self.signature() == other.signature()

    def prepare(self, vector: Iterable[float]) -> tuple[float, ...]:
        """Validate arity and apply the space's normalization policy."""

        values = validateVector(vector, dimensions=self.dimensions)
        return normalizeVector(values) if self.isNormalized else values

    def score(self, left: Sequence[float], right: Sequence[float]) -> float:
        return similarityFor(self.metric, left, right)


__all__ = [
    "DISTANCE_METRICS",
    "EMBEDDING_SOURCE_TYPES",
    "MAX_BATCH_SIZE",
    "MAX_VECTOR_DIMENSIONS",
    "NORMALIZATION_MODES",
    "SCORE_PRECISION",
    "VectorSpace",
    "contentFingerprint",
    "cosineSimilarity",
    "dotProduct",
    "ensureDimensions",
    "ensureEmbeddingEnum",
    "ensureMetric",
    "ensureNormalization",
    "ensureSourceType",
    "euclideanDistance",
    "isUnitVector",
    "l2Norm",
    "normalizeText",
    "normalizeVector",
    "similarityFor",
    "validateVector",
]
