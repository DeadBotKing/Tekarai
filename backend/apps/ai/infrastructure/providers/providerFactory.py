"""Configuration-driven provider adapter factory (Phase 13-L).

Master Specification §42 requires provider selection to be configuration-
driven and forbids hard-coded vendor wiring. This factory is the single
place that knows which adapter class implements which provider type; the
composition root (``providerWiring``) feeds it values resolved from the
environment, and tests feed it explicit values plus a fake transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.ai.domain.exceptions import AIProviderUnavailable
from apps.ai.domain.ports import AIProviderPort, DeterministicAIProvider
from apps.ai.infrastructure.providers.anthropicProvider import (
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_ANTHROPIC_VERSION,
    AnthropicProviderAdapter,
)
from apps.ai.infrastructure.providers.azureOpenAiProvider import (
    DEFAULT_AZURE_API_VERSION,
    AzureOpenAiProviderAdapter,
)
from apps.ai.infrastructure.providers.localProvider import LocalProviderAdapter
from apps.ai.infrastructure.providers.ollamaProvider import (
    DEFAULT_OLLAMA_BASE_URL,
    OllamaProviderAdapter,
)
from apps.ai.infrastructure.providers.openAiProvider import (
    DEFAULT_OPENAI_BASE_URL,
    OpenAiProviderAdapter,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

PROVIDER_ADAPTER_TYPES = (
    "OPENAI",
    "AZURE_OPENAI",
    "OLLAMA",
    "ANTHROPIC",
    "LOCAL",
    "DETERMINISTIC",
)


@dataclass(frozen=True)
class ProviderAdapterConfig:
    """Framework-free adapter configuration; secrets enter here only.

    The configuration object never travels through the provider request
    context (C §8 rule 4) — adapters receive their credentials at
    construction time and redact them from every surfaced message.
    """

    providerType: str
    baseUrl: str = ""
    apiKey: str = ""
    apiVersion: str = ""
    anthropicVersion: str = DEFAULT_ANTHROPIC_VERSION
    timeoutSeconds: float = 30.0
    supportsEmbedding: bool = False
    transport: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


def buildProviderAdapter(config: ProviderAdapterConfig) -> AIProviderPort:
    """Instantiate the adapter matching ``config.providerType`` (fail-closed)."""

    providerType = str(config.providerType or "").strip().upper()
    if providerType == "DETERMINISTIC":
        return DeterministicAIProvider()
    if providerType == "OPENAI":
        return OpenAiProviderAdapter(
            baseUrl=config.baseUrl or DEFAULT_OPENAI_BASE_URL,
            apiKey=config.apiKey,
            timeoutSeconds=config.timeoutSeconds,
            transport=config.transport,
        )
    if providerType == "AZURE_OPENAI":
        if not config.baseUrl.strip():
            raise AIProviderUnavailable("Azure OpenAI adapter requires a resource base URL.")
        return AzureOpenAiProviderAdapter(
            baseUrl=config.baseUrl,
            apiKey=config.apiKey,
            apiVersion=config.apiVersion or DEFAULT_AZURE_API_VERSION,
            timeoutSeconds=config.timeoutSeconds,
            transport=config.transport,
        )
    if providerType == "OLLAMA":
        return OllamaProviderAdapter(
            baseUrl=config.baseUrl or DEFAULT_OLLAMA_BASE_URL,
            apiKey=config.apiKey,
            timeoutSeconds=config.timeoutSeconds,
            transport=config.transport,
        )
    if providerType == "ANTHROPIC":
        return AnthropicProviderAdapter(
            baseUrl=config.baseUrl or DEFAULT_ANTHROPIC_BASE_URL,
            apiKey=config.apiKey,
            anthropicVersion=config.anthropicVersion or DEFAULT_ANTHROPIC_VERSION,
            timeoutSeconds=config.timeoutSeconds,
            transport=config.transport,
        )
    if providerType == "LOCAL":
        if not config.baseUrl.strip():
            raise AIProviderUnavailable("Local adapter requires a base URL.")
        return LocalProviderAdapter(
            baseUrl=config.baseUrl,
            apiKey=config.apiKey,
            supportsEmbedding=config.supportsEmbedding,
            timeoutSeconds=config.timeoutSeconds,
            transport=config.transport,
        )
    raise ValidationFailedError(
        f"Unknown provider adapter type '{providerType}'. "
        f"Supported types: {', '.join(PROVIDER_ADAPTER_TYPES)}."
    )


def adapterRequiresCredentials(providerType: str) -> bool:
    """Whether the adapter type needs an API key to be constructible."""

    return str(providerType or "").strip().upper() in {"OPENAI", "AZURE_OPENAI", "ANTHROPIC"}


def adapterIsConfigured(config: ProviderAdapterConfig) -> bool:
    """Whether the configuration carries everything the adapter needs."""

    providerType = str(config.providerType or "").strip().upper()
    if providerType in {"OPENAI", "ANTHROPIC"}:
        return bool(config.apiKey.strip())
    if providerType == "AZURE_OPENAI":
        return bool(config.apiKey.strip()) and bool(config.baseUrl.strip())
    if providerType == "LOCAL":
        return bool(config.baseUrl.strip())
    return providerType in {"OLLAMA", "DETERMINISTIC"}


__all__ = [
    "PROVIDER_ADAPTER_TYPES",
    "ProviderAdapterConfig",
    "adapterIsConfigured",
    "adapterRequiresCredentials",
    "buildProviderAdapter",
]
