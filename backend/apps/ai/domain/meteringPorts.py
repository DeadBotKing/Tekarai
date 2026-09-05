"""Persistence and integration ports for Phase 13-N metering.

These ``Protocol`` contracts are the only boundary the application layer
uses to store usage attempts, quota policies, and quota counters, to
resolve model cost rates, and to publish ``AIUsageRecorded`` events. They
are pure Python: no Django, ORM, queue, network, or vendor dependency.

``InMemoryUsageEventSink`` is the offline test double for the event port;
binding the event to the Tekarai event bus belongs to sub-phases O/P.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from apps.ai.domain.entities.usageRecords import AIQuotaCounter, AIQuotaPolicy, AIUsageAttempt
from apps.ai.domain.services.usageMetering import AIUsageRecorded
from apps.ai.domain.valueObjects.aiTypes import CostRate


@runtime_checkable
class UsageAttemptStore(Protocol):
    """Persistence boundary for per-attempt usage records."""

    def saveAttempt(self, attempt: AIUsageAttempt) -> AIUsageAttempt: ...
    def getAttempt(self, tenantId: uuid.UUID, attemptId: uuid.UUID) -> AIUsageAttempt: ...
    def listAttempts(
        self,
        tenantId: uuid.UUID,
        *,
        requestId: uuid.UUID | str | None = ...,
        outcome: str | None = ...,
        since: datetime | None = ...,
        until: datetime | None = ...,
    ) -> tuple[AIUsageAttempt, ...]: ...
    def findByIdempotencyKey(
        self, tenantId: uuid.UUID, idempotencyKey: str
    ) -> AIUsageAttempt | None: ...


@runtime_checkable
class QuotaPolicyStore(Protocol):
    """Persistence boundary for quota policy definitions."""

    def savePolicy(self, policy: AIQuotaPolicy) -> AIQuotaPolicy: ...
    def getPolicy(self, tenantId: uuid.UUID, policyId: uuid.UUID) -> AIQuotaPolicy: ...
    def listActivePolicies(self, tenantId: uuid.UUID) -> tuple[AIQuotaPolicy, ...]: ...
    def setPolicyActive(
        self, tenantId: uuid.UUID, policyId: uuid.UUID, isActive: bool
    ) -> AIQuotaPolicy: ...


@runtime_checkable
class QuotaCounterStore(Protocol):
    """Persistence boundary for per-window quota counters.

    Implementations must make ``addConsumption`` atomic for one
    (policy, window) row; concurrent admissions serialize on the row.
    """

    def loadCounter(
        self,
        tenantId: uuid.UUID,
        policyId: uuid.UUID,
        windowStart: datetime,
    ) -> AIQuotaCounter | None: ...
    def saveCounter(self, counter: AIQuotaCounter) -> AIQuotaCounter: ...
    def addConsumption(
        self,
        tenantId: uuid.UUID,
        policyId: uuid.UUID,
        windowStart: datetime,
        *,
        requests: int = ...,
        inputTokens: int = ...,
        outputTokens: int = ...,
        costAmount: Decimal | int | str = ...,
        currency: str = ...,
    ) -> AIQuotaCounter: ...


@runtime_checkable
class CostRateResolver(Protocol):
    """Resolves the billable token rates of a tenant-owned model."""

    def rateFor(self, tenantId: uuid.UUID, modelId: uuid.UUID) -> CostRate: ...


@runtime_checkable
class UsageEventSink(Protocol):
    """Publishes ``AIUsageRecorded`` carriers without content or secrets."""

    def publish(self, event: AIUsageRecorded) -> None: ...


class InMemoryUsageEventSink:
    """Offline test double that retains published events for assertions."""

    def __init__(self) -> None:
        self.events: list[AIUsageRecorded] = []

    def publish(self, event: AIUsageRecorded) -> None:
        if not isinstance(event, AIUsageRecorded):
            raise ValueError("Usage event sink requires an AIUsageRecorded carrier.")
        self.events.append(event)


__all__ = [
    "CostRateResolver",
    "InMemoryUsageEventSink",
    "QuotaCounterStore",
    "QuotaPolicyStore",
    "UsageAttemptStore",
    "UsageEventSink",
]
