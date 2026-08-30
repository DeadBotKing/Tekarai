"""Value-object primitives and shared validation helpers (§6 NULL meaning,
§3 camelCase naming, §8 closed vocabularies)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from apps.sharedKernel.domain.errors import ValidationFailedError

#: Tenant codes: lowercase slug, stable business identity (BR-TEN-004).
TENANT_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
#: Action-based permission codes: ``module.action`` (BR-PER-001).
PERMISSION_CODE_PATTERN = re.compile(r"^[a-z][a-zA-Z0-9]*\.[a-z][a-zA-Z0-9]*$")


class ValueObject:
    """Marker base: immutable, no identity, compared by value."""


@dataclass(frozen=True)
class EmailAddress(ValueObject):
    value: str

    def __post_init__(self) -> None:
        value = self.value.strip().lower()
        if (
            "@" not in value
            or value.startswith("@")
            or value.endswith("@")
            or "." not in value.split("@")[-1]
        ):
            raise ValidationFailedError("Invalid email address.", fieldErrors={"email": "invalid"})
        object.__setattr__(self, "value", value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ActionCode(ValueObject):
    """Action-based permission code (§42) — validated against the grammar."""

    value: str

    def __post_init__(self) -> None:
        if not PERMISSION_CODE_PATTERN.match(self.value):
            raise ValidationFailedError(
                "Invalid permission action code.",
                fieldErrors={"action": self.value},
            )

    def module(self) -> str:
        return self.value.split(".", 1)[0]

    def __str__(self) -> str:
        return self.value


def requireNonEmpty(value: str, fieldName: str) -> str:
    if not value or not value.strip():
        raise ValidationFailedError("Value must not be empty.", fieldErrors={fieldName: "required"})
    return value.strip()


def requireMaxLength(value: str, maxLength: int, fieldName: str) -> str:
    if len(value) > maxLength:
        raise ValidationFailedError(
            f"Value exceeds {maxLength} characters.",
            fieldErrors={fieldName: f"max {maxLength}"},
        )
    return value


def asUuid(value: object, fieldName: str = "id") -> uuid.UUID:
    """Coerce str/UUID inputs into UUID (path converters pass UUID objects)."""
    import uuid as uuidModule

    if isinstance(value, uuidModule.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuidModule.UUID(value)
        except ValueError as exc:
            raise ValidationFailedError(
                "Invalid identifier.",
                fieldErrors={fieldName: "not a valid id"},
            ) from exc
    raise ValidationFailedError("Invalid identifier.", fieldErrors={fieldName: "not a valid id"})
