"""Framework-free metering value objects for Phase 13-N.

This module defines the controlled vocabularies and small immutable values
used by Usage, Token, Latency, Cost and Quota tracking:

- ``QuotaScope`` / ``QuotaDimension`` / ``QuotaWindow`` — the three axes of a
  quota policy (who/what is limited, which metric, over which period);
- ``LatencyBreakdown`` — the §27 latency split (queue, context build,
  provider, validation) with a derived total;
- ``UsageAttribution`` — the §26 reporting axes (user, department, project,
  capability, model, provider) carried by every metering call;
- UTC window arithmetic — deterministic period boundaries for quota windows.

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from apps.sharedKernel.domain.errors import ValidationFailedError

QUOTA_SCOPES = (
    "TENANT",
    "USER",
    "DEPARTMENT",
    "PROJECT",
    "CAPABILITY",
    "MODEL",
)
QUOTA_DIMENSIONS = (
    "REQUESTS",
    "INPUT_TOKENS",
    "OUTPUT_TOKENS",
    "TOTAL_TOKENS",
    "COST",
)
QUOTA_WINDOWS = (
    "MINUTE",
    "HOUR",
    "DAY",
    "WEEK",
    "MONTH",
)
ATTEMPT_OUTCOMES = (
    "SUCCEEDED",
    "FAILED",
)

#: Specificity order used for quota precedence (§N.4): the most specific
#: matching policy is reported first when several policies deny one attempt.
SCOPE_PRECEDENCE = (
    "USER",
    "PROJECT",
    "DEPARTMENT",
    "CAPABILITY",
    "MODEL",
    "TENANT",
)


def ensureQuotaScope(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in QUOTA_SCOPES:
        raise ValidationFailedError("Unknown quota scope.", fieldErrors={"scope": normalized})
    return normalized


def ensureQuotaDimension(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in QUOTA_DIMENSIONS:
        raise ValidationFailedError(
            "Unknown quota dimension.", fieldErrors={"dimension": normalized}
        )
    return normalized


def ensureQuotaWindow(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in QUOTA_WINDOWS:
        raise ValidationFailedError("Unknown quota window.", fieldErrors={"window": normalized})
    return normalized


def ensureAttemptOutcome(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in ATTEMPT_OUTCOMES:
        raise ValidationFailedError("Unknown attempt outcome.", fieldErrors={"outcome": normalized})
    return normalized


def asUtc(moment: datetime) -> datetime:
    """Treat naive datetimes as UTC; convert aware datetimes to UTC."""

    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def windowStart(moment: datetime, window: str) -> datetime:
    """Return the deterministic UTC start of the window containing ``moment``.

    Weeks follow ISO-8601 (Monday 00:00 UTC); months are calendar months.
    """

    normalizedWindow = ensureQuotaWindow(window)
    current = asUtc(moment)
    if normalizedWindow == "MINUTE":
        return current.replace(second=0, microsecond=0)
    if normalizedWindow == "HOUR":
        return current.replace(minute=0, second=0, microsecond=0)
    if normalizedWindow == "DAY":
        return current.replace(hour=0, minute=0, second=0, microsecond=0)
    if normalizedWindow == "WEEK":
        monday = current - timedelta(days=current.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    firstOfMonth = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return firstOfMonth


def windowEnd(start: datetime, window: str) -> datetime:
    """Return the exclusive UTC end of the window that starts at ``start``."""

    normalizedWindow = ensureQuotaWindow(window)
    normalizedStart = asUtc(start)
    if normalizedWindow == "MINUTE":
        return normalizedStart + timedelta(minutes=1)
    if normalizedWindow == "HOUR":
        return normalizedStart + timedelta(hours=1)
    if normalizedWindow == "DAY":
        return normalizedStart + timedelta(days=1)
    if normalizedWindow == "WEEK":
        return normalizedStart + timedelta(days=7)
    if normalizedStart.month == 12:
        return normalizedStart.replace(year=normalizedStart.year + 1, month=1)
    return normalizedStart.replace(month=normalizedStart.month + 1)


@dataclass(frozen=True)
class QuotaScope:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", ensureQuotaScope(self.value))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class QuotaDimension:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", ensureQuotaDimension(self.value))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class QuotaWindow:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", ensureQuotaWindow(self.value))

    def __str__(self) -> str:
        return self.value

    def startFor(self, moment: datetime) -> datetime:
        return windowStart(moment, self.value)

    def endFor(self, start: datetime) -> datetime:
        return windowEnd(start, self.value)


@dataclass(frozen=True)
class LatencyBreakdown:
    """The §27 latency split for one provider attempt (milliseconds)."""

    queueMs: int = 0
    contextBuildMs: int = 0
    providerMs: int = 0
    validationMs: int = 0

    def __post_init__(self) -> None:
        for fieldName in ("queueMs", "contextBuildMs", "providerMs", "validationMs"):
            value = getattr(self, fieldName)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValidationFailedError(
                    "Latency parts must be non-negative integers.",
                    fieldErrors={fieldName: value},
                )

    @property
    def totalMs(self) -> int:
        return self.queueMs + self.contextBuildMs + self.providerMs + self.validationMs


@dataclass(frozen=True)
class UsageAttribution:
    """The §26 reporting axes carried by every metering and quota call.

    Only ``capabilityCode``, ``modelCode`` and ``providerCode`` identify the
    consumed platform objects; the remaining fields are opaque references
    owned by other bounded contexts (AI never resolves them).
    """

    capabilityCode: str = ""
    modelCode: str = ""
    providerCode: str = ""
    userId: str = ""
    departmentCode: str = ""
    projectId: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilityCode", str(self.capabilityCode or "").strip().upper())
        object.__setattr__(self, "modelCode", str(self.modelCode or "").strip().upper())
        object.__setattr__(self, "providerCode", str(self.providerCode or "").strip().upper())
        object.__setattr__(self, "userId", str(self.userId or "").strip())
        object.__setattr__(self, "departmentCode", str(self.departmentCode or "").strip().upper())
        object.__setattr__(self, "projectId", str(self.projectId or "").strip())


__all__ = [
    "ATTEMPT_OUTCOMES",
    "QUOTA_DIMENSIONS",
    "QUOTA_SCOPES",
    "QUOTA_WINDOWS",
    "SCOPE_PRECEDENCE",
    "LatencyBreakdown",
    "QuotaDimension",
    "QuotaScope",
    "QuotaWindow",
    "UsageAttribution",
    "asUtc",
    "ensureAttemptOutcome",
    "ensureQuotaDimension",
    "ensureQuotaScope",
    "ensureQuotaWindow",
    "windowEnd",
    "windowStart",
]
