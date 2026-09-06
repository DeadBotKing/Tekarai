"""Application orchestration for the Phase 13-Y agent foundation.

``AgentApplicationService`` implements the §31 composition end to end —
*identity → instructions → capabilities → tools → memory → policies* —
and enforces the rule that gives the chapter its teeth: **an agent is
not a prompt**. What the model produces is an ``AgentModelReply``; the
only path from a reply to an executed tool runs through the plan-act
loop, the agent's access level, and the Phase 13-X chain.

Behaviour worth stating once:

- **OQ #11 is two axes.** The access level (ADVISORY / READ_ONLY /
  MUTATING / AUTONOMOUS) is structural — a proposal whose effect
  exceeds the level never reaches the tool chain. The approval mode is
  driven by risk, with the Phase 13-X asymmetry: a definition may
  declare a *stricter* mode, never a looser one.
- **Dual control means two people.** The same approver twice is
  refused, and so is the requester approving their own run.
- **A denied run is recorded, not dropped.** Every request becomes a
  run row with a terminal status, and every model/tool step — even a
  denied one — becomes a step row. "What did the agent try?" is always
  answerable (Y-D7).
- **The agent acts with the requester's permission, not its own**
  (Y-D12): the principal that started the run is propagated to every
  tool call; the agent cannot generate new authority.
- **Input is redacted before it is stored**, using the same
  secret-key list the Phase 13-O/X scrubber uses.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings as djangoSettings

from apps.ai.domain.entities.agentRecords import (
    AIAgentApproval,
    AIAgentDefinition,
    AIAgentRun,
    AIAgentStep,
    approvalExpiry,
)
from apps.ai.domain.entities.aiRecords import requireUuid
from apps.ai.domain.exceptions import (
    AIAgentAlreadyRegistered,
    AIAgentApprovalNotFound,
    AIAgentBudgetExceeded,
    AIAgentExecutionFailed,
    AIAgentInvalid,
    AIAgentNotApproved,
    AIAgentNotFound,
    AIAgentOutputInvalid,
    AIConfigurationError,
    AIContextTooLarge,
)
from apps.ai.domain.services.agentEngine import (
    AgentContextBuilder,
    AgentGateDecision,
    AgentGatekeeper,
    AgentKnowledgeContext,
    AgentMemoryContext,
    AgentModelReply,
    AgentPlanner,
    AgentRunBudget,
    AgentToolDeclaration,
    AgentToolOutcome,
)
from apps.ai.domain.services.toolEngine import ToolProposal, ToolRegistry
from apps.ai.domain.valueObjects.agentTypes import (
    AgentPolicy,
    ensureAgentAccessLevel,
    ensureAgentCode,
    ensureAgentStatus,
    inputFingerprint,
    inputSize,
)
from apps.ai.domain.valueObjects.toolTypes import (
    ensureApprovalDecision,
    ensureRiskLevel,
)

#: Audit actions appended by Y (registered in the Phase 13-O vocabulary).
AUDIT_AGENT_REGISTERED = "AGENT_REGISTERED"
AUDIT_AGENT_APPROVED = "AGENT_APPROVED"
AUDIT_AGENT_INVOKED = "AGENT_INVOKED"
AUDIT_AGENT_DENIED = "AGENT_DENIED"

#: Permission required to run an agent that declares none of its own.
DEFAULT_AGENT_PERMISSION = "AI_AGENT_RUN"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentSettings:
    """Configuration-driven defaults (Master Specification §42)."""

    enabled: bool = True
    automaticBelowRisk: str = "HIGH"
    dualControlAtRisk: str = "CRITICAL"
    maxStepsPerRun: int = 10
    maxToolCallsPerRun: int = 20
    maxRepeatsPerRun: int = 2
    maxDurationSeconds: int = 120
    maxContextTokens: int = 16_000
    maxInstructionsBytes: int = 16_384
    maxInputBytes: int = 65_536
    approvalTtlSeconds: int = 3600
    retentionDays: int = 365

    def __post_init__(self) -> None:
        if self.maxRepeatsPerRun < 1:
            raise AIConfigurationError("aiAgentMaxRepeatsPerRun must be positive.")
        if self.approvalTtlSeconds < 1:
            raise AIConfigurationError("aiAgentApprovalTtlSeconds must be positive.")
        if self.retentionDays < 1:
            raise AIConfigurationError("aiAgentRetentionDays must be positive.")
        # Building the policy here means an impossible configuration fails
        # at construction, not on the first run.
        self.policy()

    def policy(self) -> AgentPolicy:
        return AgentPolicy(
            automaticBelowRisk=self.automaticBelowRisk,
            dualControlAtRisk=self.dualControlAtRisk,
            maxSteps=self.maxStepsPerRun,
            maxToolCalls=self.maxToolCallsPerRun,
            maxRepeats=self.maxRepeatsPerRun,
            maxDurationSeconds=self.maxDurationSeconds,
            maxContextTokens=self.maxContextTokens,
            maxInstructionsBytes=self.maxInstructionsBytes,
            maxInputBytes=self.maxInputBytes,
            approvalTtlSeconds=self.approvalTtlSeconds,
            retentionDays=self.retentionDays,
        )

    @classmethod
    def fromDjangoSettings(cls) -> AgentSettings:
        s = djangoSettings
        return cls(
            enabled=bool(getattr(s, "AI_AGENT_ENABLED", True)),
            automaticBelowRisk=str(getattr(s, "AI_AGENT_AUTOMATIC_BELOW_RISK", "HIGH")),
            dualControlAtRisk=str(getattr(s, "AI_AGENT_DUAL_CONTROL_AT_RISK", "CRITICAL")),
            maxStepsPerRun=int(getattr(s, "AI_AGENT_MAX_STEPS_PER_RUN", 10)),
            maxToolCallsPerRun=int(getattr(s, "AI_AGENT_MAX_TOOL_CALLS_PER_RUN", 20)),
            maxRepeatsPerRun=int(getattr(s, "AI_AGENT_MAX_REPEATS_PER_RUN", 2)),
            maxDurationSeconds=int(getattr(s, "AI_AGENT_MAX_DURATION_SECONDS", 120)),
            maxContextTokens=int(getattr(s, "AI_AGENT_MAX_CONTEXT_TOKENS", 16_000)),
            maxInstructionsBytes=int(getattr(s, "AI_AGENT_MAX_INSTRUCTIONS_BYTES", 16_384)),
            maxInputBytes=int(getattr(s, "AI_AGENT_MAX_INPUT_BYTES", 65_536)),
            approvalTtlSeconds=int(getattr(s, "AI_AGENT_APPROVAL_TTL_SECONDS", 3600)),
            retentionDays=int(getattr(s, "AI_AGENT_RETENTION_DAYS", 365)),
        )


@dataclass(frozen=True)
class RegisterAgentCommand:
    """Add one agent version to the registry, in ``DRAFT`` (§Y.5)."""

    code: str
    name: str
    instructions: str
    description: str = ""
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
    version: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunAgentCommand:
    """One requested run, exactly as the caller produced it (§Y.8)."""

    agentCode: str
    input: dict[str, Any] = field(default_factory=dict)
    version: int | None = None
    principal: Any = None
    actorId: uuid.UUID | None = None
    reason: str = ""
    approvalId: uuid.UUID | None = None


@dataclass(frozen=True)
class AgentDescriptor:
    """Safe read model of one registry entry."""

    agentId: uuid.UUID
    code: str
    version: int
    qualifiedCode: str
    name: str
    description: str
    accessLevel: str
    riskLevel: str
    status: str
    approvalMode: str
    capabilityCodes: tuple[str, ...]
    toolCodes: tuple[str, ...]
    requiredPermission: str
    approvedBy: uuid.UUID | None
    rejectionReason: str
    createdAt: datetime

    @classmethod
    def of(cls, definition: AIAgentDefinition, *, approvalMode: str = "") -> AgentDescriptor:
        return cls(
            agentId=definition.id,
            code=definition.code,
            version=definition.version,
            qualifiedCode=definition.qualifiedCode,
            name=definition.name,
            description=definition.description,
            accessLevel=definition.accessLevel,
            riskLevel=definition.riskLevel,
            status=definition.status,
            approvalMode=approvalMode or definition.declaredApprovalMode,
            capabilityCodes=tuple(definition.capabilityCodes),
            toolCodes=tuple(definition.toolCodes),
            requiredPermission=definition.requiredPermission,
            approvedBy=definition.approvedBy,
            rejectionReason=definition.rejectionReason,
            createdAt=definition.createdAt,
        )


@dataclass(frozen=True)
class AgentApprovalDescriptor:
    """Safe read model of one approval request."""

    approvalId: uuid.UUID
    agentCode: str
    agentVersion: int
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
    def of(cls, approval: AIAgentApproval) -> AgentApprovalDescriptor:
        return cls(
            approvalId=approval.id,
            agentCode=approval.agentCode,
            agentVersion=approval.agentVersion,
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
class AgentRunDescriptor:
    """Safe read model of one run — input is already redacted."""

    runId: uuid.UUID
    agentCode: str
    agentVersion: int
    qualifiedCode: str
    status: str
    answer: str
    output: dict[str, Any]
    errorCode: str
    inputFingerprint: str
    approvalId: uuid.UUID | None
    requestedBy: uuid.UUID | None
    modelCallCount: int
    toolCallCount: int
    inputTokens: int
    outputTokens: int
    latencyMs: int
    createdAt: datetime

    @classmethod
    def of(cls, run: AIAgentRun) -> AgentRunDescriptor:
        return cls(
            runId=run.id,
            agentCode=run.agentCode,
            agentVersion=run.agentVersion,
            qualifiedCode=run.qualifiedCode,
            status=run.status,
            answer=run.answer,
            output=dict(run.output),
            errorCode=run.errorCode,
            inputFingerprint=run.inputFingerprint,
            approvalId=run.approvalId,
            requestedBy=run.requestedBy,
            modelCallCount=run.modelCallCount,
            toolCallCount=run.toolCallCount,
            inputTokens=run.inputTokens,
            outputTokens=run.outputTokens,
            latencyMs=run.latencyMs,
            createdAt=run.createdAt,
        )


@dataclass(frozen=True)
class AgentStepDescriptor:
    """Safe read model of one step — arguments are already redacted."""

    stepId: uuid.UUID
    runId: uuid.UUID
    ordinal: int
    kind: str
    status: str
    toolCode: str
    toolVersion: int
    arguments: dict[str, Any]
    result: dict[str, Any]
    reason: str
    tokensIn: int
    tokensOut: int
    latencyMs: int
    errorCode: str
    createdAt: datetime

    @classmethod
    def of(cls, step: AIAgentStep) -> AgentStepDescriptor:
        return cls(
            stepId=step.id,
            runId=step.runId,
            ordinal=step.ordinal,
            kind=step.kind,
            status=step.status,
            toolCode=step.toolCode,
            toolVersion=step.toolVersion,
            arguments=dict(step.arguments),
            result=dict(step.result),
            reason=step.reason,
            tokensIn=step.tokensIn,
            tokensOut=step.tokensOut,
            latencyMs=step.latencyMs,
            errorCode=step.errorCode,
            createdAt=step.createdAt,
        )


@dataclass(frozen=True)
class AgentRunResult:
    """The outcome of one requested run (§Y.8)."""

    run: AgentRunDescriptor
    decision: AgentGateDecision | None = None
    approval: AgentApprovalDescriptor | None = None
    executed: bool = False

    @property
    def completed(self) -> bool:
        return self.run.status == "COMPLETED"

    @property
    def denied(self) -> bool:
        return self.run.status == "DENIED"

    @property
    def awaitingApproval(self) -> bool:
        return (
            self.run.status == "PENDING"
            and self.approval is not None
            and self.approval.decision == "PENDING"
        )


class AgentApplicationService:
    """Tenant-scoped facade for the registry, approvals, and execution."""

    def __init__(
        self,
        definitionStore: Any,
        approvalStore: Any,
        executionStore: Any,
        *,
        permissionChecker: Any = None,
        capabilityResolver: Any = None,
        memoryProvider: Any = None,
        knowledgeProvider: Any = None,
        toolExecutor: Any = None,
        modelCaller: Any = None,
        settings: AgentSettings | None = None,
        auditLogger: Any = None,
        contextBuilder: AgentContextBuilder | None = None,
        gatekeeper: AgentGatekeeper | None = None,
        planner: AgentPlanner | None = None,
        now: Any = None,
        clock: Any = None,
    ) -> None:
        if now is not None and not callable(now):
            raise TypeError("now must be callable.")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable.")
        self.definitionStore = definitionStore
        self.approvalStore = approvalStore
        self.executionStore = executionStore
        self.permissionChecker = permissionChecker
        self.capabilityResolver = capabilityResolver
        self.memoryProvider = memoryProvider
        self.knowledgeProvider = knowledgeProvider
        self.toolExecutor = toolExecutor
        self.modelCaller = modelCaller
        self.settings = settings or AgentSettings()
        self.auditLogger = auditLogger
        self.contextBuilder = contextBuilder or AgentContextBuilder()
        self.gatekeeper = gatekeeper or AgentGatekeeper()
        self._now = now
        self._clock = clock
        self._planner = planner

    def _currentNow(self) -> datetime:
        return self._now() if self._now is not None else _utcNow()

    def _currentClock(self) -> Any:
        return self._clock if self._clock is not None else _utcNow

    def _plannerFor(self) -> AgentPlanner:
        if self._planner is not None:
            return self._planner
        if self.modelCaller is None or self.toolExecutor is None:
            raise AIConfigurationError(
                "Agent execution requires a model caller and a tool executor; "
                "refusing to run unchecked."
            )
        self._planner = AgentPlanner(
            self.modelCaller, self.toolExecutor, clock=self._currentClock()
        )
        return self._planner

    # ------------------------------------------------------------------
    # Registry (§Y.5)
    # ------------------------------------------------------------------
    def registerAgent(
        self, tenantId: uuid.UUID | str, command: RegisterAgentCommand
    ) -> AgentDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(command, RegisterAgentCommand):
            raise AIAgentInvalid("Registering requires a RegisterAgentCommand.")
        code = ensureAgentCode(command.code)
        existing = self.definitionStore.listVersions(tenant, code)
        version = command.version or (max((item.version for item in existing), default=0) + 1)
        if any(item.version == version for item in existing):
            raise AIAgentAlreadyRegistered(f"{code}@{version}")
        # Capability declarations are checked against the Phase 13-F
        # registry at registration time: an agent cannot promise a
        # capability the tenant does not have.
        self._requireCapabilities(
            tenant,
            tuple(str(code).strip().upper() for code in command.capabilityCodes),
        )
        moment = self._currentNow()
        definition = AIAgentDefinition(
            tenantId=tenant,
            code=code,
            name=command.name,
            description=command.description,
            instructions=command.instructions,
            version=version,
            accessLevel=ensureAgentAccessLevel(command.accessLevel),
            riskLevel=ensureRiskLevel(command.riskLevel),
            capabilityCodes=tuple(str(c).strip().upper() for c in command.capabilityCodes),
            toolCodes=tuple(str(c).strip().upper() for c in command.toolCodes),
            outputSchema=dict(command.outputSchema),
            contextPolicy=dict(command.contextPolicy),
            modelPolicy=dict(command.modelPolicy),
            permissionPolicy=dict(command.permissionPolicy),
            executionPolicy=dict(command.executionPolicy),
            declaredApprovalMode=command.declaredApprovalMode or "",
            metadata=dict(command.metadata),
            createdAt=moment,
            updatedAt=moment,
        )
        stored = self.definitionStore.saveDefinition(definition)
        self._audit(
            tenant,
            AUDIT_AGENT_REGISTERED,
            outcome="RECORDED",
            contextSources=(stored.qualifiedCode,),
            detail={
                "accessLevel": stored.accessLevel,
                "riskLevel": stored.riskLevel,
                "approvalMode": self.settings.policy().modeFor(
                    stored.riskLevel, stored.declaredApprovalMode
                ),
            },
        )
        return self._describe(stored)

    def submitForApproval(
        self, tenantId: uuid.UUID | str, agentCode: str, version: int
    ) -> AgentDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireVersion(tenant, agentCode, version)
        definition.submitForApproval(now=self._currentNow())
        return self._describe(self.definitionStore.updateDefinition(definition))

    def approveAgent(
        self,
        tenantId: uuid.UUID | str,
        agentCode: str,
        version: int,
        *,
        approverId: uuid.UUID | str,
    ) -> AgentDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireVersion(tenant, agentCode, version)
        definition.approve(approverId=approverId, now=self._currentNow())
        stored = self.definitionStore.updateDefinition(definition)
        self._audit(
            tenant,
            AUDIT_AGENT_APPROVED,
            outcome="ALLOWED",
            actorId=stored.approvedBy,
            contextSources=(stored.qualifiedCode,),
            detail={"riskLevel": stored.riskLevel, "accessLevel": stored.accessLevel},
        )
        return self._describe(stored)

    def rejectAgent(
        self,
        tenantId: uuid.UUID | str,
        agentCode: str,
        version: int,
        reason: str,
    ) -> AgentDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireVersion(tenant, agentCode, version)
        definition.reject(reason, now=self._currentNow())
        stored = self.definitionStore.updateDefinition(definition)
        self._audit(
            tenant,
            AUDIT_AGENT_DENIED,
            outcome="DENIED",
            contextSources=(stored.qualifiedCode,),
            detail={"reason": stored.rejectionReason, "stage": "REGISTRY"},
        )
        return self._describe(stored)

    def suspendAgent(
        self, tenantId: uuid.UUID | str, agentCode: str, version: int, reason: str = ""
    ) -> AgentDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireVersion(tenant, agentCode, version)
        definition.suspend(reason, now=self._currentNow())
        return self._describe(self.definitionStore.updateDefinition(definition))

    def resumeAgent(
        self, tenantId: uuid.UUID | str, agentCode: str, version: int
    ) -> AgentDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireVersion(tenant, agentCode, version)
        definition.resume(now=self._currentNow())
        return self._describe(self.definitionStore.updateDefinition(definition))

    def retireAgent(
        self, tenantId: uuid.UUID | str, agentCode: str, version: int
    ) -> AgentDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        definition = self._requireVersion(tenant, agentCode, version)
        definition.retire(now=self._currentNow())
        return self._describe(self.definitionStore.updateDefinition(definition))

    def publishNewVersion(
        self, tenantId: uuid.UUID | str, agentCode: str, **overrides: Any
    ) -> AgentDescriptor:
        """Clone the newest version into a fresh ``DRAFT`` (§Y.5)."""

        tenant = requireUuid(tenantId, "tenantId")
        versions = self.definitionStore.listVersions(tenant, ensureAgentCode(agentCode))
        if not versions:
            raise AIAgentNotFound(ensureAgentCode(agentCode))
        successor = versions[-1].nextVersion(now=self._currentNow(), **overrides)
        return self._describe(self.definitionStore.saveDefinition(successor))

    def describeAgent(
        self, tenantId: uuid.UUID | str, agentCode: str, version: int
    ) -> AgentDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        return self._describe(self._requireVersion(tenant, agentCode, version))

    def listAgents(
        self, tenantId: uuid.UUID | str, *, statuses: tuple[str, ...] = (), limit: int = 200
    ) -> tuple[AgentDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        definitions = self.definitionStore.listDefinitions(
            tenant,
            statuses=tuple(ensureAgentStatus(value) for value in statuses),
            limit=limit,
        )
        return tuple(self._describe(item) for item in definitions)

    # ------------------------------------------------------------------
    # Execution (§Y.8 — the plan-act loop)
    # ------------------------------------------------------------------
    def runAgent(self, tenantId: uuid.UUID | str, command: RunAgentCommand) -> AgentRunResult:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(command, RunAgentCommand):
            raise AIAgentInvalid("Running requires a RunAgentCommand.")
        policy = self.settings.policy()

        # 1. Registry resolution: latest APPROVED version, or explicit.
        definition = self._resolveVersion(tenant, command.agentCode, command.version)

        # 2. Input validation (before anything is persisted).
        if inputSize(command.input) > policy.maxInputBytes:
            raise AIAgentInvalid("The run input exceeds the configured byte ceiling.")
        fingerprint = inputFingerprint(definition.code, definition.version, command.input)

        # 3. Permission (Phase 13-K) and capabilities (Phase 13-F).
        permitted = self._checkPermission(command.principal, definition)
        capabilitiesAvailable = self._capabilitiesAvailable(tenant, definition)

        # 4. Approval state for this exact input fingerprint.
        approval = self._resolveApproval(tenant, definition, fingerprint, command)

        # 5. The fail-closed gate (OQ #11).
        decision = self.gatekeeper.decide(
            definition,
            policy,
            permitted=permitted,
            capabilitiesAvailable=capabilitiesAvailable,
            approval=approval,
            now=self._currentNow(),
        )

        # 6. Every request becomes a row, even when the answer is "no".
        requestedBy = command.actorId or _principalSubject(command.principal)
        run = AIAgentRun(
            tenantId=tenant,
            agentId=definition.id,
            agentCode=definition.code,
            agentVersion=definition.version,
            input=dict(command.input),
            requestedBy=requestedBy,
            inputFingerprint=fingerprint,
            createdAt=self._currentNow(),
        )
        run = self.executionStore.saveRun(run)

        if decision.blocked:
            if decision.errorCode == "AI_AGENT_APPROVAL_REQUIRED":
                pending = approval or self._openApproval(
                    tenant, definition, run, decision, command, policy
                )
                run.approvalId = pending.id
                self.executionStore.updateRun(run)
                self._audit(
                    tenant,
                    AUDIT_AGENT_INVOKED,
                    outcome="RECORDED",
                    actorId=requestedBy,
                    contextSources=(definition.qualifiedCode,),
                    detail={
                        "runId": str(run.id),
                        "state": "AWAITING_APPROVAL",
                        "mode": decision.approvalMode,
                    },
                )
                return AgentRunResult(
                    run=AgentRunDescriptor.of(run),
                    decision=decision,
                    approval=AgentApprovalDescriptor.of(pending),
                    executed=False,
                )
            run.deny(decision.errorCode or "AI_AGENT_DENIED", now=self._currentNow())
            stored = self.executionStore.updateRun(run)
            self._audit(
                tenant,
                AUDIT_AGENT_DENIED,
                outcome="DENIED",
                actorId=requestedBy,
                errorCode=stored.errorCode,
                contextSources=(definition.qualifiedCode,),
                detail={"runId": str(stored.id), "reason": decision.reason},
            )
            return AgentRunResult(
                run=AgentRunDescriptor.of(stored),
                decision=decision,
                approval=None if approval is None else AgentApprovalDescriptor.of(approval),
                executed=False,
            )

        # 7. Execution — approved gate, now the plan-act loop.
        run.transitionTo("RUNNING", now=self._currentNow())
        self.executionStore.updateRun(run)
        planner = self._plannerFor()
        budget = AgentRunBudget.forRun(
            policy, definition, now=self._currentNow(), clock=self._currentClock()
        )
        try:
            declarations = self._buildDeclarations(tenant, definition)
            # Y-D6: a source that errors is *absent* for this run, never
            # permissive — the run continues with the sections it has.
            memory = self._safeMemory(tenant, command.principal, definition)
            query = _knowledgeQuery(command.input)
            knowledge = (
                self._safeKnowledge(tenant, command.principal, definition, query)
                if query
                else AgentKnowledgeContext()
            )
            maxContextTokens = min(
                policy.maxContextTokens,
                int(definition.contextPolicy.get("maxContextTokens", policy.maxContextTokens)),
            )
            context = self.contextBuilder.build(
                definition,
                run,
                memory=memory,
                knowledge=knowledge,
                maxContextTokens=maxContextTokens,
            )
            outcome = planner.run(
                tenant,
                definition,
                run,
                context,
                budget,
                principal=command.principal,
                declarations=declarations,
                on_step=lambda step: self._recordStep(tenant, step),
            )
            run.complete(outcome.answer, outcome.output or None, now=self._currentNow())
            run.modelCallCount = sum(1 for step in outcome.steps if step.isModelCall)
            run.toolCallCount = sum(1 for step in outcome.steps if step.isToolCall)
            run.inputTokens = budget.inputTokens
            run.outputTokens = budget.outputTokens
            stored = self.executionStore.updateRun(run)
            self._audit(
                tenant,
                AUDIT_AGENT_INVOKED,
                outcome="SUCCEEDED",
                actorId=requestedBy,
                contextSources=context.sources,
                detail={
                    "runId": str(stored.id),
                    "steps": len(outcome.steps),
                    "modelCalls": run.modelCallCount,
                    "toolCalls": run.toolCallCount,
                    "tokens": budget.totalTokens,
                },
            )
            return AgentRunResult(
                run=AgentRunDescriptor.of(stored), decision=decision, executed=True
            )
        except AIContextTooLarge:
            return self._failRun(tenant, run, "AI_CONTEXT_TOO_LARGE", requestedBy, budget)
        except AIAgentBudgetExceeded:
            return self._failRun(tenant, run, "AI_AGENT_BUDGET_EXCEEDED", requestedBy, budget)
        except AIAgentOutputInvalid:
            return self._failRun(tenant, run, "AI_AGENT_OUTPUT_INVALID", requestedBy, budget)
        except (AIAgentInvalid, AIConfigurationError):
            return self._failRun(tenant, run, "AI_AGENT_INVALID", requestedBy, budget)
        except AIAgentExecutionFailed:
            return self._failRun(tenant, run, "AI_AGENT_EXECUTION_FAILED", requestedBy, budget)

    def _safeMemory(
        self, tenant: uuid.UUID, principal: Any, definition: AIAgentDefinition
    ) -> AgentMemoryContext:
        if self.memoryProvider is None:
            return AgentMemoryContext()
        try:
            return self.memoryProvider.contextFor(tenant, principal, definition)
        except Exception:  # noqa: BLE001 — fail-closed to an empty section
            logger.warning(
                "Agent memory context unavailable for %s; continuing without it.",
                definition.qualifiedCode,
            )
            return AgentMemoryContext()

    def _safeKnowledge(
        self,
        tenant: uuid.UUID,
        principal: Any,
        definition: AIAgentDefinition,
        query: str,
    ) -> AgentKnowledgeContext:
        if self.knowledgeProvider is None:
            return AgentKnowledgeContext()
        try:
            return self.knowledgeProvider.searchFor(tenant, principal, definition, query)
        except Exception:  # noqa: BLE001 — fail-closed to an empty section
            logger.warning(
                "Agent knowledge context unavailable for %s; continuing without it.",
                definition.qualifiedCode,
            )
            return AgentKnowledgeContext()

    def _failRun(
        self,
        tenant: uuid.UUID,
        run: AIAgentRun,
        errorCode: str,
        requestedBy: uuid.UUID | None,
        budget: AgentRunBudget | None = None,
    ) -> AgentRunResult:
        run.fail(errorCode, now=self._currentNow())
        if budget is not None:
            run.inputTokens = budget.inputTokens
            run.outputTokens = budget.outputTokens
        stored = self.executionStore.updateRun(run)
        self._audit(
            tenant,
            AUDIT_AGENT_INVOKED,
            outcome="FAILED",
            actorId=requestedBy,
            errorCode=stored.errorCode,
            contextSources=(stored.qualifiedCode,),
            detail={
                "runId": str(stored.id),
                "modelCalls": run.modelCallCount,
                "toolCalls": run.toolCallCount,
            },
        )
        return AgentRunResult(run=AgentRunDescriptor.of(stored), executed=True)

    # ------------------------------------------------------------------
    # Approvals (§Y.7 — OQ #11)
    # ------------------------------------------------------------------
    def grantApproval(
        self,
        tenantId: uuid.UUID | str,
        approvalId: uuid.UUID | str,
        *,
        approverId: uuid.UUID | str,
    ) -> AgentApprovalDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        approval = self._requireApproval(tenant, approvalId)
        approval.grant(approverId, now=self._currentNow())
        stored = self.approvalStore.updateApproval(approval)
        self._audit(
            tenant,
            AUDIT_AGENT_APPROVED,
            outcome="ALLOWED" if stored.isGranted else "RECORDED",
            actorId=requireUuid(approverId, "approverId"),
            contextSources=(f"{stored.agentCode}@{stored.agentVersion}",),
            detail={
                "approvalId": str(stored.id),
                "decision": stored.decision,
                "remaining": stored.remainingApprovals,
            },
        )
        return AgentApprovalDescriptor.of(stored)

    def denyApproval(
        self,
        tenantId: uuid.UUID | str,
        approvalId: uuid.UUID | str,
        reason: str,
        *,
        approverId: uuid.UUID | str | None = None,
    ) -> AgentApprovalDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        approval = self._requireApproval(tenant, approvalId)
        approval.deny(reason, approverId=approverId, now=self._currentNow())
        stored = self.approvalStore.updateApproval(approval)
        if stored.executionId is not None:
            run = self.executionStore.getRun(tenant, stored.executionId)
            if run is not None and not run.isTerminal:
                run.deny("AI_AGENT_DENIED", now=self._currentNow())
                self.executionStore.updateRun(run)
        self._audit(
            tenant,
            AUDIT_AGENT_DENIED,
            outcome="DENIED",
            actorId=None if approverId is None else requireUuid(approverId, "approverId"),
            contextSources=(f"{stored.agentCode}@{stored.agentVersion}",),
            detail={
                "approvalId": str(stored.id),
                "reason": stored.reason,
                "stage": "APPROVAL",
            },
        )
        return AgentApprovalDescriptor.of(stored)

    def describeApproval(
        self, tenantId: uuid.UUID | str, approvalId: uuid.UUID | str
    ) -> AgentApprovalDescriptor:
        return AgentApprovalDescriptor.of(
            self._requireApproval(requireUuid(tenantId, "tenantId"), approvalId)
        )

    def listApprovals(
        self, tenantId: uuid.UUID | str, *, decisions: tuple[str, ...] = (), limit: int = 200
    ) -> tuple[AgentApprovalDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        approvals = self.approvalStore.listApprovals(
            tenant,
            decisions=tuple(ensureApprovalDecision(value) for value in decisions),
            limit=limit,
        )
        return tuple(AgentApprovalDescriptor.of(item) for item in approvals)

    # ------------------------------------------------------------------
    # Reads and retention
    # ------------------------------------------------------------------
    def describeRun(self, tenantId: uuid.UUID | str, runId: uuid.UUID | str) -> AgentRunDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        run = self.executionStore.getRun(tenant, requireUuid(runId, "runId"))
        if run is None:
            raise AIAgentNotFound(str(runId))
        return AgentRunDescriptor.of(run)

    def listRuns(
        self,
        tenantId: uuid.UUID | str,
        *,
        agentCode: str = "",
        statuses: tuple[str, ...] = (),
        limit: int = 200,
    ) -> tuple[AgentRunDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        runs = self.executionStore.listRuns(
            tenant,
            agentCode=ensureAgentCode(agentCode) if agentCode else "",
            statuses=statuses,
            limit=limit,
        )
        return tuple(AgentRunDescriptor.of(item) for item in runs)

    def listSteps(
        self, tenantId: uuid.UUID | str, runId: uuid.UUID | str
    ) -> tuple[AgentStepDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        steps = self.executionStore.listSteps(tenant, requireUuid(runId, "runId"))
        return tuple(AgentStepDescriptor.of(item) for item in steps)

    def purgeAgentRetention(
        self,
        tenantId: uuid.UUID | str | None = None,
        *,
        retentionDays: int | None = None,
        now: datetime | None = None,
    ) -> tuple[int, int]:
        """Delete settled runs (with their steps) past the cutoff.

        Runs awaiting human decision and pending approvals are never
        touched by retention (§Y.11).
        """

        self._requireEnabled()
        tenant = None if tenantId is None else requireUuid(tenantId, "tenantId")
        days = self.settings.retentionDays if retentionDays is None else int(retentionDays)
        if days < 1:
            raise AIConfigurationError("Agent retention must be at least one day.")
        cutoff = (now or self._currentNow()) - timedelta(days=days)
        return self.executionStore.deleteSettledBefore(tenant, cutoff)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _checkPermission(self, principal: Any, definition: AIAgentDefinition) -> bool:
        """Fail-closed: with no checker wired, nothing may run."""

        if self.permissionChecker is None:
            raise AIConfigurationError(
                "Agent execution requires a permission checker; refusing to run unchecked."
            )
        if principal is None:
            return False
        from apps.ai.domain.services.authorizationService import AuthorizationResource

        resource = AuthorizationResource.entity(definition.tenantId, "AI_AGENT", definition.code)
        try:
            return bool(
                self.permissionChecker.can(
                    principal, definition.requiredPermission or DEFAULT_AGENT_PERMISSION, resource
                )
            )
        except Exception:  # noqa: BLE001 - a checker that errors denies
            return False

    def _requireCapabilities(self, tenant: uuid.UUID, codes: tuple[str, ...]) -> None:
        if not codes:
            return
        if self.capabilityResolver is None:
            # No resolver wired: declarations cannot be verified, so they
            # cannot be accepted. Fail-closed (Y-D6 philosophy).
            raise AIConfigurationError(
                "Agent registration with capability declarations requires a "
                "capability resolver; refusing an unverifiable declaration."
            )
        available = self.capabilityResolver.availableCodes(tenant)
        missing = tuple(code for code in codes if code not in available)
        if missing:
            raise AIAgentInvalid(f"Unknown or inactive capability codes: {', '.join(missing)}.")

    def _capabilitiesAvailable(self, tenant: uuid.UUID, definition: AIAgentDefinition) -> bool:
        """Re-verify at run time: a capability deactivated after approval
        must not keep an agent runnable (fail-closed)."""

        if not definition.capabilityCodes:
            return True
        if self.capabilityResolver is None:
            return False
        available = self.capabilityResolver.availableCodes(tenant)
        return all(code in available for code in definition.capabilityCodes)

    def _resolveApproval(
        self,
        tenant: uuid.UUID,
        definition: AIAgentDefinition,
        fingerprint: str,
        command: RunAgentCommand,
    ) -> AIAgentApproval | None:
        if command.approvalId is not None:
            explicit = self.approvalStore.getApproval(
                tenant, requireUuid(command.approvalId, "approvalId")
            )
            # An explicit id that does not exist is a client error, not a
            # "no approval" — silently opening a fresh approval for a
            # mistyped id would turn typos into approval spam.
            if explicit is None:
                raise AIAgentApprovalNotFound(str(command.approvalId))
            return explicit
        usable = self.approvalStore.findUsable(
            tenant, definition.code, fingerprint, now=self._currentNow()
        )
        if usable is not None:
            return usable
        pending = self.approvalStore.findPending(tenant, definition.code, fingerprint)
        if pending is not None:
            return pending
        # A denial sticks for as long as it would have been valid. Without
        # this a retrying agent re-opens the same request forever and turns
        # human review into spam (decision X-D6, carried over by Y-D2).
        latest = self.approvalStore.findLatest(tenant, definition.code, fingerprint)
        if (
            latest is not None
            and latest.decision == "DENIED"
            and not latest.isExpiredAt(self._currentNow())
        ):
            return latest
        return None

    def _openApproval(
        self,
        tenant: uuid.UUID,
        definition: AIAgentDefinition,
        run: AIAgentRun,
        decision: AgentGateDecision,
        command: RunAgentCommand,
        policy: AgentPolicy,
    ) -> AIAgentApproval:
        moment = self._currentNow()
        approval = AIAgentApproval(
            tenantId=tenant,
            agentCode=definition.code,
            agentVersion=definition.version,
            inputFingerprint=run.inputFingerprint,
            mode=decision.approvalMode,
            requiredApprovals=decision.approvalsNeeded,
            requestedBy=command.actorId or _principalSubject(command.principal),
            executionId=run.id,
            reason=command.reason,
            expiresAt=approvalExpiry(moment, self.settings.approvalTtlSeconds),
            createdAt=moment,
        )
        return self.approvalStore.saveApproval(approval)

    def _buildDeclarations(
        self, tenant: uuid.UUID, definition: AIAgentDefinition
    ) -> tuple[AgentToolDeclaration, ...]:
        """Resolve the agent's tool codes against the Phase 13-X registry.

        A tool code that cannot be resolved (unknown, or no APPROVED
        version) is simply not declared: the model never sees it, and a
        proposal for it is a denied step. Fail-closed by construction.
        """

        if self.toolExecutor is None or not hasattr(self.toolExecutor, "declarationsFor"):
            return ()
        return tuple(self.toolExecutor.declarationsFor(tenant, tuple(definition.toolCodes)))

    def _recordStep(self, tenant: uuid.UUID, step: AIAgentStep) -> None:
        self.executionStore.saveStep(step)

    def _resolveVersion(
        self, tenant: uuid.UUID, agentCode: str, version: int | None
    ) -> AIAgentDefinition:
        code = ensureAgentCode(agentCode)
        versions = self.definitionStore.listVersions(tenant, code)
        if not versions:
            raise AIAgentNotFound(code)
        if version is not None:
            for item in versions:
                if item.version == version:
                    return item
            raise AIAgentNotFound(f"{code}@{version}")
        approved = [item for item in versions if item.isRunnable]
        if not approved:
            raise AIAgentNotApproved(f"No approved version of {code} exists.")
        return approved[-1]

    def _describe(self, definition: AIAgentDefinition) -> AgentDescriptor:
        return AgentDescriptor.of(
            definition,
            approvalMode=self.settings.policy().modeFor(
                definition.riskLevel, definition.declaredApprovalMode
            ),
        )

    def _requireVersion(self, tenant: uuid.UUID, agentCode: str, version: int) -> AIAgentDefinition:
        self._requireEnabled()
        definition = self.definitionStore.findVersion(
            tenant, ensureAgentCode(agentCode), int(version)
        )
        if definition is None:
            raise AIAgentNotFound(f"{ensureAgentCode(agentCode)}@{version}")
        return definition

    def _requireApproval(self, tenant: uuid.UUID, approvalId: uuid.UUID | str) -> AIAgentApproval:
        self._requireEnabled()
        approval = self.approvalStore.getApproval(tenant, requireUuid(approvalId, "approvalId"))
        if approval is None or approval.tenantId != tenant:
            raise AIAgentApprovalNotFound(str(approvalId))
        return approval

    def _requireEnabled(self) -> None:
        if not self.settings.enabled:
            raise AIConfigurationError("The AI agent platform is disabled.")

    def _audit(self, tenant: uuid.UUID, action: str, **kwargs: Any) -> None:
        if self.auditLogger is None:
            return
        self.auditLogger.logAudit(tenant, action, **kwargs)


def _utcNow() -> datetime:
    from apps.ai.domain.entities.aiRecords import utcNow

    return utcNow()


def _principalSubject(principal: Any) -> uuid.UUID | None:
    subject = getattr(principal, "subjectId", None)
    if subject is None:
        return None
    try:
        return requireUuid(subject, "subjectId")
    except (ValueError, TypeError):
        return None


def _knowledgeQuery(payload: dict[str, Any]) -> str:
    """Only an explicit query asks the knowledge boundary; a bare task
    description does not (retrieval is a deliberate, auditable read)."""

    for key in ("query", "question"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class ScriptedAgentModelCaller:
    """Deterministic test provider for the model boundary (Master §41).

    Replays a canned list of ``AgentModelReply`` values in order — the
    agent equivalent of the Phase 13-X ``CallableToolRunner``. Running
    out of replies is an execution failure, never a silent success.
    """

    def __init__(self, replies: Sequence[AgentModelReply] | None = None) -> None:
        self._replies: list[AgentModelReply] = list(replies or [])
        self.requests: list[Any] = []

    def addReply(self, reply: AgentModelReply) -> None:
        if not isinstance(reply, AgentModelReply):
            raise AIAgentInvalid("The scripted caller stores AgentModelReply values.")
        self._replies.append(reply)

    def call(self, tenantId: Any, request: Any) -> AgentModelReply:
        self.requests.append(request)
        if not self._replies:
            raise AIAgentExecutionFailed("The scripted model caller ran out of replies.")
        return self._replies.pop(0)


class ToolExecutorAdapter:
    """Adapts the Phase 13-X ``ToolApplicationService`` to the Y port.

    The adapter is where the §30 chain ends for an agent: everything the
    planner sees of a tool call is an ``AgentToolOutcome``; everything
    the X side sees is an ``InvokeToolCommand`` carrying the run's
    principal — the agent never widens its own authority (Y-D12).
    """

    def __init__(self, toolService: Any, registryProvider: Any = None) -> None:
        self._toolService = toolService
        self._registryProvider = registryProvider

    def declarationsFor(
        self, tenantId: Any, toolCodes: tuple[str, ...]
    ) -> tuple[AgentToolDeclaration, ...]:
        """Resolve declared tool codes to their latest APPROVED version."""

        registry: ToolRegistry = self._toolService.registry(tenantId)
        declarations: list[AgentToolDeclaration] = []
        for code in toolCodes:
            try:
                definition = registry.resolve(code)
            except Exception:  # noqa: BLE001 - unresolvable means undeclared
                continue
            declarations.append(
                AgentToolDeclaration(
                    code=definition.code,
                    version=definition.version,
                    name=definition.name,
                    description=definition.description,
                    effect=definition.effect,
                    inputSchema=dict(definition.inputSchema),
                )
            )
        return tuple(declarations)

    def execute(
        self, tenantId: Any, proposal: ToolProposal, *, principal: Any = None
    ) -> AgentToolOutcome:
        from apps.ai.application.services.toolService import InvokeToolCommand
        from apps.ai.domain.exceptions import (
            AIToolApprovalRequired,
            AIToolBudgetExceeded,
            AIToolDenied,
            AIToolExecutionFailed,
            AIToolNotApproved,
        )

        # Y-D12: the tool runs under the human who started the run — the
        # agent cannot mint its own identity.
        actorId = proposal.actorId
        if principal is not None:
            subject = getattr(principal, "subjectId", None)
            if subject is not None:
                try:
                    actorId = requireUuid(subject, "subjectId")
                except (ValueError, TypeError):
                    actorId = proposal.actorId
        command = InvokeToolCommand(
            toolCode=proposal.toolCode,
            arguments=dict(proposal.arguments),
            version=proposal.version,
            principal=principal,
            requestId=proposal.requestId,
            actorId=actorId,
            reason=proposal.reason,
        )
        try:
            result = self._toolService.invokeTool(tenantId, command)
        except AIToolApprovalRequired as exc:
            return AgentToolOutcome(status="AWAITING_APPROVAL", reason=str(exc))
        except AIToolDenied as exc:
            return AgentToolOutcome(status="DENIED", errorCode="AI_TOOL_DENIED", reason=str(exc))
        except AIToolNotApproved as exc:
            return AgentToolOutcome(
                status="DENIED", errorCode="AI_TOOL_NOT_APPROVED", reason=str(exc)
            )
        except AIToolBudgetExceeded as exc:
            return AgentToolOutcome(
                status="FAILED", errorCode="AI_TOOL_BUDGET_EXCEEDED", reason=str(exc)
            )
        except AIToolExecutionFailed as exc:
            return AgentToolOutcome(
                status="FAILED", errorCode="AI_TOOL_EXECUTION_FAILED", reason=str(exc)
            )
        invocation = result.invocation
        if invocation.status == "SUCCEEDED":
            return AgentToolOutcome(
                status="SUCCEEDED",
                result=dict(invocation.result),
                invocationId=invocation.invocationId,
            )
        if invocation.status == "PENDING" and result.awaitingApproval:
            return AgentToolOutcome(
                status="AWAITING_APPROVAL",
                reason="A human must approve this call.",
                approvalId=result.approval.approvalId if result.approval is not None else None,
            )
        return AgentToolOutcome(
            status=invocation.status,
            result=dict(invocation.result),
            errorCode=invocation.errorCode,
            invocationId=invocation.invocationId,
        )


__all__ = [
    "AUDIT_AGENT_APPROVED",
    "AUDIT_AGENT_DENIED",
    "AUDIT_AGENT_INVOKED",
    "AUDIT_AGENT_REGISTERED",
    "DEFAULT_AGENT_PERMISSION",
    "AgentApplicationService",
    "AgentApprovalDescriptor",
    "AgentDescriptor",
    "AgentRunDescriptor",
    "AgentRunResult",
    "AgentSettings",
    "AgentStepDescriptor",
    "RegisterAgentCommand",
    "RunAgentCommand",
    "ScriptedAgentModelCaller",
    "ToolExecutorAdapter",
]
