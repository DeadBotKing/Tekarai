"""User value objects — full account lifecycle (Phase 07 §3–§4).

Eight lifecycle states (§3): INVITED · PENDING_ACTIVATION · ACTIVE ·
SUSPENDED · LOCKED · DISABLED · EXPIRED · DELETED.

LOCKED and EXPIRED are *temporal* conditions expressed by ``lockedUntil`` /
``expiresAt`` on the aggregate (§4) — the status map models the durable
lifecycle; ``effectiveStatusOf`` derives LOCKED/EXPIRED overlays so security
checks never rely on a bare ``isActive`` flag (§3 rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.sharedKernel.domain.valueObjects import ValueObject

USER_INVITED = "invited"
USER_PENDING_ACTIVATION = "pendingActivation"
USER_ACTIVE = "active"
USER_SUSPENDED = "suspended"
USER_DISABLED = "disabled"
USER_DELETED = "deleted"

#: Durable status transitions (§3). LOCKED/EXPIRED are temporal overlays.
USER_STATUS_TRANSITIONS: dict[str, tuple[str, ...]] = {
    USER_INVITED: (USER_PENDING_ACTIVATION, USER_ACTIVE, USER_SUSPENDED, USER_DISABLED),
    USER_PENDING_ACTIVATION: (USER_ACTIVE, USER_DISABLED),
    USER_ACTIVE: (USER_SUSPENDED, USER_DISABLED),
    USER_SUSPENDED: (USER_ACTIVE, USER_DISABLED),
    USER_DISABLED: (),  # terminal — revival is a deliberate admin exception
}

#: Temporal overlay states (§3): ACTIVE → LOCKED → ACTIVE / EXPIRED.
USER_LOCKED = "locked"
USER_EXPIRED = "expired"

LOCKABLE_STATUSES = (USER_ACTIVE, USER_INVITED, USER_PENDING_ACTIVATION)


@dataclass(frozen=True)
class UserStatus(ValueObject):
    value: str

    def __post_init__(self) -> None:
        if self.value not in USER_STATUS_TRANSITIONS:
            raise ValidationFailedError("Invalid user status.", fieldErrors={"status": self.value})

    def canTransitionTo(self, target: str) -> bool:
        return target in USER_STATUS_TRANSITIONS[self.value]

    def __str__(self) -> str:
        return self.value


def effectiveStatusOf(
    status: str,
    *,
    lockedUntil: datetime | None = None,
    expiresAt: datetime | None = None,
    now: datetime,
) -> str:
    """Derive the effective security status (LOCKED/EXPIRED overlays, §3)."""
    if lockedUntil is not None and lockedUntil > now:
        return USER_LOCKED
    if expiresAt is not None and expiresAt <= now:
        return USER_EXPIRED
    return status


def validatePasswordStrength(
    plain: str,
    *,
    minLength: int = 12,
    requireComplexity: bool = True,
) -> str:
    """Configurable password policy (Phase 07 §23) — domain-side check.

    The effective configuration comes from settings (see
    ``config/settings/base.py PASSWORD_POLICY``); expiration is a business
    decision and stays OFF by default (§23).
    """
    problems: list[str] = []
    if len(plain) < minLength:
        problems.append(f"at least {minLength} characters")
    if requireComplexity:
        if plain.isalpha() or plain.isdigit() or plain.isalnum():
            problems.append("at least one non-alphanumeric character")
        if plain.islower() or plain.isupper():
            problems.append("mixed case")
    if problems:
        raise ValidationFailedError(
            "Password does not meet the policy.",
            fieldErrors={"password": "; ".join(problems)},
        )
    return plain
