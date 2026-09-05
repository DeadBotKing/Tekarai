"""Anthropic Messages API provider adapter (Phase 13-L).

Anthropic has no embedding surface and no native JSON-schema enforcement,
so its capability handshake advertises generation, streaming, and token
counting only — the feature gate in the adapter base rejects embedding or
structured calls with a stable validation error instead of a vendor error.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from apps.ai.domain.exceptions import AIOutputValidationFailed, AIProviderUnavailable
from apps.ai.domain.ports import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
    resolvedRequestId,
)
from apps.ai.infrastructure.providers.providerAdapterBase import HttpProviderAdapterBase

DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 1024

STOP_REASON_MAP = {
    "end_turn": "STOP",
    "stop_sequence": "STOP",
    "max_tokens": "LENGTH",
    "tool_use": "TOOL_CALL",
}


class AnthropicProviderAdapter(HttpProviderAdapterBase):
    providerCode = "ANTHROPIC"
    providerSlug = "anthropic"

    def __init__(
        self,
        *,
        baseUrl: str = DEFAULT_ANTHROPIC_BASE_URL,
        apiKey: str = "",
        anthropicVersion: str = DEFAULT_ANTHROPIC_VERSION,
        timeoutSeconds: float = 30.0,
        transport: Any = None,
    ) -> None:
        if not apiKey.strip():
            raise AIProviderUnavailable("Anthropic adapter requires an API key.")
        self.anthropicVersion = anthropicVersion.strip() or DEFAULT_ANTHROPIC_VERSION
        super().__init__(
            baseUrl=baseUrl,
            apiKey=apiKey.strip(),
            timeoutSeconds=timeoutSeconds,
            transport=transport,
        )

    def buildCapabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            providerCode=self.providerCode,
            features=frozenset({"GENERATION", "STREAMING", "TOKEN_COUNTING"}),
            supportsTemperature=True,
            supportsJsonSchema=False,
            supportsBatchEmbedding=False,
        )

    def authHeaders(self) -> dict[str, str]:
        return {
            "x-api-key": self.apiKey,
            "anthropic-version": self.anthropicVersion,
        }

    def generationUrl(self, model: str) -> str:
        return f"{self.baseUrl}/v1/messages"

    def embeddingUrl(self, model: str) -> str:
        return ""

    def healthUrl(self) -> str:
        return f"{self.baseUrl}/v1/models"

    def buildGenerationPayload(self, request: GenerationRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.maxTokens or DEFAULT_MAX_TOKENS,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
        }
        if request.systemInstruction.strip():
            payload["system"] = request.systemInstruction
        if request.stopSequences:
            payload["stop_sequences"] = list(request.stopSequences)
        return payload

    def parseGenerationPayload(self, payload: Any, request: GenerationRequest) -> GenerationResult:
        if not isinstance(payload, dict):
            raise AIOutputValidationFailed("Anthropic returned an unexpected response shape.")
        blocks = payload.get("content")
        content = ""
        if isinstance(blocks, list):
            content = "".join(
                str(block.get("text", ""))
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )
        stopReason = str(payload.get("stop_reason") or "").lower()
        usageRaw = payload.get("usage")
        usage = usageRaw if isinstance(usageRaw, dict) else {}
        inputTokens = usage.get("input_tokens")
        outputTokens = usage.get("output_tokens")
        return self.resultFromPayload(
            content=content,
            request=request,
            inputTokens=int(inputTokens) if isinstance(inputTokens, int) else None,
            outputTokens=int(outputTokens) if isinstance(outputTokens, int) else None,
            finishReason=STOP_REASON_MAP.get(stopReason, "UNKNOWN"),
        )

    def buildEmbeddingPayload(self, texts: tuple[str, ...], model: str) -> dict[str, Any]:
        raise AIOutputValidationFailed("Anthropic does not provide embeddings.")

    def parseEmbeddingPayload(self, payload: Any, model: str) -> tuple[list[list[float]], int]:
        raise AIOutputValidationFailed("Anthropic does not provide embeddings.")

    def iterStreamChunks(
        self,
        lines: Iterator[str],
        request: GenerationRequest,
    ) -> Iterator[GenerationChunk]:
        context = request.context
        index = 0
        emitted = False
        finalFinishReason = "UNKNOWN"
        for line in lines:
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            try:
                event = json.loads(data)
            except ValueError as exc:
                raise AIOutputValidationFailed(
                    "Anthropic stream delivered an invalid event."
                ) from exc
            if not isinstance(event, dict):
                continue
            eventType = event.get("type")
            if eventType == "content_block_delta":
                delta = event.get("delta") or {}
                content = delta.get("text") if isinstance(delta, dict) else ""
                if content:
                    emitted = True
                    yield GenerationChunk(
                        content=str(content),
                        index=index,
                        isFinal=False,
                        finishReason="UNKNOWN",
                        model=request.model,
                        provider=self.providerSlug,
                        requestId=resolvedRequestId(context),
                        correlationId=context.correlationId if context else "",
                        traceId=context.traceId if context else "",
                    )
                    index += 1
            elif eventType == "message_delta":
                delta = event.get("delta")
                stopReason = delta.get("stop_reason") if isinstance(delta, dict) else None
                if stopReason:
                    finalFinishReason = STOP_REASON_MAP.get(str(stopReason).lower(), "UNKNOWN")
            elif eventType == "message_stop":
                break
        yield GenerationChunk(
            content="",
            index=index,
            isFinal=True,
            finishReason=finalFinishReason if emitted else "STOP",
            model=request.model,
            provider=self.providerSlug,
            requestId=resolvedRequestId(context),
            correlationId=context.correlationId if context else "",
            traceId=context.traceId if context else "",
        )


__all__ = [
    "AnthropicProviderAdapter",
    "DEFAULT_ANTHROPIC_BASE_URL",
    "DEFAULT_ANTHROPIC_VERSION",
]
