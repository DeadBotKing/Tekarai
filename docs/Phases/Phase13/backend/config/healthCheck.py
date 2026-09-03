"""Framework-level health check endpoints for Tekarai.

Phase 01 scope (docs/Phases/Phase1.md §17): report the baseline status of the
application and the database. Later phases extend this with cache, queue,
storage and external service checks.

This module intentionally contains **no business logic**. It reads no business
tables and returns no business data.
"""

from __future__ import annotations

import time
from typing import Any

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

PHASE_LABEL = "01-foundation"


def buildComponentStatus(status: str, **details: Any) -> dict[str, Any]:
    """Build one component entry of a health payload with camelCase keys."""
    return {"status": status, **details}


def checkDatabase() -> tuple[str, float, str]:
    """Run ``SELECT 1`` and report status, latency and engine label.

    The engine label is derived from the settings; credentials are never
    included in health output.
    """
    from django.conf import settings

    engineLabel = settings.DATABASES["default"]["ENGINE"]
    startedAt = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # noqa: BLE001 — health checks must never crash
        return "error", _elapsedMsSince(startedAt), engineLabel
    return "ok", _elapsedMsSince(startedAt), engineLabel


def _elapsedMsSince(startedAt: float) -> float:
    return round((time.perf_counter() - startedAt) * 1000, 2)


@require_GET
def healthLive(request) -> JsonResponse:
    """Liveness: is the application process up? No external dependencies."""
    payload = {
        "status": "ok",
        "phase": PHASE_LABEL,
        "components": {
            "application": buildComponentStatus("ok"),
        },
    }
    return JsonResponse(payload)


@require_GET
def healthReady(request) -> JsonResponse:
    """Readiness: application plus database. Returns 503 when degraded."""
    databaseStatus, latencyMs, engineLabel = checkDatabase()
    degraded = databaseStatus != "ok"

    payload = {
        "status": "error" if degraded else "ok",
        "phase": PHASE_LABEL,
        "components": {
            "application": buildComponentStatus("ok"),
            "database": buildComponentStatus(
                databaseStatus,
                latencyMs=latencyMs,
                engine=engineLabel,
            ),
        },
    }
    return JsonResponse(payload, status=503 if degraded else 200)
