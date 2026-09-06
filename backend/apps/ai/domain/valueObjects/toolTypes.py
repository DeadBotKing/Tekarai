"""Framework-free tool vocabularies, contracts, and policy for Phase 13-X.

Sub-phase X answers Open Question #10 — *how are tools registered and
approved* — and enforces the §30 rule that gives the whole chapter its
teeth:

> AI نباید Tool را مستقیم اجرا کند — the model never executes a tool.

The model only ever *proposes* a call. What happens next is a pipeline
this module gives vocabulary to: registry → permission → approval →
execution → result.

Contents:

- ``TOOL_EFFECTS`` / ``TOOL_RISK_LEVELS`` — what a tool does to the world
  and how much that matters. Risk is what drives approval, so it is a
  first-class, closed vocabulary rather than a free-form tag;
- ``APPROVAL_MODES`` — the four ways a call may be authorised, from
  ``AUTOMATIC`` to ``DUAL_CONTROL``;
- ``TOOL_STATUSES`` — the registry lifecycle from draft to retired;
- ``ToolPolicy`` — the platform-wide rule that maps risk onto approval;
- argument fingerprinting and secret redaction.

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
Execution *statuses* keep using the Phase 13-B ``TOOL_EXECUTION_STATUSES``
vocabulary; X adds no parallel list.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from apps.ai.domain.valueObjects.aiTypes import (
    TOOL_EXECUTION_STATUSES,
    ensureEnum,
    validateCode,
)
from apps.ai.domain.valueObjects.auditTypes import REDACTED, isSecretKey
from apps.sharedKernel.domain.errors import ValidationFailedError

#: What a tool does to the world. The effect is the honest half of risk:
#: a read can be wrong, a write can be irreversible.
TOOL_EFFECTS = ("READ_ONLY", "MUTATING", "EXTERNAL", "NOTIFYING")

#: How much a mistake costs. Risk drives approval (§X.6).
TOOL_RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

#: How a call is authorised.
APPROVAL_MODES = ("AUTOMATIC", "HUMAN_REQUIRED", "DUAL_CONTROL", "DISABLED")

#: Registry lifecycle of a tool definition.
TOOL_STATUSES = ("DRAFT", "PENDING_APPROVAL", "APPROVED", "SUSPENDED", "RETIRED")
TERMINAL_TOOL_STATUSES = ("RETIRED",)

#: Lifecycle of one human approval request.
APPROVAL_DECISIONS = ("PENDING", "GRANTED", "DENIED", "EXPIRED")

#: Absolute guards independent of configuration (§X.12).
MAX_TOOL_VERSION = 999
MAX_ARGUMENT_BYTES = 65_536
MAX_CALLS_PER_REQUEST = 50
MAX_TIMEOUT_SECONDS = 300

#: Ordering used when a policy compares risk levels.
RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def ensureToolEnum(value: str, allowed: tuple[str, ...], fieldName: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise ValidationFailedError(
            "Unknown tool vocabulary value.", fieldErrors={fieldName: normalized}
        )
    return normalized


def ensureToolEffect(value: str) -> str:
    return ensureToolEnum(value, TOOL_EFFECTS, "effect")


def ensureRiskLevel(value: str) -> str:
    return ensureToolEnum(value, TOOL_RISK_LEVELS, "riskLevel")


def ensureApprovalMode(value: str) -> str:
    return ensureToolEnum(value, APPROVAL_MODES, "approvalMode")


def ensureToolStatus(value: str) -> str:
    return ensureToolEnum(value, TOOL_STATUSES, "toolStatus")


def ensureApprovalDecision(value: str) -> str:
    return ensureToolEnum(value, APPROVAL_DECISIONS, "decision")


def ensureExecutionStatus(value: str) -> str:
    return ensureEnum(value, TOOL_EXECUTION_STATUSES, "toolExecutionStatus")


def ensureToolCode(value: str) -> str:
    return validateCode(value, "toolCode")


def ensureToolVersion(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationFailedError("Tool version must be an integer.")
    if value < 1 or value > MAX_TOOL_VERSION:
        raise ValidationFailedError(
            "Tool version is out of range.", fieldErrors={"version": str(value)}
        )
    return value


def riskAtLeast(riskLevel: str, floor: str) -> bool:
    """True when ``riskLevel`` is at or above ``floor``."""

    return RISK_ORDER[ensureRiskLevel(riskLevel)] >= RISK_ORDER[ensureRiskLevel(floor)]


def redactArguments(arguments: Mapping[str, Any] | None) -> dict[str, Any]:
    """Recursively replace secret-looking values before anything is stored.

    Tool arguments are persisted and audited, so a token passed as an
    argument would otherwise end up in the ledger forever. The decision of
    what "looks secret" is delegated to the Phase 13-O ``isSecretKey``
    helper rather than re-implemented here: one definition, one place to
    fix, and camelCase keys (this codebase's convention) are handled the
    same way the audit scrubber handles them.
    """

    if arguments is None:
        return {}
    if not isinstance(arguments, Mapping):
        raise ValidationFailedError("Tool arguments must be a mapping.")

    def scrub(value: Any, keyHint: str = "") -> Any:
        if keyHint and isSecretKey(keyHint):
            return REDACTED
        if isinstance(value, Mapping):
            return {str(key): scrub(item, str(key)) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [scrub(item, keyHint) for item in value]
        return value

    return {str(key): scrub(item, str(key)) for key, item in arguments.items()}


def canonicalArguments(arguments: Mapping[str, Any] | None) -> dict[str, Any]:
    """Deterministic, JSON-safe form of the argument mapping."""

    if arguments is None:
        return {}
    if not isinstance(arguments, Mapping):
        raise ValidationFailedError("Tool arguments must be a mapping.")

    def canonical(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): canonical(value[key]) for key in sorted(value, key=str)}
        if isinstance(value, (list, tuple)):
            return [canonical(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        raise ValidationFailedError(
            "Tool arguments must be JSON-serializable.",
            fieldErrors={"type": type(value).__name__},
        )

    return {str(key): canonical(item) for key, item in arguments.items()}


def argumentSize(arguments: Mapping[str, Any] | None) -> int:
    return len(
        json.dumps(canonicalArguments(arguments), ensure_ascii=False, sort_keys=True).encode()
    )


def argumentFingerprint(toolCode: str, version: int, arguments: Mapping[str, Any] | None) -> str:
    """Idempotency and loop-detection key for one proposed call."""

    payload = json.dumps(
        canonicalArguments(arguments), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    seed = f"{ensureToolCode(toolCode)}:{ensureToolVersion(version)}:{payload}"
    return hashlib.sha256(seed.encode()).hexdigest()


@dataclass(frozen=True)
class ToolPolicy:
    """Platform rule mapping risk onto approval (Open Question #10)."""

    automaticBelowRisk: str = "HIGH"
    dualControlAtRisk: str = "CRITICAL"
    maxCallsPerRequest: int = 10
    defaultTimeoutSeconds: int = 30
    maxArgumentBytes: int = 16_384
    allowUnapprovedInDraft: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "automaticBelowRisk", ensureRiskLevel(self.automaticBelowRisk))
        object.__setattr__(self, "dualControlAtRisk", ensureRiskLevel(self.dualControlAtRisk))
        if self.maxCallsPerRequest < 1 or self.maxCallsPerRequest > MAX_CALLS_PER_REQUEST:
            raise ValidationFailedError("maxCallsPerRequest is out of range.")
        if self.defaultTimeoutSeconds < 1 or self.defaultTimeoutSeconds > MAX_TIMEOUT_SECONDS:
            raise ValidationFailedError("defaultTimeoutSeconds is out of range.")
        if self.maxArgumentBytes < 1 or self.maxArgumentBytes > MAX_ARGUMENT_BYTES:
            raise ValidationFailedError("maxArgumentBytes is out of range.")
        if not isinstance(self.allowUnapprovedInDraft, bool):
            raise ValidationFailedError("allowUnapprovedInDraft must be boolean.")
        if RISK_ORDER[self.dualControlAtRisk] < RISK_ORDER[self.automaticBelowRisk]:
            raise ValidationFailedError("dualControlAtRisk cannot be below automaticBelowRisk.")

    def modeFor(self, riskLevel: str, declared: str = "") -> str:
        """The approval mode a call actually gets.

        A tool may declare a stricter mode than the platform requires; it
        may never declare a looser one. That asymmetry is the point: a
        registry entry cannot talk its way out of human review.
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
            return "DISABLED"
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

    def signature(self) -> str:
        return (
            f"{self.automaticBelowRisk}|{self.dualControlAtRisk}|"
            f"{self.maxCallsPerRequest}|{self.defaultTimeoutSeconds}"
        )


__all__ = [
    "APPROVAL_DECISIONS",
    "APPROVAL_MODES",
    "MAX_ARGUMENT_BYTES",
    "MAX_CALLS_PER_REQUEST",
    "MAX_TIMEOUT_SECONDS",
    "MAX_TOOL_VERSION",
    "RISK_ORDER",
    "TERMINAL_TOOL_STATUSES",
    "TOOL_EFFECTS",
    "TOOL_RISK_LEVELS",
    "TOOL_STATUSES",
    "ToolPolicy",
    "argumentFingerprint",
    "argumentSize",
    "canonicalArguments",
    "ensureApprovalDecision",
    "ensureApprovalMode",
    "ensureExecutionStatus",
    "ensureRiskLevel",
    "ensureToolCode",
    "ensureToolEffect",
    "ensureToolEnum",
    "ensureToolStatus",
    "ensureToolVersion",
    "redactArguments",
    "riskAtLeast",
]
