"""Application orchestration for the Phase 13-X tool platform.

``ToolApplicationService`` implements the §30 chain end to end —
*registry → permission check → execution → result* — and enforces the
rule that gives the chapter its point: **the model never executes a
tool**. What the model produces is a ``ToolProposal``; what a runner
accepts is an ``ExecutionTicket``; and the only way from one to the other
runs through registry resolution, the Phase 13-K permission check, and
(for risky tools) a human approval.

Behaviour worth stating once:

- **Approval is driven by risk, not by trust.** ``ToolPolicy`` maps risk
  onto ``AUTOMATIC`` / ``HUMAN_REQUIRED`` / ``DUAL_CONTROL``; a tool may
  declare a *stricter* mode than the platform requires, never a looser
  one. That closes Open Question #10.
- **Dual control means two people.** The same approver twice is refused,
  and so is the requester approving their own call.
- **A denied call is recorded, not dropped.** Every proposal becomes an
  invocation row with a terminal status, so "what did the agent try?" is
  answerable even when the answer is "nothing, we said no".
- **Arguments are redacted before they are stored**, using the same
  secret-key list the Phase 13-O scrubber uses.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings as djangoSettings

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.toolRecords import (
    AIToolApproval,
    AIToolDefinition,
    AIToolInvocation,
    approvalExpiry,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIToolAlreadyRegistered,
    AIToolApprovalNotFound,
    AIToolDenied,
    AIToolExecutionFailed,
    AIToolInvalid,
    AIToolNotApproved,
    AIToolNotFound,
)
from apps.ai.domain.services.toolEngine import (
    ArgumentValidator,
    ExecutionBudget,
    ExecutionTicket,
    GateDecision,
    ToolGatekeeper,
    ToolProposal,
    ToolRegistry,
    prepareExecution,
)
from apps.ai.domain.toolPorts import (
    ToolApprovalStore,
    ToolAuditLogger,
    ToolDefinitionStore,
    ToolInvocationStore,
    ToolPermissionChecker,
    ToolRunner,
)
from apps.ai.domain.valueObjects.toolTypes import (
    ToolPolicy,
    ensureApprovalDecision,
    ensureRiskLevel,
    ensureToolCode,
    ensureToolEffect,
    ensureToolStatus,
    redactArguments,
)

#: Audit actions appended by X (registered in the Phase 13-O vocabulary).
AUDIT_TOOL_REGISTERED = "TOOL_REGISTERED"
AUDIT_TOOL_APPROVED = "TOOL_APPROVED"
AUDIT_TOOL_INVOKED = "TOOL_INVOKED"
AUDIT_TOOL_DENIED = "TOOL_DENIED"

#: Permission required to use a tool that declares none of its own.
DEFAULT_TOOL_PERMISSION = "AI_TOOL_EXECUTE"


@dataclass(frozen=True)
class ToolSettings:
    """Configuration-driven defaults (Master Specification §42)."""

    enabled: bool = True
    automaticBelowRisk: str = "HIGH"
    dualControlAtRisk: str = "CRITICAL"
    maxCallsPerRequest: int = 10
    maxRepeatsPerRequest: int = 2
    defaultTimeoutSeconds: int = 30
    maxArgumentBytes: int = 16_384
    approvalTtlSeconds: int = 3600
    retentionDays: int = 365

    def __post_init__(self) -> None:
        if self.maxRepeatsPerRequest < 1:
            raise AIConfigurationError("aiToolMaxRepeatsPerRequest must be positive.")
        if self.approvalTtlSeconds < 1:
            raise AIConfigurationError("aiToolApprovalTtlSeconds must be positive.")
        if self.retentionDays < 1:
            raise AIConfigurationError("aiToolRetentionDays must be positive.")
        # Building the policy here means an impossible configuration fails
        # at construction, not on the first invocation.
        self.policy()

    def policy(self) -> ToolPolicy:
        return ToolPolicy(
            automaticBelowRisk=self.automaticBelowRisk,
            dualControlAtRisk=self.dualControlAtRisk,
            maxCallsPerRequest=self.maxCallsPerRequest,
            defaultTimeoutSeconds=self.defaultTimeoutSeconds,
            maxArgumentBytes=self.maxArgumentBytes,
        )

    @classmethod
    def fromDjangoSettings(cls) -> ToolSettings:
        return cls(
            enabled=bool(getattr(djangoSettings, "AI_TOOL_ENABLED", True)),
            automaticBelowRisk=str(
                getattr(djangoSettings, "AI_TOOL_AUTOMATIC_BELOW_RISK", "HIGH") or "HIGH"
            ),
            dualControlAtRisk=str(
                getattr(djangoSettings, "AI_TOOL_DUAL_CONTROL_AT_RISK", "CRITICAL") or "CRITICAL"
            ),
            maxCallsPerRequest=int(
                getattr(djangoSettings, "AI_TOOL_MAX_CALLS_PER_REQUEST", 10) or 10
            ),
            maxRepeatsPerRequest=int(
                getattr(djangoSettings, "AI_TOOL_MAX_REPEATS_PER_REQUEST", 2) or 2
            ),
            defaultTimeoutSeconds=int(getattr(djangoSettings, "AI_TOOL_TIMEOUT_SECONDS", 30) or 30),
            maxArgumentBytes=int(
                getattr(djangoSettings, "AI_TOOL_MAX_ARGUMENT_BYTES", 16_384) or 16_384
            ),
            approvalTtlSeconds=int(
                getattr(djangoSettings, "AI_TOOL_APPROVAL_TTL_SECONDS", 3600) or 3600
            ),
            retentionDays=int(getattr(djangoSettings, "AI_TOOL_RETENTION_DAYS", 365) or 365),
        )


@dataclass(frozen=True)
class RegisterToolCommand:
    """Add one tool version to the registry, in ``DRAFT`` (§X.5)."""

    code: str
    name: str
    description: str
    effect: str = "READ_ONLY"
    riskLevel: str = "LOW"
    inputSchema: dict[str, Any] = field(default_factory=dict)
    outputSchema: dict[str, Any] = field(default_factory=dict)
    requiredPermission: str = ""
    declaredApprovalMode: str = ""
    timeoutSeconds: int = 30
    maxCallsPerRequest: int = 5
    version: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InvokeToolCommand:
    """One proposed call, exactly as the model produced it (§X.8)."""

    toolCode: str
    arguments: dict[str, Any] = field(default_factory=dict)
    version: int | None = None
    principal: Any = None
    requestId: uuid.UUID | None = None
    actorId: uuid.UUID | None = None
    reason: str = ""
    approvalId: uuid.UUID | None = None


@dataclass(frozen=True)
class ToolDescriptor:
    """Safe read model of one registry entry."""

    toolId: uuid.UUID
    code: str
    version: int
    qualifiedCode: str
    name: str
    effect: str
    riskLevel: str
    status: str
    approvalMode: str
    requiredPermission: str
    timeoutSeconds: int
    maxCallsPerRequest: int
    approvedBy: uuid.UUID | None
    rejectionReason: str
    createdAt: datetime

    @classmethod
    def of(cls, definition: AIToolDefinition, *, approvalMode: str = "") -> ToolDescriptor:
        return cls(
            toolId=definition.id,
            code=definition.code,
            version=definition.version,
            qualifiedCode=definition.qualifiedCode,
            name=definition.name,
            effect=definition.effect,
            riskLevel=definition.riskLevel,
            status=definition.status,
            approvalMode=approvalMode or definition.declaredApprovalMode,
            requiredPermission=definition.requiredPermission,
            timeoutSeconds=definition.timeoutSeconds,
            maxCallsPerRequest=definition.maxCallsPerRequest,
            approvedBy=definition.approvedBy,
            rejectionReason=definition.rejectionReason,
            createdAt=definition.createdAt,
        )


@dataclass(frozen=True)
class ApprovalDescriptor:
    """Safe read model of one approval request."""

    approvalId: uuid.UUID
    toolCode: str
    toolVersion: int
    mode: str
    decision: str
    requiredApprovals: int
    grantedCount: int
    remaining: int
    requestedBy: uuid.UUID | None
    reason: str
    expiresAt: datetime | None
    decidedAt: datetime | None

    @classmethod
    def of(cls, approval: AIToolApproval) -> ApprovalDescriptor:
        return cls(
            approvalId=approval.id,
            toolCode=approval.toolCode,
            toolVersion=approval.toolVersion,
            mode=approval.mode,
            decision=approval.decision,
            requiredApprovals=approval.requiredApprovals,
            grantedCount=len(approval.approvals),
            remaining=approval.remainingApprovals,
            requestedBy=approval.requestedBy,
            reason=approval.reason,
            expiresAt=approval.expiresAt,
            decidedAt=approval.decidedAt,
        )


@dataclass(frozen=True)
class InvocationDescriptor:
    """Safe read model of one call — arguments are already redacted."""

    invocationId: uuid.UUID
    toolCode: str
    toolVersion: int
    status: str
    errorCode: str
    result: dict[str, Any]
    latencyMs: int
    fingerprint: str
    approvalId: uuid.UUID | None
    requestId: uuid.UUID | None
    actorId: uuid.UUID | None
    createdAt: datetime

    @classmethod
    def of(cls, invocation: AIToolInvocation) -> InvocationDescriptor:
        return cls(
            invocationId=invocation.id,
            toolCode=invocation.toolCode,
            toolVersion=invocation.toolVersion,
            status=invocation.status,
            errorCode=invocation.errorCode,
            result=dict(invocation.result),
            latencyMs=invocation.latencyMs,
            fingerprint=invocation.fingerprint,
            approvalId=invocation.approvalId,
            requestId=invocation.requestId,
            actorId=invocation.actorId,
            createdAt=invocation.createdAt,
        )


@dataclass(frozen=True)
class InvocationResult:
    """The outcome of one proposal (§X.8)."""

    invocation: InvocationDescriptor
    decision: GateDecision | None = None
    approval: ApprovalDescriptor | None = None

    @property
    def succeeded(self) -> bool:
        return self.invocation.status == "SUCCEEDED"

    @property
    def awaitingApproval(self) -> bool:
        return (
            self.invocation.status == "PENDING"
            and self.approval is not None
            and self.approval.decision == "PENDING"
        )


class ToolApplicationService:
    """Tenant-scoped facade for the registry, approvals, and execution."""

    def __init__(
        self,
        definitionStore: ToolDefinitionStore,
        invocationStore: ToolInvocationStore,
        approvalStore: ToolApprovalStore,
        *,
        runners: Sequence[ToolRunner] = (),
        permissionChecker: ToolPermissionChecker | None = None,
        settings: ToolSettings | None = None,
        auditLogger: ToolAuditLogger | None = None,
        validator: ArgumentValidator | None = None,
        gatekeeper: ToolGatekeeper | None = None,
        now: Any = utcNow,
    ) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self.definitionStore = definitionStore
        self.invocationStore = invocationStore
        self.approvalStore = approvalStore
        self.runners = list(runners)
        self.permissionChecker = permissionChecker
        self.settings = settings or ToolSettings()
        self.auditLogger = auditLogger
        self.validator = validator or ArgumentValidator()
        self.gatekeeper = gatekeeper or ToolGatekeeper()
        self._now = now

    # ------------------------------------------------------------------
    # Registry (§X.5)
    # ------------------------------------------------------------------
    def registerTool(
        self, tenantId: uuid.UUID | str, command: RegisterToolCommand
    ) -> ToolDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(command, RegisterToolCommand):
            raise AIToolInvalid("Registering requires a RegisterToolCommand.")
        code = ensureToolCode(command.code)
        existing = self.definitionStore.listVersions(tenant, code)
        version = command.version or (max((item.version for item in existing), default=0) + 1)
        if any(item.version == version for item in existing):
            raise AIToolAlreadyRegistered(f"{code}@{version}")
        moment = self._now()
        definition = AIToolDefinition(
            tenantId=tenant,
            code=code,
            name=command.name,
            description=command.description,
            version=version,
            effect=ensureToolEffect(command.effect),
            riskLevel=ensureRiskLevel(command.riskLevel),
            inputSchema=dict(command.inputSchema),
            outputSchema=dict(command.outputSchema),
            requiredPermission=command.requiredPermission or DEFAULT_TOOL_PERMISSION,
            declaredApprovalMode=command.declaredApprovalMode,
            timeoutSeconds=command.timeoutSeconds,
            maxCallsPerRequest=command.maxCallsPerRequest,
            metadata=dict(command.metadata),
            createdAt=moment,
            updatedAt=moment,
        )
        stored = self.definitionStore.saveDefinition(definition)
        self._audit(
            tenant,
            AUDIT_TOOL_REGISTERED,
            outcome="RECORDED",
            contextSources=(stored.qualifiedCode,),
            detail={
                "effect": stored.effect,
                "riskLevel": stored.riskLevel,
                "approvalMode": self.settings.policy().modeFor(
                    stored.riskLevel, stored.declaredApprovalMode
                ),
            },
        )
        return self._describe(stored)

    def submitForApproval(
        self, tenantId: uuid.UUID | str, toolCode: str, version: int
    ) -> ToolDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireVersion(tenant, toolCode, version)
        definition.submitForApproval(now=self._now())
        return self._describe(self.definitionStore.updateDefinition(definition))

    def approveTool(
        self,
        tenantId: uuid.UUID | str,
        toolCode: str,
        version: int,
        *,
        approverId: uuid.UUID | str,
    ) -> ToolDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireVersion(tenant, toolCode, version)
        definition.approve(approverId=approverId, now=self._now())
        stored = self.definitionStore.updateDefinition(definition)
        self._audit(
            tenant,
            AUDIT_TOOL_APPROVED,
            outcome="ALLOWED",
            actorId=stored.approvedBy,
            contextSources=(stored.qualifiedCode,),
            detail={"riskLevel": stored.riskLevel, "effect": stored.effect},
        )
        return self._describe(stored)

    def rejectTool(
        self, tenantId: uuid.UUID | str, toolCode: str, version: int, reason: str
    ) -> ToolDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireVersion(tenant, toolCode, version)
        definition.reject(reason, now=self._now())
        stored = self.definitionStore.updateDefinition(definition)
        self._audit(
            tenant,
            AUDIT_TOOL_DENIED,
            outcome="DENIED",
            contextSources=(stored.qualifiedCode,),
            detail={"reason": stored.rejectionReason, "stage": "REGISTRY"},
        )
        return self._describe(stored)

    def suspendTool(
        self, tenantId: uuid.UUID | str, toolCode: str, version: int, reason: str = ""
    ) -> ToolDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireVersion(tenant, toolCode, version)
        definition.suspend(reason, now=self._now())
        return self._describe(self.definitionStore.updateDefinition(definition))

    def resumeTool(self, tenantId: uuid.UUID | str, toolCode: str, version: int) -> ToolDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireVersion(tenant, toolCode, version)
        definition.resume(now=self._now())
        return self._describe(self.definitionStore.updateDefinition(definition))

    def retireTool(self, tenantId: uuid.UUID | str, toolCode: str, version: int) -> ToolDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireVersion(tenant, toolCode, version)
        definition.retire(now=self._now())
        return self._describe(self.definitionStore.updateDefinition(definition))

    def publishNewVersion(
        self, tenantId: uuid.UUID | str, toolCode: str, **overrides: Any
    ) -> ToolDescriptor:
        """Clone the newest version into a fresh ``DRAFT`` (§X.5)."""

        tenant = requireUuid(tenantId, "tenantId")
        versions = self.definitionStore.listVersions(tenant, ensureToolCode(toolCode))
        if not versions:
            raise AIToolNotFound(ensureToolCode(toolCode))
        successor = versions[-1].nextVersion(now=self._now(), **overrides)
        return self._describe(self.definitionStore.saveDefinition(successor))

    def describeTool(
        self, tenantId: uuid.UUID | str, toolCode: str, version: int
    ) -> ToolDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        return self._describe(self._requireVersion(tenant, toolCode, version))

    def listTools(
        self, tenantId: uuid.UUID | str, *, statuses: tuple[str, ...] = (), limit: int = 200
    ) -> tuple[ToolDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        definitions = self.definitionStore.listDefinitions(
            tenant,
            statuses=tuple(ensureToolStatus(value) for value in statuses),
            limit=limit,
        )
        return tuple(self._describe(item) for item in definitions)

    def registry(self, tenantId: uuid.UUID | str) -> ToolRegistry:
        """The registry view a caller (or an agent in Y) resolves against."""

        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        return ToolRegistry(self.definitionStore.listDefinitions(tenant, limit=500))

    # ------------------------------------------------------------------
    # Execution (§30 chain)
    # ------------------------------------------------------------------
    def invokeTool(self, tenantId: uuid.UUID | str, command: InvokeToolCommand) -> InvocationResult:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(command, InvokeToolCommand):
            raise AIToolInvalid("Invoking requires an InvokeToolCommand.")
        policy = self.settings.policy()
        proposal = ToolProposal(
            toolCode=command.toolCode,
            arguments=command.arguments,
            version=command.version,
            requestId=command.requestId,
            actorId=command.actorId,
            reason=command.reason,
        )

        # 1. Registry.
        definition = self.registry(tenant).resolve(proposal.toolCode, proposal.version)

        # 2. Arguments (before anything is persisted or approved).
        canonical = self.validator.validate(definition, proposal.arguments, policy)
        fingerprint = proposal.fingerprintFor(definition.version)

        # 3. Budget and loop detection for this request.
        if command.requestId is not None:
            budget = ExecutionBudget(
                maxCalls=min(policy.maxCallsPerRequest, definition.maxCallsPerRequest),
                maxRepeats=self.settings.maxRepeatsPerRequest,
            )
            history = self.invocationStore.fingerprintsForRequest(
                tenant, requireUuid(command.requestId, "requestId")
            )
            budget.check(fingerprint, history)

        invocation = AIToolInvocation(
            tenantId=tenant,
            toolCode=definition.code,
            toolVersion=definition.version,
            requestId=command.requestId,
            arguments=redactArguments(canonical),
            fingerprint=fingerprint,
            actorId=command.actorId,
            toolId=definition.id,
            createdAt=self._now(),
        )
        invocation = self.invocationStore.saveInvocation(invocation)

        # 4. Permission check (Phase 13-K) and approval state.
        permitted = self._checkPermission(command.principal, definition)
        approval = self._resolveApproval(tenant, definition, fingerprint, command)
        decision = self.gatekeeper.decide(
            definition, policy, permitted=permitted, approval=approval, now=self._now()
        )

        if decision.blocked and decision.errorCode == "AI_TOOL_APPROVAL_REQUIRED":
            pending = approval or self._openApproval(
                tenant, definition, fingerprint, invocation, command, policy
            )
            self._audit(
                tenant,
                AUDIT_TOOL_INVOKED,
                outcome="RECORDED",
                actorId=command.actorId,
                contextSources=(definition.qualifiedCode,),
                detail={
                    "invocationId": str(invocation.id),
                    "state": "AWAITING_APPROVAL",
                    "mode": decision.approvalMode,
                },
            )
            return InvocationResult(
                invocation=InvocationDescriptor.of(invocation),
                decision=decision,
                approval=ApprovalDescriptor.of(pending),
            )

        if decision.blocked:
            invocation.deny(decision.errorCode or "AI_TOOL_DENIED", now=self._now())
            stored = self.invocationStore.updateInvocation(invocation)
            self._audit(
                tenant,
                AUDIT_TOOL_DENIED,
                outcome="DENIED",
                actorId=command.actorId,
                errorCode=stored.errorCode,
                contextSources=(definition.qualifiedCode,),
                detail={"invocationId": str(stored.id), "reason": decision.reason},
            )
            if decision.errorCode == "AI_TOOL_NOT_APPROVED":
                raise AIToolNotApproved(decision.reason)
            raise AIToolDenied(decision.reason)

        # 5. Execution — only ever through a ticket.
        ticket = prepareExecution(decision, canonical, policy=policy, approval=approval)
        return self._execute(tenant, invocation, ticket, command)

    def _execute(
        self,
        tenant: uuid.UUID,
        invocation: AIToolInvocation,
        ticket: ExecutionTicket,
        command: InvokeToolCommand,
    ) -> InvocationResult:
        runner = self._runnerFor(ticket.definition.code)
        invocation.transitionTo("RUNNING", now=self._now())
        self.invocationStore.updateInvocation(invocation)
        try:
            raw = runner.run(tenant, ticket)
        except Exception as error:  # noqa: BLE001 - recorded, then re-raised
            invocation.fail(
                str(getattr(error, "code", "AI_TOOL_EXECUTION_FAILED")), now=self._now()
            )
            stored = self.invocationStore.updateInvocation(invocation)
            self._audit(
                tenant,
                AUDIT_TOOL_INVOKED,
                outcome="FAILED",
                actorId=command.actorId,
                errorCode=stored.errorCode,
                contextSources=(ticket.qualifiedCode,),
                detail={"invocationId": str(stored.id), "message": str(error)[:200]},
            )
            raise AIToolExecutionFailed(str(error) or "The tool failed.") from error

        result = self.validator.validateOutput(ticket.definition, raw or {})
        invocation.succeed(result, now=self._now())
        stored = self.invocationStore.updateInvocation(invocation)
        self._audit(
            tenant,
            AUDIT_TOOL_INVOKED,
            outcome="SUCCEEDED",
            actorId=command.actorId,
            contextSources=(ticket.qualifiedCode,),
            detail={
                "invocationId": str(stored.id),
                "latencyMs": stored.latencyMs,
                "effect": ticket.definition.effect,
                "riskLevel": ticket.definition.riskLevel,
            },
        )
        return InvocationResult(
            invocation=InvocationDescriptor.of(stored), decision=ticket.decision
        )

    # ------------------------------------------------------------------
    # Approvals (§X.7 — Open Question #10)
    # ------------------------------------------------------------------
    def grantApproval(
        self,
        tenantId: uuid.UUID | str,
        approvalId: uuid.UUID | str,
        *,
        approverId: uuid.UUID | str,
    ) -> ApprovalDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        approval = self._requireApproval(tenant, approvalId)
        approval.grant(approverId, now=self._now())
        stored = self.approvalStore.updateApproval(approval)
        self._audit(
            tenant,
            AUDIT_TOOL_APPROVED,
            outcome="ALLOWED" if stored.isGranted else "RECORDED",
            actorId=requireUuid(approverId, "approverId"),
            contextSources=(f"{stored.toolCode}@{stored.toolVersion}",),
            detail={
                "approvalId": str(stored.id),
                "decision": stored.decision,
                "remaining": stored.remainingApprovals,
            },
        )
        return ApprovalDescriptor.of(stored)

    def denyApproval(
        self,
        tenantId: uuid.UUID | str,
        approvalId: uuid.UUID | str,
        reason: str,
        *,
        approverId: uuid.UUID | str | None = None,
    ) -> ApprovalDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        approval = self._requireApproval(tenant, approvalId)
        approval.deny(reason, approverId=approverId, now=self._now())
        stored = self.approvalStore.updateApproval(approval)
        if stored.invocationId is not None:
            invocation = self.invocationStore.getInvocation(tenant, stored.invocationId)
            if invocation is not None and not invocation.isTerminal:
                invocation.deny("AI_TOOL_DENIED", now=self._now())
                self.invocationStore.updateInvocation(invocation)
        self._audit(
            tenant,
            AUDIT_TOOL_DENIED,
            outcome="DENIED",
            actorId=None if approverId is None else requireUuid(approverId, "approverId"),
            contextSources=(f"{stored.toolCode}@{stored.toolVersion}",),
            detail={"approvalId": str(stored.id), "reason": stored.reason, "stage": "APPROVAL"},
        )
        return ApprovalDescriptor.of(stored)

    def describeApproval(
        self, tenantId: uuid.UUID | str, approvalId: uuid.UUID | str
    ) -> ApprovalDescriptor:
        return ApprovalDescriptor.of(
            self._requireApproval(requireUuid(tenantId, "tenantId"), approvalId)
        )

    def listApprovals(
        self, tenantId: uuid.UUID | str, *, decisions: tuple[str, ...] = (), limit: int = 200
    ) -> tuple[ApprovalDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        approvals = self.approvalStore.listApprovals(
            tenant,
            decisions=tuple(ensureApprovalDecision(value) for value in decisions),
            limit=limit,
        )
        return tuple(ApprovalDescriptor.of(item) for item in approvals)

    # ------------------------------------------------------------------
    # Reads and retention
    # ------------------------------------------------------------------
    def describeInvocation(
        self, tenantId: uuid.UUID | str, invocationId: uuid.UUID | str
    ) -> InvocationDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        invocation = self.invocationStore.getInvocation(
            tenant, requireUuid(invocationId, "invocationId")
        )
        if invocation is None:
            raise AIToolNotFound(str(invocationId))
        return InvocationDescriptor.of(invocation)

    def listInvocations(
        self,
        tenantId: uuid.UUID | str,
        *,
        requestId: uuid.UUID | str | None = None,
        toolCode: str = "",
        statuses: tuple[str, ...] = (),
        limit: int = 200,
    ) -> tuple[InvocationDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        invocations = self.invocationStore.listInvocations(
            tenant,
            requestId=None if requestId is None else requireUuid(requestId, "requestId"),
            toolCode=ensureToolCode(toolCode) if toolCode else "",
            statuses=statuses,
            limit=limit,
        )
        return tuple(InvocationDescriptor.of(item) for item in invocations)

    def purgeToolRetention(
        self,
        tenantId: uuid.UUID | str | None = None,
        *,
        retentionDays: int | None = None,
        now: datetime | None = None,
    ) -> int:
        self._requireEnabled()
        tenant = None if tenantId is None else requireUuid(tenantId, "tenantId")
        days = self.settings.retentionDays if retentionDays is None else int(retentionDays)
        if days < 1:
            raise AIConfigurationError("Tool retention must be at least one day.")
        cutoff = (now or self._now()) - timedelta(days=days)
        return self.invocationStore.deleteInvocationsBefore(tenant, cutoff)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _checkPermission(self, principal: Any, definition: AIToolDefinition) -> bool:
        """Fail-closed: with no checker wired, nothing may run."""

        if self.permissionChecker is None:
            raise AIConfigurationError(
                "Tool execution requires a permission checker; refusing to run unchecked."
            )
        if principal is None:
            return False
        from apps.ai.domain.services.authorizationService import AuthorizationResource

        resource = AuthorizationResource.entity(definition.tenantId, "AI_TOOL", definition.code)
        try:
            return bool(
                self.permissionChecker.can(
                    principal, definition.requiredPermission or DEFAULT_TOOL_PERMISSION, resource
                )
            )
        except Exception:  # noqa: BLE001 - a checker that errors denies
            return False

    def _resolveApproval(
        self,
        tenant: uuid.UUID,
        definition: AIToolDefinition,
        fingerprint: str,
        command: InvokeToolCommand,
    ) -> AIToolApproval | None:
        if command.approvalId is not None:
            return self.approvalStore.getApproval(
                tenant, requireUuid(command.approvalId, "approvalId")
            )
        usable = self.approvalStore.findUsable(
            tenant, definition.code, fingerprint, now=self._now()
        )
        if usable is not None:
            return usable
        pending = self.approvalStore.findPending(tenant, definition.code, fingerprint)
        if pending is not None:
            return pending
        # A denial sticks for as long as it would have been valid. Without
        # this a retrying agent re-opens the same request forever and turns
        # human review into spam (decision X-D6).
        latest = self.approvalStore.findLatest(tenant, definition.code, fingerprint)
        if (
            latest is not None
            and latest.decision == "DENIED"
            and not latest.isExpiredAt(self._now())
        ):
            return latest
        return None

    def _openApproval(
        self,
        tenant: uuid.UUID,
        definition: AIToolDefinition,
        fingerprint: str,
        invocation: AIToolInvocation,
        command: InvokeToolCommand,
        policy: ToolPolicy,
    ) -> AIToolApproval:
        moment = self._now()
        approval = AIToolApproval(
            tenantId=tenant,
            toolCode=definition.code,
            toolVersion=definition.version,
            argumentFingerprint=fingerprint,
            mode=policy.modeFor(definition.riskLevel, definition.declaredApprovalMode),
            requiredApprovals=policy.approvalsNeeded(
                definition.riskLevel, definition.declaredApprovalMode
            ),
            requestedBy=command.actorId,
            invocationId=invocation.id,
            reason=command.reason,
            expiresAt=approvalExpiry(moment, self.settings.approvalTtlSeconds),
            createdAt=moment,
        )
        return self.approvalStore.saveApproval(approval)

    def _runnerFor(self, toolCode: str) -> ToolRunner:
        for runner in self.runners:
            if runner.supports(toolCode):
                return runner
        raise AIConfigurationError(f"No runner is registered for {toolCode}.")

    def _describe(self, definition: AIToolDefinition) -> ToolDescriptor:
        return ToolDescriptor.of(
            definition,
            approvalMode=self.settings.policy().modeFor(
                definition.riskLevel, definition.declaredApprovalMode
            ),
        )

    def _requireVersion(self, tenant: uuid.UUID, toolCode: str, version: int) -> AIToolDefinition:
        self._requireEnabled()
        definition = self.definitionStore.findVersion(
            tenant, ensureToolCode(toolCode), int(version)
        )
        if definition is None:
            raise AIToolNotFound(f"{toolCode}@{version}")
        return definition

    def _requireApproval(self, tenant: uuid.UUID, approvalId: uuid.UUID | str) -> AIToolApproval:
        self._requireEnabled()
        approval = self.approvalStore.getApproval(tenant, requireUuid(approvalId, "approvalId"))
        if approval is None or approval.tenantId != tenant:
            raise AIToolApprovalNotFound(str(approvalId))
        return approval

    def _requireEnabled(self) -> None:
        if not self.settings.enabled:
            raise AIConfigurationError("The AI tool platform is disabled.")

    def _audit(self, tenant: uuid.UUID, action: str, **kwargs: Any) -> None:
        if self.auditLogger is None:
            return
        self.auditLogger.logAudit(tenant, action, **kwargs)


class CallableToolRunner:
    """Adapter that turns plain callables into a ``ToolRunner``.

    The callable receives the validated arguments only — never the
    principal, never the raw proposal — so a tool implementation cannot
    quietly widen its own authority.
    """

    def __init__(self, handlers: dict[str, Any] | None = None) -> None:
        self.handlers: dict[str, Any] = {}
        for code, handler in (handlers or {}).items():
            self.register(code, handler)

    def register(self, toolCode: str, handler: Any) -> None:
        if not callable(handler):
            raise AIToolInvalid("A tool handler must be callable.")
        self.handlers[ensureToolCode(toolCode)] = handler

    def supports(self, toolCode: str) -> bool:
        return ensureToolCode(toolCode) in self.handlers

    def run(self, tenantId: Any, ticket: Any) -> dict[str, Any]:
        if not isinstance(ticket, ExecutionTicket):
            raise AIToolInvalid("A runner only accepts an ExecutionTicket.")
        handler = self.handlers[ticket.definition.code]
        produced = handler(dict(ticket.arguments))
        return dict(produced or {})


__all__ = [
    "AUDIT_TOOL_APPROVED",
    "AUDIT_TOOL_DENIED",
    "AUDIT_TOOL_INVOKED",
    "AUDIT_TOOL_REGISTERED",
    "DEFAULT_TOOL_PERMISSION",
    "ApprovalDescriptor",
    "CallableToolRunner",
    "InvocationDescriptor",
    "InvocationResult",
    "InvokeToolCommand",
    "RegisterToolCommand",
    "ToolApplicationService",
    "ToolDescriptor",
    "ToolSettings",
]
