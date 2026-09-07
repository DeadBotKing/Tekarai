"""Framework-free Phase 15 security and lifecycle policies."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime
from typing import Any

from apps.sharedKernel.domain.errors import ValidationFailedError

NOTIFICATION_STATUSES = (
    "CREATED",
    "QUEUED",
    "PROCESSING",
    "SENT",
    "DELIVERED",
    "PARTIALLY_DELIVERED",
    "READ",
    "FAILED",
    "CANCELLED",
    "EXPIRED",
)
PROVIDER_CALLBACK_STATUSES = ("SENT", "DELIVERED", "FAILED", "CANCELLED")
PROVIDER_CHANNELS = ("EMAIL", "SMS", "PUSH", "WEB_PUSH", "WEBHOOK")
_SECRET_KEY_PATTERN = re.compile(r"(?i)(password|secret|token|api.?key|authorization|credential)")


def canonicalPayloadHash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def verifyWebhookSignature(
    rawBody: bytes,
    *,
    signature: str,
    timestamp: str,
    secret: str,
    nowEpoch: int,
    toleranceSeconds: int = 300,
) -> None:
    """Validate HMAC-SHA256 over ``timestamp.body`` with replay-window guard."""
    if not secret:
        raise ValidationFailedError("Provider webhook is not configured.")
    try:
        providedTimestamp = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise ValidationFailedError("Webhook timestamp is invalid.") from exc
    if abs(nowEpoch - providedTimestamp) > toleranceSeconds:
        raise ValidationFailedError("Webhook timestamp is outside the replay window.")
    normalized = str(signature or "").removeprefix("sha256=").lower()
    expected = hmac.new(
        secret.encode("utf-8"), timestamp.encode("ascii") + b"." + rawBody, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, normalized):
        raise ValidationFailedError("Webhook signature is invalid.")


def sanitizedMetadata(value: dict[str, Any], *, maxBytes: int = 16_384) -> dict[str, Any]:
    """Remove secret-like keys recursively and enforce a bounded JSON payload."""
    def clean(item: Any, depth: int = 0) -> Any:
        if depth > 8:
            return "[MAX_DEPTH]"
        if isinstance(item, dict):
            return {
                str(key)[:100]: "[REDACTED]" if _SECRET_KEY_PATTERN.search(str(key)) else clean(val, depth + 1)
                for key, val in item.items()
            }
        if isinstance(item, list):
            return [clean(element, depth + 1) for element in item[:100]]
        if item is None or isinstance(item, (str, int, float, bool)):
            return item if not isinstance(item, str) else item[:4000]
        return str(item)[:4000]

    result = clean(value)
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > maxBytes:
        raise ValidationFailedError("Notification metadata exceeds the size limit.")
    return result


def validateIsoDateRange(start: datetime | None, end: datetime | None) -> None:
    if start is not None and end is not None and start > end:
        raise ValidationFailedError("Search start date must not be after end date.")


__all__ = [
    "NOTIFICATION_STATUSES",
    "PROVIDER_CALLBACK_STATUSES",
    "PROVIDER_CHANNELS",
    "canonicalPayloadHash",
    "sanitizedMetadata",
    "validateIsoDateRange",
    "verifyWebhookSignature",
]
