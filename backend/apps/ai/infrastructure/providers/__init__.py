"""Provider adapters for the Phase 13 AI platform (Phase 13-L).

Every adapter implements the provider-neutral ``AIProviderPort`` contract
(Phase 13-C) and maps vendor failures to the stable AI domain error surface
(Phase 13-B). Vendor knowledge lives exclusively in this package — the
domain and application layers never import it directly; they receive
adapters through the Phase 13-D ``ProviderRegistry`` or the factory.
"""

from apps.ai.domain.ports import DeterministicAIProvider
from apps.ai.infrastructure.providers.anthropicProvider import AnthropicProviderAdapter
from apps.ai.infrastructure.providers.azureOpenAiProvider import AzureOpenAiProviderAdapter
from apps.ai.infrastructure.providers.localProvider import LocalProviderAdapter
from apps.ai.infrastructure.providers.ollamaProvider import OllamaProviderAdapter
from apps.ai.infrastructure.providers.openAiProvider import OpenAiProviderAdapter
from apps.ai.infrastructure.providers.providerAdapterBase import (
    HttpProviderAdapterBase,
    estimateTokenCount,
)
from apps.ai.infrastructure.providers.providerErrors import (
    executeProviderCall,
    mapHttpError,
    mapTransportError,
)
from apps.ai.infrastructure.providers.providerFactory import (
    PROVIDER_ADAPTER_TYPES,
    ProviderAdapterConfig,
    adapterIsConfigured,
    adapterRequiresCredentials,
    buildProviderAdapter,
)
from apps.ai.infrastructure.providers.providerHttp import HttpResponse, UrllibJsonTransport
from apps.ai.infrastructure.providers.providerWiring import (
    buildConfiguredProviderAdapters,
    providerConfigFromSettings,
    readProviderAdapterSettings,
)

__all__ = [
    "PROVIDER_ADAPTER_TYPES",
    "AnthropicProviderAdapter",
    "DeterministicAIProvider",
    "AzureOpenAiProviderAdapter",
    "HttpProviderAdapterBase",
    "HttpResponse",
    "LocalProviderAdapter",
    "OllamaProviderAdapter",
    "OpenAiProviderAdapter",
    "ProviderAdapterConfig",
    "UrllibJsonTransport",
    "adapterIsConfigured",
    "adapterRequiresCredentials",
    "buildConfiguredProviderAdapters",
    "buildProviderAdapter",
    "estimateTokenCount",
    "executeProviderCall",
    "mapHttpError",
    "mapTransportError",
    "providerConfigFromSettings",
    "readProviderAdapterSettings",
]
