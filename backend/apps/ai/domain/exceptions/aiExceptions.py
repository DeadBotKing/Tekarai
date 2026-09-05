"""Stable AI domain errors for Phase 13-B, Phase 13-E, Phase 13-F and Phase 13-N.

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


class AICostLimitExceeded(AIQuotaExceeded):
    """A COST-dimension quota (or the per-request cost cap) denied the attempt."""

    code = "AI_COST_LIMIT_EXCEEDED"
    httpStatus = 429


class AIQuotaPolicyAlreadyRegistered(AIError):
    code = "AI_QUOTA_POLICY_ALREADY_REGISTERED"
    httpStatus = 409

    def __init__(self, message: str = "AI quota policy is already registered.") -> None:
        super().__init__(message)


class AIQuotaPolicyNotFound(AIError):
    code = "AI_QUOTA_POLICY_NOT_FOUND"
    httpStatus = 404

    def __init__(self, policyId: str = "") -> None:
        super().__init__("AI quota policy was not found.")
        self.policyId = policyId


class AIQuotaPolicyInvalid(AIError):
    code = "AI_QUOTA_POLICY_INVALID"
    httpStatus = 422


class AIUsageAttemptAlreadyRegistered(AIError):
    code = "AI_USAGE_ATTEMPT_ALREADY_REGISTERED"
    httpStatus = 409

    def __init__(self, requestId: str = "") -> None:
        super().__init__("AI usage attempt is already registered.")
        self.requestId = requestId


class AIUsageAttemptNotFound(AIError):
    code = "AI_USAGE_ATTEMPT_NOT_FOUND"
    httpStatus = 404

    def __init__(self, attemptId: str = "") -> None:
        super().__init__("AI usage attempt was not found.")
        self.attemptId = attemptId


class AITokenLimitExceeded(AIError):
    code = "AI_TOKEN_LIMIT_EXCEEDED"
    httpStatus = 422


class AIContextTooLarge(AIError):
    code = "AI_CONTEXT_TOO_LARGE"
    httpStatus = 422


class AIContextSourceInvalid(AIError):
    code = "AI_CONTEXT_SOURCE_INVALID"
    httpStatus = 422


class AIContextTenantMismatch(AIError):
    code = "AI_CONTEXT_TENANT_MISMATCH"
    httpStatus = 403


class AIContextPolicyInvalid(AIError):
    code = "AI_CONTEXT_POLICY_INVALID"
    httpStatus = 422


class AIContextAlreadyRegistered(AIError):
    code = "AI_CONTEXT_ALREADY_REGISTERED"
    httpStatus = 409

    def __init__(self, contextId: str = "") -> None:
        super().__init__("AI context is already registered.")
        self.contextId = contextId


class AIContextNotFound(AIError):
    code = "AI_CONTEXT_NOT_FOUND"
    httpStatus = 404

    def __init__(self, contextId: str = "") -> None:
        super().__init__("AI context was not found.")
        self.contextId = contextId


class AIOutputValidationFailed(AIError):
    code = "AI_OUTPUT_VALIDATION_FAILED"
    httpStatus = 422


class AIPermissionDenied(AIError):
    code = "AI_PERMISSION_DENIED"
    httpStatus = 403


class AIAuthorizationDenied(AIPermissionDenied):
    code = "AI_AUTHORIZATION_DENIED"
    httpStatus = 403


class AIAuthorizationPrincipalInvalid(AIError):
    code = "AI_AUTHORIZATION_PRINCIPAL_INVALID"
    httpStatus = 422


class AIAuthorizationGrantInvalid(AIError):
    code = "AI_AUTHORIZATION_GRANT_INVALID"
    httpStatus = 422


class AIAuthorizationPolicyInvalid(AIError):
    code = "AI_AUTHORIZATION_POLICY_INVALID"
    httpStatus = 422


class AIAuthorizationTenantMismatch(AIError):
    code = "AI_AUTHORIZATION_TENANT_MISMATCH"
    httpStatus = 403


class AIAuthorizationAlreadyRegistered(AIError):
    code = "AI_AUTHORIZATION_ALREADY_REGISTERED"
    httpStatus = 409


class AIAuthorizationNotFound(AIError):
    code = "AI_AUTHORIZATION_NOT_FOUND"
    httpStatus = 404


class AIProviderRateLimited(AIError):
    code = "AI_PROVIDER_RATE_LIMITED"
    httpStatus = 429


class AIProviderAlreadyRegistered(AIError):
    code = "AI_PROVIDER_ALREADY_REGISTERED"
    httpStatus = 409

    def __init__(self, providerCode: str) -> None:
        super().__init__(f"AI provider {providerCode} is already registered.")
        self.providerCode = providerCode


class AIProviderNotRegistered(AIError):
    code = "AI_PROVIDER_NOT_REGISTERED"
    httpStatus = 404

    def __init__(self, providerCode: str) -> None:
        super().__init__(f"AI provider {providerCode} is not registered.")
        self.providerCode = providerCode


class AIProviderInactive(AIError):
    code = "AI_PROVIDER_INACTIVE"
    httpStatus = 503

    def __init__(self, providerCode: str) -> None:
        super().__init__(f"AI provider {providerCode} is inactive.")
        self.providerCode = providerCode


class AIProviderRegistrationInvalid(AIError):
    code = "AI_PROVIDER_REGISTRATION_INVALID"
    httpStatus = 422


class AIModelAlreadyRegistered(AIError):
    """The same tenant/provider/model-code binding already exists."""

    code = "AI_MODEL_ALREADY_REGISTERED"
    httpStatus = 409

    def __init__(self, providerCode: str, modelCode: str) -> None:
        super().__init__(f"AI model {modelCode} is already registered for provider {providerCode}.")
        self.providerCode = providerCode
        self.modelCode = modelCode


class AIModelNotRegistered(AIError):
    """The model is absent from the requested tenant/provider scope."""

    code = "AI_MODEL_NOT_REGISTERED"
    httpStatus = 404

    def __init__(self, modelCode: str, providerCode: str = "") -> None:
        super().__init__(f"AI model {modelCode} is not registered.")
        self.modelCode = modelCode
        self.providerCode = providerCode


class AIModelInactive(AIModelUnavailable):
    """A model exists but is not enabled for operational resolution."""

    code = "AI_MODEL_INACTIVE"
    httpStatus = 503

    def __init__(self, modelCode: str) -> None:
        super().__init__(f"AI model {modelCode} is inactive.")
        self.modelCode = modelCode


class AIModelRegistrationInvalid(AIError):
    code = "AI_MODEL_REGISTRATION_INVALID"
    httpStatus = 422


class AIModelProviderOwnershipInvalid(AIError):
    """The model/provider relationship is not owned by the same tenant."""

    code = "AI_MODEL_PROVIDER_OWNERSHIP_INVALID"
    httpStatus = 422


class AIModelAmbiguous(AIError):
    """A model code is shared by multiple providers and needs an owner."""

    code = "AI_MODEL_AMBIGUOUS"
    httpStatus = 409

    def __init__(self, modelCode: str) -> None:
        super().__init__(f"AI model {modelCode} is ambiguous without a provider.")
        self.modelCode = modelCode


class AIRoutingPolicyInvalid(AIError):
    code = "AI_ROUTING_POLICY_INVALID"
    httpStatus = 422


class AIRoutingNoMatch(AIError):
    """No active, owned model satisfies the request and routing policy."""

    code = "AI_ROUTING_NO_MATCH"
    httpStatus = 422

    def __init__(self, message: str = "No eligible AI model matches the routing request.") -> None:
        super().__init__(message)


class AICapabilityAlreadyRegistered(AIError):
    code = "AI_CAPABILITY_ALREADY_REGISTERED"
    httpStatus = 409

    def __init__(self, capabilityCode: str) -> None:
        super().__init__(f"AI capability {capabilityCode} is already registered.")
        self.capabilityCode = capabilityCode


class AICapabilityNotRegistered(AIError):
    code = "AI_CAPABILITY_NOT_REGISTERED"
    httpStatus = 404

    def __init__(self, capabilityCode: str) -> None:
        super().__init__(f"AI capability {capabilityCode} is not registered.")
        self.capabilityCode = capabilityCode


class AICapabilityInactive(AIError):
    code = "AI_CAPABILITY_INACTIVE"
    httpStatus = 503

    def __init__(self, capabilityCode: str) -> None:
        super().__init__(f"AI capability {capabilityCode} is inactive.")
        self.capabilityCode = capabilityCode


class AICapabilityRegistrationInvalid(AIError):
    code = "AI_CAPABILITY_REGISTRATION_INVALID"
    httpStatus = 422


class AICapabilityPolicyInvalid(AIError):
    code = "AI_CAPABILITY_POLICY_INVALID"
    httpStatus = 422


class AICapabilityRequestTypeUnsupported(AIError):
    code = "AI_CAPABILITY_REQUEST_TYPE_UNSUPPORTED"
    httpStatus = 422

    def __init__(self, capabilityCode: str, requestType: str) -> None:
        super().__init__(
            f"AI capability {capabilityCode} does not accept request type {requestType}."
        )
        self.capabilityCode = capabilityCode
        self.requestType = requestType


class AICapabilityModelNotSupported(AIError):
    code = "AI_CAPABILITY_MODEL_NOT_SUPPORTED"
    httpStatus = 422


class AICapabilityRoutingNoMatch(AIRoutingNoMatch):
    code = "AI_CAPABILITY_ROUTING_NO_MATCH"
    httpStatus = 422

    def __init__(self, capabilityCode: str) -> None:
        super().__init__(f"No eligible model supports AI capability {capabilityCode}.")
        self.capabilityCode = capabilityCode


class AIRequestNotFound(AIError):
    code = "AI_REQUEST_NOT_FOUND"
    httpStatus = 404

    def __init__(self, requestId: str = "") -> None:
        super().__init__("AI request was not found.")
        self.requestId = requestId


class AIOperationNotFound(AIError):
    code = "AI_OPERATION_NOT_FOUND"
    httpStatus = 404

    def __init__(self, operationId: str = "") -> None:
        super().__init__("AI operation was not found.")
        self.operationId = operationId


class AIRequestAlreadyRegistered(AIError):
    code = "AI_REQUEST_ALREADY_REGISTERED"
    httpStatus = 409

    def __init__(self, requestId: str = "") -> None:
        super().__init__("AI request is already registered.")
        self.requestId = requestId


class AIOperationAlreadyRegistered(AIError):
    code = "AI_OPERATION_ALREADY_REGISTERED"
    httpStatus = 409

    def __init__(self, operationId: str = "") -> None:
        super().__init__("AI operation is already registered.")
        self.operationId = operationId


class AIRequestLifecycleInvalid(AIError):
    code = "AI_REQUEST_LIFECYCLE_INVALID"
    httpStatus = 409

    def __init__(self, message: str = "AI request lifecycle transition is invalid.") -> None:
        super().__init__(message)


class AIOperationLifecycleInvalid(AIError):
    code = "AI_OPERATION_LIFECYCLE_INVALID"
    httpStatus = 409

    def __init__(self, message: str = "AI operation lifecycle transition is invalid.") -> None:
        super().__init__(message)


class AIRequestCapabilityInvalid(AIError):
    code = "AI_REQUEST_CAPABILITY_INVALID"
    httpStatus = 422

    def __init__(self, capabilityId: str = "") -> None:
        super().__init__("AI request capability is invalid for its tenant or request type.")
        self.capabilityId = capabilityId


class AIResponseNotFound(AIError):
    code = "AI_RESPONSE_NOT_FOUND"
    httpStatus = 404

    def __init__(self, responseId: str = "") -> None:
        super().__init__("AI response was not found.")
        self.responseId = responseId


class AIResponseAlreadyRegistered(AIError):
    code = "AI_RESPONSE_ALREADY_REGISTERED"
    httpStatus = 409

    def __init__(self, responseId: str = "") -> None:
        super().__init__("AI response is already registered.")
        self.responseId = responseId


class AIResponseInvalid(AIError):
    code = "AI_RESPONSE_INVALID"
    httpStatus = 422


class AIResponseRequestInvalid(AIError):
    code = "AI_RESPONSE_REQUEST_INVALID"
    httpStatus = 422

    def __init__(self, requestId: str = "") -> None:
        super().__init__("AI response request is invalid for this tenant or lifecycle state.")
        self.requestId = requestId


class AIStructuredSchemaInvalid(AIError):
    code = "AI_STRUCTURED_SCHEMA_INVALID"
    httpStatus = 422


class AIStructuredOutputInvalid(AIOutputValidationFailed):
    code = "AI_STRUCTURED_OUTPUT_INVALID"
    httpStatus = 422

    def __init__(
        self,
        message: str = "Structured AI output failed schema validation.",
        issues: tuple[object, ...] = (),
    ) -> None:
        super().__init__(message)
        self.issues = issues


class AIPromptAlreadyRegistered(AIError):
    code = "AI_PROMPT_ALREADY_REGISTERED"
    httpStatus = 409

    def __init__(self, promptCode: str = "") -> None:
        super().__init__("AI prompt is already registered.")
        self.promptCode = promptCode


class AIPromptNotFound(AIError):
    code = "AI_PROMPT_NOT_FOUND"
    httpStatus = 404

    def __init__(self, promptCode: str = "") -> None:
        super().__init__("AI prompt was not found.")
        self.promptCode = promptCode


class AIPromptVersionAlreadyRegistered(AIError):
    code = "AI_PROMPT_VERSION_ALREADY_REGISTERED"
    httpStatus = 409

    def __init__(self, version: int | str = "") -> None:
        super().__init__("AI prompt version is already registered.")
        self.version = version


class AIPromptVersionNotFound(AIError):
    code = "AI_PROMPT_VERSION_NOT_FOUND"
    httpStatus = 404

    def __init__(self, versionId: str = "") -> None:
        super().__init__("AI prompt version was not found.")
        self.versionId = versionId


class AIPromptLifecycleInvalid(AIError):
    code = "AI_PROMPT_LIFECYCLE_INVALID"
    httpStatus = 409


class AIPromptTemplateInvalid(AIError):
    code = "AI_PROMPT_TEMPLATE_INVALID"
    httpStatus = 422


class AIPromptOutputSchemaInvalid(AIError):
    code = "AI_PROMPT_OUTPUT_SCHEMA_INVALID"
    httpStatus = 422


class AIPromptVersionImmutable(AIError):
    code = "AI_PROMPT_VERSION_IMMUTABLE"
    httpStatus = 409


class AIIdempotencyConflict(AIError):
    code = "AI_IDEMPOTENCY_CONFLICT"
    httpStatus = 409


class AIToolDenied(AIError):
    code = "AI_TOOL_DENIED"
    httpStatus = 403


class AIConfigurationError(AIError):
    code = "AI_CONFIGURATION_ERROR"
    httpStatus = 500
