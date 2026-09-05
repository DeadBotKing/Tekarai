"""Provider-neutral AI contracts for Phase 13-C.

This module is the only contract a provider adapter must implement. It is pure
Python and intentionally has no HTTP, ORM, queue, framework, network, or
vendor-SDK dependency. Concrete adapters belong under infrastructure.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from apps.sharedKernel.domain.errors import ValidationFailedError

MODEL_FEATURES = (
    "GENERATION",
    "STRUCTURED_GENERATION",
    "STREAMING",
    "EMBEDDING",
    "TOKEN_COUNTING",
    "TOOLS",
    "VISION",
)
RESPONSE_FORMATS = ("TEXT", "JSON")
FINISH_REASONS = ("STOP", "LENGTH", "TOOL_CALL", "CONTENT_FILTER", "ERROR", "UNKNOWN")
HEALTH_STATUSES = ("HEALTHY", "DEGRADED", "UNAVAILABLE", "UNKNOWN")


def requireUuid(value: uuid.UUID | str, fieldName: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError) as exc:
        raise ValidationFailedError(f"{fieldName} must be a UUID.") from exc


def normalizeFeature(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in MODEL_FEATURES:
        raise ValidationFailedError(
            "Unknown provider feature.", fieldErrors={"feature": normalized}
        )
    return normalized


@dataclass(frozen=True)
class ProviderRequestContext:
    """Trace and tenant context that must travel through every adapter call."""

    tenantId: uuid.UUID | str
    requestId: uuid.UUID | str | None = None
    operationId: uuid.UUID | str | None = None
    correlationId: str = ""
    traceId: str = ""
    idempotencyKey: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenantId", requireUuid(self.tenantId, "tenantId"))
        if self.requestId is not None:
            object.__setattr__(self, "requestId", requireUuid(self.requestId, "requestId"))
        if self.operationId is not None:
            object.__setattr__(self, "operationId", requireUuid(self.operationId, "operationId"))
        if not self.correlationId.strip():
            object.__setattr__(self, "correlationId", uuid.uuid4().hex)
        if not self.traceId.strip():
            object.__setattr__(self, "traceId", uuid.uuid4().hex)


@dataclass(frozen=True)
class GenerationRequest:
    """Provider-neutral input for text or structured generation."""

    prompt: str
    model: str = "test"
    systemInstruction: str = ""
    temperature: float = 0.0
    maxTokens: int | None = None
    responseFormat: str = "TEXT"
    jsonSchema: dict[str, Any] = field(default_factory=dict)
    stopSequences: tuple[str, ...] = ()
    context: ProviderRequestContext | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ValidationFailedError("Provider prompt is required.")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValidationFailedError("Provider model is required.")
        if (
            not isinstance(self.temperature, (int, float))
            or isinstance(self.temperature, bool)
            or not math.isfinite(self.temperature)
            or self.temperature < 0
        ):
            raise ValidationFailedError("Provider temperature must be finite and non-negative.")
        if self.maxTokens is not None and (
            not isinstance(self.maxTokens, int)
            or isinstance(self.maxTokens, bool)
            or self.maxTokens < 1
        ):
            raise ValidationFailedError("Provider maxTokens must be a positive integer.")
        responseFormat = str(self.responseFormat or "").strip().upper()
        if responseFormat not in RESPONSE_FORMATS:
            raise ValidationFailedError("Unsupported provider response format.")
        object.__setattr__(self, "responseFormat", responseFormat)
        if responseFormat == "JSON" and not isinstance(self.jsonSchema, dict):
            raise ValidationFailedError("JSON response schema must be an object.")


@dataclass(frozen=True)
class GenerationResult:
    """Normalized provider output; no provider-specific response object leaks."""

    content: str = ""
    structuredData: dict[str, Any] = field(default_factory=dict)
    inputTokens: int = 0
    outputTokens: int = 0
    model: str = ""
    provider: str = ""
    finishReason: str = "STOP"
    requestId: uuid.UUID | None = None
    correlationId: str = ""
    traceId: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.content, str) or not isinstance(self.structuredData, dict):
            raise ValidationFailedError("Provider generation result has invalid data types.")
        if (
            not isinstance(self.inputTokens, int)
            or isinstance(self.inputTokens, bool)
            or not isinstance(self.outputTokens, int)
            or isinstance(self.outputTokens, bool)
            or self.inputTokens < 0
            or self.outputTokens < 0
        ):
            raise ValidationFailedError("Provider token counts must be non-negative integers.")
        finishReason = str(self.finishReason or "UNKNOWN").strip().upper()
        if finishReason not in FINISH_REASONS:
            raise ValidationFailedError("Unknown provider finish reason.")
        object.__setattr__(self, "finishReason", finishReason)
        if self.requestId is not None:
            object.__setattr__(self, "requestId", requireUuid(self.requestId, "requestId"))

    @property
    def totalTokens(self) -> int:
        return self.inputTokens + self.outputTokens


@dataclass(frozen=True)
class GenerationChunk:
    """One normalized item from a streaming generation call."""

    content: str = ""
    index: int = 0
    isFinal: bool = False
    finishReason: str = "UNKNOWN"
    model: str = ""
    provider: str = ""
    requestId: uuid.UUID | None = None
    correlationId: str = ""
    traceId: str = ""

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValidationFailedError("Provider stream index cannot be negative.")
        finishReason = str(self.finishReason or "UNKNOWN").strip().upper()
        if finishReason not in FINISH_REASONS:
            raise ValidationFailedError("Unknown provider finish reason.")
        object.__setattr__(self, "finishReason", finishReason)
        if self.requestId is not None:
            object.__setattr__(self, "requestId", requireUuid(self.requestId, "requestId"))


@dataclass(frozen=True)
class EmbeddingResult:
    """Normalized single embedding result for adapters that need metadata."""

    vector: tuple[float, ...]
    inputTokens: int = 0
    model: str = ""
    provider: str = ""
    requestId: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if not self.vector:
            raise ValidationFailedError("Provider embedding vector cannot be empty.")
        if any(not math.isfinite(value) for value in self.vector):
            raise ValidationFailedError("Provider embedding vector contains a non-finite value.")
        if self.inputTokens < 0:
            raise ValidationFailedError("Provider embedding token count cannot be negative.")
        if self.requestId is not None:
            object.__setattr__(self, "requestId", requireUuid(self.requestId, "requestId"))

    @property
    def dimensions(self) -> int:
        return len(self.vector)


@dataclass(frozen=True)
class ProviderCapabilities:
    """Feature handshake advertised by an adapter, not a vendor SDK object."""

    providerCode: str
    features: frozenset[str] = frozenset({"GENERATION"})
    maxContextWindow: int | None = None
    supportsTemperature: bool = True
    supportsJsonSchema: bool = False
    supportsBatchEmbedding: bool = False

    def __post_init__(self) -> None:
        if not self.providerCode.strip():
            raise ValidationFailedError("Provider code is required.")
        normalized = frozenset(normalizeFeature(value) for value in self.features)
        object.__setattr__(self, "providerCode", self.providerCode.strip().upper())
        object.__setattr__(self, "features", normalized)
        if self.maxContextWindow is not None and self.maxContextWindow < 1:
            raise ValidationFailedError("Provider context window must be positive.")
        if self.supportsJsonSchema and "STRUCTURED_GENERATION" not in normalized:
            raise ValidationFailedError("JSON Schema support requires structured generation.")
        if self.supportsBatchEmbedding and "EMBEDDING" not in normalized:
            raise ValidationFailedError("Batch embedding support requires embedding.")

    def supports(self, feature: str) -> bool:
        return normalizeFeature(feature) in self.features


@dataclass(frozen=True)
class ProviderHealth:
    """Non-sensitive health snapshot returned by an adapter."""

    status: str = "UNKNOWN"
    checkedAt: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    latencyMs: int | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        status = str(self.status or "UNKNOWN").strip().upper()
        if status not in HEALTH_STATUSES:
            raise ValidationFailedError("Unknown provider health status.")
        if self.latencyMs is not None and self.latencyMs < 0:
            raise ValidationFailedError("Provider health latency cannot be negative.")
        object.__setattr__(self, "status", status)


def resolvedRequestId(context: ProviderRequestContext | None) -> uuid.UUID | None:
    """Typed accessor for the normalized request id carried by a context.

    ``ProviderRequestContext.__post_init__`` normalizes ``requestId`` to a
    UUID; this helper exposes that guarantee to adapters so results and
    stream chunks can carry a strictly typed identifier.
    """

    if context is None or context.requestId is None:
        return None
    requestId = context.requestId
    return requestId if isinstance(requestId, uuid.UUID) else None


def validateGenerationResult(
    result: GenerationResult,
    *,
    expectedModel: str = "",
    expectedProvider: str = "",
) -> GenerationResult:
    """Validate the normalized boundary before application/persistence use."""

    if not isinstance(result, GenerationResult):
        raise ValidationFailedError("Provider returned an invalid generation result.")
    if expectedModel and result.model and result.model != expectedModel:
        raise ValidationFailedError("Provider result model does not match the request.")
    if expectedProvider and result.provider and result.provider != expectedProvider:
        raise ValidationFailedError("Provider result provider does not match the request.")
    return result


def validateEmbeddingVector(vector: Iterable[float]) -> tuple[float, ...]:
    normalized = tuple(float(value) for value in vector)
    return EmbeddingResult(normalized).vector


def requireProviderFeature(capabilities: ProviderCapabilities, feature: str) -> None:
    if not capabilities.supports(feature):
        raise ValidationFailedError(f"Provider does not support {normalizeFeature(feature)}.")


@runtime_checkable
class AIProviderPort(Protocol):
    """The provider adapter boundary from AI Domain/Application to Infrastructure."""

    @property
    def providerCode(self) -> str: ...

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def generate(
        self,
        *,
        prompt: str,
        systemInstruction: str = "",
        model: str,
        temperature: float = 0.0,
        maxTokens: int | None = None,
        responseFormat: str = "TEXT",
        jsonSchema: dict[str, Any] | None = None,
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> GenerationResult: ...

    def generateRequest(self, request: GenerationRequest) -> GenerationResult: ...

    def generateStructured(
        self,
        *,
        prompt: str,
        model: str,
        jsonSchema: dict[str, Any],
        systemInstruction: str = "",
        temperature: float = 0.0,
        maxTokens: int | None = None,
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> GenerationResult: ...

    def stream(
        self,
        *,
        prompt: str,
        systemInstruction: str = "",
        model: str,
        temperature: float = 0.0,
        maxTokens: int | None = None,
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> Iterable[GenerationChunk]: ...

    def embed(
        self,
        *,
        text: str,
        model: str,
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> list[float]: ...

    def embedBatch(
        self,
        *,
        texts: Iterable[str],
        model: str,
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> list[list[float]]: ...

    def countTokens(self, *, text: str, model: str, **kwargs: Any) -> int: ...

    def healthCheck(self, *, model: str = "", **kwargs: Any) -> ProviderHealth: ...


class DeterministicAIProvider:
    """Offline contract test double; production adapters belong in Infrastructure."""

    providerCode = "DETERMINISTIC"
    capabilities = ProviderCapabilities(
        providerCode=providerCode,
        features=frozenset(
            {
                "GENERATION",
                "STRUCTURED_GENERATION",
                "STREAMING",
                "EMBEDDING",
                "TOKEN_COUNTING",
            }
        ),
        maxContextWindow=32_000,
        supportsJsonSchema=True,
        supportsBatchEmbedding=True,
    )

    def generate(
        self,
        *,
        prompt: str = "",
        systemInstruction: str = "",
        model: str = "test",
        temperature: float = 0.0,
        maxTokens: int | None = None,
        responseFormat: str = "TEXT",
        jsonSchema: dict[str, Any] | None = None,
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> GenerationResult:
        request = GenerationRequest(
            prompt=prompt,
            systemInstruction=systemInstruction,
            model=model,
            temperature=temperature,
            maxTokens=maxTokens,
            responseFormat=responseFormat,
            jsonSchema=jsonSchema or {},
            context=context,
        )
        content = f"[deterministic:{request.model}] {request.prompt}"
        structuredData = (
            self._structuredData(request.jsonSchema, request.prompt, request.model)
            if request.responseFormat == "JSON"
            else {}
        )
        output = content if request.responseFormat == "TEXT" else ""
        if request.maxTokens is not None:
            output = output[: request.maxTokens]
        result = GenerationResult(
            content=output,
            structuredData=structuredData,
            inputTokens=self.countTokens(text=request.prompt, model=request.model),
            outputTokens=self.countTokens(text=output, model=request.model) if output else 1,
            model=request.model,
            provider="deterministic",
            requestId=resolvedRequestId(request.context),
            correlationId=request.context.correlationId if request.context else "",
            traceId=request.context.traceId if request.context else "",
        )
        return validateGenerationResult(
            result, expectedModel=request.model, expectedProvider="deterministic"
        )

    def generateRequest(self, request: GenerationRequest) -> GenerationResult:
        return self.generate(
            prompt=request.prompt,
            systemInstruction=request.systemInstruction,
            model=request.model,
            temperature=request.temperature,
            maxTokens=request.maxTokens,
            responseFormat=request.responseFormat,
            jsonSchema=request.jsonSchema,
            context=request.context,
        )

    def generateStructured(
        self,
        *,
        prompt: str,
        model: str = "test",
        jsonSchema: dict[str, Any],
        systemInstruction: str = "",
        temperature: float = 0.0,
        maxTokens: int | None = None,
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> GenerationResult:
        return self.generate(
            prompt=prompt,
            systemInstruction=systemInstruction,
            model=model,
            temperature=temperature,
            maxTokens=maxTokens,
            responseFormat="JSON",
            jsonSchema=jsonSchema,
            context=context,
        )

    def stream(
        self,
        *,
        prompt: str,
        systemInstruction: str = "",
        model: str = "test",
        temperature: float = 0.0,
        maxTokens: int | None = None,
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> Iterator[GenerationChunk]:
        result = self.generate(
            prompt=prompt,
            systemInstruction=systemInstruction,
            model=model,
            temperature=temperature,
            maxTokens=maxTokens,
            context=context,
        )
        words = result.content.split(" ")
        for index, word in enumerate(words):
            yield GenerationChunk(
                content=(" " if index else "") + word,
                index=index,
                isFinal=index == len(words) - 1,
                finishReason="STOP" if index == len(words) - 1 else "UNKNOWN",
                model=result.model,
                provider=result.provider,
                requestId=result.requestId,
                correlationId=result.correlationId,
                traceId=result.traceId,
            )

    def embed(
        self,
        *,
        text: str,
        model: str = "test",
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> list[float]:
        if not isinstance(text, str) or not text:
            raise ValidationFailedError("Embedding text is required.")
        vector = [float((sum(map(ord, text)) + index) % 997) / 997 for index in range(8)]
        return list(validateEmbeddingVector(vector))

    def embedBatch(
        self,
        *,
        texts: Iterable[str],
        model: str = "test",
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        return [self.embed(text=text, model=model, context=context) for text in texts]

    def countTokens(self, *, text: str, model: str = "test", **kwargs: Any) -> int:
        if not isinstance(text, str):
            raise ValidationFailedError("Token counting text must be a string.")
        return len(text.split()) if text.strip() else 0

    def healthCheck(self, *, model: str = "", **kwargs: Any) -> ProviderHealth:
        return ProviderHealth(
            status="HEALTHY", latencyMs=0, detail="offline deterministic provider"
        )

    @staticmethod
    def _structuredData(schema: dict[str, Any], prompt: str, model: str) -> dict[str, Any]:
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        required = schema.get("required", []) if isinstance(schema, dict) else []
        result: dict[str, Any] = {"text": prompt, "model": model}
        for key in required:
            propertySchema = properties.get(key, {})
            valueType = propertySchema.get("type")
            if "enum" in propertySchema and propertySchema["enum"]:
                result[key] = propertySchema["enum"][0]
            elif valueType == "array":
                result[key] = []
            elif valueType == "boolean":
                result[key] = True
            elif valueType in {"number", "integer"}:
                result[key] = 0
            elif valueType == "object":
                result[key] = {}
            else:
                result[key] = f"deterministic:{key}"
        return result


__all__ = [
    "AIProviderPort",
    "DeterministicAIProvider",
    "EmbeddingResult",
    "FINISH_REASONS",
    "GenerationChunk",
    "GenerationRequest",
    "GenerationResult",
    "HEALTH_STATUSES",
    "MODEL_FEATURES",
    "ProviderCapabilities",
    "ProviderHealth",
    "ProviderRequestContext",
    "RESPONSE_FORMATS",
    "normalizeFeature",
    "resolvedRequestId",
    "requireProviderFeature",
    "validateEmbeddingVector",
    "validateGenerationResult",
]
