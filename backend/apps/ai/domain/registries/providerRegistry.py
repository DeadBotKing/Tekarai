"""Tenant-scoped Provider Registry for Phase 13-D.

The registry owns runtime adapter registration and resolution only. It does not
choose a model, route a request, persist data, call a provider, or resolve a
Secret. Those responsibilities belong to later phases or infrastructure.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Iterable

from apps.ai.domain.entities.aiRecords import AIProvider, requireUuid
from apps.ai.domain.exceptions import (
    AIProviderAlreadyRegistered,
    AIProviderInactive,
    AIProviderNotRegistered,
    AIProviderRegistrationInvalid,
    AIProviderUnavailable,
)
from apps.ai.domain.ports import AIProviderPort, ProviderCapabilities, ProviderHealth


def utcNow() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(frozen=True)
class ProviderDescriptor:
    """Non-sensitive read model exposed by registry inspection."""

    tenantId: uuid.UUID
    providerId: uuid.UUID
    code: str
    name: str
    providerType: str
    isActive: bool
    capabilities: ProviderCapabilities
    registeredAt: datetime


@dataclass
class ProviderRegistration:
    """Runtime registration binding one tenant provider to one adapter."""

    provider: AIProvider
    adapter: AIProviderPort = field(repr=False)
    registeredAt: datetime = field(default_factory=utcNow)

    @property
    def tenantId(self) -> uuid.UUID:
        return self.provider.tenantId

    @property
    def providerCode(self) -> str:
        return self.provider.code

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self.adapter.capabilities

    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            tenantId=self.provider.tenantId,
            providerId=self.provider.id,
            code=self.provider.code,
            name=self.provider.name,
            providerType=self.provider.providerType,
            isActive=self.provider.isActive,
            capabilities=self.capabilities,
            registeredAt=self.registeredAt,
        )


class ProviderRegistry:
    """In-memory registry boundary for provider definitions and adapters.

    Persistence and distributed consistency are deliberately not hidden here.
    D supplies deterministic behaviour for one process; a repository-backed
    implementation can replace the storage mechanism in a later phase while
    keeping this public contract.
    """

    def __init__(self, registrations: Iterable[ProviderRegistration] = ()) -> None:
        self._registrations: dict[tuple[uuid.UUID, str], ProviderRegistration] = {}
        for registration in registrations:
            self.registerProvider(registration.provider, registration.adapter, registeredAt=registration.registeredAt)

    def registerProvider(
        self,
        provider: AIProvider,
        adapter: AIProviderPort,
        *,
        replace: bool = False,
        registeredAt: datetime | None = None,
    ) -> ProviderRegistration:
        self._validateRegistration(provider, adapter)
        key = self._key(provider.tenantId, provider.code)
        if key in self._registrations and not replace:
            raise AIProviderAlreadyRegistered(provider.code)
        registration = ProviderRegistration(
            provider=provider,
            adapter=adapter,
            registeredAt=registeredAt or utcNow(),
        )
        self._registrations[key] = registration
        return registration

    def register(
        self,
        provider: AIProvider,
        adapter: AIProviderPort,
        *,
        replace: bool = False,
    ) -> ProviderRegistration:
        """Short alias for application composition roots."""

        return self.registerProvider(provider, adapter, replace=replace)

    def resolveProvider(self, tenantId: uuid.UUID | str, providerCode: str) -> AIProviderPort:
        registration = self.getRegistration(tenantId, providerCode)
        if not registration.provider.isActive:
            raise AIProviderInactive(registration.provider.code)
        return registration.adapter

    def resolve(self, tenantId: uuid.UUID | str, providerCode: str) -> AIProviderPort:
        return self.resolveProvider(tenantId, providerCode)

    def getRegistration(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        *,
        includeInactive: bool = True,
    ) -> ProviderRegistration:
        key = self._key(tenantId, providerCode)
        registration = self._registrations.get(key)
        if registration is None:
            raise AIProviderNotRegistered(providerCode)
        if not includeInactive and not registration.provider.isActive:
            raise AIProviderNotRegistered(providerCode)
        return registration

    def describeProvider(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        *,
        includeInactive: bool = True,
    ) -> ProviderDescriptor:
        return self.getRegistration(
            tenantId,
            providerCode,
            includeInactive=includeInactive,
        ).descriptor()

    def listProviders(
        self,
        tenantId: uuid.UUID | str,
        *,
        activeOnly: bool = True,
    ) -> tuple[ProviderDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        descriptors = [
            registration.descriptor()
            for (registrationTenant, _), registration in self._registrations.items()
            if registrationTenant == tenant and (not activeOnly or registration.provider.isActive)
        ]
        return tuple(sorted(descriptors, key=lambda descriptor: descriptor.code))

    def activateProvider(self, tenantId: uuid.UUID | str, providerCode: str) -> ProviderDescriptor:
        registration = self.getRegistration(tenantId, providerCode)
        registration.provider.isActive = True
        return registration.descriptor()

    def deactivateProvider(self, tenantId: uuid.UUID | str, providerCode: str) -> ProviderDescriptor:
        registration = self.getRegistration(tenantId, providerCode)
        registration.provider.isActive = False
        return registration.descriptor()

    def supports(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        feature: str,
    ) -> bool:
        return self.resolveProvider(tenantId, providerCode).capabilities.supports(feature)

    def healthCheck(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        *,
        model: str = "",
    ) -> ProviderHealth:
        adapter = self.resolveProvider(tenantId, providerCode)
        try:
            health = adapter.healthCheck(model=model)
            if not isinstance(health, ProviderHealth):
                raise TypeError("Adapter returned an invalid health snapshot.")
            return health
        except AIProviderUnavailable:
            raise
        except Exception as exc:
            raise AIProviderUnavailable(providerCode) from exc

    def unregisterProvider(self, tenantId: uuid.UUID | str, providerCode: str) -> None:
        key = self._key(tenantId, providerCode)
        if key not in self._registrations:
            raise AIProviderNotRegistered(providerCode)
        del self._registrations[key]

    def unregister(self, tenantId: uuid.UUID | str, providerCode: str) -> None:
        self.unregisterProvider(tenantId, providerCode)

    def clear(self) -> None:
        """Test/composition-root helper; no persistence side effect exists in D."""

        self._registrations.clear()

    @staticmethod
    def _key(tenantId: uuid.UUID | str, providerCode: str) -> tuple[uuid.UUID, str]:
        tenant = requireUuid(tenantId, "tenantId")
        normalizedCode = str(providerCode or "").strip().upper()
        if not normalizedCode:
            raise AIProviderRegistrationInvalid("Provider code is required.")
        return tenant, normalizedCode

    @staticmethod
    def _validateRegistration(provider: AIProvider, adapter: AIProviderPort) -> None:
        if not isinstance(provider, AIProvider):
            raise AIProviderRegistrationInvalid("Provider definition is invalid.")
        if not isinstance(adapter, AIProviderPort):
            raise AIProviderRegistrationInvalid("Adapter does not implement AIProviderPort.")
        providerCode = str(getattr(adapter, "providerCode", "")).strip().upper()
        capabilities = getattr(adapter, "capabilities", None)
        if providerCode != provider.code:
            raise AIProviderRegistrationInvalid(
                "Provider definition and adapter provider codes must match."
            )
        if not isinstance(capabilities, ProviderCapabilities):
            raise AIProviderRegistrationInvalid("Adapter capabilities are invalid.")
        if capabilities.providerCode != provider.code:
            raise AIProviderRegistrationInvalid(
                "Provider definition and capability provider codes must match."
            )


AIProviderRegistry = ProviderRegistry
InMemoryProviderRegistry = ProviderRegistry
RegisteredProvider = ProviderRegistration

__all__ = [
    "AIProviderRegistry",
    "InMemoryProviderRegistry",
    "ProviderDescriptor",
    "ProviderRegistration",
    "ProviderRegistry",
    "RegisteredProvider",
]
