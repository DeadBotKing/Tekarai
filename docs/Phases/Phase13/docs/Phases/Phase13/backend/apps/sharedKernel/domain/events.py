"""Domain-event primitive (§46 field contract, framework-free)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DomainEvent:
    """Immutable fact raised inside a domain (never dispatched in-transaction)."""

    name: str
    occurredAt: datetime
    tenantId: uuid.UUID | None = None
    actorId: uuid.UUID | None = None
    correlationId: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def asDict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "occurredAt": self.occurredAt.isoformat(),
            "tenantId": str(self.tenantId) if self.tenantId else None,
            "actorId": str(self.actorId) if self.actorId else None,
            "correlationId": self.correlationId,
            "payload": self.payload,
        }
