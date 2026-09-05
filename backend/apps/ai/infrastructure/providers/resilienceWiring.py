"""Django-aware composition wiring for AI resilience (Phase 13-M).

The domain executor ``ResilientProviderExecutor`` is framework-free; this
module is the single place allowed to read Django settings and hand concrete
values to it, mirroring the Phase 13-L wiring pattern. Configuration stays
environment-driven (ADR-009, Master Specification §42): retry limits,
backoff curve, timeout budget and the fallback chain all come from
``settings.AI_RESILIENCE`` and are validated before the executor exists.
"""

from __future__ import annotations

from typing import Any

from apps.ai.domain.registries.providerRegistry import ProviderRegistry
from apps.ai.domain.services.providerResilience import (
    AttemptRecorder,
    FallbackPolicy,
    MonotonicClock,
    RealSleeper,
    ResilienceClock,
    ResilienceSleeper,
    ResilientProviderExecutor,
    RetryPolicy,
)
from apps.sharedKernel.domain.errors import ValidationFailedError


def readResilienceSettings(settingsModule: Any = None) -> dict[str, Any]:
    """Return the configured ``AI_RESILIENCE`` mapping (never None)."""

    if settingsModule is None:
        from django.conf import settings as djangoSettings

        settingsModule = djangoSettings
    mapping = getattr(settingsModule, "AI_RESILIENCE", {})
    return dict(mapping) if isinstance(mapping, dict) else {}


def parseFallbackChain(rawValue: Any) -> tuple[str, ...]:
    """Parse a comma-separated provider chain into normalized codes.

    Blank entries are ignored; ordering is preserved; normalization and
    duplicate rejection are delegated to ``FallbackPolicy``.
    """

    text = str(rawValue or "").strip()
    if not text:
        return ()
    codes = [part.strip() for part in text.split(",") if part.strip()]
    return FallbackPolicy(providerCodes=tuple(codes)).providerCodes


def buildRetryPolicy(settingsModule: Any = None) -> RetryPolicy:
    """Build the controlled retry policy from settings (§44)."""

    values = readResilienceSettings(settingsModule)
    return RetryPolicy(
        maxAttempts=int(numericSetting(values, "aiRetryMaxAttempts", 3.0)),
        initialBackoffSeconds=numericSetting(values, "aiRetryInitialBackoffSeconds", 0.25),
        backoffMultiplier=numericSetting(values, "aiRetryBackoffMultiplier", 2.0),
        maxBackoffSeconds=numericSetting(values, "aiRetryMaxBackoffSeconds", 5.0),
    )


def buildFallbackPolicy(settingsModule: Any = None) -> FallbackPolicy:
    """Build the ordered fallback chain from settings (§25)."""

    values = readResilienceSettings(settingsModule)
    return FallbackPolicy(providerCodes=parseFallbackChain(values.get("aiProviderFallbackChain")))


def numericSetting(values: dict[str, Any], key: str, default: float) -> float:
    """Parse a numeric setting value; missing/blank falls back to default.

    Explicit values — including zero — are returned as parsed, so policy
    validation can reject them instead of silently substituting a default.
    """

    raw = values.get(key)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return default
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationFailedError(f"Configuration value '{key}' must be numeric.") from exc


def readTimeoutBudgetSeconds(settingsModule: Any = None) -> float:
    """Read the wall-clock budget for one resilient operation (> 0)."""

    values = readResilienceSettings(settingsModule)
    budget = numericSetting(values, "aiProviderTimeoutBudgetSeconds", 60.0)
    if budget <= 0:
        raise ValidationFailedError("aiProviderTimeoutBudgetSeconds must be positive.")
    return budget


def fallbackStepsFor(primaryCode: str, settingsModule: Any = None) -> tuple[str, ...]:
    """Return the configured chain steps after ``primaryCode``.

    When the primary is not part of the configured chain (for example a
    tenant explicitly chose a provider outside the chain), no fallback
    steps are injected — fallback never rewrites an explicit choice.
    """

    policy = buildFallbackPolicy(settingsModule)
    return policy.stepsAfter(primaryCode)


def buildResilientExecutor(
    registry: ProviderRegistry,
    *,
    settingsModule: Any = None,
    clock: ResilienceClock | None = None,
    sleeper: ResilienceSleeper | None = None,
    recorder: AttemptRecorder | None = None,
) -> ResilientProviderExecutor:
    """Compose a fully configured executor from settings and a registry."""

    if not isinstance(registry, ProviderRegistry):
        raise ValidationFailedError("Resilient wiring requires a provider registry.")
    return ResilientProviderExecutor(
        registry,
        retryPolicy=buildRetryPolicy(settingsModule),
        clock=clock or MonotonicClock(),
        sleeper=sleeper or RealSleeper(),
        timeoutBudgetSeconds=readTimeoutBudgetSeconds(settingsModule),
        recorder=recorder,
    )


__all__ = [
    "buildFallbackPolicy",
    "buildResilientExecutor",
    "buildRetryPolicy",
    "fallbackStepsFor",
    "parseFallbackChain",
    "readResilienceSettings",
    "readTimeoutBudgetSeconds",
]
