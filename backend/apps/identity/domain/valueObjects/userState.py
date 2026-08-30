"""User value objects — closed status set (§8) and credentials policy."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.sharedKernel.domain.valueObjects import ValueObject

USER_INVITED = "invited"
USER_ACTIVE = "active"
USER_SUSPENDED = "suspended"
USER_DEACTIVATED = "deactivated"

USER_STATUS_TRANSITIONS: dict[str, tuple[str, ...]] = {
    USER_INVITED: (USER_ACTIVE, USER_SUSPENDED, USER_DEACTIVATED),
    USER_ACTIVE: (USER_SUSPENDED, USER_DEACTIVATED),
    USER_SUSPENDED: (USER_ACTIVE, USER_DEACTIVATED),
    USER_DEACTIVATED: (),
}


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


MIN_PASSWORD_LENGTH = 12


def validatePasswordStrength(plain: str) -> str:
    """Password policy (§31 security) — length + class check."""
    problems: list[str] = []
    if len(plain) < MIN_PASSWORD_LENGTH:
        problems.append(f"at least {MIN_PASSWORD_LENGTH} characters")
    if plain.isalpha() or plain.isdigit() or plain.isalnum():
        problems.append("at least one non-alphanumeric character")
    if problems:
        raise ValidationFailedError(
            "Password does not meet the policy.",
            fieldErrors={"password": "; ".join(problems)},
        )
    return plain
