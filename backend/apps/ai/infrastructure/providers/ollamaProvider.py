"""Ollama provider adapter (Phase 13-L).

Ollama is the offline/local runtime path required by Master Specification
principle 17 ("AI باید بتواند Offline/Local Provider داشته باشد"). It needs
no API key, answers chat requests at ``/api/chat`` (NDJSON streaming when
``stream=true``), and embeddings at ``/api/embed``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from apps.ai.domain.exceptions import AIOutputValidationFailed
from apps.ai.domain.ports import (
    GenerationChunk,
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
    resolvedRequestId,
)
from apps.ai.infrastructure.providers.providerAdapterBase import HttpProviderAdapterBase

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"

DONE_REASON_MAP = {
    "stop": "STOP",
    "length": "LENGTH",
    "tool_calls": "TOOL_CALL",
}


class OllamaProviderAdapter(HttpProviderAdapterBase):
    providerCode = "OLLAMA"
    providerSlug = "ollama"

    def __init__(
        self,
        *,
        baseUrl: str = DEFAULT_OLLAMA_BASE_URL,
        apiKey: str = "",
        timeoutSeconds: float = 30.0,
        transport: Any = None,
    ) -> None:
        super().__init__(
            baseUrl=baseUrl or DEFAULT_OLLAMA_BASE_URL,
            apiKey=apiKey,
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
            supportsJsonSchema=False,
            supportsBatchEmbedding=True,
        )

    def authHeaders(self) -> dict[str, str]:
        # Local runtime: a key is optional and only forwarded when configured.
        return {"Authorization": f"Bearer {self.apiKey}"} if self.apiKey else {}

    def generationUrl(self, model: str) -> str:
        return f"{self.baseUrl}/api/chat"

    def embeddingUrl(self, model: str) -> str:
        return f"{self.baseUrl}/api/embed"

    def healthUrl(self) -> str:
        return f"{self.baseUrl}/api/tags"

    def buildGenerationPayload(self, request: GenerationRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.systemInstruction.strip():
            messages.append({"role": "system", "content": request.systemInstruction})
        messages.append({"role": "user", "content": request.prompt})
        options: dict[str, Any] = {"temperature": request.temperature}
        if request.maxTokens is not None:
            options["num_predict"] = request.maxTokens
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if request.responseFormat == "JSON":
            payload["format"] = "json"
        return payload

    def parseGenerationPayload(self, payload: Any, request: GenerationRequest) -> GenerationResult:
        if not isinstance(payload, dict):
            raise AIOutputValidationFailed("Ollama returned an unexpected response shape.")
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else ""
        doneReason = str(payload.get("done_reason") or "").lower()
        finishReason = DONE_REASON_MAP.get(doneReason, "STOP" if payload.get("done") else "UNKNOWN")
        inputTokens = payload.get("prompt_eval_count")
        outputTokens = payload.get("eval_count")
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
        if not isinstance(payload, dict) or not isinstance(payload.get("embeddings"), list):
            raise AIOutputValidationFailed("Ollama embedding response is invalid.")
        vectors: list[list[float]] = []
        for item in payload["embeddings"]:
            if not isinstance(item, list):
                raise AIOutputValidationFailed("Ollama embedding entry is invalid.")
            vectors.append([float(value) for value in item])
        return vectors, 0

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
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError as exc:
                raise AIOutputValidationFailed("Ollama stream delivered an invalid event.") from exc
            if not isinstance(event, dict):
                continue
            message = event.get("message") or {}
            content = message.get("content") if isinstance(message, dict) else ""
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
            if event.get("done"):
                doneReason = str(event.get("done_reason") or "").lower()
                finalFinishReason = DONE_REASON_MAP.get(doneReason, "STOP")
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
    "DEFAULT_OLLAMA_BASE_URL",
    "OllamaProviderAdapter",
]
