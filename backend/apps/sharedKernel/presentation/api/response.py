"""Standard response contract (Phase 06 §14) — one envelope everywhere.

Success: ``{"success": true, "data": …, "meta": …, "errors": []}``
Error:   ``{"success": false, "data": null, "meta": …, "errors": [ … ]}``

Every error entry carries the stable code from
``docs/database/ErrorCodeCatalog.md``, a human message, an optional field
and correlationId. Views never build raw bodies.
"""

from __future__ import annotations

from typing import Any

from apps.sharedKernel.application.requestContext import currentContext


def successEnvelope(
    data: Any,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "meta": withCorrelation(meta or {}),
        "errors": [],
    }


def errorEnvelope(
    errors: list[dict[str, Any]],
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "meta": withCorrelation(meta or {}),
        "errors": errors,
    }


def errorEntry(
    code: str,
    message: str,
    *,
    field: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"code": code, "message": message}
    if field:
        entry["field"] = field
    if details:
        entry["details"] = details
    return entry


def withCorrelation(meta: dict[str, Any]) -> dict[str, Any]:
    context = currentContext()
    if context.correlationId and "correlationId" not in meta:
        return {**meta, "correlationId": context.correlationId}
    return meta
