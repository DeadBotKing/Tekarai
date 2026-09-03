"""Pure AI domain rules used by Phase 13-B and later application services."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable

from apps.ai.domain.exceptions import (
    AIContextTooLarge,
    AIPermissionDenied,
    AIProviderRateLimited,
    AIRequestTimeout,
    AIOutputValidationFailed,
)
from apps.ai.domain.policies.aiPolicies import ContextPolicy
from apps.ai.domain.valueObjects.aiTypes import CostRate, RetryPolicy, TokenUsage

SENSITIVE_KEYS = frozenset(
    {"apiKey", "api_key", "password", "secret", "token", "accessToken", "refreshToken"}
)


def estimateTokens(text: str) -> int:
    """Conservative provider-neutral estimate used before provider calls."""
    return 0 if not text else max(1, math.ceil(len(text) / 4))


def buildContext(
    sources: Iterable[Any],
    policy: ContextPolicy,
    *,
    externalProvider: bool = False,
) -> tuple[str, tuple[Any, ...], int]:
    """Keep only authorized, policy-permitted sources before inference."""
    allowed: list[Any] = []
    pieces: list[str] = []
    usedCharacters = 0
    for source in sources:
        classification = str(getattr(source, "classification", "INTERNAL"))
        permitted = bool(getattr(source, "allowed", True)) and policy.permits(
            classification, externalProvider=externalProvider
        )
        if not permitted or len(allowed) >= policy.maxSources:
            continue
        content = str(getattr(source, "content", ""))
        remaining = policy.maxCharacters - usedCharacters
        if not content:
            continue
        if len(content) > remaining:
            raise AIContextTooLarge("Authorized AI context exceeds character limits.")
        pieces.append(content)
        allowed.append(source)
        usedCharacters += len(content)
    content = "\n\n".join(pieces)
    tokenCount = estimateTokens(content)
    if len(content) > policy.maxCharacters or tokenCount > policy.maxTokens:
        raise AIContextTooLarge("Authorized AI context exceeds policy limits.")
    return content, tuple(allowed), tokenCount


def validateJsonSchema(value: Any, schema: dict[str, Any]) -> bool:
    """Dependency-free subset of JSON Schema for the Domain boundary."""
    if not schema:
        return True
    expectedType = schema.get("type")
    typeChecks = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float, Decimal)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    if expectedType in typeChecks and not typeChecks[expectedType]:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if isinstance(value, dict):
        required = schema.get("required", [])
        if any(key not in value for key in required):
            return False
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and any(key not in properties for key in value):
            return False
        if any(key in properties and not validateJsonSchema(item, properties[key]) for key, item in value.items()):
            return False
    if isinstance(value, list) and "items" in schema:
        if any(not validateJsonSchema(item, schema["items"]) for item in value):
            return False
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            return False
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return False
        if "maximum" in schema and value > schema["maximum"]:
            return False
    return True


def ensureStructuredOutput(value: Any, schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or not validateJsonSchema(value, schema):
        raise AIOutputValidationFailed("Structured AI output failed validation.")
    return value


def calculateCost(usage: TokenUsage, rate: CostRate) -> Decimal:
    return rate.calculate(usage).amount


def retryDelay(policy: RetryPolicy, attemptNumber: int) -> int:
    if attemptNumber < 1:
        return 0
    return min(
        policy.maxDelaySeconds,
        int(policy.initialDelaySeconds * (policy.multiplier ** (attemptNumber - 1))),
    )


def nextRetryAt(policy: RetryPolicy, attemptNumber: int, now: datetime | None = None) -> datetime:
    return (now or datetime.now(tz=UTC)) + timedelta(seconds=retryDelay(policy, attemptNumber))


def isRetryable(error: Exception) -> bool:
    return isinstance(error, (AIRequestTimeout, AIProviderRateLimited)) or bool(
        getattr(error, "retryable", False)
    )


def mapProviderFailure(error: Exception) -> Exception:
    if isinstance(error, (AIRequestTimeout, AIProviderRateLimited)):
        return error
    message = str(error).lower()
    if "timeout" in message:
        return AIRequestTimeout("AI provider request timed out.")
    if "rate" in message or "429" in message:
        return AIProviderRateLimited("AI provider rate limit reached.")
    return error


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key in SENSITIVE_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def safeAuditMetadata(value: dict[str, Any]) -> dict[str, Any]:
    return redact(value)


def idempotencyFingerprint(tenantId: str, operation: str, key: str) -> str:
    return hashlib.sha256(f"{tenantId}:{operation}:{key}".encode()).hexdigest()


def normalizeStructuredData(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise AIOutputValidationFailed("Structured AI output must be a JSON object.")


def enforceAuthoritativeChange(outputClassification: str, *, authorized: bool) -> None:
    if outputClassification == "AUTHORITATIVE" and not authorized:
        raise AIPermissionDenied("Authoritative AI output requires explicit authorization.")
