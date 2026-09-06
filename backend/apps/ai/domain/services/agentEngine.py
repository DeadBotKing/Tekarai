"""Pure agent orchestration for Phase 13-Y.

The §31 rule this module exists to enforce:

> Agent نباید فقط یک Prompt باشد — an agent is not a prompt.

An agent is a governed node: a versioned definition (identity,
instructions, access level, risk, policies) that plans and acts through
the platform's existing boundaries. The model only ever returns an
``AgentModelReply`` — frozen, untrusted data. Turning a reply into action
runs through the plan-act loop below, where every proposal is checked
against the agent's **access level** (structural — OQ #11's "what" axis)
before it may reach the Phase 13-X chain, and every step is budgeted,
recorded, and handed to the caller as an immutable row.

Contents:

- ``AgentToolDeclaration`` / ``AgentModelRequest`` / ``AgentModelReply``
  — the model boundary's vocabulary (Y-D10);
- ``AgentMemoryContext`` / ``AgentKnowledgeContext`` / ``AgentContext``
  — what the context builder assembles under a token budget (Y-D6);
- ``AgentGateDecision`` / ``AgentGatekeeper`` — the fail-closed run gate
  (OQ #11's "who says yes" axis);
- ``AgentRunBudget`` — one budget for the whole run, shared across steps
  (Y-D4, closes X-OQ #2);
- ``AgentToolOutcome`` — what the Phase 13-X boundary reports back;
- ``AgentPlanner`` — the plan-act loop itself.

The module performs no I/O and has no Django, HTTP, ORM, queue, network,
or vendor dependency.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.agentRecords import AIAgentDefinition, AIAgentRun, AIAgentStep
from apps.ai.domain.entities.aiRecords import utcNow
from apps.ai.domain.exceptions import (
    AIAgentBudgetExceeded,
    AIAgentInvalid,
    AIAgentNotApproved,
    AIAgentOutputInvalid,
    AIContextTooLarge,
)
from apps.ai.domain.services.aiRules import estimateTokens, validateJsonSchema
from apps.ai.domain.services.toolEngine import ToolProposal
from apps.ai.domain.valueObjects.agentTypes import (
    AgentPolicy,
    allowsEffect,
    canonicalInput,
)
from apps.ai.domain.valueObjects.toolTypes import (
    argumentFingerprint,
    ensureToolCode,
    ensureToolVersion,
)

#: Step-level outcome codes recorded on tool rows (not API errors).
STEP_TOOL_NOT_DECLARED = "AI_AGENT_TOOL_NOT_DECLARED"
STEP_TOOL_ACCESS_DENIED = "AI_AGENT_ACCESS_LEVEL_EXCEEDED"
STEP_TOOL_APPROVAL_REQUIRED = "AI_AGENT_TOOL_APPROVAL_REQUIRED"


@dataclass(frozen=True)
class AgentToolDeclaration:
    """One tool the agent may propose, resolved from the Phase 13-X registry."""

    code: str
    version: int
    name: str
    description: str
    effect: str
    inputSchema: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", ensureToolCode(self.code))
        object.__setattr__(self, "version", ensureToolVersion(self.version))
        if not isinstance(self.inputSchema, dict):
            raise AIAgentInvalid("A tool declaration inputSchema must be a mapping.")

    @property
    def qualifiedCode(self) -> str:
        return f"{self.code}@{self.version}"


@dataclass(frozen=True)
class AgentModelRequest:
    """Everything the model boundary may see for one step (Y-D10)."""

    agentCode: str
    agentVersion: int
    instructions: str
    contextText: str
    input: dict[str, Any]
    toolDeclarations: tuple[AgentToolDeclaration, ...] = ()
    history: tuple[AIAgentStep, ...] = ()
    outputSchema: dict[str, Any] = field(default_factory=dict)
    stepNumber: int = 0
    modelPolicy: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "input", canonicalInput(self.input))
        if self.stepNumber < 0:
            raise AIAgentInvalid("Model request stepNumber cannot be negative.")


@dataclass(frozen=True)
class AgentModelReply:
    """What the model asked for. Untrusted until the loop says otherwise.

    A reply carries either a final answer (optionally structured) or at
    least one tool proposal — never both, never neither.
    """

    answer: str | None = None
    structured: dict[str, Any] | None = None
    proposals: tuple[ToolProposal, ...] = ()
    inputTokens: int = 0
    outputTokens: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposals", tuple(self.proposals))
        for proposal in self.proposals:
            if not isinstance(proposal, ToolProposal):
                raise AIAgentInvalid("A reply proposal must be a ToolProposal.")
        if self.answer is not None:
            if self.proposals:
                raise AIAgentInvalid("A reply cannot carry both an answer and proposals.")
            if self.structured is not None and not isinstance(self.structured, dict):
                raise AIAgentInvalid("A reply structured payload must be a mapping.")
        elif not self.proposals:
            raise AIAgentInvalid("A reply must carry an answer or at least one proposal.")
        if min(self.inputTokens, self.outputTokens) < 0:
            raise AIAgentInvalid("A reply token count cannot be negative.")

    @property
    def hasAnswer(self) -> bool:
        return self.answer is not None

    @property
    def totalTokens(self) -> int:
        return self.inputTokens + self.outputTokens


@dataclass(frozen=True)
class AgentMemoryContext:
    """Authorized memories selected for this run (from Phase 13-T)."""

    text: str = ""
    sources: tuple[str, ...] = ()
    tokenCount: int = 0
    entryCount: int = 0


@dataclass(frozen=True)
class AgentKnowledgeContext:
    """Authorized knowledge selected for this run (from Phase 13-R/S)."""

    text: str = ""
    sources: tuple[str, ...] = ()
    tokenCount: int = 0
    chunkCount: int = 0


@dataclass(frozen=True)
class AgentContext:
    """The assembled, budget-checked context for one run (Y-D6)."""

    instructionText: str
    memoryText: str
    knowledgeText: str
    inputText: str
    totalTokens: int
    memorySources: tuple[str, ...] = ()
    knowledgeSources: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def sources(self) -> tuple[str, ...]:
        return self.memorySources + self.knowledgeSources

    def render(self) -> str:
        """The stable, deterministic text form handed to the model."""

        parts = [
            self.instructionText,
            "Context:",
            self.memoryText.strip(),
            self.knowledgeText.strip(),
        ]
        return "\n\n".join(part for part in parts if part) + f"\n\nInput:\n{self.inputText}"


def renderHistory(history: Sequence[AIAgentStep]) -> str:
    """Render prior steps so the model can see what already happened."""

    lines: list[str] = []
    for step in history:
        if step.isToolCall:
            lines.append(
                f"step {step.ordinal} TOOL {step.toolCode}@{step.toolVersion} {step.status}"
                + (f" error={step.errorCode}" if step.errorCode else "")
                + (
                    f" result={json.dumps(step.result, ensure_ascii=False, sort_keys=True)}"
                    if step.result
                    else ""
                )
            )
        else:
            lines.append(f"step {step.ordinal} MODEL {step.status}")
    return "\n".join(lines)


class AgentContextBuilder:
    """Assembles and budget-checks the run context (Y-D6).

    Least privilege: memory and knowledge arrive only from the T/S
    providers, which already ran the Phase 13-K filter; absence of a
    source means an empty section, never a permissive one. The only
    failure here is the token ceiling, which is fail-closed.
    """

    def build(
        self,
        definition: AIAgentDefinition,
        run: AIAgentRun,
        *,
        memory: AgentMemoryContext | None = None,
        knowledge: AgentKnowledgeContext | None = None,
        maxContextTokens: int,
    ) -> AgentContext:
        if not isinstance(definition, AIAgentDefinition):
            raise AIAgentInvalid("Context building requires an AIAgentDefinition.")
        if maxContextTokens < 1:
            raise AIAgentInvalid("The context token ceiling must be positive.")
        memoryContext = memory or AgentMemoryContext()
        knowledgeContext = knowledge or AgentKnowledgeContext()
        inputText = json.dumps(
            canonicalInput(run.input), ensure_ascii=False, sort_keys=True, indent=2
        )
        total = (
            estimateTokens(definition.instructions)
            + estimateTokens(inputText)
            + memoryContext.tokenCount
            + knowledgeContext.tokenCount
        )
        if total > maxContextTokens:
            raise AIContextTooLarge(
                f"Agent context is about {total} tokens; the ceiling is {maxContextTokens}."
            )
        return AgentContext(
            instructionText=definition.instructions,
            memoryText=memoryContext.text,
            knowledgeText=knowledgeContext.text,
            inputText=inputText,
            totalTokens=total,
            memorySources=tuple(memoryContext.sources),
            knowledgeSources=tuple(knowledgeContext.sources),
            metadata={
                "memoryEntries": memoryContext.entryCount,
                "knowledgeChunks": knowledgeContext.chunkCount,
            },
        )


@dataclass(frozen=True)
class AgentGateDecision:
    """Why a requested run may or may not start (OQ #11)."""

    allowed: bool
    definition: AIAgentDefinition
    approvalMode: str
    requiresApproval: bool
    approvalsNeeded: int
    reason: str
    errorCode: str = ""

    @property
    def blocked(self) -> bool:
        return not self.allowed


class AgentGatekeeper:
    """The fail-closed decision between registry and the plan-act loop."""

    def decide(
        self,
        definition: AIAgentDefinition,
        policy: AgentPolicy,
        *,
        permitted: bool,
        capabilitiesAvailable: bool,
        approval: Any = None,
        now: datetime | None = None,
    ) -> AgentGateDecision:
        if not isinstance(definition, AIAgentDefinition):
            raise AIAgentInvalid("Gatekeeping requires an AIAgentDefinition.")
        if not isinstance(policy, AgentPolicy):
            raise AIAgentInvalid("Gatekeeping requires an AgentPolicy.")
        moment = now or utcNow()
        mode = policy.modeFor(definition.riskLevel, definition.declaredApprovalMode)
        needed = policy.approvalsNeeded(definition.riskLevel, definition.declaredApprovalMode)

        if not definition.isRunnable:
            return AgentGateDecision(
                allowed=False,
                definition=definition,
                approvalMode=mode,
                requiresApproval=False,
                approvalsNeeded=needed,
                reason=f"The registry entry is {definition.status}, not APPROVED.",
                errorCode="AI_AGENT_NOT_APPROVED",
            )
        if not permitted:
            return AgentGateDecision(
                allowed=False,
                definition=definition,
                approvalMode=mode,
                requiresApproval=False,
                approvalsNeeded=needed,
                reason=(
                    f"The principal lacks {definition.requiredPermission} "
                    "permission to run this agent."
                ),
                errorCode="AI_AGENT_DENIED",
            )
        if not capabilitiesAvailable:
            return AgentGateDecision(
                allowed=False,
                definition=definition,
                approvalMode=mode,
                requiresApproval=False,
                approvalsNeeded=needed,
                reason="A declared capability is not registered and active for this tenant.",
                errorCode="AI_AGENT_POLICY_INVALID",
            )
        if needed:
            if approval is None:
                return AgentGateDecision(
                    allowed=False,
                    definition=definition,
                    approvalMode=mode,
                    requiresApproval=True,
                    approvalsNeeded=needed,
                    reason=f"{mode} approval is required before this run may start.",
                    errorCode="AI_AGENT_APPROVAL_REQUIRED",
                )
            if approval.decision == "DENIED":
                return AgentGateDecision(
                    allowed=False,
                    definition=definition,
                    approvalMode=mode,
                    requiresApproval=True,
                    approvalsNeeded=needed,
                    reason=approval.reason or "A human denied this run.",
                    errorCode="AI_AGENT_DENIED",
                )
            if not approval.isUsableAt(moment):
                return AgentGateDecision(
                    allowed=False,
                    definition=definition,
                    approvalMode=mode,
                    requiresApproval=True,
                    approvalsNeeded=needed,
                    reason=(
                        "The approval is still pending or has expired "
                        f"({approval.remainingApprovals} approval(s) outstanding)."
                    ),
                    errorCode="AI_AGENT_APPROVAL_REQUIRED",
                )
        return AgentGateDecision(
            allowed=True,
            definition=definition,
            approvalMode=mode,
            requiresApproval=bool(needed),
            approvalsNeeded=needed,
            reason="Approved registry entry, permitted principal, usable approval.",
        )


class AgentRunBudget:
    """One budget for the whole run, shared across steps (Y-D4).

    The step ceiling counts model calls, the call ceiling counts every
    attempted tool call (denied attempts included — a model that keeps
    proposing the same blocked call is stuck, exactly as in Phase 13-X),
    the repeat ceiling is loop detection over fingerprints accumulated
    across steps (X-OQ #2), and the duration ceiling is checked against
    an injected clock so tests stay deterministic.
    """

    def __init__(
        self,
        *,
        maxSteps: int,
        maxToolCalls: int,
        maxRepeats: int,
        maxDurationSeconds: int,
        startedAt: datetime,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if min(maxSteps, maxToolCalls, maxRepeats, maxDurationSeconds) < 1:
            raise AIAgentInvalid("Agent budget ceilings must be positive.")
        self.maxSteps = maxSteps
        self.maxToolCalls = maxToolCalls
        self.maxRepeats = maxRepeats
        self.maxDurationSeconds = maxDurationSeconds
        self.startedAt = startedAt
        self._clock = clock or utcNow
        self.modelCalls = 0
        self.toolCalls = 0
        self.inputTokens = 0
        self.outputTokens = 0
        self._toolFingerprints: tuple[str, ...] = ()

    @classmethod
    def forRun(
        cls,
        policy: AgentPolicy,
        definition: AIAgentDefinition,
        *,
        now: datetime | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> AgentRunBudget:
        """Effective budget = min(platform policy, agent executionPolicy)."""

        execution = definition.executionPolicy
        maxSteps = min(policy.maxSteps, int(execution.get("maxSteps", policy.maxSteps)))
        maxToolCalls = min(
            policy.maxToolCalls, int(execution.get("maxToolCalls", policy.maxToolCalls))
        )
        maxDuration = min(
            policy.maxDurationSeconds,
            int(execution.get("maxDurationSeconds", policy.maxDurationSeconds)),
        )
        return cls(
            maxSteps=maxSteps,
            maxToolCalls=maxToolCalls,
            maxRepeats=policy.maxRepeats,
            maxDurationSeconds=maxDuration,
            startedAt=now or utcNow(),
            clock=clock,
        )

    def _checkDuration(self, now: datetime | None) -> None:
        moment = now or self._clock()
        elapsed = (moment - self.startedAt).total_seconds()
        if elapsed > self.maxDurationSeconds:
            raise AIAgentBudgetExceeded(
                f"The run already took {int(elapsed)}s; the ceiling is {self.maxDurationSeconds}s."
            )

    def checkModelCall(self, now: datetime | None = None) -> None:
        """Claim one step. The claim happens *before* the call is made, so
        a failed call still consumed its step — a run cannot retry a
        crashed model call for free."""

        self._checkDuration(now)
        if self.modelCalls >= self.maxSteps:
            raise AIAgentBudgetExceeded(
                f"This run already made {self.modelCalls} model call(s); the ceiling is {self.maxSteps}."
            )
        self.modelCalls += 1

    def checkToolCall(self, fingerprint: str, now: datetime | None = None) -> None:
        """Claim one tool attempt. Denied attempts count too (Phase 13-X
        semantics): a model that keeps proposing the same blocked call is
        stuck, and the loop ceiling catches it even without a timer."""

        self._checkDuration(now)
        if self.toolCalls >= self.maxToolCalls:
            raise AIAgentBudgetExceeded(
                f"This run already attempted {self.toolCalls} tool call(s); the ceiling is {self.maxToolCalls}."
            )
        repeats = sum(1 for item in self._toolFingerprints if item == fingerprint)
        if repeats >= self.maxRepeats:
            raise AIAgentBudgetExceeded(
                "The same tool call is repeating across steps; refusing to loop."
            )
        self.toolCalls += 1
        self._toolFingerprints = self._toolFingerprints + (fingerprint,)

    def recordModel(self, tokensIn: int, tokensOut: int) -> None:
        """Token accounting for a claimed step (tokens, not steps)."""

        self.inputTokens += tokensIn
        self.outputTokens += tokensOut

    @property
    def totalTokens(self) -> int:
        return self.inputTokens + self.outputTokens

    def remainingSteps(self) -> int:
        return max(0, self.maxSteps - self.modelCalls)

    def remainingToolCalls(self) -> int:
        return max(0, self.maxToolCalls - self.toolCalls)


@dataclass(frozen=True)
class AgentToolOutcome:
    """What the Phase 13-X boundary reports back for one proposal."""

    status: str
    result: dict[str, Any] = field(default_factory=dict)
    errorCode: str = ""
    reason: str = ""
    invocationId: uuid.UUID | None = None
    approvalId: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.status not in ("SUCCEEDED", "FAILED", "DENIED", "AWAITING_APPROVAL"):
            raise AIAgentInvalid(f"Unknown agent tool outcome status: {self.status}")

    @property
    def succeeded(self) -> bool:
        return self.status == "SUCCEEDED"

    @property
    def blocked(self) -> bool:
        return self.status in ("DENIED", "AWAITING_APPROVAL")


@dataclass(frozen=True)
class AgentRunOutcome:
    """The terminal result of the plan-act loop (failures raise instead)."""

    status: str
    answer: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    steps: tuple[AIAgentStep, ...] = ()
    reason: str = ""


class AgentPlanner:
    """The plan-act loop (§Y.8), pure and deterministic.

    The model only ever sees ``AgentModelRequest`` and only ever returns
    ``AgentModelReply``. Every proposal is checked against the agent's
    access level *before* it may reach the tool executor, and the
    executor is the Phase 13-X chain itself — there is no other path
    from a reply to an executed tool (Y-D3).
    """

    def __init__(
        self,
        modelCaller: Any,
        toolExecutor: Any,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not callable(getattr(modelCaller, "call", None)):
            raise AIAgentInvalid("The planner requires an AgentModelCaller.")
        if not callable(getattr(toolExecutor, "execute", None)):
            raise AIAgentInvalid("The planner requires an AgentToolExecutor.")
        self.modelCaller = modelCaller
        self.toolExecutor = toolExecutor
        self._clock = clock or utcNow

    def run(
        self,
        tenantId: uuid.UUID,
        definition: AIAgentDefinition,
        run: AIAgentRun,
        context: AgentContext,
        budget: AgentRunBudget,
        *,
        principal: Any = None,
        declarations: Sequence[AgentToolDeclaration] = (),
        on_step: Callable[[AIAgentStep], None] | None = None,
    ) -> AgentRunOutcome:
        if not isinstance(definition, AIAgentDefinition) or not definition.isRunnable:
            raise AIAgentNotApproved("The planner only runs approved agent versions.")
        byCode = {declaration.code: declaration for declaration in declarations}
        history: list[AIAgentStep] = []
        ordinal = 0
        stepNumber = 0
        now = self._clock()
        while True:
            budget.checkModelCall(now)
            stepNumber += 1
            workingContext = context.render()
            if history:
                workingContext = f"{workingContext}\n\nPrevious steps:\n{renderHistory(history)}"
            request = AgentModelRequest(
                agentCode=definition.code,
                agentVersion=definition.version,
                instructions=definition.instructions,
                contextText=workingContext,
                input=dict(run.input),
                toolDeclarations=tuple(declarations),
                history=tuple(history),
                outputSchema=dict(definition.outputSchema),
                stepNumber=stepNumber,
                modelPolicy=dict(definition.modelPolicy),
            )
            reply = self.modelCaller.call(tenantId, request)
            if not isinstance(reply, AgentModelReply):
                raise AIAgentInvalid("The model caller must return an AgentModelReply.")
            budget.recordModel(reply.inputTokens, reply.outputTokens)

            if reply.hasAnswer:
                if reply.structured is not None and definition.outputSchema:
                    if not validateJsonSchema(reply.structured, definition.outputSchema):
                        raise AIAgentOutputInvalid(
                            f"The final structured output of {definition.qualifiedCode} "
                            "violates its output schema."
                        )
                ordinal += 1
                step = AIAgentStep(
                    tenantId=tenantId,
                    runId=run.id,
                    ordinal=ordinal,
                    kind="MODEL",
                    status="SUCCEEDED",
                    result={
                        "answer": reply.answer or "",
                        "structured": dict(reply.structured or {}),
                    },
                    tokensIn=reply.inputTokens,
                    tokensOut=reply.outputTokens,
                )
                history.append(step)
                if on_step is not None:
                    on_step(step)
                return AgentRunOutcome(
                    status="COMPLETED",
                    answer=reply.answer or "",
                    output=dict(reply.structured or {}),
                    steps=tuple(history),
                    reason="The model returned a final answer.",
                )

            for proposal in reply.proposals:
                ordinal += 1
                now = self._clock()
                declaration = byCode.get(proposal.toolCode)
                # Budget accounting happens for *every* attempted call —
                # denied attempts included (Phase 13-X semantics): a model
                # that keeps proposing the same blocked call is stuck.
                # Undeclared tools have no registry version to pin; the key
                # exists for loop detection only, so a placeholder version
                # keeps the seed deterministic.
                fingerprint = argumentFingerprint(
                    proposal.toolCode,
                    declaration.version if declaration is not None else 1,
                    proposal.arguments,
                )
                budget.checkToolCall(fingerprint, now)
                if declaration is None:
                    step = AIAgentStep(
                        tenantId=tenantId,
                        runId=run.id,
                        ordinal=ordinal,
                        kind="TOOL",
                        status="DENIED",
                        toolCode=proposal.toolCode,
                        toolVersion=proposal.version or 0,
                        arguments=dict(proposal.arguments),
                        reason=f"The agent may not propose {proposal.toolCode}; it is not declared.",
                        errorCode=STEP_TOOL_NOT_DECLARED,
                    )
                    history.append(step)
                    if on_step is not None:
                        on_step(step)
                    continue
                if not allowsEffect(definition.accessLevel, declaration.effect):
                    step = AIAgentStep(
                        tenantId=tenantId,
                        runId=run.id,
                        ordinal=ordinal,
                        kind="TOOL",
                        status="DENIED",
                        toolCode=declaration.code,
                        toolVersion=declaration.version,
                        arguments=dict(proposal.arguments),
                        reason=(
                            f"The agent's access level {definition.accessLevel} may not "
                            f"propose tools with effect {declaration.effect}."
                        ),
                        errorCode=STEP_TOOL_ACCESS_DENIED,
                    )
                    history.append(step)
                    if on_step is not None:
                        on_step(step)
                    continue
                outcome: AgentToolOutcome
                try:
                    outcome = self.toolExecutor.execute(tenantId, proposal, principal=principal)
                except AIAgentBudgetExceeded:
                    raise
                except Exception as exc:  # noqa: BLE001 — the boundary must not leak vendor errors
                    outcome = AgentToolOutcome(
                        status="FAILED",
                        errorCode="AI_AGENT_EXECUTION_FAILED",
                        reason=f"Tool execution failed: {type(exc).__name__}",
                    )
                if not isinstance(outcome, AgentToolOutcome):
                    outcome = AgentToolOutcome(
                        status="FAILED",
                        errorCode="AI_AGENT_EXECUTION_FAILED",
                        reason="The tool executor returned an invalid outcome.",
                    )
                status = outcome.status
                errorCode = outcome.errorCode
                reason = outcome.reason
                result = dict(outcome.result or {})
                if outcome.status == "AWAITING_APPROVAL":
                    # Y-D11: a mid-run tool that needs a human does not
                    # pause the run; the model is told the call did not
                    # happen and decides what to do next.
                    status = "DENIED"
                    errorCode = STEP_TOOL_APPROVAL_REQUIRED
                    reason = outcome.reason or "The tool requires human approval; it did not run."
                step = AIAgentStep(
                    tenantId=tenantId,
                    runId=run.id,
                    ordinal=ordinal,
                    kind="TOOL",
                    status=status,
                    toolCode=declaration.code,
                    toolVersion=declaration.version,
                    arguments=dict(proposal.arguments),
                    result=result,
                    reason=reason,
                    errorCode=errorCode,
                )
                history.append(step)
                if on_step is not None:
                    on_step(step)
            # The model returned only proposals; the loop continues and the
            # budget decides how many more chances it gets.


def toolFingerprintFor(
    definition: AIAgentDefinition, toolCode: str, version: int, arguments: Any
) -> str:
    """Convenience: the loop-detection key for one proposed call."""

    return argumentFingerprint(toolCode, version, arguments)


def inputKeyFor(definition: AIAgentDefinition, payload: Any) -> str:
    """The approval-binding key for one requested run input."""

    return json.dumps(canonicalInput(payload), ensure_ascii=False, sort_keys=True)


__all__ = [
    "AgentContext",
    "AgentContextBuilder",
    "AgentGateDecision",
    "AgentGatekeeper",
    "AgentKnowledgeContext",
    "AgentMemoryContext",
    "AgentModelReply",
    "AgentModelRequest",
    "AgentPlanner",
    "AgentRunBudget",
    "AgentRunOutcome",
    "AgentToolDeclaration",
    "AgentToolOutcome",
    "STEP_TOOL_ACCESS_DENIED",
    "STEP_TOOL_APPROVAL_REQUIRED",
    "STEP_TOOL_NOT_DECLARED",
    "inputKeyFor",
    "renderHistory",
    "toolFingerprintFor",
]
