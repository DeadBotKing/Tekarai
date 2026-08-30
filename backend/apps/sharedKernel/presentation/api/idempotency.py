"""Idempotency for sensitive POST endpoints (Phase 06 §20).

Clients send ``Idempotency-Key``; the mixin fingerprints
actor + tenant + key + request body and replays the stored response instead
of re-executing the use case (§20 use cases: payments, notifications,
integrations, commands, file upload, webhooks).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider

IDEMPOTENCY_HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotency-Replayed"
DEFAULT_TTL_SECONDS = 24 * 60 * 60


class IdempotencyMixin(APIView):
    """Add to APIView subclasses whose POST must be replay-safe (§20)."""

    idempotencyTtlSeconds: int = DEFAULT_TTL_SECONDS

    def dispatch(self, request, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        if request.method != "POST":
            return super().dispatch(request, *args, **kwargs)
        key = request.headers.get(IDEMPOTENCY_HEADER, "").strip()
        if not key:
            return super().dispatch(request, *args, **kwargs)
        fingerprint = idempotencyFingerprint(key, request)
        store = sharedKernelProvider("idempotencyStore")()
        cached = store.lookup(fingerprint)
        if cached is not None:
            httpStatus, body = cached
            from django.http import JsonResponse

            response = JsonResponse(
                body, status=httpStatus, json_dumps_params={"ensure_ascii": False}
            )
            response[REPLAYED_HEADER] = "true"
            return response
        response = super().dispatch(request, *args, **kwargs)
        if 200 <= response.status_code < 300 and isinstance(response, Response):
            store.store(
                fingerprint,
                response.status_code,
                dict(response.data) if response.data is not None else {},
                self.idempotencyTtlSeconds,
            )
        return response


def idempotencyFingerprint(key: str, request: Any) -> str:
    context = currentContext()
    body = getattr(request, "body", b"") or b""
    payloadHash = hashlib.sha256(body).hexdigest()
    parts = json.dumps(
        {
            "actorId": context.actorId,
            "tenantId": context.tenantId or context.actorTenantId,
            "key": key,
            "path": getattr(getattr(request, "path", ""), "__str__", lambda: "")(),
            "payloadHash": payloadHash,
        },
        sort_keys=True,
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()
