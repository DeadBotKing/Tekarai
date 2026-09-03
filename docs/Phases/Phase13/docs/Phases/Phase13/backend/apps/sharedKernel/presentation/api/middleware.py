"""Correlation-ID and request-context middleware (Phase 06 §25–§26).

Request lifecycle (§26): middleware binds correlation + request context
before routing; authentication enriches it with actor/tenant; use cases,
audit rows, domain events, logs and the response envelope all read it.
Incoming ``X-Correlation-ID`` is honoured (trusted internal header policy),
otherwise a fresh id is minted. The id is echoed back on every response.
"""

from __future__ import annotations

import uuid

from django.http import HttpRequest, HttpResponse

from apps.sharedKernel.application.requestContext import (
    RequestContext,
    bindContext,
    resetContext,
)

CORRELATION_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"


class CorrelationContextMiddleware:
    """Binds correlation/request context for the whole request (§25)."""

    def __init__(self, getResponse) -> None:  # noqa: N803 — Django signature
        self.getResponse = getResponse

    def __call__(self, request: HttpRequest) -> HttpResponse:
        context = RequestContext(
            correlationId=sanitizeHeaderValue(request.headers.get(CORRELATION_HEADER, ""))
            or uuid.uuid4().hex,
            requestId=uuid.uuid4().hex,
            ipAddress=clientIpOf(request),
            userAgent=request.headers.get("User-Agent", "")[:300],
        )
        token = bindContext(context)
        try:
            response = self.getResponse(request)
        finally:
            resetContext(token)
        response[CORRELATION_HEADER] = context.correlationId
        response[REQUEST_ID_HEADER] = context.requestId
        return response


def clientIpOf(request: HttpRequest) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def sanitizeHeaderValue(value: str) -> str:
    """Header values are echoed only when they are plain hex/ascii tokens."""
    cleaned = value.strip()[:64]
    if cleaned and all(character.isalnum() or character in "-._" for character in cleaned):
        return cleaned
    return ""
