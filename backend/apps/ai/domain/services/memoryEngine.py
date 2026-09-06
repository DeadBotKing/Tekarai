"""Pure memory coordination for Phase 13-T.

Three deterministic services, all offline:

- ``MemoryWriter`` — decides what a write means. Writing the same value
  again is a no-op (``UNCHANGED``); a different value produces the next
  immutable version and supersedes its predecessor;
- ``RetentionEvaluator`` — applies a ``ScopeBudget`` to a scope: expiring
  entries whose time-to-live passed, then evicting the overflow according
  to the scope's strategy. Every decision is returned as an explicit
  ``RetentionDecision`` so the caller (and the audit ledger) can see why
  an entry disappeared;
- ``MemorySelector`` — chooses which memories may enter a prompt, in a
  stable order and under a token budget.

The module performs no I/O and has no Django, HTTP, ORM, queue, network,
or vendor dependency: entries are handed in by the application layer.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.aiRecords import utcNow
from apps.ai.domain.entities.memoryRecords import AIMemoryEntry
from apps.ai.domain.exceptions import (
    AIMemoryBudgetExceeded,
    AIMemoryInvalid,
    AIMemoryPolicyInvalid,
    AIMemoryValueTooLarge,
)
from apps.ai.domain.services.aiRules import estimateTokens
from apps.ai.domain.valueObjects.memoryTypes import (
    MemoryBudget,
    MemoryKey,
    ScopeBudget,
    ensureMemoryScope,
    ensureRetentionAction,
    valueChecksum,
    valueSize,
)

#: Verdicts a write can produce.
WRITE_ACTIONS = ("CREATED", "VERSIONED", "UNCHANGED")


@dataclass(frozen=True)
class WritePlan:
    """What a remember() call should actually do (§T.5)."""

    action: str
    entry: AIMemoryEntry
    superseded: AIMemoryEntry | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.action not in WRITE_ACTIONS:
            raise AIMemoryInvalid("Unknown memory write action.")

    @property
    def isNoop(self) -> bool:
        return self.action == "UNCHANGED"


@dataclass(frozen=True)
class RetentionDecision:
    """Why one entry was kept, expired, or evicted."""

    entry: AIMemoryEntry
    action: str
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", ensureRetentionAction(self.action))


@dataclass(frozen=True)
class RetentionPlan:
    """The full verdict for one scope."""

    scope: str
    decisions: tuple[RetentionDecision, ...] = ()
    budget: ScopeBudget | None = None

    @property
    def expired(self) -> tuple[AIMemoryEntry, ...]:
        return tuple(item.entry for item in self.decisions if item.action == "EXPIRE")

    @property
    def evicted(self) -> tuple[AIMemoryEntry, ...]:
        return tuple(item.entry for item in self.decisions if item.action == "EVICT")

    @property
    def kept(self) -> tuple[AIMemoryEntry, ...]:
        return tuple(item.entry for item in self.decisions if item.action == "KEEP")

    @property
    def removedCount(self) -> int:
        return len(self.expired) + len(self.evicted)


@dataclass(frozen=True)
class MemorySelection:
    """Memories chosen for a prompt, with the accounting behind the cut."""

    entries: tuple[AIMemoryEntry, ...] = ()
    tokenCount: int = 0
    consideredCount: int = 0
    droppedCount: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryWriter:
    """Versioning rules for remembering a value (§T.5)."""

    def __init__(self, *, now: Any = utcNow) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self._now = now

    def plan(
        self,
        tenantId: Any,
        memoryKey: MemoryKey,
        value: Any,
        *,
        latest: AIMemoryEntry | None = None,
        budget: ScopeBudget | None = None,
        kind: str = "FACT",
        userId: Any = None,
        conversationId: str = "",
        classification: str = "INTERNAL",
        expiresAt: datetime | None = None,
        sourceReference: str = "",
        metadata: dict[str, Any] | None = None,
        force: bool = False,
    ) -> WritePlan:
        if not isinstance(memoryKey, MemoryKey):
            raise AIMemoryInvalid("Writing requires a MemoryKey.")
        scopeBudget = budget or ScopeBudget()
        if not isinstance(scopeBudget, ScopeBudget):
            raise AIMemoryPolicyInvalid("Writing requires a ScopeBudget.")
        size = valueSize(value)
        if size > scopeBudget.maxValueBytes:
            raise AIMemoryValueTooLarge("Memory value exceeds the scope byte ceiling.")
        moment = self._now()

        if latest is not None and latest.isUsableAt(moment):
            if (
                not force
                and latest.hasSameValueAs(value)
                and latest.classification == (classification or latest.classification)
            ):
                return WritePlan(
                    action="UNCHANGED",
                    entry=latest,
                    reason="Identical value already remembered.",
                )
            successor = latest.nextVersion(
                value,
                now=moment,
                kind=kind,
                classification=classification,
                expiresAt=expiresAt,
                sourceReference=sourceReference,
                metadata=metadata,
            )
            successor.withExpiry(scopeBudget, now=moment)
            return WritePlan(
                action="VERSIONED",
                entry=successor,
                superseded=latest,
                reason="Value changed." if not force else "Write forced by the caller.",
            )

        created = AIMemoryEntry(
            tenantId=tenantId,
            memoryKey=memoryKey,
            value=value,
            kind=kind,
            userId=userId,
            conversationId=conversationId,
            classification=classification,
            version=1 if latest is None else latest.version + 1,
            expiresAt=expiresAt,
            sourceReference=sourceReference,
            metadata=dict(metadata or {}),
            createdAt=moment,
        )
        created.withExpiry(scopeBudget, now=moment)
        reason = (
            "No prior memory for this key."
            if latest is None
            else "Previous version was expired or inactive."
        )
        return WritePlan(action="CREATED", entry=created, reason=reason)

    @staticmethod
    def checksumFor(value: Any) -> str:
        return valueChecksum(value)


class RetentionEvaluator:
    """Budget and time-to-live enforcement for one scope (§T.6)."""

    def evaluate(
        self,
        scope: str,
        entries: Sequence[AIMemoryEntry],
        budget: ScopeBudget,
        *,
        now: datetime | None = None,
        incoming: int = 0,
    ) -> RetentionPlan:
        normalizedScope = ensureMemoryScope(scope)
        if not isinstance(budget, ScopeBudget):
            raise AIMemoryPolicyInvalid("Retention requires a ScopeBudget.")
        moment = now or utcNow()
        decisions: list[RetentionDecision] = []
        alive: list[AIMemoryEntry] = []

        for entry in entries:
            if not entry.isUsableAt(moment):
                reason = (
                    "Time-to-live elapsed."
                    if entry.isExpiredAt(moment)
                    else "Entry is inactive or superseded."
                )
                decisions.append(RetentionDecision(entry=entry, action="EXPIRE", reason=reason))
                continue
            alive.append(entry)

        overflow = len(alive) + max(0, incoming) - budget.maxEntries
        if overflow > 0:
            if budget.eviction == "NONE":
                raise AIMemoryBudgetExceeded("Memory scope is full and eviction is disabled.")
            ordered = self._evictionOrder(alive, budget)
            for entry in ordered[:overflow]:
                decisions.append(
                    RetentionDecision(
                        entry=entry,
                        action="EVICT",
                        reason=f"Scope over budget by {overflow} entry(ies).",
                    )
                )
            evictedIds = {entry.id for entry in ordered[:overflow]}
            alive = [entry for entry in alive if entry.id not in evictedIds]

        decisions.extend(
            RetentionDecision(entry=entry, action="KEEP", reason="Within budget.")
            for entry in alive
        )
        return RetentionPlan(scope=normalizedScope, decisions=tuple(decisions), budget=budget)

    @staticmethod
    def _evictionOrder(
        entries: Sequence[AIMemoryEntry], budget: ScopeBudget
    ) -> list[AIMemoryEntry]:
        """Order in which entries would be dropped (first = dropped first).

        ``OLDEST_FIRST`` uses ``createdAt`` and never needs a write on
        read; ``LOWEST_PRIORITY`` uses the caller-supplied
        ``metadata["priority"]`` (default 0) before falling back to age.
        Ties break on the identifier so two runs never disagree.
        """

        if budget.eviction == "LOWEST_PRIORITY":
            return sorted(
                entries,
                key=lambda entry: (
                    int(entry.metadata.get("priority", 0) or 0),
                    entry.createdAt,
                    str(entry.id),
                ),
            )
        return sorted(entries, key=lambda entry: (entry.createdAt, str(entry.id)))


class MemorySelector:
    """Chooses the memories that may enter a prompt (§T.9)."""

    def select(
        self,
        entries: Iterable[AIMemoryEntry],
        *,
        scopes: tuple[str, ...] = (),
        maxEntries: int = 10,
        maxTokens: int = 1000,
        now: datetime | None = None,
        userId: Any = None,
    ) -> MemorySelection:
        if maxEntries < 1 or maxTokens < 1:
            raise AIMemoryInvalid("Memory selection limits must be positive.")
        moment = now or utcNow()
        wanted = tuple(ensureMemoryScope(scope) for scope in scopes)
        considered: list[AIMemoryEntry] = []
        for entry in entries:
            if not entry.isUsableAt(moment):
                continue
            if wanted and entry.scope not in wanted:
                continue
            if not entry.isOwnedBy(userId):
                continue
            considered.append(entry)

        # Latest version wins per key; history never competes with itself.
        latestByKey: dict[str, AIMemoryEntry] = {}
        for entry in considered:
            existing = latestByKey.get(entry.qualifiedKey)
            if existing is None or entry.version > existing.version:
                latestByKey[entry.qualifiedKey] = entry

        ordered = sorted(
            latestByKey.values(),
            key=lambda entry: (
                entry.memoryKey.priority,
                -entry.createdAt.timestamp(),
                entry.qualifiedKey,
            ),
        )
        chosen: list[AIMemoryEntry] = []
        usedTokens = 0
        for entry in ordered:
            if len(chosen) >= maxEntries:
                break
            tokens = estimateTokens(entry.renderedValue())
            if chosen and usedTokens + tokens > maxTokens:
                continue
            chosen.append(entry)
            usedTokens += tokens
        return MemorySelection(
            entries=tuple(chosen),
            tokenCount=usedTokens,
            consideredCount=len(latestByKey),
            droppedCount=len(latestByKey) - len(chosen),
            metadata={"scopes": list(wanted)},
        )


def budgetFor(budget: MemoryBudget, scope: str) -> ScopeBudget:
    """Convenience accessor used by the application layer."""

    if not isinstance(budget, MemoryBudget):
        raise AIMemoryPolicyInvalid("A MemoryBudget is required.")
    return budget.forScope(scope)


__all__ = [
    "WRITE_ACTIONS",
    "MemorySelection",
    "MemorySelector",
    "MemoryWriter",
    "RetentionDecision",
    "RetentionEvaluator",
    "RetentionPlan",
    "WritePlan",
    "budgetFor",
]
