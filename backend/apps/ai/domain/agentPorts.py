"""Agent foundation ports for Phase 13-Y.

Minimal contracts the application layer depends on:

- ``AgentDefinitionStore`` / ``AgentApprovalStore`` / ``AgentExecutionStore``
  — persistence of the registry, of human approvals, and of runs/steps;
- ``AgentModelCaller`` — the model boundary. It accepts an
  ``AgentModelRequest`` and returns a frozen ``AgentModelReply``; no
  provider SDK is allowed to cross this boundary (Y-D10);
- ``AgentToolExecutor`` — the Phase 13-X boundary. The planner only ever
  sees this protocol, which is how the §30 rule ("the model never
  executes a tool") stays structural for agents too (Y-D3);
- ``AgentMemoryProvider`` / ``AgentKnowledgeProvider`` — the Phase 13-T
  and 13-R/S boundaries; both are fail-closed inside (K permission
  filter) and their absence means *empty context*, never *open context*
  (Y-D6);
- ``AgentCapabilityResolver`` — the Phase 13-F boundary: which
  capability codes are registered and active for the tenant;
- ``AgentPermissionChecker`` — the Phase 13-K boundary;
- ``AgentAuditLogger`` — the single Phase 13-O ledger append.

``datetime`` and ``uuid`` are typing-only; the module has no Django, ORM,
HTTP, provider SDK, Redis, queue, or network dependency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


class AgentDefinitionStore(Protocol):
    """Persistence contract for the agent registry."""

    def saveDefinition(self, definition: Any) -> Any: ...
    def updateDefinition(self, definition: Any) -> Any: ...
    def getDefinition(self, tenantId: UUID, definitionId: UUID) -> Any | None: ...
    def findVersion(self, tenantId: UUID, agentCode: str, version: int) -> Any | None: ...
    def listVersions(self, tenantId: UUID, agentCode: str) -> tuple[Any, ...]: ...
    def listDefinitions(
        self,
        tenantId: UUID,
        *,
        statuses: tuple[str, ...] = (),
        limit: int = 200,
    ) -> tuple[Any, ...]: ...


class AgentApprovalStore(Protocol):
    """Persistence contract for human approvals of runs."""

    def saveApproval(self, approval: Any) -> Any: ...
    def updateApproval(self, approval: Any) -> Any: ...
    def getApproval(self, tenantId: UUID, approvalId: UUID) -> Any | None: ...
    def findPending(self, tenantId: UUID, agentCode: str, fingerprint: str) -> Any | None: ...
    def findUsable(
        self, tenantId: UUID, agentCode: str, fingerprint: str, *, now: datetime | None = None
    ) -> Any | None: ...
    def findLatest(self, tenantId: UUID, agentCode: str, fingerprint: str) -> Any | None: ...
    def listApprovals(
        self, tenantId: UUID, *, decisions: tuple[str, ...] = (), limit: int = 200
    ) -> tuple[Any, ...]: ...


class AgentExecutionStore(Protocol):
    """Persistence contract for runs and their step rows."""

    def saveRun(self, run: Any) -> Any: ...
    def updateRun(self, run: Any) -> Any: ...
    def getRun(self, tenantId: UUID, runId: UUID) -> Any | None: ...
    def listRuns(
        self,
        tenantId: UUID,
        *,
        agentCode: str = "",
        statuses: tuple[str, ...] = (),
        limit: int = 200,
    ) -> tuple[Any, ...]: ...
    def saveStep(self, step: Any) -> Any: ...
    def listSteps(self, tenantId: UUID, runId: UUID) -> tuple[Any, ...]: ...
    def deleteSettledBefore(self, tenantId: UUID | None, cutoff: datetime) -> tuple[int, int]: ...


class AgentModelCaller(Protocol):
    """The model boundary (Y-D10): request in, frozen reply out."""

    def call(self, tenantId: Any, request: Any) -> Any: ...


class AgentToolExecutor(Protocol):
    """Phase 13-X boundary: runs one tool proposal through the §30 chain."""

    def execute(self, tenantId: Any, proposal: Any, *, principal: Any = None) -> Any: ...


class AgentMemoryProvider(Protocol):
    """Phase 13-T boundary: authorized memories for this agent run."""

    def contextFor(self, tenantId: Any, principal: Any, definition: Any) -> Any: ...


class AgentKnowledgeProvider(Protocol):
    """Phase 13-R/S boundary: authorized knowledge for this agent run."""

    def searchFor(self, tenantId: Any, principal: Any, definition: Any, query: str) -> Any: ...


class AgentCapabilityResolver(Protocol):
    """Phase 13-F boundary: which capability codes are available."""

    def availableCodes(self, tenantId: Any) -> frozenset[str]: ...


class AgentPermissionChecker(Protocol):
    """Phase 13-K: may this principal run this agent (and its tools)?"""

    def can(self, principal: Any, permissionCode: str, resource: Any) -> bool: ...


class AgentAuditLogger(Protocol):
    """The single Phase 13-O entry point Y needs (one ledger append)."""

    def logAudit(
        self,
        tenantId: Any,
        action: str,
        *,
        outcome: str = ...,
        errorCode: str = ...,
        actorId: Any = ...,
        contextSources: tuple[str, ...] | list[str] | None = ...,
        detail: dict[str, Any] | None = ...,
    ) -> Any: ...


__all__ = [
    "AgentApprovalStore",
    "AgentAuditLogger",
    "AgentCapabilityResolver",
    "AgentDefinitionStore",
    "AgentExecutionStore",
    "AgentKnowledgeProvider",
    "AgentMemoryProvider",
    "AgentModelCaller",
    "AgentPermissionChecker",
    "AgentToolExecutor",
]
