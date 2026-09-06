"""Infrastructure adapters for the Phase 13-Y agent boundaries.

Three adapters wire the Y ports to the platform's existing services:

- ``DjangoAgentCapabilityResolver`` — the Phase 13-F boundary: which
  capability codes are registered and active for the tenant;
- ``MemoryContextAdapter`` — the Phase 13-T boundary: it calls
  ``MemoryApplicationService.buildContextSources`` (which already ran
  the Phase 13-K filter) and shapes the result for the context builder;
- ``KnowledgeContextAdapter`` — the Phase 13-R/S boundary: it calls
  ``RetrievalApplicationService.retrieve`` (K-filtered inside) and
  shapes the result for the context builder.

Both source adapters are fail-closed: an error inside the underlying
service becomes an *empty* context, never a permissive one (Y-D6), and
absent configuration means the agent simply has no memory/knowledge.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.ai.domain.services.agentEngine import (
    AgentKnowledgeContext,
    AgentMemoryContext,
)
from apps.ai.domain.services.aiRules import estimateTokens

logger = logging.getLogger(__name__)


class DjangoAgentCapabilityResolver:
    """``AgentCapabilityResolver`` over the Phase 13-F capability table."""

    def availableCodes(self, tenantId: Any) -> frozenset[str]:
        from apps.ai.infrastructure.models import AICapabilityModel

        rows = AICapabilityModel.objects.filter(tenantId=tenantId, isActive=True).values_list(
            "code", flat=True
        )
        return frozenset(str(code).upper() for code in rows)


class MemoryContextAdapter:
    """``AgentMemoryProvider`` over the Phase 13-T memory service."""

    def __init__(self, memoryService: Any) -> None:
        self._memoryService = memoryService

    def contextFor(self, tenantId: Any, principal: Any, definition: Any) -> AgentMemoryContext:
        contextPolicy = dict(getattr(definition, "contextPolicy", {}) or {})
        try:
            result = self._memoryService.buildContextSources(
                tenantId,
                principal,
                scopes=("AGENT",),
                maxEntries=int(contextPolicy.get("maxMemoryEntries", 10)),
                maxTokens=int(contextPolicy.get("maxMemoryTokens", 2000)),
            )
        except Exception as exc:  # noqa: BLE001 — fail-closed, never permissive
            logger.warning("Agent memory context unavailable: %s", type(exc).__name__)
            return AgentMemoryContext()
        lines: list[str] = []
        sources: list[str] = []
        for entry in result.entries:
            value = getattr(entry, "value", "")
            rendered = value if isinstance(value, str) else str(value)
            key = getattr(entry, "key", "")
            scope = getattr(entry, "scope", "")
            lines.append(f"[memory {scope}:{key}] {rendered}")
            sources.append(f"memory:{scope}:{key}")
        return AgentMemoryContext(
            text="\n".join(lines),
            sources=tuple(sources),
            tokenCount=getattr(result, "tokenCount", 0) or estimateTokens("\n".join(lines)),
            entryCount=len(lines),
        )


class KnowledgeContextAdapter:
    """``AgentKnowledgeProvider`` over the Phase 13-R/S retrieval service."""

    def __init__(self, retrievalService: Any) -> None:
        self._retrievalService = retrievalService

    def searchFor(
        self, tenantId: Any, principal: Any, definition: Any, query: str
    ) -> AgentKnowledgeContext:
        if not query:
            return AgentKnowledgeContext()
        contextPolicy = dict(getattr(definition, "contextPolicy", {}) or {})
        spaceCode = str(contextPolicy.get("spaceCode", "") or "").strip().upper()
        if not spaceCode:
            # No vector space configured for this agent: no knowledge.
            return AgentKnowledgeContext()
        try:
            from apps.ai.application.services.retrievalService import RetrievalRequest
            from apps.ai.domain.valueObjects.retrievalTypes import RetrievalPolicy

            result = self._retrievalService.retrieve(
                tenantId,
                RetrievalRequest(
                    spaceCode=spaceCode,
                    question=query,
                    principal=principal,
                    policy=RetrievalPolicy(topK=int(contextPolicy.get("maxKnowledgeChunks", 5))),
                ),
            )
        except Exception as exc:  # noqa: BLE001 — fail-closed, never permissive
            logger.warning("Agent knowledge context unavailable: %s", type(exc).__name__)
            return AgentKnowledgeContext()
        lines: list[str] = []
        sources: list[str] = []
        for candidate in getattr(result, "candidates", ()) or ():
            content = getattr(candidate, "text", "") or ""
            ref = getattr(candidate, "sourceReference", "") or ""
            lines.append(f"[knowledge] {content}")
            if ref:
                sources.append(f"knowledge:{ref}")
        return AgentKnowledgeContext(
            text="\n".join(lines),
            sources=tuple(sources),
            tokenCount=estimateTokens("\n".join(lines)),
            chunkCount=len(lines),
        )


__all__ = [
    "DjangoAgentCapabilityResolver",
    "KnowledgeContextAdapter",
    "MemoryContextAdapter",
]
