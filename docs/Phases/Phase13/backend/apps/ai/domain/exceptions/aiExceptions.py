"""Stable AI domain errors for Phase 13-B.

Provider-specific failures are mapped to these errors by later infrastructure
adapters. No vendor exception is allowed to cross the AI boundary.
"""

from __future__ import annotations

from apps.sharedKernel.domain.errors import TekaraiError


class AIError(TekaraiError):
    code = "AI_ERROR"
    httpStatus = 422


class AIProviderUnavailable(AIError):
    code = "AI_PROVIDER_UNAVAILABLE"
    httpStatus = 503


class AIModelUnavailable(AIError):
    code = "AI_MODEL_UNAVAILABLE"
    httpStatus = 503


class AIRequestTimeout(AIError):
    code = "AI_REQUEST_TIMEOUT"
    httpStatus = 504


class AIQuotaExceeded(AIError):
    code = "AI_QUOTA_EXCEEDED"
    httpStatus = 429


class AITokenLimitExceeded(AIError):
    code = "AI_TOKEN_LIMIT_EXCEEDED"
    httpStatus = 422


class AIContextTooLarge(AIError):
    code = "AI_CONTEXT_TOO_LARGE"
    httpStatus = 422


class AIOutputValidationFailed(AIError):
    code = "AI_OUTPUT_VALIDATION_FAILED"
    httpStatus = 422


class AIPermissionDenied(AIError):
    code = "AI_PERMISSION_DENIED"
    httpStatus = 403


class AIProviderRateLimited(AIError):
    code = "AI_PROVIDER_RATE_LIMITED"
    httpStatus = 429


class AIPromptNotFound(AIError):
    code = "AI_PROMPT_NOT_FOUND"
    httpStatus = 404


class AIIdempotencyConflict(AIError):
    code = "AI_IDEMPOTENCY_CONFLICT"
    httpStatus = 409


class AIToolDenied(AIError):
    code = "AI_TOOL_DENIED"
    httpStatus = 403


class AIConfigurationError(AIError):
    code = "AI_CONFIGURATION_ERROR"
    httpStatus = 500
