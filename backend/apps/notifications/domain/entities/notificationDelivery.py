"""Per-channel delivery entity (Phase 09 §25, §24, §47)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from apps.notifications.domain.valueObjects.notificationTypes import (
    DEFAULT_MAX_ATTEMPTS,
    DELIVERY_DELIVERED,
    DELIVERY_FAILED,
    DELIVERY_PERMANENTLY_FAILED,
    DELIVERY_PENDING,
    DELIVERY_RETRY_SCHEDULED,
    DELIVERY_SENT,
    DELIVERY_SKIPPED,
    DELIVERY_STATUSES,
    PERMANENT_ERROR_CODES,
    RETRY_BACKOFF_MULTIPLIER,
    RETRY_BASE_DELAY_SECONDS,
    RETRY_MAX_DELAY_SECONDS,
)
from apps.sharedKernel.domain.entities import AggregateRoot
from apps.sharedKernel.domain.errors import ValidationFailedError


class NotificationDelivery(AggregateRoot):
    """§25 — every channel keeps its OWN status; §47 — one channel failing
    never fails the notification."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        notificationId: uuid.UUID,
        channel: str,
        provider: str,
        *,
        status: str = DELIVERY_PENDING,
        attemptCount: int = 0,
        maxAttempts: int = DEFAULT_MAX_ATTEMPTS,
        lastAttemptAt: datetime | None = None,
        nextAttemptAt: datetime | None = None,
        deliveredAt: datetime | None = None,
        failedAt: datetime | None = None,
        errorCode: str = "",
        errorMessage: str = "",
        createdAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        if status not in DELIVERY_STATUSES:
            raise ValidationFailedError(
                "Unknown delivery status.", fieldErrors={"status": status}
            )
        self.tenantId = tenantId
        self.notificationId = notificationId
        self.channel = channel
        self.provider = provider
        self.status = status
        self.attemptCount = attemptCount
        self.maxAttempts = maxAttempts
        self.lastAttemptAt = lastAttemptAt
        self.nextAttemptAt = nextAttemptAt
        self.deliveredAt = deliveredAt
        self.failedAt = failedAt
        self.errorCode = errorCode
        self.errorMessage = errorMessage
        self.createdAt = createdAt or datetime.now()

    # -- outcomes -------------------------------------------------------------

    def skip(self, now: datetime, reason: str) -> None:
        """Preference/policy turned the channel off — not a failure."""
        self.status = DELIVERY_SKIPPED
        self.errorMessage = reason

    def markSent(self, now: datetime) -> None:
        self.status = DELIVERY_SENT
        self.lastAttemptAt = now
        self.attemptCount += 1

    def markDelivered(self, now: datetime) -> None:
        self.status = DELIVERY_DELIVERED
        self.deliveredAt = now
        self.lastAttemptAt = now
        self.errorCode = ""
        self.errorMessage = ""

    def markFailed(
        self, now: datetime, *, errorCode: str, errorMessage: str
    ) -> bool:
        """Returns True when a retry is scheduled (§24 exponential backoff)."""
        self.lastAttemptAt = now
        self.errorCode = errorCode
        self.errorMessage = errorMessage[:500]
        if errorCode in PERMANENT_ERROR_CODES:
            self.status = DELIVERY_PERMANENTLY_FAILED  # §24 — never retry these
            self.failedAt = now
            return False
        if self.attemptCount >= self.maxAttempts:
            self.status = DELIVERY_PERMANENTLY_FAILED
            self.failedAt = now
            return False
        self.status = DELIVERY_RETRY_SCHEDULED
        self.nextAttemptAt = now + timedelta(
            seconds=backoffDelay(self.attemptCount + 1)
        )
        return True

    def retryIsDue(self, now: datetime) -> bool:
        """True when a RETRY_SCHEDULED delivery's backoff window elapsed."""
        if self.status != DELIVERY_RETRY_SCHEDULED:
            return False
        return self.nextAttemptAt is not None and self.nextAttemptAt <= now

    def isPendingRetry(self) -> bool:
        return self.status == DELIVERY_RETRY_SCHEDULED


def backoffDelay(attempt: int) -> int:
    """§24 — 30s → 2m → 10m … capped."""
    delay = RETRY_BASE_DELAY_SECONDS * (RETRY_BACKOFF_MULTIPLIER ** max(0, attempt - 1))
    return min(int(delay), RETRY_MAX_DELAY_SECONDS)
