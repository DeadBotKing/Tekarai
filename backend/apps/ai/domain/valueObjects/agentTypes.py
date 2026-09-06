"""Framework-free agent vocabularies, contracts, and policy for Phase 13-Y.

Sub-phase Y answers Open Question #11 — *what may an agent do, and who
says yes* — as two deliberately separate axes:

1. **Access level** (``ADVISORY`` / ``READ_ONLY`` / ``MUTATING`` /
   ``AUTONOMOUS``): what the agent may *do* to the world. This axis is
   structural — a proposal whose tool effect exceeds the level's
   allowlist never reaches the Phase 13-X chain, so no amount of
   approval can buy a higher effect. The level lives in the immutable
   versioned definition, not in the approval workflow;
2. **Approval** (risk → ``AUTOMATIC`` / ``HUMAN_REQUIRED`` /
   ``DUAL_CONTROL``): who says *yes* to a run. The mapping is
   configuration-driven and reuses the Phase 13-X asymmetry: a
   definition may declare a *stricter* mode, never a looser one.

Contents:

- ``AGENT_ACCESS_LEVELS`` / ``ACCESS_EFFECT_ALLOWLIST`` — the structural
  axis, expressed as an effect allowlist per level;
- ``AGENT_STATUSES`` — the registry lifecycle (mirror of X);
- ``AGENT_STEP_KINDS`` / ``AGENT_STEP_STATUSES`` — what one step row is;
- ``AgentPolicy`` — platform rule mapping risk onto approval plus the
  budget ceilings for one run;
- input fingerprinting and secret redaction (delegated to the shared
  Phase 13-O/X definitions).

The module has no Django, HTTP, ORM, queue, network, or vendor
dependency. Execution *statuses* keep using the Phase 13-B
``AGENT_EXECUTION_STATUSES`` vocabulary; Y adds no parallel list.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from apps.ai.domain.valueObjects.aiTypes import validateCode
from apps.ai.domain.valueObjects.toolTypes import (
    RISK_ORDER,
    TOOL_EFFECTS,
    TOOL_STATUSES,
    argumentFingerprint,
    canonicalArguments,
    ensureApprovalMode,
    ensureRiskLevel,
    redactArguments,
    riskAtLeast,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

#: What an agent may do to the world (the "what" half of OQ #11).
AGENT_ACCESS_LEVELS = ("ADVISORY", "READ_ONLY", "MUTATING", "AUTONOMOUS")

#: The structural allowlist: which tool effects each level may ever
#: propose. ``ADVISORY`` has none — an advisory agent is text for humans
#: and no amount of approval changes that.
ACCESS_EFFECT_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "ADVISORY": (),
    "READ_ONLY": ("READ_ONLY",),
    "MUTATING": ("READ_ONLY", "MUTATING", "NOTIFYING"),
    "AUTONOMOUS": TOOL_EFFECTS,
}

#: Ordering used when an agent compares access levels.
ACCESS_ORDER = {"ADVISORY": 0, "READ_ONLY": 1, "MUTATING": 2, "AUTONOMOUS": 3}

#: Registry lifecycle of an agent definition (mirror of the tool one).
AGENT_STATUSES = TOOL_STATUSES
TERMINAL_AGENT_STATUSES = ("RETIRED",)

#: What one step row records.
AGENT_STEP_KINDS = ("MODEL", "TOOL")

#: Terminal statuses a step row is written with (steps are immutable).
AGENT_STEP_STATUSES = ("SUCCEEDED", "FAILED", "DENIED")

#: Absolute guards independent of configuration (§Y.15).
MAX_AGENT_VERSION = 999
MAX_AGENT_STEPS = 50
MAX_AGENT_TOOL_CALLS = 100
MAX_AGENT_REPEATS = 5
MAX_AGENT_DURATION_SECONDS = 1800
MAX_APPROVAL_TTL_SECONDS = 30 * 24 * 3600  # a month: review must be possible
MAX_AGENT_CONTEXT_TOKENS = 131_072
MAX_INSTRUCTIONS_BYTES = 65_536
MAX_AGENT_INPUT_BYTES = 65_536
MAX_AGENT_NAME_LENGTH = 160
MAX_AGENT_DESCRIPTION_LENGTH = 1000

#: Permission required to run an agent that declares none of its own.
DEFAULT_AGENT_PERMISSION = "AI_AGENT_RUN"


def ensureAgentEnum(value: str, allowed: tuple[str, ...], fieldName: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise ValidationFailedError(
            "Unknown agent vocabulary value.", fieldErrors={fieldName: normalized}
        )
    return normalized


def ensureAgentAccessLevel(value: str) -> str:
    return ensureAgentEnum(value, AGENT_ACCESS_LEVELS, "accessLevel")


def ensureAgentStatus(value: str) -> str:
    return ensureAgentEnum(value, AGENT_STATUSES, "agentStatus")


def ensureStepKind(value: str) -> str:
    return ensureAgentEnum(value, AGENT_STEP_KINDS, "stepKind")


def ensureStepStatus(value: str) -> str:
    return ensureAgentEnum(value, AGENT_STEP_STATUSES, "stepStatus")


def ensureAgentCode(value: str) -> str:
    return validateCode(value, "agentCode")


def ensureAgentVersion(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationFailedError("Agent version must be an integer.")
    if value < 1 or value > MAX_AGENT_VERSION:
        raise ValidationFailedError(
            "Agent version is out of range.", fieldErrors={"version": str(value)}
        )
    return value


def accessEffectAllowlist(accessLevel: str) -> tuple[str, ...]:
    """The tool effects this level may ever propose (§Y.4.1)."""

    return ACCESS_EFFECT_ALLOWLIST[ensureAgentAccessLevel(accessLevel)]


def allowsEffect(accessLevel: str, effect: str) -> bool:
    """Structural check: may this level even *propose* this effect?"""

    if effect not in TOOL_EFFECTS:
        return False
    return effect in accessEffectAllowlist(accessLevel)


def redactInput(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Secret scrubbing for run input — the Phase 13-O/X definition."""

    return redactArguments(payload)


def inputFingerprint(agentCode: str, version: int, payload: Mapping[str, Any] | None) -> str:
    """Idempotency and approval-binding key for one requested run."""

    return argumentFingerprint(agentCode, version, payload)


@dataclass(frozen=True)
class AgentPolicy:
    """Platform rule mapping risk onto approval (OQ #11) plus budget ceilings.

    Mirrors the Phase 13-X ``ToolPolicy`` risk mapping so an agent and a
    tool with the same risk get the same human review. The asymmetry rule
    is identical: a definition may declare a *stricter* approval mode than
    the platform requires, never a looser one.
    """

    automaticBelowRisk: str = "HIGH"
    dualControlAtRisk: str = "CRITICAL"
    maxSteps: int = 10
    maxToolCalls: int = 20
    maxRepeats: int = 2
    maxDurationSeconds: int = 120
    maxContextTokens: int = 16_000
    maxInstructionsBytes: int = 16_384
    maxInputBytes: int = 65_536
    approvalTtlSeconds: int = 3600
    retentionDays: int = 365

    def __post_init__(self) -> None:
        object.__setattr__(self, "automaticBelowRisk", ensureRiskLevel(self.automaticBelowRisk))
        object.__setattr__(self, "dualControlAtRisk", ensureRiskLevel(self.dualControlAtRisk))
        if RISK_ORDER[self.dualControlAtRisk] < RISK_ORDER[self.automaticBelowRisk]:
            raise ValidationFailedError("dualControlAtRisk cannot be below automaticBelowRisk.")
        for name, ceiling in (
            ("maxSteps", MAX_AGENT_STEPS),
            ("maxToolCalls", MAX_AGENT_TOOL_CALLS),
            ("maxRepeats", MAX_AGENT_REPEATS),
            ("maxDurationSeconds", MAX_AGENT_DURATION_SECONDS),
            ("maxContextTokens", MAX_AGENT_CONTEXT_TOKENS),
            ("maxInstructionsBytes", MAX_INSTRUCTIONS_BYTES),
            ("maxInputBytes", MAX_AGENT_INPUT_BYTES),
            ("approvalTtlSeconds", MAX_APPROVAL_TTL_SECONDS),
            ("retentionDays", 36_500),
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValidationFailedError(f"Agent policy {name} must be an integer.")
            if value < 1 or value > ceiling:
                raise ValidationFailedError(
                    f"Agent policy {name} is out of range.", fieldErrors={name: str(value)}
                )

    def modeFor(self, riskLevel: str, declared: str = "") -> str:
        """The approval mode a run actually gets (the "who says yes" axis).

        An agent definition may declare a stricter mode than the platform
        requires; it may never declare a looser one — the registry entry
        cannot talk its way out of human review.
        """

        risk = ensureRiskLevel(riskLevel)
        if riskAtLeast(risk, self.dualControlAtRisk):
            required = "DUAL_CONTROL"
        elif riskAtLeast(risk, self.automaticBelowRisk):
            required = "HUMAN_REQUIRED"
        else:
            required = "AUTOMATIC"
        if not declared:
            return required
        chosen = ensureApprovalMode(declared)
        if chosen == "DISABLED":
            # A tool may declare itself disabled; an agent expresses the
            # same thing through its registry status (SUSPENDED), so
            # DISABLED is not a valid agent declaration.
            raise ValidationFailedError("Agents cannot declare DISABLED; suspend instead.")
        strictness = {"AUTOMATIC": 0, "HUMAN_REQUIRED": 1, "DUAL_CONTROL": 2}
        return chosen if strictness[chosen] > strictness[required] else required

    def requiresHuman(self, riskLevel: str, declared: str = "") -> bool:
        return self.modeFor(riskLevel, declared) in ("HUMAN_REQUIRED", "DUAL_CONTROL")

    def approvalsNeeded(self, riskLevel: str, declared: str = "") -> int:
        mode = self.modeFor(riskLevel, declared)
        if mode == "DUAL_CONTROL":
            return 2
        if mode == "HUMAN_REQUIRED":
            return 1
        return 0


def canonicalInput(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Deterministic, JSON-safe form of the run input."""

    return canonicalArguments(payload)


def inputSize(payload: Mapping[str, Any] | None) -> int:
    return len(json.dumps(canonicalInput(payload), ensure_ascii=False, sort_keys=True).encode())


__all__ = [
    "ACCESS_EFFECT_ALLOWLIST",
    "ACCESS_ORDER",
    "AGENT_ACCESS_LEVELS",
    "AGENT_STATUSES",
    "AGENT_STEP_KINDS",
    "AGENT_STEP_STATUSES",
    "AgentPolicy",
    "DEFAULT_AGENT_PERMISSION",
    "MAX_AGENT_CONTEXT_TOKENS",
    "MAX_AGENT_DESCRIPTION_LENGTH",
    "MAX_AGENT_DURATION_SECONDS",
    "MAX_AGENT_INPUT_BYTES",
    "MAX_AGENT_NAME_LENGTH",
    "MAX_AGENT_REPEATS",
    "MAX_APPROVAL_TTL_SECONDS",
    "MAX_AGENT_STEPS",
    "MAX_AGENT_TOOL_CALLS",
    "MAX_AGENT_VERSION",
    "MAX_INSTRUCTIONS_BYTES",
    "TERMINAL_AGENT_STATUSES",
    "accessEffectAllowlist",
    "allowsEffect",
    "canonicalInput",
    "ensureAgentAccessLevel",
    "ensureAgentCode",
    "ensureAgentEnum",
    "ensureAgentStatus",
    "ensureAgentVersion",
    "ensureStepKind",
    "ensureStepStatus",
    "inputFingerprint",
    "inputSize",
    "redactInput",
]
