"""AI memory entities for Phase 13-T.

``AIMemoryEntry`` is one *version* of one memory slot. Versions are
immutable: remembering a new value never edits history, it supersedes it.
That is what makes memory auditable (§17) and what lets a caller inspect
"what did the assistant believe last Tuesday" without a separate log.

The record carries everything the platform needs to enforce §17 in full:

- **Tenant-aware** — ``tenantId`` on every row and every query;
- **User-aware** — an optional ``userId`` owner; entries without one are
  tenant-wide;
- **Permission-aware** — a ``classification`` the Phase 13-K filter can
  act on, plus ``toContextSource`` so memory enters a prompt through the
  same authorized path as knowledge (never a side door);
- **Versioned** — ``version`` plus ``supersededAt``;
- **Auditable** — a value checksum and stable size accounting.

Pure dataclasses: no Django, ORM, HTTP, provider SDK, queue, or network
dependency. ``toDomainMemory`` bridges to the Phase 13-B ``AIMemory``
primitive so earlier consumers keep working.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from apps.ai.domain.entities.aiRecords import AIMemory, newId, requireUuid, utcNow
from apps.ai.domain.valueObjects.aiTypes import DATA_CLASSIFICATIONS, ensureEnum
from apps.ai.domain.valueObjects.memoryTypes import (
    MemoryKey,
    ScopeBudget,
    canonicalValue,
    ensureMemoryKind,
    valueChecksum,
    valueSize,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

_CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")

MAX_SOURCE_REFERENCE_LENGTH = 200


def ensureValueChecksum(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _CHECKSUM_PATTERN.fullmatch(normalized):
        raise ValidationFailedError(
            "Memory checksum must be a SHA-256 hex digest.",
            fieldErrors={"checksum": normalized[:16]},
        )
    return normalized


@dataclass
class AIMemoryEntry:
    """One immutable version of one memory slot (§T.4)."""

    tenantId: uuid.UUID
    memoryKey: MemoryKey
    value: Any
    kind: str = "FACT"
    userId: uuid.UUID | None = None
    conversationId: str = ""
    classification: str = "INTERNAL"
    version: int = 1
    isActive: bool = True
    expiresAt: datetime | None = None
    supersededAt: datetime | None = None
    sourceReference: str = ""
    checksum: str = ""
    sizeBytes: int = 0
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        if self.userId is not None:
            self.userId = requireUuid(self.userId, "userId")
        if not isinstance(self.memoryKey, MemoryKey):
            raise ValidationFailedError("A memory entry requires a MemoryKey.")
        self.kind = ensureMemoryKind(self.kind)
        self.classification = ensureEnum(
            self.classification, DATA_CLASSIFICATIONS, "classification"
        )
        self.conversationId = str(self.conversationId or "").strip()
        self.sourceReference = str(self.sourceReference or "").strip()
        if len(self.sourceReference) > MAX_SOURCE_REFERENCE_LENGTH:
            raise ValidationFailedError("Memory sourceReference is too long.")
        if not isinstance(self.version, int) or isinstance(self.version, bool):
            raise ValidationFailedError("Memory version must be an integer.")
        if self.version < 1:
            raise ValidationFailedError("Memory version must be positive.")
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Memory metadata must be a mapping.")
        self.value = canonicalValue(self.value)
        computed = valueChecksum(self.value)
        if self.checksum and ensureValueChecksum(self.checksum) != computed:
            raise ValidationFailedError("Memory checksum does not match its value.")
        self.checksum = computed
        self.sizeBytes = self.sizeBytes or valueSize(self.value)
        if self.expiresAt is not None and not isinstance(self.expiresAt, datetime):
            raise ValidationFailedError("Memory expiresAt must be a datetime.")

    # -- identity -------------------------------------------------------
    @property
    def scope(self) -> str:
        return self.memoryKey.scope

    @property
    def key(self) -> str:
        return self.memoryKey.key

    @property
    def qualifiedKey(self) -> str:
        return self.memoryKey.qualified()

    def belongsTo(self, tenantId: uuid.UUID | str) -> bool:
        return self.tenantId == requireUuid(tenantId, "tenantId")

    def isOwnedBy(self, userId: uuid.UUID | str | None) -> bool:
        """Tenant-wide entries (no owner) are readable by every principal."""

        if self.userId is None:
            return True
        if userId is None:
            return False
        return self.userId == requireUuid(userId, "userId")

    def hasSameValueAs(self, value: Any) -> bool:
        return valueChecksum(value) == self.checksum

    # -- lifecycle ------------------------------------------------------
    def isExpiredAt(self, now: datetime | None = None) -> bool:
        return self.expiresAt is not None and self.expiresAt <= (now or utcNow())

    def isUsableAt(self, now: datetime | None = None) -> bool:
        return self.isActive and self.supersededAt is None and not self.isExpiredAt(now)

    def supersede(self, *, now: datetime | None = None) -> None:
        """Retire this version; the row survives for history and audit."""

        if self.supersededAt is not None:
            return
        self.supersededAt = now or utcNow()
        self.isActive = False

    def forget(self, *, now: datetime | None = None) -> None:
        """Deactivate without pretending the version never existed."""

        self.isActive = False
        if self.supersededAt is None:
            self.supersededAt = now or utcNow()

    def withExpiry(self, budget: ScopeBudget, *, now: datetime | None = None) -> None:
        """Apply a scope's time-to-live when the caller gave none."""

        if self.expiresAt is not None or not budget.expires:
            return
        self.expiresAt = (now or utcNow()) + timedelta(seconds=budget.ttlSeconds)

    def nextVersion(
        self,
        value: Any,
        *,
        now: datetime | None = None,
        kind: str = "",
        classification: str = "",
        expiresAt: datetime | None = None,
        sourceReference: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AIMemoryEntry:
        """Build the successor version of this slot (this one is untouched)."""

        return AIMemoryEntry(
            tenantId=self.tenantId,
            memoryKey=self.memoryKey,
            value=value,
            kind=kind or self.kind,
            userId=self.userId,
            conversationId=self.conversationId,
            classification=classification or self.classification,
            version=self.version + 1,
            expiresAt=expiresAt,
            sourceReference=sourceReference or self.sourceReference,
            metadata=dict(metadata if metadata is not None else self.metadata),
            createdAt=now or utcNow(),
        )

    # -- projections ----------------------------------------------------
    def toContextSource(self) -> dict[str, Any]:
        """Shape used to build a Phase 13-J/K context source candidate.

        A plain mapping keeps the domain free of the context engine; the
        application layer turns it into a ``ContextSourceCandidate`` so
        memory is filtered by Phase 13-K exactly like knowledge is.
        """

        return {
            "sourceDomain": "MEMORY",
            "sourceEntityType": self.scope,
            "sourceEntityId": self.key,
            "content": self.renderedValue(),
            "classification": self.classification,
            "metadata": {
                "memoryId": str(self.id),
                "version": self.version,
                "kind": self.kind,
                "qualifiedKey": self.qualifiedKey,
            },
        }

    def renderedValue(self) -> str:
        """Human-readable projection used inside a prompt."""

        if isinstance(self.value, str):
            return self.value
        from apps.ai.domain.valueObjects.memoryTypes import serializeValue

        return serializeValue(self.value)

    def toDomainMemory(self) -> AIMemory:
        """Bridge to the Phase 13-B ``AIMemory`` primitive."""

        return AIMemory(
            tenantId=self.tenantId,
            scope=self.scope,
            key=self.key,
            value=self.value,
            userId=self.userId,
            version=self.version,
            id=self.id,
            isActive=self.isActive,
            expiresAt=self.expiresAt,
            createdAt=self.createdAt,
        )


__all__ = [
    "MAX_SOURCE_REFERENCE_LENGTH",
    "AIMemoryEntry",
    "ensureValueChecksum",
]
