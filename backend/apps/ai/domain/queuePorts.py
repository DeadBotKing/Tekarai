"""Async execution port interfaces for Phase 13-P.

Minimal contracts the application layer depends on:

- ``JobStore`` — persistence of ``AIJob`` records, including the atomic
  row-level claim the queue needs for single-flight execution;
- ``JobHandler`` — one executable kind (plus the worker-owned
  ``EVENT_DISPATCH`` kind);
- ``EventBusPort`` — durable event publication (the application
  ``QueuedEventBus`` sends envelopes through the queue).

``datetime`` and ``uuid`` are typing-only; the module has no Django, ORM,
HTTP, provider SDK, Redis, queue, or network dependency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from apps.ai.domain.entities.jobRecords import AIJob
from apps.ai.domain.services.eventBus import AIEventEnvelope
from apps.ai.domain.services.jobQueue import JobOutcome


class JobStore(Protocol):
    """Persistence contract for the async job ledger."""

    def save(self, job: AIJob) -> AIJob: ...
    def get(self, tenantId: UUID, jobId: UUID) -> AIJob | None: ...
    def findByIdempotencyKey(self, tenantId: UUID, idempotencyKey: str) -> AIJob | None: ...
    def claimRow(
        self, tenantId: UUID | None, workerId: str, leaseSeconds: int, limit: int, now: datetime
    ) -> tuple[AIJob, ...]: ...
    def update(self, job: AIJob) -> AIJob: ...
    def listTenantJobs(self, tenantId: UUID) -> tuple[AIJob, ...]: ...
    def deleteJobsBefore(
        self, tenantId: UUID | None, cutoff: datetime, statuses: tuple[str, ...]
    ) -> int: ...


class JobHandler(Protocol):
    """Executable handler for one job kind."""

    def kind(self) -> str: ...
    def execute(self, job: AIJob) -> JobOutcome: ...


class EventBusPort(Protocol):
    """Durable event publication."""

    def publish(self, envelope: AIEventEnvelope, **kwargs: Any) -> AIJob: ...


__all__ = [
    "EventBusPort",
    "JobHandler",
    "JobStore",
]
