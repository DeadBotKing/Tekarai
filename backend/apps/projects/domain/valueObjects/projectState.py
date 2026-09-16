"""Project value objects — closed status set + business code (Phase 18b)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.sharedKernel.domain.valueObjects import ValueObject

PROJECT_ACTIVE = "active"
PROJECT_ON_HOLD = "onHold"
PROJECT_COMPLETED = "completed"
PROJECT_ARCHIVED = "archived"

ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    PROJECT_ACTIVE: (PROJECT_ON_HOLD, PROJECT_COMPLETED, PROJECT_ARCHIVED),
    PROJECT_ON_HOLD: (PROJECT_ACTIVE, PROJECT_COMPLETED, PROJECT_ARCHIVED),
    PROJECT_COMPLETED: (PROJECT_ARCHIVED,),
    PROJECT_ARCHIVED: (),
}

PROJECT_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,31}$")


def clampPercent(value: int) -> int:
    """Health/progress live in the closed 0..100 range."""
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class ProjectStatus(ValueObject):
    value: str

    def __post_init__(self) -> None:
        if self.value not in ALLOWED_TRANSITIONS:
            raise ValidationFailedError(
                "Invalid project status.",
                fieldErrors={"status": self.value},
            )

    def canTransitionTo(self, target: str) -> bool:
        return target in ALLOWED_TRANSITIONS[self.value]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ProjectCode(ValueObject):
    """Tenant-unique business code (e.g. ``NOVA-24``)."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if not PROJECT_CODE_PATTERN.match(normalized):
            raise ValidationFailedError(
                "Project code must be 2-32 chars of A-Z, 0-9 and dashes.",
                fieldErrors={"code": self.value},
            )
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
