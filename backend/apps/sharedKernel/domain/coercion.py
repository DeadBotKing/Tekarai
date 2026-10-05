"""Safe coercions for loosely-typed inbound payloads.

Repositories and use cases receive `dict[str, object]` payloads that have
already passed serializer validation, so the previous code called `int(...)` /
`list(...)` on them directly. That is both untypeable and fragile: a value the
serializer let through as `None`, `""` or a nested structure raises `TypeError`
or `ValueError` deep inside persistence instead of producing the documented
default. These helpers make the fallback explicit and keep call sites readable.
"""

from __future__ import annotations

import builtins
from decimal import Decimal, InvalidOperation


def asInt(value: object, default: int = 0) -> int:
    """Best-effort integer, falling back to `default` for empty/invalid input."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default


def asDecimal(value: object, default: Decimal = Decimal("0")) -> Decimal:
    """Best-effort Decimal, routed through `str` so floats keep their text form."""
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def asStringList(value: object) -> builtins.list[str]:
    """Normalise an arbitrary payload value into a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (builtins.list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]
