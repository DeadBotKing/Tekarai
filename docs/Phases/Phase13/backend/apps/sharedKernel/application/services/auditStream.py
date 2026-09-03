"""Audit stream read contract (§19 visibility; §21 cursor pagination).

Application-level port: the platform audit trail is read as plain records
through keyset pagination — never via ORM objects leaking upward
(BR-PERF-002: append-only streams use cursors, not offsets).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class AuditStreamPage:
    items: list[dict[str, Any]]
    nextCursor: str
    hasNext: bool


@runtime_checkable
class AuditStreamReader(Protocol):
    def readPage(self, *, cursor: str = "", pageSize: int = 50) -> AuditStreamPage: ...
