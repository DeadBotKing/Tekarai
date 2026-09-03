"""Tenant-aware Capability Registry for Phase 13-F.

The Capability Registry owns business-level AI capability definitions such as
summarization or extraction. It is deliberately independent of any provider
vendor. Optional composition with the Phase 13-E ModelRegistry verifies that an
active capability is declared by an active, tenant-owned model before routing.

This module is pure Python: no ORM, persistence, HTTP, queue, network, secret
resolution, provider SDK, retry, or failover execution is allowed here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Iterable

from apps.ai.domain.entities.aiRecords import AICapability, AIModel, requireUuid
from apps.ai.domain.exceptions import (
    AICapabilityAlreadyRegistered,
    AICapabilityInactive,
    AICapabilityModelNotSupported,
    AICapabilityNotRegistered,
    AICapabilityPolicyInvalid,
    AICapabilityRegistrationInvalid,
    AICapabilityRequestTypeUnsupported,
    AICapabilityRoutingNoMatch,
)
from apps.ai.domain.registries.modelRegistry import (
    ModelDescriptor,
    ModelRegistry,
    ModelRoutingPolicy,
    ModelRoutingRequest,
    RoutingDecision,
)
from apps.ai.domain.valueObjects.aiTypes import CAPABILITY_CODES, REQUEST_TYPES, ensureEnum, validateCode


def utcNow() -> datetime:
    return datetime.now(tz=UTC)


def _normalizeCapabilityCode(value: str) -> str:
    try:
        normalized = validateCode(value, "capabilityCode")
    except Exception as exc:
        raise AICapabilityRegistrationInvalid("Capability code is invalid.") from exc
    if normalized not in CAPABILITY_CODES and not normalized.startswith("CUSTOM_"):
        raise AICapabilityRegistrationInvalid(f"Unsupported AI capability: {normalized}.")
    return normalized


def _normalizeRequestType(value: str) -> str:
    try:
        return ensureEnum(value, REQUEST_TYPES, "requestType")
    except Exception as exc:
        raise AICapabilityPolicyInvalid(f"Unsupported AI request type: {value}.") from exc


def _policyRequestTypes(capability: AICapability) -> tuple[str, ...]:
    """Read and validate the non-sensitive request-type allowlist.

    Existing B capabilities with an empty policy retain the B contract and
    accept every known request type. Once ``allowedRequestTypes`` is present,
    its value is an explicit allowlist; an empty tuple intentionally allows no
    request type.
    """

    if not isinstance(capability.policy, dict):
        raise AICapabilityPolicyInvalid("Capability policy must be an object.")
    if "allowedRequestTypes" not in capability.policy:
        return REQUEST_TYPES
    raw = capability.policy["allowedRequestTypes"]
    if not isinstance(raw, (tuple, list, set, frozenset)):
        raise AICapabilityPolicyInvalid("allowedRequestTypes must be a sequence of request types.")
    values = tuple(_normalizeRequestType(value) for value in raw)
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True)
class CapabilityDescriptor:
    """Non-sensitive, immutable Capability read model."""

    tenantId: uuid.UUID
    capabilityId: uuid.UUID
    code: str
    name: str
    description: str
    isActive: bool
    supportedRequestTypes: tuple[str, ...]
    registeredAt: datetime


@dataclass
class CapabilityRegistration:
    """Binding for one Tenant-owned ``AICapability`` definition."""

    capability: AICapability = field(repr=False)
    registeredAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        if not isinstance(self.capability, AICapability):
            raise AICapabilityRegistrationInvalid("Capability definition is invalid.")
        _policyRequestTypes(self.capability)

    @property
    def supportedRequestTypes(self) -> tuple[str, ...]:
        """Read the live policy so post-registration policy changes are not stale."""

        return _policyRequestTypes(self.capability)

    @property
    def tenantId(self) -> uuid.UUID:
        return self.capability.tenantId

    @property
    def capabilityId(self) -> uuid.UUID:
        return self.capability.id

    @property
    def capabilityCode(self) -> str:
        return self.capability.code

    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            tenantId=self.capability.tenantId,
            capabilityId=self.capability.id,
            code=self.capability.code,
            name=self.capability.name,
            description=self.capability.description,
            isActive=self.capability.isActive,
            supportedRequestTypes=self.supportedRequestTypes,
            registeredAt=self.registeredAt,
        )


@dataclass(frozen=True)
class CapabilityRoutingRequest:
    """Capability-first routing constraints composed with ModelRoutingRequest."""

    tenantId: uuid.UUID | str
    capabilityCode: str
    requestType: str = ""
    modelType: str = ""
    requiredFeatures: tuple[str, ...] = ()
    requiresStreaming: bool = False
    requiresTools: bool = False
    requiresVision: bool = False
    requiresEmbeddings: bool = False
    minimumContextWindow: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenantId", requireUuid(self.tenantId, "tenantId"))
        object.__setattr__(self, "capabilityCode", _normalizeCapabilityCode(self.capabilityCode))
        if self.requestType:
            object.__setattr__(self, "requestType", _normalizeRequestType(self.requestType))

    def toModelRoutingRequest(self) -> ModelRoutingRequest:
        return ModelRoutingRequest(
            tenantId=self.tenantId,
            modelType=self.modelType,
            capabilityCode=self.capabilityCode,
            requiredFeatures=self.requiredFeatures,
            requiresStreaming=self.requiresStreaming,
            requiresTools=self.requiresTools,
            requiresVision=self.requiresVision,
            requiresEmbeddings=self.requiresEmbeddings,
            minimumContextWindow=self.minimumContextWindow,
        )


class CapabilityRegistry:
    """In-memory, tenant-scoped registry for business AI capabilities."""

    def __init__(
        self,
        modelRegistry: ModelRegistry | None = None,
        registrations: Iterable[CapabilityRegistration] = (),
    ) -> None:
        if modelRegistry is not None and not isinstance(modelRegistry, ModelRegistry):
            raise AICapabilityRegistrationInvalid("modelRegistry must be a ModelRegistry.")
        self.modelRegistry = modelRegistry
        self._registrations: dict[tuple[uuid.UUID, str], CapabilityRegistration] = {}
        for registration in registrations:
            if not isinstance(registration, CapabilityRegistration):
                raise AICapabilityRegistrationInvalid("Initial capability registrations are invalid.")
            self.registerCapability(
                registration.capability,
                registeredAt=registration.registeredAt,
            )

    def registerCapability(
        self,
        capability: AICapability,
        *,
        replace: bool = False,
        registeredAt: datetime | None = None,
    ) -> CapabilityRegistration:
        if not isinstance(capability, AICapability):
            raise AICapabilityRegistrationInvalid("Capability definition is invalid.")
        # Validate the policy before mutating Registry state.
        supportedRequestTypes = _policyRequestTypes(capability)
        key = self._key(capability.tenantId, capability.code)
        if key in self._registrations and not replace:
            raise AICapabilityAlreadyRegistered(capability.code)
        registration = CapabilityRegistration(
            capability=capability,
            registeredAt=registeredAt or utcNow(),
        )
        if registration.supportedRequestTypes != supportedRequestTypes:
            raise AICapabilityPolicyInvalid("Capability policy changed during registration.")
        self._registrations[key] = registration
        return registration

    def register(
        self,
        capability: AICapability,
        *,
        replace: bool = False,
    ) -> CapabilityRegistration:
        """Short alias for application composition roots."""

        return self.registerCapability(capability, replace=replace)

    def getRegistration(
        self,
        tenantId: uuid.UUID | str,
        capabilityCode: str,
        *,
        includeInactive: bool = True,
    ) -> CapabilityRegistration:
        tenant = requireUuid(tenantId, "tenantId")
        normalizedCode = _normalizeCapabilityCode(capabilityCode)
        registration = self._registrations.get((tenant, normalizedCode))
        if registration is None or (not includeInactive and not registration.capability.isActive):
            raise AICapabilityNotRegistered(normalizedCode)
        return registration

    def getCapabilityRegistration(
        self,
        tenantId: uuid.UUID | str,
        capabilityCode: str,
        *,
        includeInactive: bool = True,
    ) -> CapabilityRegistration:
        return self.getRegistration(tenantId, capabilityCode, includeInactive=includeInactive)

    def resolveCapability(self, tenantId: uuid.UUID | str, capabilityCode: str) -> AICapability:
        registration = self.getRegistration(tenantId, capabilityCode)
        if not registration.capability.isActive:
            raise AICapabilityInactive(registration.capability.code)
        return registration.capability

    def resolve(self, tenantId: uuid.UUID | str, capabilityCode: str) -> AICapability:
        return self.resolveCapability(tenantId, capabilityCode)

    def resolveForRequest(
        self,
        tenantId: uuid.UUID | str,
        capabilityCode: str,
        requestType: str,
    ) -> AICapability:
        registration = self.getRegistration(tenantId, capabilityCode)
        if not registration.capability.isActive:
            raise AICapabilityInactive(registration.capability.code)
        normalizedRequestType = _normalizeRequestType(requestType)
        if normalizedRequestType not in registration.supportedRequestTypes:
            raise AICapabilityRequestTypeUnsupported(
                registration.capability.code,
                normalizedRequestType,
            )
        return registration.capability

    def supportsRequestType(
        self,
        tenantId: uuid.UUID | str,
        capabilityCode: str,
        requestType: str,
    ) -> bool:
        registration = self.getRegistration(tenantId, capabilityCode)
        normalizedRequestType = _normalizeRequestType(requestType)
        return registration.capability.isActive and normalizedRequestType in registration.supportedRequestTypes

    def acceptsRequestType(
        self,
        tenantId: uuid.UUID | str,
        capabilityCode: str,
        requestType: str,
    ) -> bool:
        return self.supportsRequestType(tenantId, capabilityCode, requestType)

    def describeCapability(
        self,
        tenantId: uuid.UUID | str,
        capabilityCode: str,
        *,
        includeInactive: bool = True,
    ) -> CapabilityDescriptor:
        return self.getRegistration(
            tenantId,
            capabilityCode,
            includeInactive=includeInactive,
        ).descriptor()

    def listCapabilities(
        self,
        tenantId: uuid.UUID | str,
        *,
        activeOnly: bool = True,
    ) -> tuple[CapabilityDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        descriptors = [
            registration.descriptor()
            for registration in self._registrations.values()
            if registration.tenantId == tenant and (not activeOnly or registration.capability.isActive)
        ]
        return tuple(sorted(descriptors, key=lambda descriptor: descriptor.code))

    def activateCapability(
        self,
        tenantId: uuid.UUID | str,
        capabilityCode: str,
    ) -> CapabilityDescriptor:
        registration = self.getRegistration(tenantId, capabilityCode)
        registration.capability.isActive = True
        return registration.descriptor()

    def deactivateCapability(
        self,
        tenantId: uuid.UUID | str,
        capabilityCode: str,
    ) -> CapabilityDescriptor:
        registration = self.getRegistration(tenantId, capabilityCode)
        registration.capability.isActive = False
        return registration.descriptor()

    def unregisterCapability(self, tenantId: uuid.UUID | str, capabilityCode: str) -> None:
        registration = self.getRegistration(tenantId, capabilityCode)
        self._registrations.pop((registration.tenantId, registration.capabilityCode), None)

    def unregister(self, tenantId: uuid.UUID | str, capabilityCode: str) -> None:
        self.unregisterCapability(tenantId, capabilityCode)

    def clear(self) -> None:
        """Test/composition-root helper; no persistence side effect exists in F."""

        self._registrations.clear()

    def modelSupportsCapability(
        self,
        tenantId: uuid.UUID | str,
        capabilityCode: str,
        model: AIModel | ModelDescriptor,
        *,
        requestType: str = "",
    ) -> bool:
        self._resolveCapabilityForOptionalRequest(tenantId, capabilityCode, requestType)
        tenant = requireUuid(tenantId, "tenantId")
        if isinstance(model, AIModel):
            if model.tenantId != tenant or not model.isActive:
                return False
            return model.supportsCapability(_normalizeCapabilityCode(capabilityCode))
        if isinstance(model, ModelDescriptor):
            if model.tenantId != tenant or not model.isActive or not model.providerIsActive:
                return False
            return self._descriptorSupportsCapability(model, _normalizeCapabilityCode(capabilityCode))
        raise AICapabilityModelNotSupported("Model must be an AIModel or ModelDescriptor.")

    def supportsModel(
        self,
        tenantId: uuid.UUID | str,
        capabilityCode: str,
        model: AIModel | ModelDescriptor,
        *,
        requestType: str = "",
    ) -> bool:
        return self.modelSupportsCapability(
            tenantId,
            capabilityCode,
            model,
            requestType=requestType,
        )

    def listModelsForCapability(
        self,
        tenantId: uuid.UUID | str,
        capabilityCode: str,
        modelRegistry: ModelRegistry | None = None,
        *,
        activeOnly: bool = True,
        requestType: str = "",
    ) -> tuple[ModelDescriptor, ...]:
        self._resolveCapabilityForOptionalRequest(tenantId, capabilityCode, requestType)
        registry = self._requireModelRegistry(modelRegistry)
        normalizedCode = _normalizeCapabilityCode(capabilityCode)
        return tuple(
            descriptor
            for descriptor in registry.listModels(tenantId, activeOnly=activeOnly)
            if self._descriptorSupportsCapability(descriptor, normalizedCode)
        )

    def routeForCapability(
        self,
        request: CapabilityRoutingRequest,
        policy: ModelRoutingPolicy | None = None,
        modelRegistry: ModelRegistry | None = None,
    ) -> RoutingDecision:
        if not isinstance(request, CapabilityRoutingRequest):
            raise AICapabilityPolicyInvalid("A CapabilityRoutingRequest is required.")
        self._resolveCapabilityForOptionalRequest(
            request.tenantId,
            request.capabilityCode,
            request.requestType,
        )
        registry = self._requireModelRegistry(modelRegistry)
        try:
            return registry.route(request.toModelRoutingRequest(), policy)
        except AICapabilityRoutingNoMatch:
            raise
        except Exception as exc:
            # Only the routing no-match boundary is translated. Invalid Policy
            # and Contract errors remain explicit Domain errors from E/F.
            from apps.ai.domain.exceptions import AIRoutingNoMatch

            if isinstance(exc, AIRoutingNoMatch):
                raise AICapabilityRoutingNoMatch(
                    request.capabilityCode,
                ) from exc
            raise

    def resolveModelForCapability(
        self,
        request: CapabilityRoutingRequest,
        policy: ModelRoutingPolicy | None = None,
        modelRegistry: ModelRegistry | None = None,
    ) -> AIModel:
        registry = self._requireModelRegistry(modelRegistry)
        decision = self.routeForCapability(request, policy, registry)
        return registry.resolveModel(
            decision.tenantId,
            decision.providerCode,
            decision.modelCode,
        )

    def _resolveCapabilityForOptionalRequest(
        self,
        tenantId: uuid.UUID | str,
        capabilityCode: str,
        requestType: str,
    ) -> AICapability:
        if requestType:
            return self.resolveForRequest(tenantId, capabilityCode, requestType)
        return self.resolveCapability(tenantId, capabilityCode)

    def _requireModelRegistry(self, modelRegistry: ModelRegistry | None) -> ModelRegistry:
        registry = modelRegistry or self.modelRegistry
        if not isinstance(registry, ModelRegistry):
            raise AICapabilityRegistrationInvalid("A ModelRegistry is required for model integration.")
        return registry

    @staticmethod
    def _descriptorSupportsCapability(descriptor: ModelDescriptor, capabilityCode: str) -> bool:
        return not descriptor.inputCapability or (
            capabilityCode in descriptor.inputCapability or capabilityCode in descriptor.outputCapability
        )

    @staticmethod
    def _key(tenantId: uuid.UUID | str, capabilityCode: str) -> tuple[uuid.UUID, str]:
        return requireUuid(tenantId, "tenantId"), _normalizeCapabilityCode(capabilityCode)


AICapabilityRegistry = CapabilityRegistry
InMemoryCapabilityRegistry = CapabilityRegistry
RegisteredCapability = CapabilityRegistration
CapabilitySelectionRequest = CapabilityRoutingRequest
CapabilityRouting = CapabilityRoutingRequest

__all__ = [
    "AICapabilityRegistry",
    "CapabilityDescriptor",
    "CapabilityRouting",
    "CapabilityRoutingRequest",
    "CapabilitySelectionRequest",
    "CapabilityRegistration",
    "CapabilityRegistry",
    "InMemoryCapabilityRegistry",
    "RegisteredCapability",
]
