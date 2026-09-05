"""OpenAI (and OpenAI-compatible) provider adapter (Phase 13-L).

Vendor knowledge is confined to this module: chat-completion payloads,
embedding payloads, SSE streaming frames, and finish-reason vocabulary.
Everything crosses the Phase 13-C contract only — no OpenAI object ever
reaches application or domain code.
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

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

FINISH_REASON_MAP = {
    "stop": "STOP",
    "length": "LENGTH",
    "tool_calls": "TOOL_CALL",
    "content_filter": "CONTENT_FILTER",
}


class OpenAiProviderAdapter(HttpProviderAdapterBase):
    providerCode = "OPENAI"
    providerSlug = "openai"

    def __init__(
        self,
        *,
        baseUrl: str = DEFAULT_OPENAI_BASE_URL,
        apiKey: str = "",
        timeoutSeconds: float = 30.0,
        transport: Any = None,
    ) -> None:
        if not apiKey.strip():
            raise AIProviderUnavailable("OpenAI adapter requires an API key.")
        super().__init__(
            baseUrl=baseUrl,
            apiKey=apiKey.strip(),
            timeoutSeconds=timeoutSeconds,
            transport=transport,
        )

    def buildCapabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            providerCode=self.providerCode,
            features=frozenset(
                {
                    "GENERATION",
                    "STRUCTURED_GENERATION",
                    "STREAMING",
                    "EMBEDDING",
                    "TOKEN_COUNTING",
                }
            ),
            supportsTemperature=True,
            supportsJsonSchema=True,
            supportsBatchEmbedding=True,
        )

    def authHeaders(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.apiKey}"}

    def generationUrl(self, model: str) -> str:
        return f"{self.baseUrl}/chat/completions"

    def embeddingUrl(self, model: str) -> str:
        return f"{self.baseUrl}/embeddings"

    def healthUrl(self) -> str:
        return f"{self.baseUrl}/models"

    def buildGenerationPayload(self, request: GenerationRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.systemInstruction.strip():
            messages.append({"role": "system", "content": request.systemInstruction})
        messages.append({"role": "user", "content": request.prompt})
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.maxTokens is not None:
            payload["max_tokens"] = request.maxTokens
        if request.stopSequences:
            payload["stop"] = list(request.stopSequences)
        if request.responseFormat == "JSON":
            payload["response_format"] = self._responseFormat(request)
        return payload

    def _responseFormat(self, request: GenerationRequest) -> dict[str, Any]:
        if request.jsonSchema:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "structuredOutput",
                    "schema": request.jsonSchema,
                    "strict": True,
                },
            }
        return {"type": "json_object"}

    def parseGenerationPayload(self, payload: Any, request: GenerationRequest) -> GenerationResult:
        if not isinstance(payload, dict):
            raise AIOutputValidationFailed("OpenAI returned an unexpected response shape.")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise AIOutputValidationFailed("OpenAI response has no choices.")
        message = choices[0].get("message") or {}
        content = message.get("content") if isinstance(message, dict) else ""
        finishReason = FINISH_REASON_MAP.get(
            str(choices[0].get("finish_reason") or "").lower(),
            "UNKNOWN",
        )
        usageRaw = payload.get("usage")
        usage = usageRaw if isinstance(usageRaw, dict) else {}
        inputTokens = usage.get("prompt_tokens")
        outputTokens = usage.get("completion_tokens")
        return self.resultFromPayload(
            content=str(content or ""),
            request=request,
            inputTokens=int(inputTokens) if isinstance(inputTokens, int) else None,
            outputTokens=int(outputTokens) if isinstance(outputTokens, int) else None,
            finishReason=finishReason,
        )

    def buildEmbeddingPayload(self, texts: tuple[str, ...], model: str) -> dict[str, Any]:
        return {"model": model, "input": list(texts)}

    def parseEmbeddingPayload(self, payload: Any, model: str) -> tuple[list[list[float]], int]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise AIOutputValidationFailed("OpenAI embedding response is invalid.")
        vectors: list[list[float]] = []
        for item in payload["data"]:
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise AIOutputValidationFailed("OpenAI embedding entry is invalid.")
            vectors.append([float(value) for value in item["embedding"]])
        usageRaw = payload.get("usage")
        usage = usageRaw if isinstance(usageRaw, dict) else {}
        tokens = usage.get("prompt_tokens")
        return vectors, int(tokens) if isinstance(tokens, int) else 0

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
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except ValueError as exc:
                raise AIOutputValidationFailed("OpenAI stream delivered an invalid event.") from exc
            choices = event.get("choices") if isinstance(event, dict) else None
            if not isinstance(choices, list) or not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content") if isinstance(delta, dict) else None
            finish = choices[0].get("finish_reason")
            if finish:
                finalFinishReason = FINISH_REASON_MAP.get(str(finish).lower(), "UNKNOWN")
            if content is None and not finish:
                continue
            emitted = True
            yield GenerationChunk(
                content=str(content or ""),
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
    "DEFAULT_OPENAI_BASE_URL",
    "OpenAiProviderAdapter",
]
