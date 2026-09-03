"""Access-control value objects (§42–§43): action codes and scopes."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.domain.valueObjects import ValueObject

SCOPE_GLOBAL = "GLOBAL"
SCOPE_TENANT = "TENANT"
SCOPE_ORGANIZATION = "ORGANIZATION"
SCOPE_DEPARTMENT = "DEPARTMENT"
SCOPE_PROJECT = "PROJECT"

SCOPES = (SCOPE_GLOBAL, SCOPE_TENANT, SCOPE_ORGANIZATION, SCOPE_DEPARTMENT, SCOPE_PROJECT)


@dataclass(frozen=True)
class AccessScope(ValueObject):
    value: str

    def __post_init__(self) -> None:
        if self.value not in SCOPES:
            raise ValueError(f"Unknown scope: {self.value}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AccessGrant(ValueObject):
    """One permission holding: action pattern + scope (§43).

    ``actionPattern`` is an exact action code (``user.create``) or a module
    wildcard (``user.*`` / ``*``). ``scopeRef`` narrows TENANT/… scopes to a
    concrete id; empty means "the actor's own tenant".
    """

    actionPattern: str
    scopeType: str
    scopeRef: str = ""
    effect: str = "allow"  # allow | deny (BR-PER-003)

    def matchesAction(self, action: str) -> bool:
        if self.actionPattern == "*":
            return True
        if self.actionPattern.endswith(".*"):
            return action.startswith(self.actionPattern[: -len(".*")] + ".")
        return self.actionPattern == action
