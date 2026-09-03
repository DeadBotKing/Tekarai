"""Command and Query message bases (Phase 06 §5–§7).

A Command asks the system to change state; a Query asks for data. Both are
dumb data carriers: no HTTP, no serialization concerns, no business rules.
DTOs returned by queries live next to their use cases.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    """Intent to change state — validated by the receiving use case (§53)."""


@dataclass(frozen=True)
class Query:
    """Intent to read state — must never mutate anything (§6)."""
