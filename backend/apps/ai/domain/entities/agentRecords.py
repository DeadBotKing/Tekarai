"""Agent foundation entities for Phase 13-Y.

Four records implement the §31 composition *identity → instructions →
capabilities → tools → memory → policies* as a governed, versioned
registry entry:

- ``AIAgentDefinition`` — one **version** of one agent, with its
  instructions, its access level (the "what" half of OQ #11), its risk
  (the "who says yes" half), and the registry lifecycle that decides
  whether it may run at all. Versions are immutable: changing the
  instructions means a new version, so a run recorded last month can
  still be read against the contract it actually used;
- ``AIAgentApproval`` — one human decision about one requested run,
  bound to the **input fingerprint**; ``DUAL_CONTROL`` is why it is a
  record rather than a boolean;
- ``AIAgentRun`` — one requested run and what happened to it, from
  ``PENDING`` to a terminal state, with redacted input;
- ``AIAgentStep`` — one step of the plan-act loop (a model call or a
  tool call), written even when the answer was "no".

Pure dataclasses: no Django, ORM, HTTP, provider SDK, queue, or network
dependency. ``AIAgentRun.toDomainExecution`` bridges to the Phase 13-B
``AIAgentExecution`` primitive and ``AIAgentDefinition.toBaseAgent`` to
the Phase 13-B ``AIAgent`` primitive.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from apps.ai.domain.entities.aiRecords import AIAgent, AIAgentExecution, newId, requireUuid, utcNow
from apps.ai.domain.valueObjects.agentTypes import (
    MAX_AGENT_CONTEXT_TOKENS,
    MAX_AGENT_DESCRIPTION_LENGTH,
    MAX_AGENT_DURATION_SECONDS,
    MAX_AGENT_NAME_LENGTH,
    MAX_AGENT_STEPS,
    MAX_AGENT_TOOL_CALLS,
    accessEffectAllowlist,
    ensureAgentAccessLevel,
    ensureAgentCode,
    ensureAgentStatus,
    ensureAgentVersion,
    ensureStepKind,
    ensureStepStatus,
    inputFingerprint,
    redactInput,
)
from apps.ai.domain.valueObjects.aiTypes import AGENT_EXECUTION_STATUSES, ensureEnum
from apps.ai.domain.valueObjects.toolTypes import (
    MAX_TOOL_VERSION,
    ensureApprovalDecision,
    ensureApprovalMode,
    ensureRiskLevel,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

#: Registry lifecycle (§Y.5) — mirror of the Phase 13-X machine.
_AGENT_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"PENDING_APPROVAL", "RETIRED"},
    "PENDING_APPROVAL": {"APPROVED", "DRAFT", "RETIRED"},
    "APPROVED": {"SUSPENDED", "RETIRED"},
    "SUSPENDED": {"APPROVED", "RETIRED"},
    "RETIRED": set(),
}

#: Execution lifecycle — the Phase 13-B machine, kept exactly.
_RUN_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"RUNNING", "DENIED", "CANCELLED"},
    "RUNNING": {"COMPLETED", "FAILED", "CANCELLED"},
    "COMPLETED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
    "DENIED": set(),
}

#: Effective ceilings for one run — the absolute platform guards.
MAX_EFFECTIVE_STEPS = MAX_AGENT_STEPS
MAX_EFFECTIVE_TOOL_CALLS = MAX_AGENT_TOOL_CALLS
MAX_EFFECTIVE_DURATION_SECONDS = MAX_AGENT_DURATION_SECONDS


def _isPositiveInt(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _checkCeiling(policy: dict[str, Any], key: str, ceiling: int, label: str) -> None:
    if key not in policy:
        return
    value = policy[key]
    if not _isPositiveInt(value) or value > ceiling:
        raise ValidationFailedError(f"Agent {label}.{key} is out of range.")


@dataclass
class AIAgentDefinition:
    """One immutable version of one registered agent (§Y.4)."""

    tenantId: uuid.UUID
    code: str
    name: str
    instructions: str
    description: str = ""
    version: int = 1
    accessLevel: str = "ADVISORY"
    riskLevel: str = "LOW"
    capabilityCodes: tuple[str, ...] = ()
    toolCodes: tuple[str, ...] = ()
    outputSchema: dict[str, Any] = field(default_factory=dict)
    contextPolicy: dict[str, Any] = field(default_factory=dict)
    modelPolicy: dict[str, Any] = field(default_factory=dict)
    permissionPolicy: dict[str, Any] = field(default_factory=dict)
    executionPolicy: dict[str, Any] = field(default_factory=dict)
    declaredApprovalMode: str = ""
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
        self.code = ensureAgentCode(self.code)
        self.version = ensureAgentVersion(self.version)
        self.accessLevel = ensureAgentAccessLevel(self.accessLevel)
        self.riskLevel = ensureRiskLevel(self.riskLevel)
        self.status = ensureAgentStatus(self.status)
        if self.declaredApprovalMode:
            self.declaredApprovalMode = ensureApprovalMode(self.declaredApprovalMode)
        self.name = str(self.name or "").strip()
        self.description = str(self.description or "").strip()
        self.instructions = str(self.instructions or "").strip()
        if not self.name or not self.instructions:
            raise ValidationFailedError("Agent name and instructions are required.")
        if (
            len(self.name) > MAX_AGENT_NAME_LENGTH
            or len(self.description) > MAX_AGENT_DESCRIPTION_LENGTH
        ):
            raise ValidationFailedError("Agent name or description is too long.")
        self.capabilityCodes = tuple(
            str(code).strip().upper() for code in self.capabilityCodes if str(code).strip()
        )
        self.toolCodes = tuple(
            str(code).strip().upper() for code in self.toolCodes if str(code).strip()
        )
        for schemaName in (
            "outputSchema",
            "contextPolicy",
            "modelPolicy",
            "permissionPolicy",
            "executionPolicy",
        ):
            if not isinstance(getattr(self, schemaName), dict):
                raise ValidationFailedError(f"Agent {schemaName} must be a mapping.")
        self._validateExecutionPolicy()
        self._validateContextPolicy()
        if self.approvedBy is not None:
            self.approvedBy = requireUuid(self.approvedBy, "approvedBy")
        self.rejectionReason = str(self.rejectionReason or "").strip()[:500]
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Agent metadata must be a mapping.")

    def _validateExecutionPolicy(self) -> None:
        _checkCeiling(self.executionPolicy, "maxSteps", MAX_EFFECTIVE_STEPS, "executionPolicy")
        _checkCeiling(
            self.executionPolicy, "maxToolCalls", MAX_EFFECTIVE_TOOL_CALLS, "executionPolicy"
        )
        _checkCeiling(
            self.executionPolicy,
            "maxDurationSeconds",
            MAX_EFFECTIVE_DURATION_SECONDS,
            "executionPolicy",
        )

    def _validateContextPolicy(self) -> None:
        _checkCeiling(
            self.contextPolicy, "maxContextTokens", MAX_AGENT_CONTEXT_TOKENS, "contextPolicy"
        )

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
    def requiredPermission(self) -> str:
        value = str(self.permissionPolicy.get("requiredPermission", "") or "").strip().upper()
        return value or "AI_AGENT_RUN"

    def allowsEffect(self, effect: str) -> bool:
        """The structural access check (Y-D2): may this version propose it?"""

        return effect in accessEffectAllowlist(self.accessLevel)

    # -- lifecycle ------------------------------------------------------
    def transitionTo(self, status: str, *, now: datetime | None = None) -> None:
        target = ensureAgentStatus(status)
        if target != self.status and target not in _AGENT_TRANSITIONS[self.status]:
            raise ValidationFailedError(
                f"Invalid agent transition {self.status} → {target}.",
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
            raise ValidationFailedError("Rejecting an agent requires a reason.")
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

    def nextVersion(self, *, now: datetime | None = None, **overrides: Any) -> AIAgentDefinition:
        """Build the successor version; this definition stays untouched."""

        payload: dict[str, Any] = {
            "tenantId": self.tenantId,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "version": self.version + 1,
            "accessLevel": self.accessLevel,
            "riskLevel": self.riskLevel,
            "capabilityCodes": tuple(self.capabilityCodes),
            "toolCodes": tuple(self.toolCodes),
            "outputSchema": dict(self.outputSchema),
            "contextPolicy": dict(self.contextPolicy),
            "modelPolicy": dict(self.modelPolicy),
            "permissionPolicy": dict(self.permissionPolicy),
            "executionPolicy": dict(self.executionPolicy),
            "declaredApprovalMode": self.declaredApprovalMode,
            "metadata": dict(self.metadata),
            "createdAt": now or utcNow(),
            "updatedAt": now or utcNow(),
        }
        payload.update(overrides)
        return AIAgentDefinition(**payload)

    def toBaseAgent(self) -> AIAgent:
        """Bridge to the Phase 13-B ``AIAgent`` primitive."""

        return AIAgent(
            tenantId=self.tenantId,
            code=self.code,
            name=self.name,
            instructions=self.instructions,
            capabilityCodes=tuple(self.capabilityCodes),
            toolCodes=tuple(self.toolCodes),
            memoryScope="AGENT",
            contextPolicy=dict(self.contextPolicy),
            modelPolicy=dict(self.modelPolicy),
            permissionPolicy=dict(self.permissionPolicy),
            executionPolicy=dict(self.executionPolicy),
            id=self.id,
            isActive=self.isActive,
        )

    @property
    def isActive(self) -> bool:
        return self.status == "APPROVED"


@dataclass
class AIAgentApproval:
    """One human decision about one requested run (§Y.7)."""

    tenantId: uuid.UUID
    agentCode: str
    agentVersion: int
    inputFingerprint: str
    mode: str = "HUMAN_REQUIRED"
    decision: str = "PENDING"
    requiredApprovals: int = 1
    approvals: tuple[uuid.UUID, ...] = ()
    requestedBy: uuid.UUID | None = None
    executionId: uuid.UUID | None = None
    reason: str = ""
    expiresAt: datetime | None = None
    decidedAt: datetime | None = None
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.agentCode = ensureAgentCode(self.agentCode)
        self.agentVersion = ensureAgentVersion(self.agentVersion)
        self.mode = ensureApprovalMode(self.mode)
        self.decision = ensureApprovalDecision(self.decision)
        if self.requestedBy is not None:
            self.requestedBy = requireUuid(self.requestedBy, "requestedBy")
        if self.executionId is not None:
            self.executionId = requireUuid(self.executionId, "executionId")
        self.approvals = tuple(requireUuid(value, "approverId") for value in self.approvals)
        if not _isPositiveInt(self.requiredApprovals) or self.requiredApprovals > 5:
            raise ValidationFailedError("requiredApprovals is out of range.")
        self.reason = str(self.reason or "").strip()[:500]
        if len(str(self.inputFingerprint or "")) != 64:
            raise ValidationFailedError("Approval requires an input fingerprint.")
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
            raise ValidationFailedError("The requester cannot approve their own run.")
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
class AIAgentRun:
    """One requested run and what happened to it (§Y.8)."""

    tenantId: uuid.UUID
    agentId: uuid.UUID
    agentCode: str
    agentVersion: int
    input: dict[str, Any] = field(default_factory=dict)
    status: str = "PENDING"
    requestedBy: uuid.UUID | None = None
    inputFingerprint: str = ""
    answer: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    errorCode: str = ""
    approvalId: uuid.UUID | None = None
    startedAt: datetime | None = None
    completedAt: datetime | None = None
    latencyMs: int = 0
    modelCallCount: int = 0
    toolCallCount: int = 0
    inputTokens: int = 0
    outputTokens: int = 0
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.agentId = requireUuid(self.agentId, "agentId")
        self.agentCode = ensureAgentCode(self.agentCode)
        self.agentVersion = ensureAgentVersion(self.agentVersion)
        self.status = ensureEnum(self.status, AGENT_EXECUTION_STATUSES, "agentExecutionStatus")
        if self.requestedBy is not None:
            self.requestedBy = requireUuid(self.requestedBy, "requestedBy")
        if self.approvalId is not None:
            self.approvalId = requireUuid(self.approvalId, "approvalId")
        self.input = redactInput(self.input)
        if not isinstance(self.output, dict):
            raise ValidationFailedError("Agent run output must be a mapping.")
        self.errorCode = str(self.errorCode or "").strip().upper()
        self.answer = str(self.answer or "").strip()
        for name in ("latencyMs", "modelCallCount", "toolCallCount", "inputTokens", "outputTokens"):
            value = getattr(self, name)
            if not _isPositiveInt(value) and value != 0:
                raise ValidationFailedError(f"Agent run {name} must be a non-negative integer.")
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Agent run metadata must be a mapping.")
        if not self.inputFingerprint:
            self.inputFingerprint = inputFingerprint(self.agentCode, self.agentVersion, self.input)

    @property
    def qualifiedCode(self) -> str:
        return f"{self.agentCode}@{self.agentVersion}"

    @property
    def isTerminal(self) -> bool:
        return self.status in ("COMPLETED", "FAILED", "CANCELLED", "DENIED")

    def transitionTo(
        self, status: str, *, errorCode: str = "", now: datetime | None = None
    ) -> None:
        target = ensureEnum(status, AGENT_EXECUTION_STATUSES, "agentExecutionStatus")
        if target != self.status and target not in _RUN_TRANSITIONS[self.status]:
            raise ValidationFailedError(
                f"Invalid agent run transition {self.status} → {target}.",
                fieldErrors={"status": target},
            )
        moment = now or utcNow()
        if target == "RUNNING" and self.startedAt is None:
            self.startedAt = moment
        if target in ("COMPLETED", "FAILED", "CANCELLED", "DENIED"):
            self.completedAt = moment
            if self.startedAt is not None:
                self.latencyMs = max(0, int((moment - self.startedAt).total_seconds() * 1000))
        self.status = target
        if errorCode:
            self.errorCode = str(errorCode).strip().upper()

    def complete(
        self, answer: str = "", output: dict[str, Any] | None = None, *, now: datetime | None = None
    ) -> None:
        self.transitionTo("COMPLETED", now=now)
        self.answer = str(answer or "").strip()
        if output is not None:
            if not isinstance(output, dict):
                raise ValidationFailedError("Agent run output must be a mapping.")
            self.output = dict(output)
        self.errorCode = ""

    def fail(self, errorCode: str, *, now: datetime | None = None) -> None:
        self.transitionTo("FAILED", errorCode=errorCode or "AI_AGENT_EXECUTION_FAILED", now=now)

    def deny(self, errorCode: str = "AI_AGENT_DENIED", *, now: datetime | None = None) -> None:
        self.transitionTo("DENIED", errorCode=errorCode, now=now)

    def toDomainExecution(self) -> AIAgentExecution:
        """Bridge to the Phase 13-B ``AIAgentExecution`` primitive."""

        return AIAgentExecution(
            tenantId=self.tenantId,
            agentId=self.agentId,
            requestedBy=self.requestedBy,
            inputData=dict(self.input),
            id=self.id,
            status=self.status,
            outputData=dict(self.output),
            errorCode=self.errorCode,
            createdAt=self.createdAt,
        )


@dataclass
class AIAgentStep:
    """One step of the plan-act loop — a model call or a tool call.

    Steps are immutable and terminal when written; a denied tool call is
    still a row, so "what did the agent try?" always has an answer
    (Y-D7).
    """

    tenantId: uuid.UUID
    runId: uuid.UUID
    ordinal: int
    kind: str
    status: str = "SUCCEEDED"
    toolCode: str = ""
    toolVersion: int = 0
    arguments: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    tokensIn: int = 0
    tokensOut: int = 0
    latencyMs: int = 0
    errorCode: str = ""
    id: uuid.UUID = field(default_factory=newId)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.runId = requireUuid(self.runId, "runId")
        self.kind = ensureStepKind(self.kind)
        self.status = ensureStepStatus(self.status)
        if not _isPositiveInt(self.ordinal):
            raise ValidationFailedError("Agent step ordinal must be a positive integer.")
        self.toolCode = str(self.toolCode or "").strip().upper()
        if self.toolVersion and (
            not _isPositiveInt(self.toolVersion) or self.toolVersion > MAX_TOOL_VERSION
        ):
            raise ValidationFailedError("Agent step toolVersion is out of range.")
        if self.kind == "TOOL" and not self.toolCode:
            raise ValidationFailedError("A tool step requires a toolCode.")
        self.arguments = redactInput(self.arguments)
        if not isinstance(self.result, dict):
            raise ValidationFailedError("Agent step result must be a mapping.")
        self.reason = str(self.reason or "").strip()[:500]
        self.errorCode = str(self.errorCode or "").strip().upper()
        for name in ("tokensIn", "tokensOut", "latencyMs"):
            value = getattr(self, name)
            if not _isPositiveInt(value) and value != 0:
                raise ValidationFailedError(f"Agent step {name} must be a non-negative integer.")

    @property
    def isModelCall(self) -> bool:
        return self.kind == "MODEL"

    @property
    def isToolCall(self) -> bool:
        return self.kind == "TOOL"


def approvalExpiry(now: datetime, seconds: int) -> datetime:
    if not _isPositiveInt(seconds):
        raise ValidationFailedError("Approval expiry must be positive.")
    return now + timedelta(seconds=seconds)


__all__ = [
    "AIAgentApproval",
    "AIAgentDefinition",
    "AIAgentRun",
    "AIAgentStep",
    "MAX_EFFECTIVE_DURATION_SECONDS",
    "MAX_EFFECTIVE_STEPS",
    "MAX_EFFECTIVE_TOOL_CALLS",
    "approvalExpiry",
]
