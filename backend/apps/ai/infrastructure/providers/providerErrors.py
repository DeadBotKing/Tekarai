"""Provider error mapping and secret redaction for Phase 13-L.

Phase 13-C fixed the port contract and deferred the final vendor-error
mapping to this sub-phase (C §3 rule 5). Every transport or vendor failure
crossing an adapter boundary is translated into one of the stable AI domain
errors defined in Phase 13-B — raw SDK/vendor/HTTP exceptions never leave
the infrastructure layer (Master Specification §43, Data Flow §16).

Retry classification is intentionally NOT performed here; M decides which of
these errors is retryable. L only guarantees a stable, provider-neutral
error surface and that no secret ever appears in an error message, health
detail, or log line.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError

from apps.ai.domain.exceptions import (
    AIModelUnavailable,
    AIOutputValidationFailed,
    AIProviderRateLimited,
    AIProviderUnavailable,
    AIRequestTimeout,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

REDACTED = "[REDACTED]"


class TransportTimeout(Exception):
    """Internal transport signal: the provider did not answer in time."""


class TransportConnectionFailed(Exception):
    """Internal transport signal: the provider endpoint was unreachable."""


def redactSecret(secret: str) -> str:
    """Return a fixed redaction token; never reveal any part of a secret."""

    return REDACTED if secret else ""


def sanitizeText(text: str, secrets: tuple[str, ...]) -> str:
    """Remove secret substrings from any text that may surface to callers."""

    sanitized = text
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, REDACTED)
    return sanitized


def extractErrorDetail(payload: Any) -> str:
    """Pull a short, non-sensitive message from a vendor error payload."""

    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message[:300]
    if isinstance(payload.get("detail"), str):
        return payload["detail"][:300]
    if isinstance(payload.get("message"), str):
        return payload["message"][:300]
    return ""


def mapHttpError(
    status: int,
    payload: Any,
    *,
    providerCode: str,
    model: str,
    secrets: tuple[str, ...] = (),
) -> Exception:
    """Map an HTTP error status to the stable AI domain error surface."""

    detail = sanitizeText(extractErrorDetail(payload), secrets)
    suffix = f" ({detail})" if detail else ""
    if status in (401, 403):
        # Credential rejection is a provider availability problem from the
        # platform's perspective; the caller must fix configuration.
        return AIProviderUnavailable(f"{providerCode} rejected the configured credentials.")
    if status == 404 and model:
        return AIModelUnavailable(f"Model {model} is not available at {providerCode}.{suffix}")
    if status == 429:
        return AIProviderRateLimited(f"{providerCode} rate limit reached.{suffix}")
    if status in (400, 422):
        # Invalid request material: retrying without change is forbidden
        # (Master Specification §44), so this stays a validation failure.
        return ValidationFailedError(f"{providerCode} rejected the request.{suffix}")
    return AIProviderUnavailable(f"{providerCode} returned HTTP {status}.{suffix}")


def mapTransportError(
    exc: Exception,
    *,
    providerCode: str,
    secrets: tuple[str, ...] = (),
) -> Exception:
    """Map transport-level failures (timeouts, DNS, connection) to domain errors."""

    message = sanitizeText(str(exc) or exc.__class__.__name__, secrets)
    if isinstance(exc, (TransportTimeout, TimeoutError)):
        return AIRequestTimeout(f"{providerCode} did not respond in time.")
    if isinstance(exc, (TransportConnectionFailed, ConnectionError, URLError)):
        return AIProviderUnavailable(f"{providerCode} endpoint is unreachable.")
    return AIProviderUnavailable(f"{providerCode} transport failure ({message}).")


def parseJsonBody(body: bytes, *, providerCode: str) -> Any:
    """Decode a JSON response body or fail with the domain validation error."""

    try:
        return json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AIOutputValidationFailed(f"{providerCode} returned a non-JSON response.") from exc


def executeProviderCall[ResultT](
    operation: Callable[[], ResultT],
    *,
    providerCode: str,
    model: str = "",
    secrets: tuple[str, ...] = (),
) -> ResultT:
    """Run an adapter operation and translate every failure to a domain error.

    Domain errors raised by the operation itself pass through untouched;
    everything else is mapped so no vendor exception crosses the boundary.
    """

    try:
        return operation()
    except (
        AIProviderUnavailable,
        AIModelUnavailable,
        AIRequestTimeout,
        AIProviderRateLimited,
        AIOutputValidationFailed,
        ValidationFailedError,
    ):
        raise
    except HTTPError as exc:
        payload: Any = {}
        try:
            payload = parseJsonBody(exc.read(), providerCode=providerCode)
        except AIOutputValidationFailed:
            payload = {}
        raise mapHttpError(
            exc.code,
            payload,
            providerCode=providerCode,
            model=model,
            secrets=secrets,
        ) from exc
    except (
        TransportTimeout,
        TransportConnectionFailed,
        TimeoutError,
        URLError,
        ConnectionError,
        OSError,
    ) as exc:
        raise mapTransportError(exc, providerCode=providerCode, secrets=secrets) from exc
    except Exception as exc:  # noqa: BLE001 — fail closed at the boundary
        raise mapTransportError(exc, providerCode=providerCode, secrets=secrets) from exc


__all__ = [
    "REDACTED",
    "TransportConnectionFailed",
    "TransportTimeout",
    "executeProviderCall",
    "extractErrorDetail",
    "mapHttpError",
    "mapTransportError",
    "parseJsonBody",
    "redactSecret",
    "sanitizeText",
]
