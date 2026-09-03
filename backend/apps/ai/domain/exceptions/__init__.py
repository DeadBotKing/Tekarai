"""Public Phase 13 AI errors."""

from apps.ai.domain.exceptions.aiExceptions import (
    AIConfigurationError,
    AIContextTooLarge,
    AIError,
    AIIdempotencyConflict,
    AIModelUnavailable,
    AIPermissionDenied,
    AIPromptNotFound,
    AIProviderRateLimited,
    AIProviderUnavailable,
    AIQuotaExceeded,
    AIRequestTimeout,
    AITokenLimitExceeded,
    AIToolDenied,
    AIOutputValidationFailed,
)

__all__ = [
    "AIConfigurationError",
    "AIContextTooLarge",
    "AIError",
    "AIIdempotencyConflict",
    "AIModelUnavailable",
    "AIPermissionDenied",
    "AIPromptNotFound",
    "AIProviderRateLimited",
    "AIProviderUnavailable",
    "AIQuotaExceeded",
    "AIRequestTimeout",
    "AITokenLimitExceeded",
    "AIToolDenied",
    "AIOutputValidationFailed",
]
