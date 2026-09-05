"""Retrieval and RAG port interfaces for Phase 13-S.

S owns no storage. It reads through four narrow contracts, each matching
the surface of an existing sub-phase exactly so the real services satisfy
them structurally and S imports none of them:

- ``CandidateSearcher`` — Phase 13-Q semantic search;
- ``ChunkTextResolver`` — Phase 13-R chunk hydration and lexical listing;
- ``SourcePermissionFilter`` — the Phase 13-K fail-closed filter, the only
  authority on what a principal may see;
- ``GroundedGenerator`` — the provider surface used to answer from context
  (Phase 13-C ``generate``);
- ``RetrievalAuditLogger`` — the single Phase 13-O ledger append.

``uuid`` is typing-only; the module has no Django, ORM, HTTP, provider SDK,
Redis, queue, or network dependency.
"""

from __future__ import annotations

from typing import Any, Protocol


class CandidateSearcher(Protocol):
    """Phase 13-Q: nearest-neighbour search inside one vector space."""

    def searchSimilar(self, tenantId: Any, query: Any) -> Any: ...


class ChunkTextResolver(Protocol):
    """Phase 13-R: hydrate ranked hits back into chunk text."""

    def resolveChunks(self, tenantId: Any, chunkIds: Any) -> Any: ...
    def listSources(
        self, tenantId: Any, *, statuses: tuple[str, ...] = ..., sourceDomain: str = ...
    ) -> Any: ...
    def listChunks(self, tenantId: Any, sourceId: Any) -> Any: ...


class SourcePermissionFilter(Protocol):
    """Phase 13-K: the fail-closed permission boundary."""

    def filterSources(
        self, principal: Any, sources: Any, *, action: Any = ..., now: Any = ...
    ) -> Any: ...


class GroundedGenerator(Protocol):
    """Phase 13-C provider surface used for the answer step."""

    def generate(self, *, prompt: str, model: str, **kwargs: Any) -> Any: ...


class RetrievalAuditLogger(Protocol):
    """The single Phase 13-O entry point S needs (one ledger append)."""

    def logAudit(
        self,
        tenantId: Any,
        action: str,
        *,
        outcome: str = ...,
        classification: str = ...,
        errorCode: str = ...,
        actorId: Any = ...,
        contextSources: tuple[str, ...] | list[str] | None = ...,
        detail: dict[str, Any] | None = ...,
    ) -> Any: ...


__all__ = [
    "CandidateSearcher",
    "ChunkTextResolver",
    "GroundedGenerator",
    "RetrievalAuditLogger",
    "SourcePermissionFilter",
]
