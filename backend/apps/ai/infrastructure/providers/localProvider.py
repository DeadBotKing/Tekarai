"""Local / custom enterprise model provider adapter (Phase 13-L).

Master Specification §23 lists ``LocalProvider`` as a first-class adapter:
a generic JSON endpoint owned by the deployment (an internal inference
server, a fine-tuned enterprise model, or an air-gapped runtime). The wire
contract is deliberately provider-neutral — the same shape the platform
itself uses — so enterprises can expose their own models without adopting
any vendor SDK:

    POST {baseUrl}{invocationPath}
    {
      "model": "...", "prompt": "...", "systemInstruction": "...",
      "temperature": 0.0, "maxTokens": null, "responseFormat": "TEXT"
    }
    ->
    {
      "content": "...", "structuredData": {}, "inputTokens": 0,
      "outputTokens": 0, "finishReason": "STOP"
    }
"""

from __future__ import annotations

from typing import Any

from apps.ai.domain.exceptions import AIOutputValidationFailed
from apps.ai.domain.ports import (
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
)
from apps.ai.infrastructure.providers.providerAdapterBase import HttpProviderAdapterBase

DEFAULT_INVOCATION_PATH = "/invocations"
DEFAULT_EMBEDDING_PATH = "/embeddings"
DEFAULT_HEALTH_PATH = "/health"


class LocalProviderAdapter(HttpProviderAdapterBase):
    providerCode = "LOCAL"
    providerSlug = "local"

    def __init__(
        self,
        *,
        baseUrl: str,
        apiKey: str = "",
        invocationPath: str = DEFAULT_INVOCATION_PATH,
        embeddingPath: str = DEFAULT_EMBEDDING_PATH,
        healthPath: str = DEFAULT_HEALTH_PATH,
        supportsEmbedding: bool = False,
        timeoutSeconds: float = 30.0,
        transport: Any = None,
    ) -> None:
        self.invocationPath = invocationPath or DEFAULT_INVOCATION_PATH
        self.embeddingPath = embeddingPath or DEFAULT_EMBEDDING_PATH
        self.healthPath = healthPath or DEFAULT_HEALTH_PATH
        self.supportsEmbedding = bool(supportsEmbedding)
        super().__init__(
            baseUrl=baseUrl,
            apiKey=apiKey.strip(),
            timeoutSeconds=timeoutSeconds,
            transport=transport,
        )

    def buildCapabilities(self) -> ProviderCapabilities:
        features = {"GENERATION", "STRUCTURED_GENERATION", "TOKEN_COUNTING"}
        if self.supportsEmbedding:
            features.add("EMBEDDING")
        return ProviderCapabilities(
            providerCode=self.providerCode,
            features=frozenset(features),
            supportsTemperature=True,
            supportsJsonSchema=False,
            supportsBatchEmbedding=self.supportsEmbedding,
        )

    def authHeaders(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.apiKey}"} if self.apiKey else {}

    def generationUrl(self, model: str) -> str:
        return f"{self.baseUrl}{self.invocationPath}"

    def embeddingUrl(self, model: str) -> str:
        return f"{self.baseUrl}{self.embeddingPath}"

    def healthUrl(self) -> str:
        return f"{self.baseUrl}{self.healthPath}"

    def buildGenerationPayload(self, request: GenerationRequest) -> dict[str, Any]:
        return {
            "model": request.model,
            "prompt": request.prompt,
            "systemInstruction": request.systemInstruction,
            "temperature": request.temperature,
            "maxTokens": request.maxTokens,
            "responseFormat": request.responseFormat,
            "jsonSchema": request.jsonSchema if request.responseFormat == "JSON" else {},
        }

    def parseGenerationPayload(self, payload: Any, request: GenerationRequest) -> GenerationResult:
        if not isinstance(payload, dict):
            raise AIOutputValidationFailed("Local model returned an unexpected response shape.")
        content = payload.get("content")
        structuredData = payload.get("structuredData")
        if structuredData is not None and not isinstance(structuredData, dict):
            raise AIOutputValidationFailed("Local model structuredData must be an object.")
        inputTokens = payload.get("inputTokens")
        outputTokens = payload.get("outputTokens")
        finishReason = str(payload.get("finishReason") or "STOP")
        return self.resultFromPayload(
            content=str(content or ""),
            request=request,
            structuredData=structuredData,
            inputTokens=int(inputTokens) if isinstance(inputTokens, int) else None,
            outputTokens=int(outputTokens) if isinstance(outputTokens, int) else None,
            finishReason=finishReason,
        )

    def buildEmbeddingPayload(self, texts: tuple[str, ...], model: str) -> dict[str, Any]:
        return {"model": model, "texts": list(texts)}

    def parseEmbeddingPayload(self, payload: Any, model: str) -> tuple[list[list[float]], int]:
        if not isinstance(payload, dict) or not isinstance(payload.get("vectors"), list):
            raise AIOutputValidationFailed("Local model embedding response is invalid.")
        vectors: list[list[float]] = []
        for item in payload["vectors"]:
            if not isinstance(item, list):
                raise AIOutputValidationFailed("Local model embedding entry is invalid.")
            vectors.append([float(value) for value in item])
        return vectors, 0


__all__ = [
    "LocalProviderAdapter",
]
