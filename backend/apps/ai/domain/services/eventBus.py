"""Pure in-process event bus for Phase 13-P transport (§36).

``AIEventEnvelope`` is the transport-agnostic carrier: the event name is
restricted to ``AUDIT_ACTIONS`` (closed both ways — only known platform
events travel), the payload carries references and counts (never content
or secrets), and every envelope has its own id so queued delivery stays
idempotent.

``EventBusService`` fans one envelope out to every subscriber of its
event name. A failing subscriber never stops the others; every delivery
is reported in ``EventDispatchReport``. Durable delivery (surviving a
process restart) is the application layer's ``QueuedEventBus``, which
sends envelopes through the job queue — this service stays the
synchronous in-process fan-out both paths share.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.exceptions import AIError, AIEventInvalid
from apps.ai.domain.valueObjects.auditTypes import ensureAuditAction
from apps.ai.domain.valueObjects.usageTypes import asUtc


def _normalizeReference(value: Any) -> str:
    return str(value or "").strip()


def _normalizePayload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Event payload must be a mapping.")
    return {str(key): item for key, item in value.items()}


@dataclass(frozen=True)
class AIEventEnvelope:
    """One transport-agnostic platform event (§36)."""

    tenantId: uuid.UUID
    eventName: str
    envelopeId: uuid.UUID = field(default_factory=lambda: uuid.uuid4())
    occurredAt: datetime = field(default_factory=utcNow)
    payload: dict[str, Any] = field(default_factory=dict)
    correlationId: str = ""
    traceId: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenantId", requireUuid(self.tenantId, "tenantId"))
        object.__setattr__(self, "eventName", ensureAuditAction(self.eventName))
        object.__setattr__(self, "envelopeId", requireUuid(self.envelopeId, "envelopeId"))
        occurred = self.occurredAt
        if not isinstance(occurred, datetime):
            raise ValueError("Event occurredAt must be a datetime.")
        object.__setattr__(self, "occurredAt", asUtc(occurred))
        try:
            normalizedPayload = _normalizePayload(self.payload)
        except ValueError as exc:
            raise AIEventInvalid(str(exc)) from exc
        object.__setattr__(self, "payload", normalizedPayload)
        object.__setattr__(self, "correlationId", _normalizeReference(self.correlationId))
        object.__setattr__(self, "traceId", _normalizeReference(self.traceId))

    def toJobPayload(self) -> dict[str, Any]:
        """Serialize for an ``EVENT_DISPATCH`` job payload (JSON-safe keys)."""

        return {
            "envelopeId": str(self.envelopeId),
            "eventName": self.eventName,
            "tenantId": str(self.tenantId),
            "occurredAt": self.occurredAt.isoformat(),
            "payload": dict(self.payload),
            "correlationId": self.correlationId,
            "traceId": self.traceId,
        }

    @classmethod
    def fromJobPayload(cls, payload: Mapping[str, Any] | Any) -> AIEventEnvelope:
        """Rebuild an envelope; corrupt payloads raise ``AIEventInvalid``."""

        if not isinstance(payload, Mapping):
            raise AIEventInvalid("Event job payload must be a mapping.")
        tenantRaw = payload.get("tenantId")
        nameRaw = payload.get("eventName")
        envelopeRaw = payload.get("envelopeId")
        if (
            not isinstance(tenantRaw, (str, uuid.UUID))
            or not isinstance(nameRaw, str)
            or not isinstance(envelopeRaw, (str, uuid.UUID))
        ):
            raise AIEventInvalid("Event job payload identity is missing.")
        try:
            return cls(
                tenantId=requireUuid(tenantRaw, "tenantId"),
                eventName=ensureAuditAction(nameRaw),
                envelopeId=requireUuid(envelopeRaw, "envelopeId"),
                occurredAt=asUtc(datetime.fromisoformat(str(payload.get("occurredAt")))),
                payload=dict(payload.get("payload") or {}),
                correlationId=str(payload.get("correlationId") or ""),
                traceId=str(payload.get("traceId") or ""),
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIEventInvalid(f"Event job payload is corrupt: {exc}") from exc


@dataclass(frozen=True)
class SubscriberDelivery:
    subscriber: str
    delivered: bool
    error: str = ""


@dataclass(frozen=True)
class EventDispatchReport:
    tenantId: uuid.UUID
    eventName: str
    envelopeId: uuid.UUID
    deliveries: tuple[SubscriberDelivery, ...] = ()


class EventBusService:
    """In-process fan-out registry for event envelopes."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Any]] = {}

    def subscribe(self, eventName: str, subscriber: Any) -> Any:
        """Register ``subscriber`` for one event name (dupes ignored)."""

        normalized = ensureAuditAction(eventName)
        if not hasattr(subscriber, "handle") or not callable(subscriber.handle):
            raise AIEventInvalid("Event subscribers require a handle(envelope) method.")
        bucket = self._subscribers.setdefault(normalized, [])
        if subscriber not in bucket:
            bucket.append(subscriber)
        return subscriber

    def unsubscribe(self, eventName: str, subscriber: Any) -> None:
        normalized = ensureAuditAction(eventName)
        bucket = self._subscribers.get(normalized, [])
        if subscriber in bucket:
            bucket.remove(subscriber)

    def subscriberCount(self, eventName: str) -> int:
        return len(self._subscribers.get(ensureAuditAction(eventName), []))

    def dispatch(self, envelope: AIEventEnvelope) -> EventDispatchReport:
        """Deliver to every subscriber; one failure never stops the others."""

        if not isinstance(envelope, AIEventEnvelope):
            raise AIEventInvalid("Dispatch requires an AIEventEnvelope.")
        deliveries: list[SubscriberDelivery] = []
        for subscriber in list(self._subscribers.get(envelope.eventName, [])):
            try:
                subscriber.handle(envelope)
            except Exception as exc:
                deliveries.append(
                    SubscriberDelivery(
                        subscriber=type(subscriber).__name__,
                        delivered=False,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
            else:
                deliveries.append(
                    SubscriberDelivery(subscriber=type(subscriber).__name__, delivered=True)
                )
        return EventDispatchReport(
            tenantId=envelope.tenantId,
            eventName=envelope.eventName,
            envelopeId=envelope.envelopeId,
            deliveries=tuple(deliveries),
        )


AIEventBus = EventBusService
InMemoryEventBus = EventBusService

__all__ = [
    "AIEventBus",
    "AIEventEnvelope",
    "EventBusService",
    "EventDispatchReport",
    "InMemoryEventBus",
    "SubscriberDelivery",
]
