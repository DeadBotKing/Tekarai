"""Pure async-execution job entity for Phase 13-P.

``AIJob`` is one durable unit of async AI work (§35). Execution references
(``requestId``) are plain UUID columns with **no foreign keys** on purpose:
retention purges of the referenced rows must never cascade into the job
ledger (the same pattern as the Phase 13-O audit trail). ``payload`` is an
opaque mapping owned by the job kind — the queue never interprets it, and
audit records about jobs carry only references, never the payload.

The record contains no ORM, HTTP, provider SDK, Redis, queue, or Django
dependency. Persistence mapping belongs to the infrastructure layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.valueObjects.queueTypes import (
    DEFAULT_JOB_PRIORITY,
    ensureJobKind,
    ensureJobPriority,
    ensureJobStatus,
)
from apps.ai.domain.valueObjects.usageTypes import asUtc


def _normalizeReference(value: Any) -> str:
    return str(value or "").strip()


def _normalizePayload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Job payload must be a mapping.")
    return {str(key): item for key, item in value.items()}


@dataclass
class AIJob:
    """One durable async AI job.

    ``attempts`` counts claims (including the current one); ``maxAttempts``
    bounds retries. ``leaseExpiresAt`` guards the ``RUNNING`` state: only
    the holder (``claimedBy``) may settle or heartbeat, and an expired
    lease makes the job claimable again. ``idempotencyKey`` is
    tenant-scoped; an empty key opts out of idempotent submission.
    """

    tenantId: uuid.UUID
    kind: str
    id: uuid.UUID = field(default_factory=lambda: uuid.uuid4())
    requestId: uuid.UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    idempotencyKey: str = ""
    status: str = "PENDING"
    priority: int = DEFAULT_JOB_PRIORITY
    attempts: int = 0
    maxAttempts: int = 3
    runAt: datetime = field(default_factory=utcNow)
    claimedBy: str = ""
    leaseExpiresAt: datetime | None = None
    resultSummary: dict[str, Any] = field(default_factory=dict)
    errorCode: str = ""
    correlationId: str = ""
    traceId: str = ""
    createdAt: datetime = field(default_factory=utcNow)
    updatedAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.kind = ensureJobKind(self.kind)
        if self.requestId is not None:
            self.requestId = requireUuid(self.requestId, "requestId")
        self.payload = _normalizePayload(self.payload)
        self.idempotencyKey = _normalizeReference(self.idempotencyKey)
        self.status = ensureJobStatus(self.status)
        self.priority = ensureJobPriority(self.priority)
        if (
            not isinstance(self.attempts, int)
            or isinstance(self.attempts, bool)
            or self.attempts < 0
        ):
            raise ValueError("Job attempts cannot be negative.")
        if (
            not isinstance(self.maxAttempts, int)
            or isinstance(self.maxAttempts, bool)
            or self.maxAttempts < 1
        ):
            raise ValueError("Job max attempts must be at least one.")
        self.runAt = asUtc(self.runAt)
        self.claimedBy = _normalizeReference(self.claimedBy)
        if self.leaseExpiresAt is not None:
            self.leaseExpiresAt = asUtc(self.leaseExpiresAt)
        self.resultSummary = _normalizePayload(self.resultSummary)
        self.errorCode = _normalizeReference(self.errorCode).upper()
        self.correlationId = _normalizeReference(self.correlationId)
        self.traceId = _normalizeReference(self.traceId)
        self.createdAt = asUtc(self.createdAt)
        self.updatedAt = asUtc(self.updatedAt)

    @property
    def isTerminal(self) -> bool:
        return self.status in ("SUCCEEDED", "FAILED", "CANCELLED", "DEAD")

    def leaseHeldBy(self, workerId: str, now: datetime) -> bool:
        """A live lease held by ``workerId`` at ``now`` (UTC-normalized)."""

        moment = asUtc(now)
        return bool(
            self.claimedBy
            and self.claimedBy == str(workerId or "").strip()
            and self.leaseExpiresAt is not None
            and self.leaseExpiresAt > moment
        )

    def leaseExpired(self, now: datetime) -> bool:
        moment = asUtc(now)
        return self.leaseExpiresAt is not None and self.leaseExpiresAt <= moment


__all__ = [
    "AIJob",
]
