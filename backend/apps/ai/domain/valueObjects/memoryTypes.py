"""Framework-free memory vocabularies, budget policy, and value math (13-T).

This module owns what an AI memory *is* and what its limits are:

- ``MEMORY_KINDS`` — what a remembered value represents (§17);
- ``EVICTION_STRATEGIES`` / ``RETENTION_ACTIONS`` — how a scope stays inside
  its budget and what happened to each entry when it did not;
- ``MemoryKey`` — the normalized, validated ``(scope, key)`` identity;
- ``ScopeBudget`` / ``MemoryBudget`` — the per-scope caps and time-to-live
  that close Open Question #8 from sub-phase A (memory ceiling and
  retention);
- ``canonicalValue`` / ``valueChecksum`` / ``valueSize`` — deterministic
  value identity and sizing, so an idempotent write is decidable without
  a database round trip.

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
Memory *scopes* keep using the Phase 13-B ``MEMORY_SCOPES`` vocabulary; T
adds no parallel scope list.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from apps.ai.domain.valueObjects.aiTypes import MEMORY_SCOPES, ensureEnum
from apps.sharedKernel.domain.errors import ValidationFailedError

#: What a remembered value represents (§17).
MEMORY_KINDS = (
    "FACT",
    "PREFERENCE",
    "SUMMARY",
    "DECISION",
    "ENTITY",
    "INSTRUCTION",
)

#: How a scope is trimmed when it exceeds its entry budget.
#: ``OLDEST_FIRST`` is deterministic and needs no write-on-read; ``LRU``
#: would require touching a row on every recall, which is a cost the
#: platform deliberately refuses (decision T-D4).
EVICTION_STRATEGIES = ("OLDEST_FIRST", "LOWEST_PRIORITY", "NONE")

#: What retention decided about one entry.
RETENTION_ACTIONS = ("KEEP", "EXPIRE", "EVICT")

#: Absolute guards independent of configuration (§T.11).
MAX_KEY_LENGTH = 160
MAX_VALUE_BYTES = 262_144
MAX_ENTRIES_PER_SCOPE = 10_000
MAX_TTL_SECONDS = 315_360_000  # ten years

#: Order used when several scopes contribute to one context (§T.9).
SCOPE_PRIORITY = {
    "INSTRUCTION": 0,
    "AGENT": 1,
    "TASK": 2,
    "CONVERSATION": 3,
    "SHORT_TERM": 4,
    "LONG_TERM": 5,
}

_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:\-]{0,159}$")


def ensureMemoryEnum(value: str, allowed: tuple[str, ...], fieldName: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise ValidationFailedError(
            "Unknown memory vocabulary value.", fieldErrors={fieldName: normalized}
        )
    return normalized


def ensureMemoryKind(value: str) -> str:
    return ensureMemoryEnum(value, MEMORY_KINDS, "kind")


def ensureEvictionStrategy(value: str) -> str:
    return ensureMemoryEnum(value, EVICTION_STRATEGIES, "eviction")


def ensureRetentionAction(value: str) -> str:
    return ensureMemoryEnum(value, RETENTION_ACTIONS, "action")


def ensureMemoryScope(value: str) -> str:
    return ensureEnum(value, MEMORY_SCOPES, "memoryScope")


def normalizeKey(value: str) -> str:
    """Canonical memory key: NFC, case-folded, trimmed, pattern-checked.

    Keys are addresses, not prose: a stable, predictable shape is what
    lets a caller overwrite "the user's preferred language" instead of
    accumulating near-duplicates.
    """

    if not isinstance(value, str):
        raise ValidationFailedError("Memory key must be a string.")
    normalized = unicodedata.normalize("NFC", value).strip().casefold()
    normalized = re.sub(r"\s+", "_", normalized)
    if not _KEY_PATTERN.fullmatch(normalized):
        raise ValidationFailedError(
            "Memory key must be lowercase alphanumerics with . : _ - separators.",
            fieldErrors={"key": normalized[:40]},
        )
    return normalized


def canonicalValue(value: Any) -> Any:
    """Deterministic, JSON-safe form of a remembered value.

    Mappings are key-sorted and tuples become lists, so two logically
    identical values always produce the same checksum regardless of how
    the caller built them.
    """

    if isinstance(value, dict):
        return {str(key): canonicalValue(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [canonicalValue(item) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    raise ValidationFailedError(
        "Memory values must be JSON-serializable primitives, lists, or mappings.",
        fieldErrors={"type": type(value).__name__},
    )


def serializeValue(value: Any) -> str:
    return json.dumps(
        canonicalValue(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def valueChecksum(value: Any) -> str:
    """SHA-256 of the canonical value — the idempotency key of a write."""

    return hashlib.sha256(serializeValue(value).encode()).hexdigest()


def valueSize(value: Any) -> int:
    """Byte size of the canonical value, used by the budget."""

    return len(serializeValue(value).encode())


@dataclass(frozen=True)
class MemoryKey:
    """The addressable identity of one memory slot."""

    scope: str
    key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", ensureMemoryScope(self.scope))
        object.__setattr__(self, "key", normalizeKey(self.key))

    def qualified(self) -> str:
        return f"{self.scope}:{self.key}"

    @property
    def priority(self) -> int:
        return SCOPE_PRIORITY.get(self.scope, len(SCOPE_PRIORITY))


@dataclass(frozen=True)
class ScopeBudget:
    """Ceiling and time-to-live for one memory scope (Open Question #8)."""

    maxEntries: int = 200
    ttlSeconds: int = 0  # 0 means "no expiry"
    maxValueBytes: int = 32_768
    eviction: str = "OLDEST_FIRST"

    def __post_init__(self) -> None:
        object.__setattr__(self, "eviction", ensureEvictionStrategy(self.eviction))
        for name in ("maxEntries", "ttlSeconds", "maxValueBytes"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValidationFailedError(
                    "Memory budget values must be integers.", fieldErrors={name: str(value)}
                )
        if self.maxEntries < 1 or self.maxEntries > MAX_ENTRIES_PER_SCOPE:
            raise ValidationFailedError(
                "Scope maxEntries is out of range.",
                fieldErrors={"maxEntries": str(self.maxEntries)},
            )
        if self.ttlSeconds < 0 or self.ttlSeconds > MAX_TTL_SECONDS:
            raise ValidationFailedError("Scope ttlSeconds is out of range.")
        if self.maxValueBytes < 1 or self.maxValueBytes > MAX_VALUE_BYTES:
            raise ValidationFailedError("Scope maxValueBytes is out of range.")

    @property
    def expires(self) -> bool:
        return self.ttlSeconds > 0


@dataclass(frozen=True)
class MemoryBudget:
    """Per-scope budgets with a documented default for every scope.

    Short-lived scopes expire quickly and hold few entries; long-term
    memory keeps more for longer. Nothing is unbounded by default, which
    is the point of closing Open Question #8.
    """

    scopes: dict[str, ScopeBudget] = field(default_factory=dict)
    default: ScopeBudget = field(default_factory=ScopeBudget)

    def __post_init__(self) -> None:
        normalized: dict[str, ScopeBudget] = {}
        for scope, budget in (self.scopes or {}).items():
            if not isinstance(budget, ScopeBudget):
                raise ValidationFailedError("Memory budget values must be ScopeBudget objects.")
            normalized[ensureMemoryScope(scope)] = budget
        object.__setattr__(self, "scopes", normalized)
        if not isinstance(self.default, ScopeBudget):
            raise ValidationFailedError("Default memory budget must be a ScopeBudget.")

    def forScope(self, scope: str) -> ScopeBudget:
        return self.scopes.get(ensureMemoryScope(scope), self.default)

    @classmethod
    def platformDefault(cls) -> MemoryBudget:
        """The shipped defaults; configuration may narrow them (§T.11)."""

        return cls(
            scopes={
                "SHORT_TERM": ScopeBudget(maxEntries=50, ttlSeconds=86_400, maxValueBytes=8_192),
                "CONVERSATION": ScopeBudget(
                    maxEntries=100, ttlSeconds=2_592_000, maxValueBytes=16_384
                ),
                "TASK": ScopeBudget(maxEntries=200, ttlSeconds=7_776_000, maxValueBytes=16_384),
                "AGENT": ScopeBudget(maxEntries=200, ttlSeconds=7_776_000, maxValueBytes=32_768),
                "LONG_TERM": ScopeBudget(maxEntries=500, ttlSeconds=0, maxValueBytes=32_768),
            },
            default=ScopeBudget(),
        )


__all__ = [
    "EVICTION_STRATEGIES",
    "MAX_ENTRIES_PER_SCOPE",
    "MAX_KEY_LENGTH",
    "MAX_TTL_SECONDS",
    "MAX_VALUE_BYTES",
    "MEMORY_KINDS",
    "RETENTION_ACTIONS",
    "SCOPE_PRIORITY",
    "MemoryBudget",
    "MemoryKey",
    "ScopeBudget",
    "canonicalValue",
    "ensureEvictionStrategy",
    "ensureMemoryEnum",
    "ensureMemoryKind",
    "ensureMemoryScope",
    "ensureRetentionAction",
    "normalizeKey",
    "serializeValue",
    "valueChecksum",
    "valueSize",
]
