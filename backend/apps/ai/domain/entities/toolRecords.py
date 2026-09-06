"""Tool registry and execution entities for Phase 13-X.

Three records implement the §30 chain *registry → permission → execution*:

- ``AIToolDefinition`` — one **version** of one tool, with its schemas,
  its effect and risk, and the registry lifecycle that decides whether it
  may run at all. Versions are immutable: changing a schema means a new
  version, so a call recorded last month can still be read against the
  contract it actually used;
- ``AIToolApproval`` — one human decision about one proposed call. This
  is the workflow half of Open Question #10, and ``DUAL_CONTROL`` is why
  it is a record rather than a boolean;
- ``AIToolInvocation`` — one proposed call and what happened to it, from
  ``PENDING`` to a terminal state, with redacted arguments.

Pure dataclasses: no Django, ORM, HTTP, provider SDK, queue, or network
dependency. ``AIToolInvocation.toDomainExecution`` bridges to the
Phase 13-B ``AIToolExecution`` primitive.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from apps.ai.domain.entities.aiRecords import AIToolExecution, newId, requireUuid, utcNow
from apps.ai.domain.valueObjects.toolTypes import (
    MAX_CALLS_PER_REQUEST,
    MAX_TIMEOUT_SECONDS,
    argumentFingerprint,
    argumentSize,
    canonicalArguments,
    ensureApprovalDecision,
    ensureApprovalMode,
    ensureExecutionStatus,
    ensureRiskLevel,
    ensureToolCode,
    ensureToolEffect,
    ensureToolStatus,
    ensureToolVersion,
    redactArguments,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

#: Registry lifecycle (§X.5). ``RETIRED`` is terminal.
_TOOL_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"PENDING_APPROVAL", "RETIRED"},
    "PENDING_APPROVAL": {"APPROVED", "DRAFT", "RETIRED"},
    "APPROVED": {"SUSPENDED", "RETIRED"},
    "SUSPENDED": {"APPROVED", "RETIRED"},
    "RETIRED": set(),
}

#: Execution lifecycle mirrors the Phase 13-B machine exactly.
_EXECUTION_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"RUNNING", "DENIED", "CANCELLED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "CANCELLED"},
    "SUCCEEDED": set(),
    "FAILED": set(),
    "DENIED": set(),
    "CANCELLED": set(),
}

MAX_NAME_LENGTH = 160
MAX_DESCRIPTION_LENGTH = 1000


@dataclass
class AIToolDefinition:
    """One immutable version of one registered tool (§X.4)."""

    tenantId: uuid.UUID
    code: str
    name: str
    description: str
    version: int = 1
    effect: str = "READ_ONLY"
    riskLevel: str = "LOW"
    inputSchema: dict[str, Any] = field(default_factory=dict)
    outputSchema: dict[str, Any] = field(default_factory=dict)
    requiredPermission: str = ""
    declaredApprovalMode: str = ""
    timeoutSeconds: int = 30
    maxCallsPerRequest: int = 5
    status: str = "DRAFT"
    approvedBy: uuid.UUID | None = None
    approvedAt: datetime | None = None
    retiredAt: datetime | None = None
    rejectionReason: str = ""
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)
    updatedAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.code = ensureToolCode(self.code)
        self.version = ensureToolVersion(self.version)
        self.effect = ensureToolEffect(self.effect)
        self.riskLevel = ensureRiskLevel(self.riskLevel)
        self.status = ensureToolStatus(self.status)
        if self.declaredApprovalMode:
            self.declaredApprovalMode = ensureApprovalMode(self.declaredApprovalMode)
        self.name = str(self.name or "").strip()
        self.description = str(self.description or "").strip()
        if not self.name or not self.description:
            raise ValidationFailedError("Tool name and description are required.")
        if len(self.name) > MAX_NAME_LENGTH or len(self.description) > MAX_DESCRIPTION_LENGTH:
            raise ValidationFailedError("Tool name or description is too long.")
        for schemaName in ("inputSchema", "outputSchema"):
            if not isinstance(getattr(self, schemaName), dict):
                raise ValidationFailedError(f"Tool {schemaName} must be a mapping.")
        self.requiredPermission = str(self.requiredPermission or "").strip().upper()
        if self.approvedBy is not None:
            self.approvedBy = requireUuid(self.approvedBy, "approvedBy")
        for name, ceiling in (
            ("timeoutSeconds", MAX_TIMEOUT_SECONDS),
            ("maxCallsPerRequest", MAX_CALLS_PER_REQUEST),
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValidationFailedError(f"Tool {name} must be an integer.")
            if value < 1 or value > ceiling:
                raise ValidationFailedError(
                    f"Tool {name} is out of range.", fieldErrors={name: str(value)}
                )
        self.rejectionReason = str(self.rejectionReason or "").strip()[:500]
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Tool metadata must be a mapping.")

    # -- identity -------------------------------------------------------
    @property
    def qualifiedCode(self) -> str:
        return f"{self.code}@{self.version}"

    @property
    def isRunnable(self) -> bool:
        return self.status == "APPROVED"

    @property
    def isTerminal(self) -> bool:
        return self.status == "RETIRED"

    @property
    def mutatesState(self) -> bool:
        return self.effect in ("MUTATING", "EXTERNAL", "NOTIFYING")

    # -- lifecycle ------------------------------------------------------
    def transitionTo(self, status: str, *, now: datetime | None = None) -> None:
        target = ensureToolStatus(status)
        if target != self.status and target not in _TOOL_TRANSITIONS[self.status]:
            raise ValidationFailedError(
                f"Invalid tool transition {self.status} → {target}.",
                fieldErrors={"status": target},
            )
        self.status = target
        self.updatedAt = now or utcNow()

    def submitForApproval(self, *, now: datetime | None = None) -> None:
        self.transitionTo("PENDING_APPROVAL", now=now)
        self.rejectionReason = ""

    def approve(self, *, approverId: uuid.UUID | str, now: datetime | None = None) -> None:
        """Approve the registry entry. Self-approval of a draft is refused
        elsewhere (the application layer knows who submitted it)."""

        moment = now or utcNow()
        self.transitionTo("APPROVED", now=moment)
        self.approvedBy = requireUuid(approverId, "approverId")
        self.approvedAt = moment
        self.rejectionReason = ""

    def reject(self, reason: str, *, now: datetime | None = None) -> None:
        cleaned = str(reason or "").strip()
        if not cleaned:
            raise ValidationFailedError("Rejecting a tool requires a reason.")
        self.transitionTo("DRAFT", now=now)
        self.rejectionReason = cleaned[:500]

    def suspend(self, reason: str = "", *, now: datetime | None = None) -> None:
        self.transitionTo("SUSPENDED", now=now)
        if reason:
            self.rejectionReason = str(reason).strip()[:500]

    def resume(self, *, now: datetime | None = None) -> None:
        self.transitionTo("APPROVED", now=now)
        self.rejectionReason = ""

    def retire(self, *, now: datetime | None = None) -> None:
        moment = now or utcNow()
        self.transitionTo("RETIRED", now=moment)
        self.retiredAt = moment

    def nextVersion(self, *, now: datetime | None = None, **overrides: Any) -> AIToolDefinition:
        """Build the successor version; this definition stays untouched."""

        payload: dict[str, Any] = {
            "tenantId": self.tenantId,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "version": self.version + 1,
            "effect": self.effect,
            "riskLevel": self.riskLevel,
            "inputSchema": dict(self.inputSchema),
            "outputSchema": dict(self.outputSchema),
            "requiredPermission": self.requiredPermission,
            "declaredApprovalMode": self.declaredApprovalMode,
            "timeoutSeconds": self.timeoutSeconds,
            "maxCallsPerRequest": self.maxCallsPerRequest,
            "metadata": dict(self.metadata),
            "createdAt": now or utcNow(),
            "updatedAt": now or utcNow(),
        }
        payload.update(overrides)
        return AIToolDefinition(**payload)


@dataclass
class AIToolApproval:
    """One human decision about one proposed call (§X.7)."""

    tenantId: uuid.UUID
    toolCode: str
    toolVersion: int
    argumentFingerprint: str
    mode: str = "HUMAN_REQUIRED"
    decision: str = "PENDING"
    requiredApprovals: int = 1
    approvals: tuple[uuid.UUID, ...] = ()
    requestedBy: uuid.UUID | None = None
    invocationId: uuid.UUID | None = None
    reason: str = ""
    expiresAt: datetime | None = None
    decidedAt: datetime | None = None
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.toolCode = ensureToolCode(self.toolCode)
        self.toolVersion = ensureToolVersion(self.toolVersion)
        self.mode = ensureApprovalMode(self.mode)
        self.decision = ensureApprovalDecision(self.decision)
        if self.requestedBy is not None:
            self.requestedBy = requireUuid(self.requestedBy, "requestedBy")
        if self.invocationId is not None:
            self.invocationId = requireUuid(self.invocationId, "invocationId")
        self.approvals = tuple(requireUuid(value, "approverId") for value in self.approvals)
        if not isinstance(self.requiredApprovals, int) or isinstance(self.requiredApprovals, bool):
            raise ValidationFailedError("requiredApprovals must be an integer.")
        if self.requiredApprovals < 1 or self.requiredApprovals > 5:
            raise ValidationFailedError("requiredApprovals is out of range.")
        self.reason = str(self.reason or "").strip()[:500]
        if len(str(self.argumentFingerprint or "")) != 64:
            raise ValidationFailedError("Approval requires an argument fingerprint.")
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Approval metadata must be a mapping.")

    @property
    def isPending(self) -> bool:
        return self.decision == "PENDING"

    @property
    def isGranted(self) -> bool:
        return self.decision == "GRANTED"

    @property
    def remainingApprovals(self) -> int:
        return max(0, self.requiredApprovals - len(self.approvals))

    def isExpiredAt(self, now: datetime | None = None) -> bool:
        return self.expiresAt is not None and self.expiresAt <= (now or utcNow())

    def isUsableAt(self, now: datetime | None = None) -> bool:
        return self.isGranted and not self.isExpiredAt(now)

    def grant(self, approverId: uuid.UUID | str, *, now: datetime | None = None) -> None:
        """Record one approval; ``DUAL_CONTROL`` needs two distinct people.

        The same person approving twice is the exact failure dual control
        exists to prevent, so it is refused rather than counted.
        """

        if not self.isPending:
            raise ValidationFailedError("This approval has already been decided.")
        moment = now or utcNow()
        if self.isExpiredAt(moment):
            self.decision = "EXPIRED"
            self.decidedAt = moment
            raise ValidationFailedError("This approval request has expired.")
        approver = requireUuid(approverId, "approverId")
        if approver in self.approvals:
            raise ValidationFailedError("Dual control requires two distinct approvers.")
        if approver == self.requestedBy:
            raise ValidationFailedError("The requester cannot approve their own call.")
        self.approvals = self.approvals + (approver,)
        if len(self.approvals) >= self.requiredApprovals:
            self.decision = "GRANTED"
            self.decidedAt = moment

    def deny(
        self, reason: str, *, approverId: uuid.UUID | str | None = None, now: datetime | None = None
    ) -> None:
        if not self.isPending:
            raise ValidationFailedError("This approval has already been decided.")
        cleaned = str(reason or "").strip()
        if not cleaned:
            raise ValidationFailedError("Denying an approval requires a reason.")
        self.decision = "DENIED"
        self.reason = cleaned[:500]
        self.decidedAt = now or utcNow()
        if approverId is not None:
            self.approvals = self.approvals + (requireUuid(approverId, "approverId"),)

    def expire(self, *, now: datetime | None = None) -> None:
        if self.isPending:
            self.decision = "EXPIRED"
            self.decidedAt = now or utcNow()


@dataclass
class AIToolInvocation:
    """One proposed call and what happened to it (§X.8)."""

    tenantId: uuid.UUID
    toolCode: str
    toolVersion: int
    requestId: uuid.UUID | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
    status: str = "PENDING"
    result: dict[str, Any] = field(default_factory=dict)
    errorCode: str = ""
    approvalId: uuid.UUID | None = None
    actorId: uuid.UUID | None = None
    startedAt: datetime | None = None
    completedAt: datetime | None = None
    latencyMs: int = 0
    toolId: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.toolCode = ensureToolCode(self.toolCode)
        self.toolVersion = ensureToolVersion(self.toolVersion)
        self.status = ensureExecutionStatus(self.status)
        for name in ("requestId", "approvalId", "actorId", "toolId"):
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, requireUuid(value, name))
        self.arguments = redactArguments(canonicalArguments(self.arguments))
        if not isinstance(self.result, dict):
            raise ValidationFailedError("Tool result must be a mapping.")
        self.errorCode = str(self.errorCode or "").strip().upper()
        if not isinstance(self.latencyMs, int) or isinstance(self.latencyMs, bool):
            raise ValidationFailedError("Tool latencyMs must be an integer.")
        if self.latencyMs < 0:
            raise ValidationFailedError("Tool latencyMs cannot be negative.")
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Tool invocation metadata must be a mapping.")
        if not self.fingerprint:
            self.fingerprint = argumentFingerprint(self.toolCode, self.toolVersion, self.arguments)

    @property
    def qualifiedCode(self) -> str:
        return f"{self.toolCode}@{self.toolVersion}"

    @property
    def isTerminal(self) -> bool:
        return self.status in ("SUCCEEDED", "FAILED", "DENIED", "CANCELLED")

    @property
    def argumentBytes(self) -> int:
        return argumentSize(self.arguments)

    def transitionTo(
        self, status: str, *, errorCode: str = "", now: datetime | None = None
    ) -> None:
        target = ensureExecutionStatus(status)
        if target != self.status and target not in _EXECUTION_TRANSITIONS[self.status]:
            raise ValidationFailedError(
                f"Invalid tool execution transition {self.status} → {target}.",
                fieldErrors={"status": target},
            )
        moment = now or utcNow()
        if target == "RUNNING" and self.startedAt is None:
            self.startedAt = moment
        if target in ("SUCCEEDED", "FAILED", "DENIED", "CANCELLED"):
            self.completedAt = moment
            if self.startedAt is not None:
                self.latencyMs = max(0, int((moment - self.startedAt).total_seconds() * 1000))
        self.status = target
        if errorCode:
            self.errorCode = str(errorCode).strip().upper()

    def succeed(self, result: dict[str, Any], *, now: datetime | None = None) -> None:
        if not isinstance(result, dict):
            raise ValidationFailedError("Tool result must be a mapping.")
        self.transitionTo("SUCCEEDED", now=now)
        self.result = canonicalArguments(result)
        self.errorCode = ""

    def fail(self, errorCode: str, *, now: datetime | None = None) -> None:
        self.transitionTo("FAILED", errorCode=errorCode or "AI_TOOL_EXECUTION_FAILED", now=now)

    def deny(self, errorCode: str = "AI_TOOL_DENIED", *, now: datetime | None = None) -> None:
        self.transitionTo("DENIED", errorCode=errorCode, now=now)

    def toDomainExecution(self) -> AIToolExecution:
        """Bridge to the Phase 13-B ``AIToolExecution`` primitive."""

        if self.requestId is None or self.toolId is None:
            raise ValidationFailedError(
                "An invocation without requestId and toolId cannot be bridged."
            )
        return AIToolExecution(
            tenantId=self.tenantId,
            requestId=self.requestId,
            toolId=self.toolId,
            inputData=dict(self.arguments),
            id=self.id,
            status=self.status,
            outputData=dict(self.result),
            errorCode=self.errorCode,
            approved=self.approvalId is not None,
            createdAt=self.createdAt,
        )


def approvalExpiry(now: datetime, seconds: int) -> datetime:
    if seconds < 1:
        raise ValidationFailedError("Approval expiry must be positive.")
    return now + timedelta(seconds=seconds)


__all__ = [
    "MAX_DESCRIPTION_LENGTH",
    "MAX_NAME_LENGTH",
    "AIToolApproval",
    "AIToolDefinition",
    "AIToolInvocation",
    "approvalExpiry",
]
