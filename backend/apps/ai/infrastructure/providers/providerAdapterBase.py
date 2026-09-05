"""Shared base for HTTP provider adapters (Phase 13-L).

The base implements the complete ``AIProviderPort`` surface once — input
validation, feature gating, error mapping, result normalization, secret
redaction — while each vendor adapter only supplies payload building,
response parsing, endpoint shape, authentication headers, and capability
handshake. This keeps vendor code thin and guarantees that no adapter can
leak a vendor exception or secret through the port (C §3 rules 4-7).
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Iterable, Iterator
from typing import Any
from urllib.error import HTTPError

from apps.ai.domain.exceptions import (
    AIOutputValidationFailed,
    AIProviderUnavailable,
)
from apps.ai.domain.ports import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderRequestContext,
    requireProviderFeature,
    resolvedRequestId,
    validateEmbeddingVector,
    validateGenerationResult,
)
from apps.ai.infrastructure.providers.providerErrors import (
    executeProviderCall,
    mapHttpError,
    mapTransportError,
    parseJsonBody,
    sanitizeText,
)
from apps.ai.infrastructure.providers.providerHttp import HttpResponse, UrllibJsonTransport
from apps.sharedKernel.domain.errors import ValidationFailedError

HEALTH_TIMEOUT_SECONDS = 5.0
CORRELATION_HEADER = "X-Correlation-Id"
TRACE_HEADER = "X-Trace-Id"


def estimateTokenCount(text: str) -> int:
    """Deterministic offline token estimate (C §5.5 — port contract only).

    Model-specific tokenizers are deliberately not imported; accurate usage
    accounting is a later sub-phase concern. The estimate is stable, cheap,
    and always a non-negative integer as the port requires.
    """

    if not isinstance(text, str) or not text.strip():
        return 0
    return max(1, math.ceil(len(text) / 4))


class HttpProviderAdapterBase:
    """Provider-neutral HTTP adapter implementing ``AIProviderPort``."""

    providerCode: str = ""
    providerSlug: str = ""
    supportsHealthEndpoint: bool = True

    def __init__(
        self,
        *,
        baseUrl: str,
        apiKey: str = "",
        timeoutSeconds: float = 30.0,
        transport: UrllibJsonTransport | None = None,
        capabilities: ProviderCapabilities | None = None,
    ) -> None:
        normalizedBase = str(baseUrl or "").strip().rstrip("/")
        if not normalizedBase:
            raise AIProviderUnavailable(f"{self.providerCode} requires a base URL.")
        if timeoutSeconds <= 0:
            raise ValidationFailedError("Provider timeout must be positive.")
        self.baseUrl = normalizedBase
        self.apiKey = apiKey
        self.timeoutSeconds = float(timeoutSeconds)
        self.transport = transport or UrllibJsonTransport(timeoutSeconds=self.timeoutSeconds)
        self._capabilities = capabilities or self.buildCapabilities()

    # ------------------------------------------------------------------ #
    # Contract surface required of every vendor adapter
    # ------------------------------------------------------------------ #
    def buildCapabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    def authHeaders(self) -> dict[str, str]:
        return {}

    def secrets(self) -> tuple[str, ...]:
        return (self.apiKey,) if self.apiKey else ()

    def generationUrl(self, model: str) -> str:
        raise NotImplementedError

    def embeddingUrl(self, model: str) -> str:
        raise NotImplementedError

    def healthUrl(self) -> str:
        return ""

    def buildGenerationPayload(self, request: GenerationRequest) -> dict[str, Any]:
        raise NotImplementedError

    def parseGenerationPayload(self, payload: Any, request: GenerationRequest) -> GenerationResult:
        raise NotImplementedError

    def buildEmbeddingPayload(self, texts: tuple[str, ...], model: str) -> dict[str, Any]:
        raise NotImplementedError

    def parseEmbeddingPayload(self, payload: Any, model: str) -> tuple[list[list[float]], int]:
        raise NotImplementedError

    def iterStreamChunks(
        self,
        lines: Iterator[str],
        request: GenerationRequest,
    ) -> Iterator[GenerationChunk]:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # AIProviderPort implementation
    # ------------------------------------------------------------------ #
    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

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
        return self.generateRequest(request)

    def generateRequest(self, request: GenerationRequest) -> GenerationResult:
        requireProviderFeature(self._capabilities, "GENERATION")
        if request.responseFormat == "JSON":
            requireProviderFeature(self._capabilities, "STRUCTURED_GENERATION")
        payload = self.buildGenerationPayload(request)
        url = self.generationUrl(request.model)

        def call() -> GenerationResult:
            response = self.transport.request(
                "POST",
                url,
                payload=payload,
                headers=self.requestHeaders(request.context),
            )
            self.assertSuccess(response, model=request.model)
            parsed = parseJsonBody(response.body, providerCode=self.providerCode)
            return self.parseGenerationPayload(parsed, request)

        result = executeProviderCall(
            call,
            providerCode=self.providerCode,
            model=request.model,
            secrets=self.secrets(),
        )
        return validateGenerationResult(
            result,
            expectedModel=request.model,
            expectedProvider=self.providerSlug,
        )

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
    ) -> GenerationResult:
        if not isinstance(jsonSchema, dict) or not jsonSchema:
            raise ValidationFailedError("Structured generation requires a JSON schema.")
        requireProviderFeature(self._capabilities, "STRUCTURED_GENERATION")
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
        model: str,
        temperature: float = 0.0,
        maxTokens: int | None = None,
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> Iterable[GenerationChunk]:
        request = GenerationRequest(
            prompt=prompt,
            systemInstruction=systemInstruction,
            model=model,
            temperature=temperature,
            maxTokens=maxTokens,
            context=context,
        )
        requireProviderFeature(self._capabilities, "STREAMING")
        payload = self.buildGenerationPayload(request)
        payload["stream"] = True
        url = self.generationUrl(request.model)
        headers = self.requestHeaders(request.context)

        def lineIterator() -> Iterator[str]:
            return self.transport.streamLines(
                "POST",
                url,
                payload=payload,
                headers=headers,
            )

        lines = executeProviderCall(
            lineIterator,
            providerCode=self.providerCode,
            model=request.model,
            secrets=self.secrets(),
        )
        return self._mappedChunkIterator(lines, request)

    def embed(
        self,
        *,
        text: str,
        model: str,
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> list[float]:
        if not isinstance(text, str) or not text.strip():
            raise ValidationFailedError("Embedding text is required.")
        vectors = self._embedTexts((text,), model, context)
        return vectors[0]

    def embedBatch(
        self,
        *,
        texts: Iterable[str],
        model: str,
        context: ProviderRequestContext | None = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        normalized = tuple(str(item) for item in texts)
        if not normalized or any(not item.strip() for item in normalized):
            raise ValidationFailedError("Embedding batch must contain non-empty texts.")
        return self._embedTexts(normalized, model, context)

    def countTokens(self, *, text: str, model: str = "", **kwargs: Any) -> int:
        if not isinstance(text, str):
            raise ValidationFailedError("Token counting text must be a string.")
        return estimateTokenCount(text)

    def healthCheck(self, *, model: str = "", **kwargs: Any) -> ProviderHealth:
        url = self.healthUrl()
        if not url or not self.supportsHealthEndpoint:
            return ProviderHealth(
                status="UNKNOWN",
                detail="no health endpoint configured",
            )
        started = time.monotonic()
        try:
            response = self.transport.request(
                "GET",
                url,
                headers=self.authHeaders(),
                timeoutSeconds=min(self.timeoutSeconds, HEALTH_TIMEOUT_SECONDS),
            )
        except HTTPError as exc:
            return ProviderHealth(
                status="DEGRADED",
                latencyMs=int((time.monotonic() - started) * 1000),
                detail=f"health probe returned HTTP {exc.code}",
            )
        except Exception as exc:  # noqa: BLE001 — health never raises
            detail = sanitizeText(str(exc) or exc.__class__.__name__, self.secrets())
            return ProviderHealth(
                status="UNAVAILABLE",
                latencyMs=int((time.monotonic() - started) * 1000),
                detail=f"health probe failed: {detail[:200]}",
            )
        latencyMs = int((time.monotonic() - started) * 1000)
        if response.ok:
            return ProviderHealth(
                status="HEALTHY", latencyMs=latencyMs, detail="endpoint reachable"
            )
        return ProviderHealth(
            status="DEGRADED",
            latencyMs=latencyMs,
            detail=f"health probe returned HTTP {response.status}",
        )

    # ------------------------------------------------------------------ #
    # Shared helpers
    # ------------------------------------------------------------------ #
    def requestHeaders(self, context: ProviderRequestContext | None) -> dict[str, str]:
        headers = dict(self.authHeaders())
        if context is not None:
            # Trace identifiers are non-sensitive (ADR-016); tenant identity
            # is never propagated to external providers.
            headers[CORRELATION_HEADER] = context.correlationId
            headers[TRACE_HEADER] = context.traceId
        return headers

    def assertSuccess(self, response: HttpResponse, *, model: str) -> None:
        if response.ok:
            return
        payload = parseJsonBody(response.body, providerCode=self.providerCode)
        raise mapHttpError(
            response.status,
            payload,
            providerCode=self.providerCode,
            model=model,
            secrets=self.secrets(),
        )

    def _embedTexts(
        self,
        texts: tuple[str, ...],
        model: str,
        context: ProviderRequestContext | None,
    ) -> list[list[float]]:
        requireProviderFeature(self._capabilities, "EMBEDDING")
        if not model.strip():
            raise ValidationFailedError("Embedding model is required.")
        payload = self.buildEmbeddingPayload(texts, model)
        url = self.embeddingUrl(model)

        def call() -> list[list[float]]:
            response = self.transport.request(
                "POST",
                url,
                payload=payload,
                headers=self.requestHeaders(context),
            )
            self.assertSuccess(response, model=model)
            parsed = parseJsonBody(response.body, providerCode=self.providerCode)
            vectors, _tokens = self.parseEmbeddingPayload(parsed, model)
            if len(vectors) != len(texts):
                raise AIOutputValidationFailed(
                    f"{self.providerCode} returned an unexpected embedding count."
                )
            return [list(validateEmbeddingVector(vector)) for vector in vectors]

        return executeProviderCall(
            call,
            providerCode=self.providerCode,
            model=model,
            secrets=self.secrets(),
        )

    def _mappedChunkIterator(
        self,
        lines: Iterator[str],
        request: GenerationRequest,
    ) -> Iterator[GenerationChunk]:
        """Map stream establishment and mid-stream failures to domain errors."""

        iterator = self.iterStreamChunks(lines, request)
        while True:
            try:
                chunk = next(iterator)
            except StopIteration:
                return
            except (
                AIOutputValidationFailed,
                AIProviderUnavailable,
            ):
                raise
            except Exception as exc:  # noqa: BLE001 — boundary mapping
                raise mapTransportError(
                    exc,
                    providerCode=self.providerCode,
                    secrets=self.secrets(),
                ) from exc
            yield chunk

    def resultFromPayload(
        self,
        *,
        content: str,
        request: GenerationRequest,
        structuredData: dict[str, Any] | None = None,
        inputTokens: int | None = None,
        outputTokens: int | None = None,
        finishReason: str = "STOP",
    ) -> GenerationResult:
        """Build the normalized result shared by every vendor parser."""

        resolvedStructured: dict[str, Any] = {}
        resolvedContent = content if isinstance(content, str) else ""
        if request.responseFormat == "JSON":
            if structuredData is not None:
                resolvedStructured = structuredData
            else:
                resolvedStructured = self.parseStructuredContent(resolvedContent)
        context = request.context
        return GenerationResult(
            content=resolvedContent if request.responseFormat == "TEXT" else "",
            structuredData=resolvedStructured,
            inputTokens=(
                inputTokens
                if inputTokens is not None
                else estimateTokenCount(request.prompt + request.systemInstruction)
            ),
            outputTokens=(
                outputTokens
                if outputTokens is not None
                else estimateTokenCount(resolvedContent or json.dumps(resolvedStructured))
            ),
            model=request.model,
            provider=self.providerSlug,
            finishReason=finishReason,
            requestId=resolvedRequestId(context),
            correlationId=context.correlationId if context else "",
            traceId=context.traceId if context else "",
        )

    def parseStructuredContent(self, content: str) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError) as exc:
            raise AIOutputValidationFailed(
                f"{self.providerCode} did not return valid JSON output."
            ) from exc
        if not isinstance(parsed, dict):
            raise AIOutputValidationFailed(f"{self.providerCode} JSON output must be an object.")
        return parsed


__all__ = [
    "HttpProviderAdapterBase",
    "estimateTokenCount",
]
