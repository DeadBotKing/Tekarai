"""Controlled retry, fallback, timeout and error boundary for Phase 13-M.

M builds on the stable domain error surface fixed by Phase 13-L: adapter
failures already arrive as classified Tekarai errors, so this pure domain
service decides *which* of them are transient, how many times an operation
may be repeated, which provider chain to walk, and where the whole operation
stops. The master specification §25 requires a configurable failover chain
(primary -> secondary -> local) and §44 forbids blind retries — this module
is the mechanical form of those two rules.

The service is framework-free and deterministic: clock and sleep arrive
through small injected ports, the provider registry (Phase 13-D) resolves
adapters per tenant, and operations are received as callables. Persistence,
queueing, cost accounting and audit are later sub-phases (N/O/P).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, runtime_checkable

from apps.ai.domain.exceptions import (
    AIProviderInactive,
    AIProviderNotRegistered,
    AIProviderUnavailable,
    AIRequestTimeout,
)
from apps.ai.domain.ports import AIProviderPort, GenerationRequest
from apps.ai.domain.registries.providerRegistry import ProviderRegistry
from apps.sharedKernel.domain.errors import TekaraiError, ValidationFailedError

ResultT = TypeVar("ResultT")

#: Transient error codes per master specification §44 — the only class of
#: failures a controlled retry may repeat. Everything else is fatal.
TRANSIENT_ERROR_CODES = frozenset(
    {
        "AI_REQUEST_TIMEOUT",
        "AI_PROVIDER_UNAVAILABLE",
        "AI_PROVIDER_RATE_LIMITED",
    }
)

OUTCOME_SUCCESS = "SUCCESS"
OUTCOME_RETRYABLE_ERROR = "RETRYABLE_ERROR"
OUTCOME_FATAL_ERROR = "FATAL_ERROR"
OUTCOME_SKIPPED = "SKIPPED"
OUTCOMES = (OUTCOME_SUCCESS, OUTCOME_RETRYABLE_ERROR, OUTCOME_FATAL_ERROR, OUTCOME_SKIPPED)

REPORT_ATTRIBUTE = "resilienceReport"


# --------------------------------------------------------------------------- #
# Time ports (injectable — tests use deterministic fakes)
# --------------------------------------------------------------------------- #
@runtime_checkable
class ResilienceClock(Protocol):
    def monotonicSeconds(self) -> float: ...


@runtime_checkable
class ResilienceSleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


class MonotonicClock:
    """Default clock backed by the monotonic system clock."""

    def monotonicSeconds(self) -> float:
        return time.monotonic()


class RealSleeper:
    """Default sleeper for production execution."""

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


# --------------------------------------------------------------------------- #
# Policies
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RetryPolicy:
    """Controlled retry behaviour for one chain step (master spec §44)."""

    maxAttempts: int = 3
    initialBackoffSeconds: float = 0.25
    backoffMultiplier: float = 2.0
    maxBackoffSeconds: float = 5.0
    retryableErrorCodes: frozenset[str] = TRANSIENT_ERROR_CODES

    def __post_init__(self) -> None:
        if not isinstance(self.maxAttempts, int) or isinstance(self.maxAttempts, bool):
            raise ValidationFailedError("Retry maxAttempts must be an integer.")
        if self.maxAttempts < 1:
            raise ValidationFailedError("Retry maxAttempts must be at least 1.")
        for name, value in (
            ("initialBackoffSeconds", self.initialBackoffSeconds),
            ("maxBackoffSeconds", self.maxBackoffSeconds),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValidationFailedError(f"Retry {name} must be a non-negative number.")
        if (
            not isinstance(self.backoffMultiplier, (int, float))
            or isinstance(self.backoffMultiplier, bool)
            or self.backoffMultiplier < 1
        ):
            raise ValidationFailedError("Retry backoffMultiplier must be at least 1.")
        if self.maxBackoffSeconds < self.initialBackoffSeconds:
            raise ValidationFailedError("Retry maxBackoffSeconds must cap the initial backoff.")
        if not isinstance(self.retryableErrorCodes, frozenset):
            raise ValidationFailedError("Retry retryableErrorCodes must be a frozenset.")
        normalized = frozenset(str(code).strip().upper() for code in self.retryableErrorCodes)
        object.__setattr__(self, "retryableErrorCodes", normalized)

    def backoffForAttempt(self, retryIndex: int) -> float:
        """Deterministic backoff before retry number ``retryIndex`` (0-based)."""

        if retryIndex < 0:
            raise ValidationFailedError("Retry index cannot be negative.")
        delay = self.initialBackoffSeconds * (self.backoffMultiplier**retryIndex)
        return min(delay, self.maxBackoffSeconds)

    def isTransient(self, error: BaseException) -> bool:
        return isinstance(error, TekaraiError) and error.code in self.retryableErrorCodes


@dataclass(frozen=True)
class FallbackPolicy:
    """Ordered provider chain; the first member is the primary step."""

    providerCodes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized: list[str] = []
        for code in self.providerCodes:
            clean = str(code or "").strip().upper()
            if not clean:
                raise ValidationFailedError("Fallback provider codes must be non-empty.")
            if clean in normalized:
                raise ValidationFailedError(f"Duplicate fallback provider code '{clean}'.")
            normalized.append(clean)
        object.__setattr__(self, "providerCodes", tuple(normalized))

    @property
    def primaryCode(self) -> str:
        if not self.providerCodes:
            raise ValidationFailedError("Fallback policy has no primary provider.")
        return self.providerCodes[0]

    def stepsAfter(self, providerCode: str) -> tuple[str, ...]:
        anchor = str(providerCode or "").strip().upper()
        if anchor not in self.providerCodes:
            return self.providerCodes
        anchorIndex = self.providerCodes.index(anchor)
        return self.providerCodes[anchorIndex + 1 :]


# --------------------------------------------------------------------------- #
# Records and reports
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AttemptRecord:
    """One observed attempt inside a resilient execution."""

    providerCode: str
    attemptNumber: int
    outcome: str
    errorCode: str = ""
    backoffSeconds: float = 0.0

    def __post_init__(self) -> None:
        if not str(self.providerCode).strip():
            raise ValidationFailedError("Attempt record requires a provider code.")
        if self.attemptNumber < 1:
            raise ValidationFailedError("Attempt number must be positive.")
        if self.outcome not in OUTCOMES:
            raise ValidationFailedError("Unknown attempt outcome.")
        if self.backoffSeconds < 0:
            raise ValidationFailedError("Attempt backoff cannot be negative.")
        object.__setattr__(self, "providerCode", str(self.providerCode).strip().upper())
        object.__setattr__(self, "errorCode", str(self.errorCode or "").strip().upper())


@dataclass(frozen=True)
class ResilienceReport:
    """Immutable execution report attached to outcomes and final errors."""

    success: bool
    finalProviderCode: str = ""
    attempts: tuple[AttemptRecord, ...] = ()
    fallbackUsed: bool = False
    finalErrorCode: str = ""
    totalBackoffSeconds: float = 0.0

    def __post_init__(self) -> None:
        if self.finalProviderCode:
            object.__setattr__(self, "finalProviderCode", self.finalProviderCode.upper())
        if self.finalErrorCode:
            object.__setattr__(self, "finalErrorCode", self.finalErrorCode.upper())

    @property
    def attemptsCount(self) -> int:
        return len(self.attempts)


@dataclass(frozen=True)
class ExecutionOutcome:
    """Successful resilient execution: business result plus its report."""

    result: Any
    report: ResilienceReport


def reportFromError(error: BaseException) -> ResilienceReport | None:
    """Read the resilience report attached to a final error, if present."""

    report = getattr(error, REPORT_ATTRIBUTE, None)
    return report if isinstance(report, ResilienceReport) else None


def attachReport(error: BaseException, report: ResilienceReport) -> BaseException:
    setattr(error, REPORT_ATTRIBUTE, report)
    return error


# --------------------------------------------------------------------------- #
# Executor
# --------------------------------------------------------------------------- #
AttemptRecorder = Callable[[AttemptRecord], None]


class ResilientProviderExecutor:
    """Retry + fallback + timeout budget + error boundary around the registry.

    The executor never opens the network itself; it runs the supplied
    operation against adapters resolved from the Phase 13-D registry and
    applies the configured policies to whatever domain error surfaces.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        retryPolicy: RetryPolicy | None = None,
        clock: ResilienceClock | None = None,
        sleeper: ResilienceSleeper | None = None,
        timeoutBudgetSeconds: float | None = None,
        recorder: AttemptRecorder | None = None,
    ) -> None:
        if not isinstance(registry, ProviderRegistry):
            raise ValidationFailedError("Resilient executor requires a provider registry.")
        if timeoutBudgetSeconds is not None and timeoutBudgetSeconds <= 0:
            raise ValidationFailedError("Timeout budget must be positive when provided.")
        self.registry = registry
        self.retryPolicy = retryPolicy or RetryPolicy()
        self.clock = clock or MonotonicClock()
        self.sleeper = sleeper or RealSleeper()
        self.timeoutBudgetSeconds = timeoutBudgetSeconds
        self.recorder = recorder

    # ------------------------------------------------------------------ #
    # Public surface
    # ------------------------------------------------------------------ #
    def execute(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        operation: Callable[[AIProviderPort], ResultT],
        *,
        fallbackProviderCodes: Iterable[str] = (),
    ) -> ExecutionOutcome:
        """Run ``operation`` with retry/fallback; raise the final domain error."""

        chain = self._buildChain(providerCode, fallbackProviderCodes)
        startedAt = self.clock.monotonicSeconds()
        attempts: list[AttemptRecord] = []
        lastError: BaseException | None = None
        primaryCode = chain[0]

        for index, stepCode in enumerate(chain):
            isPrimary = index == 0
            adapter = self._resolveStep(tenantId, stepCode, attempts, isPrimary=isPrimary)
            if adapter is None:
                continue  # unresolvable fallback step — recorded SKIPPED
            for attemptNumber in range(1, self.retryPolicy.maxAttempts + 1):
                self._assertBudget(startedAt, attempts, primaryCode)
                outcome, error, result = self._attempt(adapter, operation)
                if outcome == OUTCOME_SUCCESS:
                    successRecord = AttemptRecord(
                        providerCode=stepCode,
                        attemptNumber=attemptNumber,
                        outcome=OUTCOME_SUCCESS,
                    )
                    attempts.append(successRecord)
                    self._record(successRecord)
                    report = self._report(
                        success=True,
                        finalProviderCode=stepCode,
                        attempts=attempts,
                        primaryCode=primaryCode,
                    )
                    return ExecutionOutcome(result=result, report=report)
                assert error is not None
                attempts.append(
                    AttemptRecord(
                        providerCode=stepCode,
                        attemptNumber=attemptNumber,
                        outcome=outcome,
                        errorCode=errorCodeOf(error),
                    )
                )
                self._record(attempts[-1])
                if outcome == OUTCOME_FATAL_ERROR:
                    raise self._finalize(error, attempts, primaryCode)
                lastError = error
                if attemptNumber < self.retryPolicy.maxAttempts:
                    backoff = self.retryPolicy.backoffForAttempt(attemptNumber - 1)
                    self.sleeper.sleep(backoff)
                    attempts[-1] = AttemptRecord(
                        providerCode=stepCode,
                        attemptNumber=attemptNumber,
                        outcome=outcome,
                        errorCode=errorCodeOf(error),
                        backoffSeconds=backoff,
                    )

        # Chain exhausted — every step burned its retry budget.
        finalError = lastError or AIProviderUnavailable("Provider chain exhausted.")
        raise self._finalize(finalError, attempts, primaryCode)

    def generateWithFallback(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        request: GenerationRequest,
        *,
        fallbackProviderCodes: Iterable[str] = (),
    ) -> ExecutionOutcome:
        """Convenience wrapper: resilient generation from a C-contract request."""

        if not isinstance(request, GenerationRequest):
            raise ValidationFailedError("Resilient generation requires a GenerationRequest.")
        return self.execute(
            tenantId,
            providerCode,
            lambda adapter: adapter.generateRequest(request),
            fallbackProviderCodes=fallbackProviderCodes,
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _buildChain(self, providerCode: str, fallbackProviderCodes: Iterable[str]) -> list[str]:
        primary = str(providerCode or "").strip().upper()
        if not primary:
            raise ValidationFailedError("Provider code is required.")
        chain = [primary]
        for code in fallbackProviderCodes:
            normalized = str(code or "").strip().upper()
            if normalized and normalized not in chain:
                chain.append(normalized)
        return chain

    def _resolveStep(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        attempts: list[AttemptRecord],
        *,
        isPrimary: bool,
    ) -> AIProviderPort | None:
        try:
            return self.registry.resolveProvider(tenantId, providerCode)
        except (AIProviderNotRegistered, AIProviderInactive) as error:
            if isPrimary:
                # A missing/inactive primary is a configuration error — it is
                # raised immediately; fallback cannot repair configuration.
                raise
            record = AttemptRecord(
                providerCode=providerCode,
                attemptNumber=1,
                outcome=OUTCOME_SKIPPED,
                errorCode=errorCodeOf(error),
            )
            attempts.append(record)
            self._record(record)
            return None

    def _attempt(
        self,
        adapter: AIProviderPort,
        operation: Callable[[AIProviderPort], ResultT],
    ) -> tuple[str, BaseException | None, ResultT | None]:
        try:
            result = operation(adapter)
        except TekaraiError as error:
            if self.retryPolicy.isTransient(error):
                return OUTCOME_RETRYABLE_ERROR, error, None
            return OUTCOME_FATAL_ERROR, error, None
        except Exception as exc:  # noqa: BLE001 — the error boundary
            # Non-domain exceptions never cross the boundary: they become a
            # stable, classified, fatal domain error (fail closed).
            boundaryError = AIProviderUnavailable("Provider operation failed unexpectedly.")
            boundaryError.__cause__ = exc
            return OUTCOME_FATAL_ERROR, boundaryError, None
        return OUTCOME_SUCCESS, None, result

    def _assertBudget(
        self,
        startedAt: float,
        attempts: list[AttemptRecord],
        primaryCode: str,
    ) -> None:
        if self.timeoutBudgetSeconds is None:
            return
        elapsed = self.clock.monotonicSeconds() - startedAt
        if elapsed >= self.timeoutBudgetSeconds:
            timeoutError = AIRequestTimeout("AI operation exceeded its timeout budget.")
            raise self._finalize(timeoutError, attempts, primaryCode)

    def _finalize(
        self,
        error: BaseException,
        attempts: list[AttemptRecord],
        primaryCode: str,
    ) -> BaseException:
        finalCode = errorCodeOf(error)
        fallbackUsed = any(record.providerCode != primaryCode for record in attempts)
        report = ResilienceReport(
            success=False,
            finalProviderCode=attempts[-1].providerCode if attempts else primaryCode,
            attempts=tuple(attempts),
            fallbackUsed=fallbackUsed,
            finalErrorCode=finalCode,
            totalBackoffSeconds=sum(record.backoffSeconds for record in attempts),
        )
        return attachReport(error, report)

    def _report(
        self,
        *,
        success: bool,
        finalProviderCode: str,
        attempts: list[AttemptRecord],
        primaryCode: str,
    ) -> ResilienceReport:
        fallbackUsed = any(record.providerCode != primaryCode for record in attempts)
        return ResilienceReport(
            success=success,
            finalProviderCode=finalProviderCode,
            attempts=tuple(attempts),
            fallbackUsed=fallbackUsed,
            totalBackoffSeconds=sum(record.backoffSeconds for record in attempts),
        )

    def _record(self, record: AttemptRecord) -> None:
        if self.recorder is None:
            return
        self.recorder(record)


def errorCodeOf(error: BaseException) -> str:
    """Stable error code for reports; non-domain errors are labelled."""

    code = getattr(error, "code", "")
    return str(code).strip().upper() if code else "SYS_INTERNAL_ERROR"


__all__ = [
    "AttemptRecord",
    "AttemptRecorder",
    "ExecutionOutcome",
    "FallbackPolicy",
    "MonotonicClock",
    "OUTCOME_FATAL_ERROR",
    "OUTCOME_RETRYABLE_ERROR",
    "OUTCOME_SKIPPED",
    "OUTCOME_SUCCESS",
    "OUTCOMES",
    "REPORT_ATTRIBUTE",
    "RealSleeper",
    "ResilienceClock",
    "ResilienceReport",
    "ResilientProviderExecutor",
    "ResilienceSleeper",
    "RetryPolicy",
    "TRANSIENT_ERROR_CODES",
    "attachReport",
    "errorCodeOf",
    "reportFromError",
]
