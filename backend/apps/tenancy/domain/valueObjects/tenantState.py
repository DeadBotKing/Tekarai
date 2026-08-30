"""Tenant value objects — closed status set (§8) and business code (§12)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.sharedKernel.domain.valueObjects import ValueObject

#: Tenant lifecycle (StateMachineCatalog §secondary — Tenant machine).
TENANT_ACTIVE = "active"
TENANT_SUSPENDED = "suspended"
TENANT_CLOSED = "closed"

ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    TENANT_ACTIVE: (TENANT_SUSPENDED, TENANT_CLOSED),
    TENANT_SUSPENDED: (TENANT_ACTIVE, TENANT_CLOSED),
    TENANT_CLOSED: (),
}

TENANT_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


@dataclass(frozen=True)
class TenantStatus(ValueObject):
    value: str

    def __post_init__(self) -> None:
        if self.value not in ALLOWED_TRANSITIONS:
            raise ValidationFailedError(
                "Invalid tenant status.",
                fieldErrors={"status": self.value},
            )

    def canTransitionTo(self, target: str) -> bool:
        return target in ALLOWED_TRANSITIONS[self.value]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class TenantCode(ValueObject):
    """Globally-unique business code (BR-TEN-004) — never the PK (§12)."""

    value: str

    def __post_init__(self) -> None:
        if not TENANT_CODE_PATTERN.match(self.value):
            raise ValidationFailedError(
                "Tenant code must be a lowercase slug (2-64 chars).",
                fieldErrors={"code": self.value},
            )

    def __str__(self) -> str:
        return self.value
