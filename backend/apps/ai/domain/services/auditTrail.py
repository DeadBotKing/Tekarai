"""Pure append-only audit trail with tamper-evidence (Phase 13-O).

``AuditTrailService`` is a tenant-scoped in-memory coordinator for audit
entries (§28). It owns no persistence: the application layer appends to its
store and hydrates the service for reads and chain verification (the same
split as the Phase 13-G/N coordinators).

Tamper-evidence (§O.5):

- every entry carries ``prevHash`` (the hash of the previous entry of the
  same tenant, or ``GENESIS_HASH`` for the first one) and ``hash``
  (sha256 over tenant + prevHash + canonical payload);
- ``verifyAuditChain`` recomputes every hash, checks every link, and
  detects forks (the same non-genesis ``prevHash`` claimed twice);
- any violation raises ``AIAuditTrailTampered`` — detection, not
  prevention: fully concurrent appends can fork (documented limitation
  for the sub-phase P worker serialization).

``scrubDetail`` (§47) recursively redacts secret-valued keys and enforces
the RESTRICTED rule: without an explicit opt-in, restricted detail is
replaced wholesale while reference fields stay (references are not
content).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.auditRecords import AIAuditEntry
from apps.ai.domain.exceptions import (
    AIAuditRecordInvalid,
    AIAuditRecordNotFound,
    AIAuditTrailTampered,
    AIError,
)
from apps.ai.domain.valueObjects.auditTypes import (
    GENESIS_HASH,
    REDACTED,
    ensureActorType,
    ensureAuditAction,
    ensureAuditOutcome,
    isSecretKey,
)
from apps.ai.domain.valueObjects.usageTypes import asUtc

#: Hard cap for scrubber recursion (payloads are small metadata dicts).
_SCRUB_MAX_DEPTH = 12


def _canonicalValue(value: Any, depth: int = 0) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalValue(value[key], depth + 1)
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalValue(item, depth + 1) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonicalValue(item, depth + 1) for item in value), key=repr)
    if isinstance(value, (uuid.UUID, datetime)):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return str(value)
    except Exception:
        return repr(value)


def _entryPayload(entry: AIAuditEntry) -> dict[str, Any]:
    return {
        "action": entry.action,
        "occurredAt": entry.occurredAt.isoformat(),
        "actorType": entry.actorType,
        "actorId": str(entry.actorId) if entry.actorId else "",
        "requestId": str(entry.requestId) if entry.requestId else "",
        "attemptId": str(entry.attemptId) if entry.attemptId else "",
        "policyId": str(entry.policyId) if entry.policyId else "",
        "capabilityCode": entry.capabilityCode,
        "providerCode": entry.providerCode,
        "modelCode": entry.modelCode,
        "promptVersion": entry.promptVersion,
        "classification": entry.classification,
        "outcome": entry.outcome,
        "errorCode": entry.errorCode,
        "correlationId": entry.correlationId,
        "traceId": entry.traceId,
        "contextSources": list(entry.contextSources),
        "detail": _canonicalValue(entry.detail),
    }


def auditEntryHash(tenantId: uuid.UUID, prevHash: str, entry: AIAuditEntry) -> str:
    """Stable sha256 identity of one chained audit entry."""

    if not isinstance(entry, AIAuditEntry):
        raise ValueError("Audit hashing requires an AIAuditEntry.")
    canonical = {
        "tenantId": str(requireUuid(tenantId, "tenantId")),
        "prevHash": str(prevHash or ""),
        "payload": _entryPayload(entry),
    }
    encoded = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def verifyAuditChain(entries: tuple[AIAuditEntry, ...] | list[AIAuditEntry]) -> int:
    """Verify one tenant's chain by walking its links; return the verified count.

    Link-walking (not timestamp sorting) defines chain order, so entries
    sharing a microsecond stay verifiable. Every payload hash is
    recomputed; exactly one genesis entry (``prevHash == GENESIS_HASH``)
    must exist; every step must have exactly one child. Violations raise
    ``AIAuditTrailTampered``: payload mismatch, missing/duplicate genesis,
    fork (a ``prevHash`` claimed twice), early end, or disconnected
    entries. An empty chain verifies trivially to zero.
    """

    ordered = list(entries)
    if not ordered:
        return 0
    for entry in ordered:
        recomputed = auditEntryHash(entry.tenantId, entry.prevHash, entry)
        if recomputed != entry.hash:
            raise AIAuditTrailTampered(f"Audit entry {entry.id} payload does not match its hash.")
    genesis = [entry for entry in ordered if entry.prevHash == GENESIS_HASH]
    if not genesis:
        raise AIAuditTrailTampered("Audit chain has no genesis entry.")
    if len(genesis) > 1:
        raise AIAuditTrailTampered("Audit chain has competing genesis entries (fork).")
    byPrev: dict[str, list[AIAuditEntry]] = {}
    for entry in ordered:
        byPrev.setdefault(entry.prevHash, []).append(entry)
    visited: set[tuple[object, object]] = set()
    current = genesis[0]
    while True:
        key = (current.tenantId, current.id)
        if key in visited:
            raise AIAuditTrailTampered(f"Audit chain cycles at entry {current.id}.")
        visited.add(key)
        children = [
            entry for entry in byPrev.get(current.hash, []) if (entry.tenantId, entry.id) != key
        ]
        if not children:
            break
        if len(children) > 1:
            raise AIAuditTrailTampered(
                f"Audit chain forks at entry {children[1].id} (prevHash reused)."
            )
        current = children[0]
    if len(visited) != len(ordered):
        raise AIAuditTrailTampered("Audit chain holds disconnected entries.")
    return len(ordered)


def scrubDetail(
    value: Any,
    *,
    classification: str = "INTERNAL",
    allowRestrictedDetail: bool = False,
) -> Any:
    """Redact secrets from an audit detail payload (§47).

    - mapping keys matching ``SECRET_KEY_PATTERNS`` become ``REDACTED``;
    - lists/tuples/sets are scrubbed element-wise (tuples/sets normalize
      to lists so the result is always JSON-safe);
    - unknown scalars pass through; unknown objects fall back to ``repr``;
    - when ``classification`` is RESTRICTED without an explicit opt-in,
      the whole payload is replaced by a redaction marker.
    """

    normalizedClassification = str(classification or "").strip().upper()
    if normalizedClassification == "RESTRICTED" and not allowRestrictedDetail:
        return {"redacted": True, "reason": "RESTRICTED detail requires an explicit opt-in."}
    return _scrubValue(value, 0)


def _scrubValue(value: Any, depth: int) -> Any:
    if depth > _SCRUB_MAX_DEPTH:
        return REDACTED
    if isinstance(value, Mapping):
        scrubbed: dict[str, Any] = {}
        for key in sorted(value, key=lambda item: str(item)):
            textKey = str(key)
            if isSecretKey(textKey):
                scrubbed[textKey] = REDACTED
            else:
                scrubbed[textKey] = _scrubValue(value[key], depth + 1)
        return scrubbed
    if isinstance(value, (list, tuple)):
        return [_scrubValue(item, depth + 1) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_scrubValue(item, depth + 1) for item in value), key=repr)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return str(value)
    except Exception:
        return repr(value)


@dataclass(frozen=True)
class AuditEntryDescriptor:
    """Safe audit read model; carries references and hashes, never content."""

    tenantId: uuid.UUID
    entryId: uuid.UUID
    action: str
    occurredAt: datetime
    actorType: str
    actorId: uuid.UUID | None
    requestId: uuid.UUID | None
    attemptId: uuid.UUID | None
    policyId: uuid.UUID | None
    capabilityCode: str
    providerCode: str
    modelCode: str
    promptVersion: str
    classification: str
    outcome: str
    errorCode: str
    correlationId: str
    traceId: str
    contextSources: tuple[str, ...]
    prevHash: str
    hash: str


@dataclass(frozen=True)
class AuditEntryFilter:
    """Read filter for audit listings; tenant is always mandatory."""

    action: str | None = None
    actorId: uuid.UUID | str | None = None
    requestId: uuid.UUID | str | None = None
    outcome: str | None = None
    since: datetime | None = None
    until: datetime | None = None


@dataclass(frozen=True)
class RetentionCutoff:
    """Deterministic retention boundary: entries strictly before it purge."""

    tenantId: uuid.UUID
    cutoff: datetime
    retentionDays: int


class AuditTrailService:
    """Tenant-scoped in-memory coordinator for the audit ledger."""

    def __init__(self, *, now: Any = utcNow) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self._now = now
        self._entries: dict[tuple[uuid.UUID, uuid.UUID], AIAuditEntry] = {}

    # ------------------------------------------------------------------
    # Appending (no update, no delete — the ledger is append-only)
    # ------------------------------------------------------------------
    def logEntry(
        self,
        tenantId: uuid.UUID | str,
        action: str,
        *,
        occurredAt: datetime | None = None,
        entryId: uuid.UUID | str | None = None,
        actorType: str = "SYSTEM",
        actorId: uuid.UUID | str | None = None,
        requestId: uuid.UUID | str | None = None,
        attemptId: uuid.UUID | str | None = None,
        policyId: uuid.UUID | str | None = None,
        capabilityCode: str = "",
        providerCode: str = "",
        modelCode: str = "",
        promptVersion: str = "",
        classification: str = "INTERNAL",
        outcome: str = "RECORDED",
        errorCode: str = "",
        correlationId: str = "",
        traceId: str = "",
        contextSources: tuple[str, ...] | list[str] | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AIAuditEntry:
        tenant = requireUuid(tenantId, "tenantId")
        try:
            entry = AIAuditEntry(
                tenantId=tenant,
                action=ensureAuditAction(action),
                occurredAt=asUtc(occurredAt) if occurredAt is not None else self._now(),
                id=requireUuid(entryId, "entryId") if entryId is not None else uuid.uuid4(),
                actorType=ensureActorType(actorType),
                actorId=requireUuid(actorId, "actorId") if actorId is not None else None,
                requestId=requireUuid(requestId, "requestId") if requestId is not None else None,
                attemptId=requireUuid(attemptId, "attemptId") if attemptId is not None else None,
                policyId=requireUuid(policyId, "policyId") if policyId is not None else None,
                capabilityCode=capabilityCode,
                providerCode=providerCode,
                modelCode=modelCode,
                promptVersion=promptVersion,
                classification=classification,
                outcome=ensureAuditOutcome(outcome),
                errorCode=errorCode,
                correlationId=correlationId,
                traceId=traceId,
                contextSources=tuple(contextSources) if contextSources is not None else (),
                detail=dict(detail) if detail is not None else {},
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIAuditRecordInvalid(str(exc)) from exc
        return self._chainAndStore(entry)

    def importEntry(self, entry: AIAuditEntry) -> AIAuditEntry:
        """Load a persisted entry (application hydration) without re-chaining."""

        if not isinstance(entry, AIAuditEntry):
            raise ValueError("Only AIAuditEntry records can be imported.")
        key = (entry.tenantId, entry.id)
        if key in self._entries:
            return self._entries[key]
        self._entries[key] = entry
        return entry

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def getEntry(self, tenantId: uuid.UUID | str, entryId: uuid.UUID | str) -> AIAuditEntry:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(entryId, "entryId")
        entry = self._entries.get((tenant, identifier))
        if entry is None:
            raise AIAuditRecordNotFound(str(identifier))
        return entry

    def describeEntry(
        self, tenantId: uuid.UUID | str, entryId: uuid.UUID | str
    ) -> AuditEntryDescriptor:
        entry = self.getEntry(tenantId, entryId)
        return AuditEntryDescriptor(
            tenantId=entry.tenantId,
            entryId=entry.id,
            action=entry.action,
            occurredAt=entry.occurredAt,
            actorType=entry.actorType,
            actorId=entry.actorId,
            requestId=entry.requestId,
            attemptId=entry.attemptId,
            policyId=entry.policyId,
            capabilityCode=entry.capabilityCode,
            providerCode=entry.providerCode,
            modelCode=entry.modelCode,
            promptVersion=entry.promptVersion,
            classification=entry.classification,
            outcome=entry.outcome,
            errorCode=entry.errorCode,
            correlationId=entry.correlationId,
            traceId=entry.traceId,
            contextSources=entry.contextSources,
            prevHash=entry.prevHash,
            hash=entry.hash,
        )

    def listEntries(
        self,
        tenantId: uuid.UUID | str,
        entryFilter: AuditEntryFilter | None = None,
    ) -> tuple[AIAuditEntry, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        active = entryFilter or AuditEntryFilter()
        action = ensureAuditAction(active.action) if active.action else None
        actor = requireUuid(active.actorId, "actorId") if active.actorId is not None else None
        request = (
            requireUuid(active.requestId, "requestId") if active.requestId is not None else None
        )
        outcome = ensureAuditOutcome(active.outcome) if active.outcome else None
        since = asUtc(active.since) if active.since is not None else None
        until = asUtc(active.until) if active.until is not None else None
        selected = [
            entry
            for (entryTenant, _), entry in self._entries.items()
            if entryTenant == tenant
            and (action is None or entry.action == action)
            and (actor is None or entry.actorId == actor)
            and (request is None or entry.requestId == request)
            and (outcome is None or entry.outcome == outcome)
            and (since is None or entry.occurredAt >= since)
            and (until is None or entry.occurredAt < until)
        ]
        return tuple(sorted(selected, key=lambda item: (item.occurredAt, str(item.id))))

    def entriesForTenant(self, tenantId: uuid.UUID | str) -> tuple[AIAuditEntry, ...]:
        return self.listEntries(tenantId)

    def latestHash(self, tenantId: uuid.UUID | str) -> str:
        tenant = requireUuid(tenantId, "tenantId")
        chained = [entry for entry in self.entriesForTenant(tenant) if entry.hash]
        if not chained:
            return GENESIS_HASH
        claimed = {entry.prevHash for entry in chained}
        tips = [entry for entry in chained if entry.hash not in claimed]
        if not tips:
            tips = chained
        tip = max(tips, key=lambda item: (item.occurredAt, str(item.id)))
        return tip.hash

    def verifyChain(self, tenantId: uuid.UUID | str) -> int:
        """Verify this tenant's in-memory chain; return the verified count."""

        return verifyAuditChain(self.entriesForTenant(tenantId))

    def retentionCutoff(
        self,
        tenantId: uuid.UUID | str,
        retentionDays: int,
        *,
        now: datetime | None = None,
    ) -> RetentionCutoff:
        tenant = requireUuid(tenantId, "tenantId")
        if (
            not isinstance(retentionDays, int)
            or isinstance(retentionDays, bool)
            or retentionDays < 1
        ):
            raise AIAuditRecordInvalid("Retention days must be a positive integer.")
        moment = asUtc(now) if now is not None else self._now()
        return RetentionCutoff(
            tenantId=tenant,
            cutoff=moment - timedelta(days=retentionDays),
            retentionDays=retentionDays,
        )

    # ------------------------------------------------------------------
    # Internal invariants
    # ------------------------------------------------------------------
    def _chainAndStore(self, entry: AIAuditEntry) -> AIAuditEntry:
        key = (entry.tenantId, entry.id)
        if key in self._entries:
            return self._entries[key]
        entry.prevHash = self.latestHash(entry.tenantId)
        entry.hash = auditEntryHash(entry.tenantId, entry.prevHash, entry)
        self._entries[key] = entry
        return entry


AuditLog = AuditTrailService
InMemoryAuditTrail = AuditTrailService
AIAuditService = AuditTrailService

__all__ = [
    "AIAuditService",
    "AuditEntryDescriptor",
    "AuditEntryFilter",
    "AuditLog",
    "AuditTrailService",
    "InMemoryAuditTrail",
    "RetentionCutoff",
    "auditEntryHash",
    "scrubDetail",
    "verifyAuditChain",
]
