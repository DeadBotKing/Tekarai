"""Pure AI Response and Structured Output contracts for Phase 13-H.

H consumes the ``AIResponse`` and ``AIRequest`` entities defined in Phase 13-B
and the Request lifecycle boundary from Phase 13-G.  It validates and indexes
responses in memory; it does not execute a provider, persist data, publish an
event, or call a framework.

Structured output is deliberately treated as untrusted provider data.  The
small dependency-free JSON Schema validator below covers the JSON Schema
keywords needed by the Domain boundary while keeping schema validation
explainable and vendor-neutral.  A later infrastructure boundary may use a
full standards-compliant validator, but it must preserve H's "validate before
publish/deliver" contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from apps.ai.domain.entities.aiRecords import AIRequest, AIResponse, requireUuid, utcNow
from apps.ai.domain.exceptions import (
    AIError,
    AIResponseAlreadyRegistered,
    AIResponseInvalid,
    AIResponseNotFound,
    AIResponseRequestInvalid,
    AIStructuredOutputInvalid,
    AIStructuredSchemaInvalid,
    AIPermissionDenied,
)
from apps.ai.domain.services.aiRules import enforceAuthoritativeChange
from apps.ai.domain.services.requestLifecycle import RequestLifecycleService
from apps.ai.domain.valueObjects.aiTypes import OUTPUT_CLASSIFICATIONS, RESPONSE_STATUSES, ensureEnum


JSON_SCHEMA_TYPES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})


def _plainValue(value: Any) -> Any:
    """Convert frozen schema containers to JSON-compatible containers."""

    if isinstance(value, Mapping):
        return {str(key): _plainValue(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plainValue(item) for item in value]
    return value


def _freezeValue(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freezeValue(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freezeValue(item) for item in value)
    return value


def _schemaTypeMatches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _validateSchemaDefinition(schema: Any, path: str = "$") -> None:
    if not isinstance(schema, Mapping):
        raise AIStructuredSchemaInvalid(f"JSON Schema at {path} must be an object.")
    for key in schema:
        if not isinstance(key, str):
            raise AIStructuredSchemaInvalid(f"JSON Schema key at {path} must be a string.")
    if "type" in schema:
        expected = schema["type"]
        expectedTypes = expected if isinstance(expected, (list, tuple)) else (expected,)
        if not expectedTypes or any(item not in JSON_SCHEMA_TYPES for item in expectedTypes):
            raise AIStructuredSchemaInvalid(f"JSON Schema type at {path} is invalid.")
    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, (list, tuple)) or any(not isinstance(item, str) for item in required):
            raise AIStructuredSchemaInvalid(f"JSON Schema required at {path} is invalid.")
    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, Mapping):
            raise AIStructuredSchemaInvalid(f"JSON Schema properties at {path} must be an object.")
        for name, child in properties.items():
            if not isinstance(name, str):
                raise AIStructuredSchemaInvalid(f"JSON Schema property name at {path} is invalid.")
            _validateSchemaDefinition(child, f"{path}.properties.{name}")
    if "additionalProperties" in schema:
        additional = schema["additionalProperties"]
        if not isinstance(additional, (bool, Mapping)):
            raise AIStructuredSchemaInvalid(f"JSON Schema additionalProperties at {path} is invalid.")
        if isinstance(additional, Mapping):
            _validateSchemaDefinition(additional, f"{path}.additionalProperties")
    if "items" in schema:
        _validateSchemaDefinition(schema["items"], f"{path}.items")
    for keyword in ("oneOf", "anyOf", "allOf"):
        if keyword in schema:
            alternatives = schema[keyword]
            if not isinstance(alternatives, (list, tuple)) or not alternatives:
                raise AIStructuredSchemaInvalid(f"JSON Schema {keyword} at {path} is invalid.")
            for index, child in enumerate(alternatives):
                _validateSchemaDefinition(child, f"{path}.{keyword}[{index}]")
    if "enum" in schema and not isinstance(schema["enum"], (list, tuple)):
        raise AIStructuredSchemaInvalid(f"JSON Schema enum at {path} is invalid.")
    if "pattern" in schema:
        if not isinstance(schema["pattern"], str):
            raise AIStructuredSchemaInvalid(f"JSON Schema pattern at {path} is invalid.")
        try:
            re.compile(schema["pattern"])
        except re.error as exc:
            raise AIStructuredSchemaInvalid(f"JSON Schema pattern at {path} is invalid.") from exc
    for keyword in ("minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties"):
        if keyword in schema and (
            not isinstance(schema[keyword], int) or isinstance(schema[keyword], bool) or schema[keyword] < 0
        ):
            raise AIStructuredSchemaInvalid(f"JSON Schema {keyword} at {path} is invalid.")
    for keyword in ("minimum", "maximum"):
        if keyword in schema and (
            not isinstance(schema[keyword], (int, float))
            or isinstance(schema[keyword], bool)
            or not math.isfinite(float(schema[keyword]))
        ):
            raise AIStructuredSchemaInvalid(f"JSON Schema {keyword} at {path} is invalid.")


def _normalizeJsonValue(value: Any, path: str = "$") -> Any:
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise AIStructuredOutputInvalid(
                    f"Structured output object key at {path} must be a string.",
                    (ValidationIssue(path, "object-key", "Object keys must be strings"),),
                )
            normalized[key] = _normalizeJsonValue(item, f"{path}.{key}")
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalizeJsonValue(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, str) or value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AIStructuredOutputInvalid(
                f"Structured output number at {path} must be finite.",
                (ValidationIssue(path, "number", "Number must be finite"),),
            )
        return value
    raise AIStructuredOutputInvalid(
        f"Structured output at {path} contains a non-JSON value.",
        (ValidationIssue(path, "json-type", "Value is not JSON-compatible"),),
    )


def normalizeStructuredOutput(value: Any) -> dict[str, Any]:
    """Parse raw JSON or mapping data and require an object root for AIResponse."""

    candidate = value
    if isinstance(value, str):
        try:
            candidate = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise AIStructuredOutputInvalid(
                "Structured AI output is not valid JSON.",
                (ValidationIssue("$", "json", "Value is not valid JSON"),),
            ) from exc
    normalized = _normalizeJsonValue(candidate)
    if not isinstance(normalized, dict):
        raise AIStructuredOutputInvalid(
            "Structured AI output must have a JSON object root.",
            (ValidationIssue("$", "type", "Expected an object root"),),
        )
    return normalized


@dataclass(frozen=True)
class ValidationIssue:
    """Non-sensitive, explainable schema validation issue."""

    path: str
    keyword: str
    message: str


def _validateValue(value: Any, schema: Mapping[str, Any], path: str, issues: list[ValidationIssue]) -> None:
    if "const" in schema and value != schema["const"]:
        issues.append(ValidationIssue(path, "const", "Value does not equal const"))
    if "enum" in schema and value not in schema["enum"]:
        issues.append(ValidationIssue(path, "enum", "Value is not in enum"))

    expected = schema.get("type")
    expectedTypes = expected if isinstance(expected, (list, tuple)) else ((expected,) if expected else ())
    if expectedTypes and not any(_schemaTypeMatches(value, item) for item in expectedTypes):
        issues.append(ValidationIssue(path, "type", f"Expected {', '.join(expectedTypes)}"))
        return

    if isinstance(value, dict):
        required = schema.get("required", ())
        for name in required:
            if name not in value:
                issues.append(ValidationIssue(f"{path}.{name}", "required", "Required property is missing"))
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for name, item in value.items():
            if name in properties:
                issues.extend(_validateWithCombinators(item, properties[name], f"{path}.{name}"))
            elif additional is False:
                issues.append(ValidationIssue(f"{path}.{name}", "additionalProperties", "Property is not allowed"))
            elif isinstance(additional, Mapping):
                issues.extend(_validateWithCombinators(item, additional, f"{path}.{name}"))
        if "minProperties" in schema and len(value) < schema["minProperties"]:
            issues.append(ValidationIssue(path, "minProperties", "Too few properties"))
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            issues.append(ValidationIssue(path, "maxProperties", "Too many properties"))
    elif isinstance(value, list):
        if "items" in schema:
            for index, item in enumerate(value):
                issues.extend(_validateWithCombinators(item, schema["items"], f"{path}[{index}]"))
        if "minItems" in schema and len(value) < schema["minItems"]:
            issues.append(ValidationIssue(path, "minItems", "Too few items"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            issues.append(ValidationIssue(path, "maxItems", "Too many items"))
    elif isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            issues.append(ValidationIssue(path, "minLength", "String is too short"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            issues.append(ValidationIssue(path, "maxLength", "String is too long"))
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            issues.append(ValidationIssue(path, "pattern", "String does not match pattern"))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            issues.append(ValidationIssue(path, "minimum", "Number is below minimum"))
        if "maximum" in schema and value > schema["maximum"]:
            issues.append(ValidationIssue(path, "maximum", "Number is above maximum"))


def _validateWithCombinators(value: Any, schema: Mapping[str, Any], path: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    baseSchema = {key: item for key, item in schema.items() if key not in {"oneOf", "anyOf", "allOf"}}
    _validateValue(value, baseSchema, path, issues)
    if "allOf" in schema:
        for child in schema["allOf"]:
            issues.extend(_validateWithCombinators(value, child, path))
    if "anyOf" in schema:
        branchIssues = [_validateWithCombinators(value, child, path) for child in schema["anyOf"]]
        if all(branchIssues):
            issues.append(ValidationIssue(path, "anyOf", "Value does not match any alternative"))
    if "oneOf" in schema:
        branchIssues = [_validateWithCombinators(value, child, path) for child in schema["oneOf"]]
        matches = sum(not branch for branch in branchIssues)
        if matches != 1:
            issues.append(ValidationIssue(path, "oneOf", "Value must match exactly one alternative"))
    return issues


@dataclass(frozen=True)
class StructuredOutputSchema:
    """Immutable, tenant-neutral JSON Schema contract for one response shape."""

    schema: Mapping[str, Any] = field(default_factory=dict)
    name: str = "structured-output"
    version: str = "1"

    def __post_init__(self) -> None:
        if not isinstance(self.schema, Mapping):
            raise AIStructuredSchemaInvalid("JSON Schema must be an object.")
        _validateSchemaDefinition(self.schema)
        if not str(self.name or "").strip() or not str(self.version or "").strip():
            raise AIStructuredSchemaInvalid("Structured output schema name and version are required.")
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "version", str(self.version).strip())
        object.__setattr__(self, "schema", _freezeValue(_plainValue(self.schema)))

    def asDict(self) -> dict[str, Any]:
        return _plainValue(self.schema)

    def validate(self, value: Any) -> tuple[ValidationIssue, ...]:
        normalized = _normalizeJsonValue(value)
        return tuple(_validateWithCombinators(normalized, self.schema, "$"))

    def assertValid(self, value: Any) -> Any:
        try:
            issues = self.validate(value)
        except AIStructuredOutputInvalid:
            raise
        if issues:
            raise AIStructuredOutputInvalid(
                "Structured AI output failed schema validation.",
                issues,
            )
        return value

    def fingerprint(self) -> str:
        encoded = json.dumps(
            {"name": self.name, "version": self.version, "schema": self.asDict()},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StructuredOutput:
    """Validated object-root output ready for an AIResponse boundary."""

    data: Mapping[str, Any]
    schemaFingerprint: str = ""
    validated: bool = True

    def __post_init__(self) -> None:
        normalized = normalizeStructuredOutput(self.data)
        object.__setattr__(self, "data", MappingProxyType(normalized))

    def asDict(self) -> dict[str, Any]:
        return dict(self.data)


@dataclass(frozen=True)
class ResponseDescriptor:
    """Safe immutable response read model; output content is intentionally omitted."""

    tenantId: uuid.UUID
    responseId: uuid.UUID
    requestId: uuid.UUID
    modelId: uuid.UUID
    providerId: uuid.UUID
    status: str
    contentPresent: bool
    hasStructuredData: bool
    structuredOutputValidated: bool
    structuredSchemaFingerprint: str
    outputClassification: str
    promptVersionId: uuid.UUID | None
    inputTokens: int
    outputTokens: int
    totalTokens: int
    latencyMs: int
    errorCode: str
    correlationId: str
    traceId: str
    createdAt: datetime


@dataclass
class RegisteredResponseState:
    response: AIResponse
    hasStructuredData: bool
    structuredOutputValidated: bool
    schemaFingerprint: str
    validationIssues: tuple[ValidationIssue, ...] = ()


class AIResponseService:
    """Tenant-aware in-memory Response registry and Structured Output boundary."""

    def __init__(
        self,
        *,
        requestLifecycle: RequestLifecycleService | None = None,
        now: Any = utcNow,
    ) -> None:
        if requestLifecycle is not None and not isinstance(requestLifecycle, RequestLifecycleService):
            raise TypeError("requestLifecycle must be a RequestLifecycleService.")
        if not callable(now):
            raise TypeError("now must be callable.")
        self.requestLifecycle = requestLifecycle
        self._now = now
        self._responses: dict[tuple[uuid.UUID, uuid.UUID], RegisteredResponseState] = {}

    def createResponse(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
        modelId: uuid.UUID | str,
        providerId: uuid.UUID | str,
        *,
        content: str = "",
        structuredData: Any = None,
        structuredOutputSchema: StructuredOutputSchema | Mapping[str, Any] | None = None,
        schema: StructuredOutputSchema | Mapping[str, Any] | None = None,
        status: str = "COMPLETED",
        outputClassification: str = "ADVISORY",
        promptVersionId: uuid.UUID | str | None = None,
        inputTokens: int = 0,
        outputTokens: int = 0,
        totalTokens: int = 0,
        latencyMs: int = 0,
        errorCode: str = "",
        responseId: uuid.UUID | str | None = None,
        authorized: bool = False,
    ) -> AIResponse:
        if structuredOutputSchema is not None and schema is not None:
            raise AIResponseInvalid("Provide only one structured output schema argument.")
        outputSchema = self._coerceSchema(
            structuredOutputSchema if structuredOutputSchema is not None else schema
        )
        normalizedStatus = self._normalizeStatus(status)
        normalizedClassification = self._normalizeClassification(outputClassification)
        try:
            enforceAuthoritativeChange(normalizedClassification, authorized=authorized)
        except AIPermissionDenied:
            raise
        except Exception as exc:
            raise AIResponseInvalid("Output classification authorization is invalid.") from exc

        normalizedStructured: dict[str, Any] = {}
        hasStructuredData = structuredData is not None
        structuredValidated = False
        validationIssues: tuple[ValidationIssue, ...] = ()
        if normalizedStatus == "VALIDATION_FAILED":
            normalizedErrorCode = str(errorCode or "AI_STRUCTURED_OUTPUT_INVALID").strip().upper()
            if hasStructuredData and outputSchema is not None:
                try:
                    candidate = normalizeStructuredOutput(structuredData)
                    validationIssues = outputSchema.validate(candidate)
                except AIStructuredOutputInvalid as exc:
                    validationIssues = exc.issues
            normalizedErrorCode = normalizedErrorCode or "AI_STRUCTURED_OUTPUT_INVALID"
            errorCode = normalizedErrorCode
            # Invalid provider output is never retained as deliverable data.
            normalizedStructured = {}
        else:
            if not isinstance(content, str):
                raise AIResponseInvalid("Response content must be a string.")
            if hasStructuredData:
                normalizedStructured = self._normalizeAndValidate(structuredData, outputSchema)
                structuredValidated = outputSchema is not None
            if normalizedStatus == "COMPLETED" and not content and not hasStructuredData:
                raise AIResponseInvalid("A completed response requires content or structured data.")
            if normalizedStatus == "FAILED":
                errorCode = str(errorCode or "").strip().upper()
                if not errorCode:
                    raise AIResponseInvalid("A failed response requires an error code.")

        tenant = requireUuid(tenantId, "tenantId")
        request = self._validateRequest(tenant, requestId, normalizedStatus)
        response = AIResponse(
            tenantId=tenant,
            requestId=requireUuid(requestId, "requestId"),
            modelId=requireUuid(modelId, "modelId"),
            providerId=requireUuid(providerId, "providerId"),
            status=normalizedStatus,
            content=content,
            structuredData=normalizedStructured,
            inputTokens=inputTokens,
            outputTokens=outputTokens,
            totalTokens=totalTokens,
            latencyMs=latencyMs,
            outputClassification=normalizedClassification,
            promptVersionId=(requireUuid(promptVersionId, "promptVersionId") if promptVersionId is not None else None),
            id=(requireUuid(responseId, "responseId") if responseId is not None else uuid.uuid4()),
            errorCode=errorCode,
            createdAt=self._now(),
        )
        # Keep this local variable explicit: it documents that Request lookup
        # is an ownership check, not an automatic Request state mutation.
        _ = request
        return self.registerResponse(
            response,
            structuredOutputSchema=outputSchema,
            hasStructuredData=hasStructuredData,
            structuredOutputValidated=structuredValidated,
            validationIssues=validationIssues,
        )

    def registerResponse(
        self,
        response: AIResponse,
        *,
        structuredOutputSchema: StructuredOutputSchema | Mapping[str, Any] | None = None,
        schema: StructuredOutputSchema | Mapping[str, Any] | None = None,
        hasStructuredData: bool | None = None,
        structuredOutputValidated: bool | None = None,
        validationIssues: tuple[ValidationIssue, ...] = (),
    ) -> AIResponse:
        if not isinstance(response, AIResponse):
            raise AIResponseInvalid("Response definition must be an AIResponse.")
        if structuredOutputSchema is not None and schema is not None:
            raise AIResponseInvalid("Provide only one structured output schema argument.")
        outputSchema = self._coerceSchema(
            structuredOutputSchema if structuredOutputSchema is not None else schema
        )
        self._validateRequest(response.tenantId, response.requestId, response.status)
        if response.status == "COMPLETED":
            if not isinstance(response.content, str):
                raise AIResponseInvalid("Response content must be a string.")
            inferredHasData = (
                hasStructuredData
                if hasStructuredData is not None
                else bool(response.structuredData) or outputSchema is not None
            )
            if not response.content and not inferredHasData:
                raise AIResponseInvalid("A completed response requires content or structured data.")
            if outputSchema is not None:
                response.structuredData = self._normalizeAndValidate(response.structuredData, outputSchema)
            elif response.structuredData:
                response.structuredData = normalizeStructuredOutput(response.structuredData)
        elif response.status == "FAILED" and not str(response.errorCode or "").strip():
            raise AIResponseInvalid("A failed response requires an error code.")
        if response.status == "VALIDATION_FAILED":
            if not str(response.errorCode or "").strip():
                raise AIResponseInvalid("A validation-failed response requires an error code.")
            if response.structuredData:
                raise AIResponseInvalid("A validation-failed response cannot retain output payload.")

        key = (response.tenantId, response.id)
        if key in self._responses:
            raise AIResponseAlreadyRegistered(str(response.id))
        registered = RegisteredResponseState(
            response=response,
            hasStructuredData=(hasStructuredData if hasStructuredData is not None else bool(response.structuredData)),
            structuredOutputValidated=(
                structuredOutputValidated
                if structuredOutputValidated is not None
                else outputSchema is not None
            ),
            schemaFingerprint=outputSchema.fingerprint() if outputSchema is not None else "",
            validationIssues=validationIssues,
        )
        self._responses[key] = registered
        return response

    def validateStructuredOutput(
        self,
        value: Any,
        schema: StructuredOutputSchema | Mapping[str, Any],
    ) -> StructuredOutput:
        outputSchema = self._coerceSchema(schema)
        normalized = normalizeStructuredOutput(value)
        issues = outputSchema.validate(normalized)
        if issues:
            raise AIStructuredOutputInvalid("Structured AI output failed schema validation.", issues)
        return StructuredOutput(
            normalized,
            schemaFingerprint=outputSchema.fingerprint(),
            validated=True,
        )

    def getResponse(self, tenantId: uuid.UUID | str, responseId: uuid.UUID | str) -> AIResponse:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(responseId, "responseId")
        registration = self._responses.get((tenant, identifier))
        if registration is None:
            raise AIResponseNotFound(str(identifier))
        return registration.response

    def describeResponse(
        self,
        tenantId: uuid.UUID | str,
        responseId: uuid.UUID | str,
    ) -> ResponseDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(responseId, "responseId")
        registration = self._responses.get((tenant, identifier))
        if registration is None:
            raise AIResponseNotFound(str(identifier))
        response = registration.response
        correlationId = ""
        traceId = ""
        if self.requestLifecycle is not None:
            requestDescriptor = self.requestLifecycle.describeRequest(tenant, response.requestId)
            correlationId = requestDescriptor.correlationId
            traceId = requestDescriptor.traceId
        return ResponseDescriptor(
            tenantId=response.tenantId,
            responseId=response.id,
            requestId=response.requestId,
            modelId=response.modelId,
            providerId=response.providerId,
            status=response.status,
            contentPresent=bool(response.content),
            hasStructuredData=registration.hasStructuredData,
            structuredOutputValidated=registration.structuredOutputValidated,
            structuredSchemaFingerprint=registration.schemaFingerprint,
            outputClassification=response.outputClassification,
            promptVersionId=response.promptVersionId,
            inputTokens=response.inputTokens,
            outputTokens=response.outputTokens,
            totalTokens=response.totalTokens,
            latencyMs=response.latencyMs,
            errorCode=response.errorCode,
            correlationId=correlationId,
            traceId=traceId,
            createdAt=response.createdAt,
        )

    def listResponses(
        self,
        tenantId: uuid.UUID | str,
        *,
        requestId: uuid.UUID | str | None = None,
        status: str | None = None,
    ) -> tuple[ResponseDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        requested = requireUuid(requestId, "requestId") if requestId is not None else None
        normalizedStatus = self._normalizeStatus(status) if status else None
        descriptors = [
            self.describeResponse(tenant, response.response.id)
            for (responseTenant, _), response in self._responses.items()
            if responseTenant == tenant
            and (requested is None or response.response.requestId == requested)
            and (normalizedStatus is None or response.response.status == normalizedStatus)
        ]
        return tuple(sorted(descriptors, key=lambda item: (item.createdAt, str(item.responseId))))

    def responseCount(self, tenantId: uuid.UUID | str, requestId: uuid.UUID | str | None = None) -> int:
        return len(self.listResponses(tenantId, requestId=requestId))

    def register(self, response: AIResponse, **kwargs: Any) -> AIResponse:
        return self.registerResponse(response, **kwargs)

    def get(self, tenantId: uuid.UUID | str, responseId: uuid.UUID | str) -> AIResponse:
        return self.getResponse(tenantId, responseId)

    def _validateRequest(
        self,
        tenantId: uuid.UUID,
        requestId: uuid.UUID | str,
        responseStatus: str,
    ) -> AIRequest | None:
        if self.requestLifecycle is None:
            return None
        identifier = requireUuid(requestId, "requestId")
        try:
            request = self.requestLifecycle.getRequest(tenantId, identifier)
        except AIError as exc:
            raise AIResponseRequestInvalid(str(identifier)) from exc
        if request.status == "CANCELLED":
            raise AIResponseRequestInvalid(str(identifier))
        if responseStatus == "COMPLETED" and request.status == "FAILED":
            raise AIResponseRequestInvalid(str(identifier))
        return request

    @staticmethod
    def _normalizeAndValidate(
        value: Any,
        outputSchema: StructuredOutputSchema | None,
    ) -> dict[str, Any]:
        normalized = normalizeStructuredOutput(value)
        if outputSchema is not None:
            outputSchema.assertValid(normalized)
        return normalized

    @staticmethod
    def _coerceSchema(
        schema: StructuredOutputSchema | Mapping[str, Any] | None,
    ) -> StructuredOutputSchema | None:
        if schema is None:
            return None
        if isinstance(schema, StructuredOutputSchema):
            return schema
        if isinstance(schema, Mapping):
            return StructuredOutputSchema(schema=schema)
        raise AIStructuredSchemaInvalid("Structured output schema is invalid.")

    @staticmethod
    def _normalizeStatus(status: str) -> str:
        try:
            return ensureEnum(status, RESPONSE_STATUSES, "responseStatus")
        except Exception as exc:
            raise AIResponseInvalid("Response status is invalid.") from exc

    @staticmethod
    def _normalizeClassification(classification: str) -> str:
        try:
            return ensureEnum(classification, OUTPUT_CLASSIFICATIONS, "outputClassification")
        except Exception as exc:
            raise AIResponseInvalid("Output classification is invalid.") from exc


AIResponseLifecycle = AIResponseService
ResponseLifecycleService = AIResponseService
ResponseRegistry = AIResponseService
AIResponseRegistry = AIResponseService
InMemoryResponseRegistry = AIResponseService
StructuredOutputValidator = StructuredOutputSchema
ResponseContract = StructuredOutputSchema

__all__ = [
    "AIResponseLifecycle",
    "AIResponseRegistry",
    "AIResponseService",
    "InMemoryResponseRegistry",
    "ResponseContract",
    "ResponseDescriptor",
    "ResponseLifecycleService",
    "ResponseRegistry",
    "StructuredOutput",
    "StructuredOutputSchema",
    "StructuredOutputValidator",
    "ValidationIssue",
    "normalizeStructuredOutput",
]
