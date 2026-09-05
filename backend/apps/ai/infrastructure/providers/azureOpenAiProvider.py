"""Azure OpenAI provider adapter (Phase 13-L).

Azure deploys models as named deployments addressed in the URL path with an
``api-version`` query parameter, and authenticates through the ``api-key``
header instead of a bearer token. Everything else mirrors the OpenAI wire
contract, so this adapter extends the OpenAI adapter only for the deltas —
Master Specification §23 lists Azure OpenAI as a first-class adapter.
"""

from __future__ import annotations

from typing import Any

from apps.ai.domain.ports import ProviderCapabilities
from apps.ai.infrastructure.providers.openAiProvider import OpenAiProviderAdapter
from apps.sharedKernel.domain.errors import ValidationFailedError

DEFAULT_AZURE_API_VERSION = "2024-10-21"


class AzureOpenAiProviderAdapter(OpenAiProviderAdapter):
    providerCode = "AZURE_OPENAI"
    providerSlug = "azure-openai"

    def __init__(
        self,
        *,
        baseUrl: str,
        apiKey: str = "",
        apiVersion: str = DEFAULT_AZURE_API_VERSION,
        timeoutSeconds: float = 30.0,
        transport: Any = None,
    ) -> None:
        if not apiVersion.strip():
            raise ValidationFailedError("Azure OpenAI adapter requires an apiVersion.")
        self.apiVersion = apiVersion.strip()
        super().__init__(
            baseUrl=baseUrl,
            apiKey=apiKey,
            timeoutSeconds=timeoutSeconds,
            transport=transport,
        )

    def buildCapabilities(self) -> ProviderCapabilities:
        capabilities = super().buildCapabilities()
        return ProviderCapabilities(
            providerCode=self.providerCode,
            features=capabilities.features,
            maxContextWindow=capabilities.maxContextWindow,
            supportsTemperature=capabilities.supportsTemperature,
            supportsJsonSchema=capabilities.supportsJsonSchema,
            supportsBatchEmbedding=capabilities.supportsBatchEmbedding,
        )

    def authHeaders(self) -> dict[str, str]:
        return {"api-key": self.apiKey}

    def generationUrl(self, model: str) -> str:
        return (
            f"{self.baseUrl}/openai/deployments/{model}/chat/completions"
            f"?api-version={self.apiVersion}"
        )

    def embeddingUrl(self, model: str) -> str:
        return f"{self.baseUrl}/openai/deployments/{model}/embeddings?api-version={self.apiVersion}"

    def healthUrl(self) -> str:
        return f"{self.baseUrl}/openai/models?api-version={self.apiVersion}"


__all__ = [
    "AzureOpenAiProviderAdapter",
    "DEFAULT_AZURE_API_VERSION",
]
