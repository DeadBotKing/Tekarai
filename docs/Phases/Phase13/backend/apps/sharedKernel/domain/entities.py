"""Entity and aggregate-root primitives (framework-free).

Domain entities are pure Python: identifiers are UUIDs (§12 surrogate key),
aggregates record domain events that the application layer dispatches after
the transaction commits (§36 — side effects never inside the transaction).
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.sharedKernel.domain.events import DomainEvent


def newId() -> uuid.UUID:
    """New surrogate id (database-independent identity source)."""
    return uuid.uuid4()


class Entity:
    """Base class for domain entities identified by a surrogate UUID."""

    def __init__(self, id: uuid.UUID) -> None:  # noqa: A002 — domain vocabulary
        self.id = id

    def __eq__(self, other: object) -> bool:
        return type(self) is type(other) and getattr(other, "id", None) == self.id

    def __hash__(self) -> int:
        return hash((type(self).__name__, self.id))


class AggregateRoot(Entity):
    """Aggregate boundary (§47): the only transactional entry point.

    Collects domain events; ``pullEvents`` hands them to the dispatcher once
    the use case has persisted the aggregate (§8 step 6).
    """

    def __init__(self, id: uuid.UUID) -> None:  # noqa: A002
        super().__init__(id)
        self._events: list[DomainEvent] = []

    def recordEvent(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pullEvents(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events

    def pendingEventCount(self) -> int:
        return len(self._events)

    def snapshot(self) -> dict[str, Any]:
        """Plain-state view for audit before/after records (§19)."""
        raise NotImplementedError
