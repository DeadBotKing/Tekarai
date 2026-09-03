"""Phase 12 notification value objects & constants (docs/Phases/Phase12.md).

Phase 09 shipped a single-recipient notification row. Phase 12 introduces the
canonical multi-recipient model (§12.3/§12.7/§12.8): one Notification that
fans out to many NotificationRecipients, each owning its own read/archive
state (never a ``Notification.isRead`` — §12.8), plus delivery attempts
(§12.16), dead-letter (§12.18), quiet hours (§12.21), rules (§12.24) and a
webhook channel (§12.12). Everything here is framework-free.
"""

from __future__ import annotations

from apps.sharedKernel.domain.errors import ValidationFailedError

# ---------------------------------------------------------------------------
# §12.15 delivery lifecycle (superset; §12.15 keeps SENT vs DELIVERED distinct)
# ---------------------------------------------------------------------------

DLV_PENDING = "PENDING"
DLV_QUEUED = "QUEUED"
DLV_PROCESSING = "PROCESSING"
DLV_SENT = "SENT"
DLV_DELIVERED = "DELIVERED"
DLV_FAILED = "FAILED"
DLV_CANCELLED = "CANCELLED"
DLV_EXPIRED = "EXPIRED"
DLV_DEAD_LETTER = "DEAD_LETTER"

DELIVERY_LIFECYCLE = (
    DLV_PENDING,
    DLV_QUEUED,
    DLV_PROCESSING,
    DLV_SENT,
    DLV_DELIVERED,
    DLV_FAILED,
    DLV_CANCELLED,
    DLV_EXPIRED,
    DLV_DEAD_LETTER,
)

# legal forward transitions for a channel delivery
DELIVERY_TRANSITIONS: dict[str, tuple[str, ...]] = {
    DLV_PENDING: (DLV_QUEUED, DLV_CANCELLED, DLV_EXPIRED, DLV_FAILED),
    DLV_QUEUED: (DLV_PROCESSING, DLV_CANCELLED, DLV_EXPIRED, DLV_FAILED),
    DLV_PROCESSING: (DLV_SENT, DLV_DELIVERED, DLV_FAILED, DLV_CANCELLED, DLV_EXPIRED),
    DLV_SENT: (DLV_DELIVERED, DLV_FAILED),
    DLV_FAILED: (DLV_QUEUED, DLV_DEAD_LETTER, DLV_CANCELLED),
    DLV_DELIVERED: (),
    DLV_CANCELLED: (),
    DLV_EXPIRED: (),
    DLV_DEAD_LETTER: (DLV_QUEUED,),  # ops can re-queue a dead letter (§12.18)
}

# ---------------------------------------------------------------------------
# §12.16 attempt outcome
# ---------------------------------------------------------------------------

ATTEMPT_FAILED = "FAILED"
ATTEMPT_SENT = "SENT"
ATTEMPT_DELIVERED = "DELIVERED"

ATTEMPT_OUTCOMES = (ATTEMPT_FAILED, ATTEMPT_SENT, ATTEMPT_DELIVERED)

# ---------------------------------------------------------------------------
# §12.7 recipient state (read state lives HERE, never on Notification)
# ---------------------------------------------------------------------------

RECIPIENT_UNREAD = "UNREAD"
RECIPIENT_READ = "READ"
RECIPIENT_ARCHIVED = "ARCHIVED"
RECIPIENT_DISMISSED = "DISMISSED"

RECIPIENT_STATES = (
    RECIPIENT_UNREAD,
    RECIPIENT_READ,
    RECIPIENT_ARCHIVED,
    RECIPIENT_DISMISSED,
)

RECIPIENT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    RECIPIENT_UNREAD: (RECIPIENT_READ, RECIPIENT_ARCHIVED, RECIPIENT_DISMISSED),
    RECIPIENT_READ: (RECIPIENT_UNREAD, RECIPIENT_ARCHIVED, RECIPIENT_DISMISSED),
    RECIPIENT_ARCHIVED: (RECIPIENT_READ, RECIPIENT_UNREAD),
    RECIPIENT_DISMISSED: (RECIPIENT_READ, RECIPIENT_UNREAD),
}

# ---------------------------------------------------------------------------
# §12.6 severity (distinct from priority §12.5)
# ---------------------------------------------------------------------------

SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_ERROR = "ERROR"
SEVERITY_CRITICAL = "CRITICAL"

SEVERITIES = (SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ERROR, SEVERITY_CRITICAL)

# ---------------------------------------------------------------------------
# §12.12 channels — Phase 12 adds WEBHOOK to the Phase 09 set
# ---------------------------------------------------------------------------

CHANNEL_WEBHOOK = "WEBHOOK"

# priority → default channels (§12.5). Higher priority fans out wider.
PRIORITY_CHANNEL_ROUTING: dict[str, tuple[str, ...]] = {
    "LOW": ("IN_APP",),
    "NORMAL": ("IN_APP", "EMAIL"),
    "HIGH": ("IN_APP", "EMAIL", "PUSH"),
    "URGENT": ("IN_APP", "EMAIL", "PUSH", "SMS"),
    "CRITICAL": ("IN_APP", "EMAIL", "PUSH", "SMS", "WEBHOOK"),
}

# priorities that bypass quiet hours (§12.21)
QUIET_HOURS_BYPASS_PRIORITIES = ("URGENT", "CRITICAL")
QUIET_HOURS_BYPASS_CATEGORIES = ("SECURITY", "SYSTEM")

# ---------------------------------------------------------------------------
# §12.22 schedule lifecycle
# ---------------------------------------------------------------------------

SCHEDULE_SCHEDULED = "SCHEDULED"
SCHEDULE_PROCESSING = "PROCESSING"
SCHEDULE_COMPLETED = "COMPLETED"
SCHEDULE_FAILED = "FAILED"
SCHEDULE_CANCELLED = "CANCELLED"

SCHEDULE_STATES = (
    SCHEDULE_SCHEDULED,
    SCHEDULE_PROCESSING,
    SCHEDULE_COMPLETED,
    SCHEDULE_FAILED,
    SCHEDULE_CANCELLED,
)

# ---------------------------------------------------------------------------
# §12.17 retry policy defaults (never hard-coded at call sites — overridable)
# ---------------------------------------------------------------------------

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_INITIAL_DELAY_SECONDS = 30
DEFAULT_BACKOFF_MULTIPLIER = 2.0
DEFAULT_MAX_DELAY_SECONDS = 3600  # 1 hour


class RetryPolicy:
    """§12.17 — configurable exponential backoff (no hard-coded retries)."""

    def __init__(
        self,
        *,
        maxAttempts: int = DEFAULT_MAX_ATTEMPTS,
        initialDelaySeconds: int = DEFAULT_INITIAL_DELAY_SECONDS,
        backoffMultiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
        maxDelaySeconds: int = DEFAULT_MAX_DELAY_SECONDS,
    ) -> None:
        if maxAttempts < 1:
            raise ValidationFailedError(
                "maxAttempts must be >= 1.", fieldErrors={"maxAttempts": maxAttempts}
            )
        if initialDelaySeconds < 0 or maxDelaySeconds < 0:
            raise ValidationFailedError("delays must be non-negative.")
        if backoffMultiplier < 1.0:
            raise ValidationFailedError("backoffMultiplier must be >= 1.0.")
        self.maxAttempts = maxAttempts
        self.initialDelaySeconds = initialDelaySeconds
        self.backoffMultiplier = backoffMultiplier
        self.maxDelaySeconds = maxDelaySeconds

    def delayForAttempt(self, attemptNumber: int) -> int:
        """Delay (seconds) before the given 1-based attempt number."""
        if attemptNumber <= 1:
            return 0
        raw = self.initialDelaySeconds * (
            self.backoffMultiplier ** (attemptNumber - 2)
        )
        return min(int(raw), self.maxDelaySeconds)

    def isExhausted(self, attemptCount: int) -> bool:
        """§12.18 — attempts at/over the cap become dead-letter candidates."""
        return attemptCount >= self.maxAttempts


# ---------------------------------------------------------------------------
# §12.21 quiet hours
# ---------------------------------------------------------------------------


class QuietHours:
    """Per-user daily quiet window; supports windows crossing midnight.

    Times are minutes-from-midnight in the user's timezone (we keep the value
    object tz-agnostic; the application layer supplies the local wall clock).
    """

    def __init__(self, startMinute: int, endMinute: int) -> None:
        for label, value in (("startMinute", startMinute), ("endMinute", endMinute)):
            if not 0 <= value <= 24 * 60:
                raise ValidationFailedError(
                    f"{label} out of range.", fieldErrors={label: value}
                )
        if startMinute == endMinute:
            raise ValidationFailedError("quiet hours start and end cannot be equal.")
        self.startMinute = startMinute
        self.endMinute = endMinute

    def contains(self, minuteOfDay: int) -> bool:
        if self.startMinute < self.endMinute:
            # same-day window, e.g. 08:00 -> 18:00
            return self.startMinute <= minuteOfDay < self.endMinute
        # overnight window, e.g. 22:00 -> 08:00
        return minuteOfDay >= self.startMinute or minuteOfDay < self.endMinute


def shouldBypassQuietHours(priority: str, category: str) -> bool:
    """§12.21 — CRITICAL/URGENT and security/system alerts go out immediately."""
    return (
        priority in QUIET_HOURS_BYPASS_PRIORITIES
        or category in QUIET_HOURS_BYPASS_CATEGORIES
    )


def validateOneOf(value: str, allowed: tuple[str, ...], *, field: str) -> str:
    if value not in allowed:
        raise ValidationFailedError(f"Invalid {field}.", fieldErrors={field: value})
    return value
