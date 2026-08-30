"""Django implementations of the shared-kernel ports (Phase 06 §10 rule 5).

Infrastructure may know Django/DRF; nothing above the ports does. All
providers are stateless and instantiated once via ``wiring.sharedKernelProvider``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from django.db import transaction

from apps.sharedKernel.application.requestContext import snapshotContext
from apps.sharedKernel.domain.events import DomainEvent

logger = logging.getLogger("tekarai.events")


class SystemClock:
    def nowUtc(self) -> datetime:
        return datetime.now(tz=UTC)


class UnitOfWorkDjango:
    """Transaction boundary (§9): one atomic block per use case."""

    def __enter__(self) -> UnitOfWorkDjango:
        self.atomic = transaction.atomic()
        self.atomic.__enter__()
        return self

    def __exit__(self, excType: object, excValue: object, traceback: object) -> None:
        self.atomic.__exit__(excType, excValue, traceback)
        # returning None = never swallow


class AuditRecorderDjango:
    """Appends §19-shaped audit rows inside the use-case transaction."""

    def record(
        self,
        *,
        action: str,
        resourceType: str,
        resourceId: str,
        tenantId: uuid.UUID | None,
        before: dict[str, object] | None = None,
        after: dict[str, object] | None = None,
    ) -> None:
        from apps.sharedKernel.infrastructure.models import AuditEventModel

        snapshot = snapshotContext()
        AuditEventModel.objects.create(
            actorUserId=uuid.UUID(snapshot.actorId) if snapshot.actorId else None,
            tenantId=tenantId or (uuid.UUID(snapshot.tenantId) if snapshot.tenantId else None),
            action=action,
            resourceType=resourceType,
            resourceId=str(resourceId or ""),
            ipAddress=snapshot.ipAddress[:64],
            userAgent=snapshot.userAgent[:300],
            beforeState=before,
            afterState=after,
            correlationId=snapshot.correlationId[:64],
            requestId=snapshot.requestId[:64],
        )


class InProcessEventDispatcher:
    """Post-commit domain-event publishing (§36) — modular monolith default.

    Handlers subscribe by event name; failures are logged, never propagated
    into the caller that already committed (outbox arrives with Phase 07+).

    EVOLUTION NOTE (Phase 09 §30): consumers in other contexts (e.g. the
    notification engine) subscribe once at boot, while composition roots
    instantiate this class per use case. The handler registry is therefore
    CLASS-LEVEL and shared by every instance — exactly the single-registry
    semantics a modular monolith needs. Swap the class (settings) for a
    broker-backed dispatcher without touching subscribers.
    """

    _sharedHandlers: dict[str, list[Any]] = {}

    def __init__(self) -> None:
        self.handlers: dict[str, list[Any]] = InProcessEventDispatcher._sharedHandlers
        self.fallbackHandler: Any = self.logEvent

    def subscribe(self, eventName: str, handler: Any) -> None:
        self.handlers.setdefault(eventName, []).append(handler)

    def dispatch(self, event: DomainEvent) -> None:
        for handler in self.handlers.get(event.name, [self.fallbackHandler]):
            try:
                handler(event)
            except Exception:  # noqa: BLE001 — boundary isolation
                logger.exception("Event handler failed", extra={"event": event.name})

    @staticmethod
    def logEvent(event: DomainEvent) -> None:
        logger.info("Domain event", extra={"eventName": event.name, "event": event.asDict()})


class CacheIdempotencyStore:
    """Fingerprint → stored response via the Django cache (§20).

    LocMem in development; Redis/Memcached in production by swapping the
    cache backend — the port stays identical.
    """

    cacheKeyPrefix = "tekarai:idempotency:"

    def lookup(self, key: str) -> tuple[int, dict[str, object]] | None:
        from django.core.cache import cache

        stored = cache.get(self.cacheKeyPrefix + key)
        if stored is None:
            return None
        statusPart, body = stored
        return int(statusPart), dict(body)

    def store(self, key: str, httpStatus: int, body: dict[str, object], ttlSeconds: int) -> None:
        from django.core.cache import cache

        cache.set(self.cacheKeyPrefix + key, (httpStatus, body), timeout=ttlSeconds)


class CacheRateLimiter:
    """Fixed-window counter on the Django cache (§23)."""

    cacheKeyPrefix = "tekarai:rateLimit:"

    def hit(self, scope: str, identity: str, limit: int, windowSeconds: int) -> int:
        from django.core.cache import cache

        key = f"{self.cacheKeyPrefix}{scope}:{identity}:{int(limit)}"
        try:
            counted = cache.incr(key)
        except ValueError:
            # Key absent in this window — start a fresh fixed window.
            cache.add(key, 1, timeout=windowSeconds)
            counted = 1
        return counted


__all__ = [
    "SystemClock",
    "UnitOfWorkDjango",
    "AuditRecorderDjango",
    "InProcessEventDispatcher",
    "CacheIdempotencyStore",
    "CacheRateLimiter",
]
