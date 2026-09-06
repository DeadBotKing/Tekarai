"""Pure tool registry, gatekeeping, and execution planning for 13-X.

§30 states the rule this module exists to enforce:

> AI نباید Tool را مستقیم اجرا کند — the model never executes a tool.

So the model's output is only ever a ``ToolProposal``. Turning a proposal
into something runnable requires walking the whole chain — registry →
permission → approval — and the only object that can be executed,
``ExecutionTicket``, cannot be constructed any other way. A caller that
"forgets" the permission check has nothing to hand the runner.

Contents:

- ``ToolProposal`` — what the model asked for (untrusted by definition);
- ``ToolRegistry`` — resolution by code and version, latest approved wins;
- ``ArgumentValidator`` — schema, size, and canonical-form checks;
- ``ToolGatekeeper`` — the fail-closed decision, including whether a
  human must approve;
- ``ExecutionBudget`` — per-request call ceiling and loop detection;
- ``ExecutionTicket`` — the only thing an executor accepts.

The module performs no I/O and has no Django, HTTP, ORM, queue, network,
or vendor dependency.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.aiRecords import utcNow
from apps.ai.domain.entities.toolRecords import AIToolApproval, AIToolDefinition
from apps.ai.domain.exceptions import (
    AIToolArgumentsInvalid,
    AIToolBudgetExceeded,
    AIToolInvalid,
    AIToolNotApproved,
    AIToolNotFound,
    AIToolOutputInvalid,
)
from apps.ai.domain.services.aiRules import validateJsonSchema
from apps.ai.domain.valueObjects.toolTypes import (
    ToolPolicy,
    argumentFingerprint,
    argumentSize,
    canonicalArguments,
    ensureToolCode,
    ensureToolVersion,
)


@dataclass(frozen=True)
class ToolProposal:
    """What the model asked for. Untrusted until the chain says otherwise."""

    toolCode: str
    arguments: dict[str, Any] = field(default_factory=dict)
    version: int | None = None
    requestId: uuid.UUID | None = None
    actorId: uuid.UUID | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "toolCode", ensureToolCode(self.toolCode))
        object.__setattr__(self, "arguments", canonicalArguments(self.arguments))
        if self.version is not None:
            object.__setattr__(self, "version", ensureToolVersion(self.version))
        object.__setattr__(self, "reason", str(self.reason or "").strip()[:500])

    def fingerprintFor(self, version: int) -> str:
        return argumentFingerprint(self.toolCode, version, self.arguments)


class ToolRegistry:
    """Resolution over a set of definitions (§30 step one)."""

    def __init__(self, definitions: Sequence[AIToolDefinition] = ()) -> None:
        self._definitions: list[AIToolDefinition] = []
        for definition in definitions:
            self.add(definition)

    def add(self, definition: AIToolDefinition) -> AIToolDefinition:
        if not isinstance(definition, AIToolDefinition):
            raise AIToolInvalid("The registry holds AIToolDefinition values.")
        self._definitions.append(definition)
        return definition

    def versions(self, toolCode: str) -> tuple[AIToolDefinition, ...]:
        code = ensureToolCode(toolCode)
        return tuple(
            sorted(
                (item for item in self._definitions if item.code == code),
                key=lambda item: item.version,
            )
        )

    def resolve(self, toolCode: str, version: int | None = None) -> AIToolDefinition:
        """Resolve a proposal to one definition.

        Without an explicit version the **latest approved** one wins —
        never merely the latest, because a draft must not become callable
        by existing.
        """

        candidates = self.versions(toolCode)
        if not candidates:
            raise AIToolNotFound(ensureToolCode(toolCode))
        if version is not None:
            wanted = ensureToolVersion(version)
            for item in candidates:
                if item.version == wanted:
                    return item
            raise AIToolNotFound(f"{ensureToolCode(toolCode)}@{wanted}")
        approved = [item for item in candidates if item.isRunnable]
        if not approved:
            raise AIToolNotApproved(f"No approved version of {ensureToolCode(toolCode)} exists.")
        return approved[-1]

    def listRunnable(self) -> tuple[AIToolDefinition, ...]:
        return tuple(item for item in self._definitions if item.isRunnable)


class ArgumentValidator:
    """Schema, size, and shape checks for a proposal (§X.9)."""

    def validate(
        self,
        definition: AIToolDefinition,
        arguments: Mapping[str, Any] | None,
        policy: ToolPolicy,
    ) -> dict[str, Any]:
        if not isinstance(definition, AIToolDefinition):
            raise AIToolInvalid("Validation requires an AIToolDefinition.")
        canonical = canonicalArguments(arguments)
        size = argumentSize(canonical)
        if size > policy.maxArgumentBytes:
            raise AIToolArgumentsInvalid(
                f"Arguments are {size} bytes; the ceiling is {policy.maxArgumentBytes}."
            )
        if definition.inputSchema and not validateJsonSchema(canonical, definition.inputSchema):
            raise AIToolArgumentsInvalid(
                f"Arguments do not satisfy the schema of {definition.qualifiedCode}."
            )
        return canonical

    def validateOutput(
        self, definition: AIToolDefinition, result: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        canonical = canonicalArguments(result)
        if definition.outputSchema and not validateJsonSchema(canonical, definition.outputSchema):
            raise AIToolOutputInvalid(
                f"The result of {definition.qualifiedCode} violates its output schema."
            )
        return canonical


@dataclass(frozen=True)
class GateDecision:
    """Why a proposal may or may not proceed (§X.6)."""

    allowed: bool
    definition: AIToolDefinition
    approvalMode: str
    requiresApproval: bool
    approvalsNeeded: int
    reason: str
    errorCode: str = ""

    @property
    def blocked(self) -> bool:
        return not self.allowed


class ToolGatekeeper:
    """The fail-closed decision between registry and execution (§30)."""

    def decide(
        self,
        definition: AIToolDefinition,
        policy: ToolPolicy,
        *,
        permitted: bool,
        approval: AIToolApproval | None = None,
        now: datetime | None = None,
    ) -> GateDecision:
        if not isinstance(definition, AIToolDefinition):
            raise AIToolInvalid("Gatekeeping requires an AIToolDefinition.")
        if not isinstance(policy, ToolPolicy):
            raise AIToolInvalid("Gatekeeping requires a ToolPolicy.")
        moment = now or utcNow()
        mode = policy.modeFor(definition.riskLevel, definition.declaredApprovalMode)
        needed = policy.approvalsNeeded(definition.riskLevel, definition.declaredApprovalMode)

        if mode == "DISABLED":
            return GateDecision(
                allowed=False,
                definition=definition,
                approvalMode=mode,
                requiresApproval=False,
                approvalsNeeded=0,
                reason="The tool declares itself disabled.",
                errorCode="AI_TOOL_NOT_APPROVED",
            )
        if not definition.isRunnable:
            return GateDecision(
                allowed=False,
                definition=definition,
                approvalMode=mode,
                requiresApproval=False,
                approvalsNeeded=needed,
                reason=f"The registry entry is {definition.status}, not APPROVED.",
                errorCode="AI_TOOL_NOT_APPROVED",
            )
        if not permitted:
            return GateDecision(
                allowed=False,
                definition=definition,
                approvalMode=mode,
                requiresApproval=False,
                approvalsNeeded=needed,
                reason=(
                    f"The principal lacks {definition.requiredPermission or 'the required'} "
                    "permission for this tool."
                ),
                errorCode="AI_TOOL_DENIED",
            )
        if needed:
            if approval is None:
                return GateDecision(
                    allowed=False,
                    definition=definition,
                    approvalMode=mode,
                    requiresApproval=True,
                    approvalsNeeded=needed,
                    reason=f"{mode} approval is required before this call may run.",
                    errorCode="AI_TOOL_APPROVAL_REQUIRED",
                )
            if approval.decision == "DENIED":
                return GateDecision(
                    allowed=False,
                    definition=definition,
                    approvalMode=mode,
                    requiresApproval=True,
                    approvalsNeeded=needed,
                    reason=approval.reason or "A human denied this call.",
                    errorCode="AI_TOOL_DENIED",
                )
            if not approval.isUsableAt(moment):
                return GateDecision(
                    allowed=False,
                    definition=definition,
                    approvalMode=mode,
                    requiresApproval=True,
                    approvalsNeeded=needed,
                    reason=(
                        "The approval is still pending or has expired "
                        f"({approval.remainingApprovals} approval(s) outstanding)."
                    ),
                    errorCode="AI_TOOL_APPROVAL_REQUIRED",
                )
        return GateDecision(
            allowed=True,
            definition=definition,
            approvalMode=mode,
            requiresApproval=bool(needed),
            approvalsNeeded=needed,
            reason="Registered, permitted, and approved.",
        )


class ExecutionBudget:
    """Per-request call ceiling and loop detection (§X.10).

    An agent that calls the same tool with the same arguments over and
    over is not working, it is stuck. Counting identical fingerprints is
    the cheapest way to notice, and it needs no timer.
    """

    def __init__(self, *, maxCalls: int, maxRepeats: int = 2) -> None:
        if maxCalls < 1:
            raise AIToolInvalid("The call budget must be positive.")
        if maxRepeats < 1:
            raise AIToolInvalid("The repeat budget must be positive.")
        self.maxCalls = maxCalls
        self.maxRepeats = maxRepeats

    def check(self, fingerprint: str, history: Sequence[str]) -> None:
        used = len(history)
        if used >= self.maxCalls:
            raise AIToolBudgetExceeded(
                f"This request already made {used} tool call(s); the ceiling is {self.maxCalls}."
            )
        repeats = sum(1 for item in history if item == fingerprint)
        if repeats >= self.maxRepeats:
            raise AIToolBudgetExceeded("The same tool call is repeating; refusing to loop.")

    def remaining(self, history: Sequence[str]) -> int:
        return max(0, self.maxCalls - len(history))


@dataclass(frozen=True)
class ExecutionTicket:
    """The only object a tool runner accepts (§30's structural guarantee).

    A ticket can only be produced by ``prepareExecution`` below, which in
    turn requires an *allowed* ``GateDecision``. There is no constructor
    path from a raw model proposal to a runnable ticket.
    """

    definition: AIToolDefinition
    arguments: dict[str, Any]
    fingerprint: str
    approvalId: uuid.UUID | None
    timeoutSeconds: int
    decision: GateDecision

    @property
    def qualifiedCode(self) -> str:
        return self.definition.qualifiedCode


def prepareExecution(
    decision: GateDecision,
    arguments: Mapping[str, Any],
    *,
    policy: ToolPolicy,
    approval: AIToolApproval | None = None,
) -> ExecutionTicket:
    """Turn an allowed decision into a runnable ticket.

    Refusing to build a ticket from a blocked decision is what makes the
    §30 rule structural rather than advisory.
    """

    if not isinstance(decision, GateDecision):
        raise AIToolInvalid("Preparing execution requires a GateDecision.")
    if decision.blocked:
        raise AIToolNotApproved(f"Refusing to execute a blocked proposal: {decision.reason}")
    definition = decision.definition
    canonical = canonicalArguments(arguments)
    return ExecutionTicket(
        definition=definition,
        arguments=canonical,
        fingerprint=argumentFingerprint(definition.code, definition.version, canonical),
        approvalId=None if approval is None else approval.id,
        timeoutSeconds=min(definition.timeoutSeconds, policy.defaultTimeoutSeconds)
        if definition.timeoutSeconds > policy.defaultTimeoutSeconds
        else definition.timeoutSeconds,
        decision=decision,
    )


__all__ = [
    "ArgumentValidator",
    "ExecutionBudget",
    "ExecutionTicket",
    "GateDecision",
    "ToolGatekeeper",
    "ToolProposal",
    "ToolRegistry",
    "prepareExecution",
]
