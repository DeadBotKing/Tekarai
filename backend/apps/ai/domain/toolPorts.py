"""Tool registry and execution ports for Phase 13-X.

Minimal contracts the application layer depends on:

- ``ToolDefinitionStore`` / ``ToolInvocationStore`` / ``ToolApprovalStore``
  — persistence of the registry, of what ran, and of who approved it;
- ``ToolRunner`` — the adapter that actually performs the work. It
  accepts an ``ExecutionTicket`` and nothing else, which is how the §30
  rule ("the model never executes a tool") is enforced by types rather
  than by convention;
- ``ToolPermissionChecker`` — the Phase 13-K boundary;
- ``ToolAuditLogger`` — the single Phase 13-O ledger append.

``datetime`` and ``uuid`` are typing-only; the module has no Django, ORM,
HTTP, provider SDK, Redis, queue, or network dependency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from apps.ai.domain.entities.toolRecords import (
    AIToolApproval,
    AIToolDefinition,
    AIToolInvocation,
)


class ToolDefinitionStore(Protocol):
    """Persistence contract for the tool registry."""

    def saveDefinition(self, definition: AIToolDefinition) -> AIToolDefinition: ...
    def updateDefinition(self, definition: AIToolDefinition) -> AIToolDefinition: ...
    def getDefinition(self, tenantId: UUID, definitionId: UUID) -> AIToolDefinition | None: ...
    def findVersion(
        self, tenantId: UUID, toolCode: str, version: int
    ) -> AIToolDefinition | None: ...
    def listVersions(self, tenantId: UUID, toolCode: str) -> tuple[AIToolDefinition, ...]: ...
    def listDefinitions(
        self, tenantId: UUID, *, statuses: tuple[str, ...] = (), limit: int = 200
    ) -> tuple[AIToolDefinition, ...]: ...


class ToolApprovalStore(Protocol):
    """Persistence contract for human approvals."""

    def saveApproval(self, approval: AIToolApproval) -> AIToolApproval: ...
    def updateApproval(self, approval: AIToolApproval) -> AIToolApproval: ...
    def getApproval(self, tenantId: UUID, approvalId: UUID) -> AIToolApproval | None: ...
    def findPending(
        self, tenantId: UUID, toolCode: str, fingerprint: str
    ) -> AIToolApproval | None: ...
    def findUsable(
        self, tenantId: UUID, toolCode: str, fingerprint: str, *, now: datetime | None = None
    ) -> AIToolApproval | None: ...
    def findLatest(
        self, tenantId: UUID, toolCode: str, fingerprint: str
    ) -> AIToolApproval | None: ...
    def listApprovals(
        self, tenantId: UUID, *, decisions: tuple[str, ...] = (), limit: int = 200
    ) -> tuple[AIToolApproval, ...]: ...


class ToolInvocationStore(Protocol):
    """Persistence contract for tool calls."""

    def saveInvocation(self, invocation: AIToolInvocation) -> AIToolInvocation: ...
    def updateInvocation(self, invocation: AIToolInvocation) -> AIToolInvocation: ...
    def getInvocation(self, tenantId: UUID, invocationId: UUID) -> AIToolInvocation | None: ...
    def listInvocations(
        self,
        tenantId: UUID,
        *,
        requestId: UUID | None = None,
        toolCode: str = "",
        statuses: tuple[str, ...] = (),
        limit: int = 200,
    ) -> tuple[AIToolInvocation, ...]: ...
    def fingerprintsForRequest(self, tenantId: UUID, requestId: UUID) -> tuple[str, ...]: ...
    def deleteInvocationsBefore(self, tenantId: UUID | None, cutoff: datetime) -> int: ...


class ToolRunner(Protocol):
    """Performs the work described by an ``ExecutionTicket``."""

    def supports(self, toolCode: str) -> bool: ...
    def run(self, tenantId: Any, ticket: Any) -> Any: ...


class ToolPermissionChecker(Protocol):
    """Phase 13-K: may this principal use this tool?"""

    def can(self, principal: Any, permissionCode: str, resource: Any) -> bool: ...


class ToolAuditLogger(Protocol):
    """The single Phase 13-O entry point X needs (one ledger append)."""

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
    "ToolApprovalStore",
    "ToolAuditLogger",
    "ToolDefinitionStore",
    "ToolInvocationStore",
    "ToolPermissionChecker",
    "ToolRunner",
]
