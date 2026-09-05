"""Django-aware composition wiring for provider adapters (Phase 13-L).

Adapters themselves are framework-free (constructor injection). This module
is the single place allowed to read Django settings and hand concrete values
to the factory — keeping the dependency direction intact: infrastructure
implements the ports defined by the domain, and configuration stays
environment-driven (ADR-009).

``settings.AI_PROVIDER_ADAPTERS`` maps a provider type to its resolved
configuration values. Unconfigured entries (empty credentials/URL where the
type requires them) are skipped, never guessed — an operator enables a
provider by supplying environment values, and nothing else changes.
"""

from __future__ import annotations

from typing import Any

from apps.ai.domain.ports import AIProviderPort
from apps.ai.infrastructure.providers.providerFactory import (
    ProviderAdapterConfig,
    adapterIsConfigured,
    buildProviderAdapter,
)


def readProviderAdapterSettings(settingsModule: Any = None) -> dict[str, dict[str, Any]]:
    """Return the configured ``AI_PROVIDER_ADAPTERS`` mapping (never None)."""

    if settingsModule is None:
        from django.conf import settings as djangoSettings

        settingsModule = djangoSettings
    mapping = getattr(settingsModule, "AI_PROVIDER_ADAPTERS", {})
    return dict(mapping) if isinstance(mapping, dict) else {}


def providerConfigFromSettings(
    providerType: str,
    values: dict[str, Any],
) -> ProviderAdapterConfig:
    """Build a factory config from raw settings values with safe extraction."""

    return ProviderAdapterConfig(
        providerType=providerType,
        baseUrl=str(values.get("baseUrl", "") or ""),
        apiKey=str(values.get("apiKey", "") or ""),
        apiVersion=str(values.get("apiVersion", "") or ""),
        anthropicVersion=str(values.get("anthropicVersion", "") or ""),
        timeoutSeconds=float(values.get("timeoutSeconds", 30.0) or 30.0),
        supportsEmbedding=bool(values.get("supportsEmbedding", False)),
        transport=values.get("transport"),
    )


def buildConfiguredProviderAdapters(settingsModule: Any = None) -> dict[str, AIProviderPort]:
    """Instantiate every provider adapter whose configuration is complete.

    Returns a mapping of provider type to adapter. Providers without
    complete configuration are omitted (fail-closed, no guessing); callers
    register the result into the Phase 13-D ``ProviderRegistry``.
    """

    adapters: dict[str, AIProviderPort] = {}
    for providerType, values in readProviderAdapterSettings(settingsModule).items():
        config = providerConfigFromSettings(
            providerType, values if isinstance(values, dict) else {}
        )
        if not adapterIsConfigured(config):
            continue
        adapters[str(providerType).strip().upper()] = buildProviderAdapter(config)
    return adapters


__all__ = [
    "buildConfiguredProviderAdapters",
    "providerConfigFromSettings",
    "readProviderAdapterSettings",
]
