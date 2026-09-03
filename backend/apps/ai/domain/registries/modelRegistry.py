"""Tenant-aware Model Registry and deterministic Model Routing for Phase 13-E.

This module composes the pure ``AIModel`` entity from Phase 13-B with the
``ProviderRegistry`` contract from Phase 13-D. It deliberately contains no
persistence, framework, network, retry/failover execution, secret resolution,
or provider SDK dependency.

The registry owns model definitions. The Provider Registry remains the owner of
provider definitions and runtime adapters. A model is operationally usable only
when both definitions are active and the model's provider ID belongs to the
same tenant/provider binding.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Iterable

from apps.ai.domain.entities.aiRecords import AIModel, requireUuid
from apps.ai.domain.exceptions import (
    AIModelAlreadyRegistered,
    AIModelAmbiguous,
    AIModelInactive,
    AIModelNotRegistered,
    AIModelProviderOwnershipInvalid,
    AIModelRegistrationInvalid,
    AIProviderInactive,
    AIRoutingNoMatch,
    AIRoutingPolicyInvalid,
)
from apps.ai.domain.ports import MODEL_FEATURES, ProviderCapabilities
from apps.ai.domain.registries.providerRegistry import ProviderRegistration, ProviderRegistry
from apps.ai.domain.valueObjects.aiTypes import CAPABILITY_CODES, MODEL_TYPES, validateCode


def utcNow() -> datetime:
    return datetime.now(tz=UTC)


def _normalizeCode(
    value: str,
    fieldName: str,
    *,
    errorType: type[Exception] = AIModelRegistrationInvalid,
) -> str:
    try:
        return validateCode(value, fieldName)
    except Exception as exc:
        raise errorType(f"Invalid {fieldName}.") from exc


def _normalizeModelType(value: str, *, errorType: type[Exception] = AIModelRegistrationInvalid) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in MODEL_TYPES and not normalized.startswith("CUSTOM_"):
        raise errorType(f"Unsupported model type: {normalized}.")
    return normalized


def _normalizeCapability(value: str, *, errorType: type[Exception] = AIModelRegistrationInvalid) -> str:
    normalized = _normalizeCode(value, "capabilityCode", errorType=errorType)
    if normalized not in CAPABILITY_CODES and not normalized.startswith("CUSTOM_"):
        raise errorType(f"Unsupported AI capability: {normalized}.")
    return normalized


def _normalizeOptionalCode(
    value: str,
    fieldName: str,
    *,
    errorType: type[Exception] = AIModelRegistrationInvalid,
) -> str:
    if not str(value or "").strip():
        return ""
    return _normalizeCode(value, fieldName, errorType=errorType)


@dataclass(frozen=True)
class ModelDescriptor:
    """Non-sensitive model read model suitable for inspection and routing logs.

    Runtime adapters, configuration references, metadata, token rates, secrets,
    and arbitrary provider payloads are intentionally absent.
    """

    tenantId: uuid.UUID
    modelId: uuid.UUID
    providerId: uuid.UUID
    providerCode: str
    code: str
    name: str
    modelType: str
    version: str
    contextWindow: int
    inputCapability: tuple[str, ...]
    outputCapability: tuple[str, ...]
    supportsStreaming: bool
    supportsTools: bool
    supportsEmbeddings: bool
    supportsVision: bool
    isActive: bool
    providerIsActive: bool
    registeredAt: datetime


@dataclass
class ModelRegistration:
    """Binding between one tenant-owned ``AIModel`` and a provider code.

    The provider adapter is not copied or exposed here. It remains exclusively
    behind ``ProviderRegistry`` and is only consulted during routing checks.
    """

    model: AIModel = field(repr=False)
    providerCode: str
    registeredAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        if not isinstance(self.model, AIModel):
            raise AIModelRegistrationInvalid("Model definition is invalid.")
        self.providerCode = _normalizeCode(self.providerCode, "providerCode")

    @property
    def tenantId(self) -> uuid.UUID:
        return self.model.tenantId

    @property
    def modelId(self) -> uuid.UUID:
        return self.model.id

    @property
    def modelCode(self) -> str:
        return self.model.code

    @property
    def providerId(self) -> uuid.UUID:
        return self.model.providerId

    def descriptor(self, *, providerIsActive: bool) -> ModelDescriptor:
        return ModelDescriptor(
            tenantId=self.model.tenantId,
            modelId=self.model.id,
            providerId=self.model.providerId,
            providerCode=self.providerCode,
            code=self.model.code,
            name=self.model.name,
            modelType=self.model.modelType,
            version=self.model.version,
            contextWindow=self.model.contextWindow,
            inputCapability=self.model.inputCapability,
            outputCapability=self.model.outputCapability,
            supportsStreaming=self.model.supportsStreaming,
            supportsTools=self.model.supportsTools,
            supportsEmbeddings=self.model.supportsEmbeddings,
            supportsVision=self.model.supportsVision,
            isActive=self.model.isActive,
            providerIsActive=providerIsActive,
            registeredAt=self.registeredAt,
        )


@dataclass(frozen=True)
class ModelRouteTarget:
    """An ordered, provider-neutral routing target.

    Either component may be empty. A provider-only target selects the first
    eligible model on that provider; a model-only target selects the first
    eligible owner of that model code.
    """

    providerCode: str = ""
    modelCode: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "providerCode",
            _normalizeOptionalCode(self.providerCode, "providerCode", errorType=AIRoutingPolicyInvalid),
        )
        object.__setattr__(
            self,
            "modelCode",
            _normalizeOptionalCode(self.modelCode, "modelCode", errorType=AIRoutingPolicyInvalid),
        )
        if not self.providerCode and not self.modelCode:
            raise AIRoutingPolicyInvalid("A routing target must identify a provider, a model, or both.")


@dataclass(frozen=True)
class ModelRoutingRequest:
    """Pure constraints used to find an operational model.

    ``requiredFeatures`` are Provider Port features. The boolean flags are
    model-level requirements which are also checked against the provider
    capability handshake where such a feature exists.
    """

    tenantId: uuid.UUID | str
    modelType: str = ""
    capabilityCode: str = ""
    requiredFeatures: tuple[str, ...] = ()
    requiresStreaming: bool = False
    requiresTools: bool = False
    requiresVision: bool = False
    requiresEmbeddings: bool = False
    minimumContextWindow: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenantId", requireUuid(self.tenantId, "tenantId"))
        if self.modelType:
            object.__setattr__(self, "modelType", _normalizeModelType(self.modelType))
        if self.capabilityCode:
            object.__setattr__(
                self,
                "capabilityCode",
                _normalizeCapability(self.capabilityCode, errorType=AIRoutingPolicyInvalid),
            )
        normalizedFeatures: list[str] = []
        for feature in self.requiredFeatures:
            normalized = str(feature or "").strip().upper()
            if normalized not in MODEL_FEATURES:
                raise AIRoutingPolicyInvalid(f"Unknown required provider feature: {normalized}.")
            if normalized not in normalizedFeatures:
                normalizedFeatures.append(normalized)
        object.__setattr__(self, "requiredFeatures", tuple(normalizedFeatures))
        for flagName in (
            "requiresStreaming",
            "requiresTools",
            "requiresVision",
            "requiresEmbeddings",
        ):
            if not isinstance(getattr(self, flagName), bool):
                raise AIRoutingPolicyInvalid(f"{flagName} must be boolean.")
        if self.minimumContextWindow is not None and (
            not isinstance(self.minimumContextWindow, int)
            or isinstance(self.minimumContextWindow, bool)
            or self.minimumContextWindow < 1
        ):
            raise AIRoutingPolicyInvalid("minimumContextWindow must be a positive integer.")

    @property
    def requiredProviderFeatures(self) -> tuple[str, ...]:
        """Readable alias clarifying that ``requiredFeatures`` is Port-level."""

        return self.requiredFeatures


@dataclass(frozen=True)
class ModelRoutingPolicy:
    """Explicit preference/default/fallback policy for one routing decision.

    Routing never retries a provider call. ``allowFallback`` only permits the
    resolver to consider the declared ordered targets after a preferred target
    is not eligible. This is policy evaluation, not failover execution.
    """

    preferredProviderCode: str = ""
    preferredModelCode: str = ""
    defaultProviderCode: str = ""
    defaultModelCode: str = ""
    fallbackTargets: tuple[ModelRouteTarget, ...] = ()
    fallbackModelCodes: tuple[str, ...] = ()
    fallbackProviderCodes: tuple[str, ...] = ()
    allowFallback: bool = False
    fallbackEnabled: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "preferredProviderCode",
            _normalizeOptionalCode(
                self.preferredProviderCode,
                "preferredProviderCode",
                errorType=AIRoutingPolicyInvalid,
            ),
        )
        object.__setattr__(
            self,
            "preferredModelCode",
            _normalizeOptionalCode(
                self.preferredModelCode,
                "preferredModelCode",
                errorType=AIRoutingPolicyInvalid,
            ),
        )
        object.__setattr__(
            self,
            "defaultProviderCode",
            _normalizeOptionalCode(
                self.defaultProviderCode,
                "defaultProviderCode",
                errorType=AIRoutingPolicyInvalid,
            ),
        )
        object.__setattr__(
            self,
            "defaultModelCode",
            _normalizeOptionalCode(
                self.defaultModelCode,
                "defaultModelCode",
                errorType=AIRoutingPolicyInvalid,
            ),
        )
        object.__setattr__(
            self,
            "fallbackModelCodes",
            tuple(
                _normalizeCode(value, "fallbackModelCode", errorType=AIRoutingPolicyInvalid)
                for value in self.fallbackModelCodes
            ),
        )
        object.__setattr__(
            self,
            "fallbackProviderCodes",
            tuple(
                _normalizeCode(value, "fallbackProviderCode", errorType=AIRoutingPolicyInvalid)
                for value in self.fallbackProviderCodes
            ),
        )
        normalizedTargets: list[ModelRouteTarget] = []
        for target in self.fallbackTargets:
            if isinstance(target, ModelRouteTarget):
                normalizedTargets.append(target)
            elif isinstance(target, (tuple, list)) and len(target) == 2:
                normalizedTargets.append(ModelRouteTarget(providerCode=target[0], modelCode=target[1]))
            else:
                raise AIRoutingPolicyInvalid("fallbackTargets must contain ModelRouteTarget values.")
        object.__setattr__(self, "fallbackTargets", tuple(normalizedTargets))
        if not isinstance(self.allowFallback, bool):
            raise AIRoutingPolicyInvalid("allowFallback must be boolean.")
        if self.fallbackEnabled is not None:
            if not isinstance(self.fallbackEnabled, bool):
                raise AIRoutingPolicyInvalid("fallbackEnabled must be boolean.")
            object.__setattr__(self, "allowFallback", self.fallbackEnabled)
        object.__setattr__(self, "fallbackEnabled", self.allowFallback)

    @property
    def hasPreferredTarget(self) -> bool:
        return bool(self.preferredProviderCode or self.preferredModelCode)

    @property
    def hasDefaultTarget(self) -> bool:
        return bool(self.defaultProviderCode or self.defaultModelCode)

    def orderedFallbackTargets(self) -> tuple[ModelRouteTarget, ...]:
        """Return explicit targets followed by compact list-based targets."""

        targets = list(self.fallbackTargets)
        providers = self.fallbackProviderCodes
        models = self.fallbackModelCodes
        if providers and models:
            if len(providers) == len(models):
                pairs = zip(providers, models)
            elif len(providers) == 1:
                pairs = ((providers[0], model) for model in models)
            elif len(models) == 1:
                pairs = ((provider, models[0]) for provider in providers)
            else:
                raise AIRoutingPolicyInvalid(
                    "fallbackProviderCodes and fallbackModelCodes must have equal lengths or one side must contain one value."
                )
            targets.extend(ModelRouteTarget(providerCode=provider, modelCode=model) for provider, model in pairs)
        elif providers:
            targets.extend(ModelRouteTarget(providerCode=provider) for provider in providers)
        else:
            targets.extend(ModelRouteTarget(modelCode=model) for model in models)
        return tuple(targets)


@dataclass(frozen=True)
class RoutingDecision:
    """Auditable, non-sensitive result of one deterministic selection."""

    tenantId: uuid.UUID
    providerId: uuid.UUID
    providerCode: str
    modelId: uuid.UUID
    modelCode: str
    modelType: str
    reason: str
    usedFallback: bool
    rank: int
    descriptor: ModelDescriptor

    @property
    def provider(self) -> str:
        return self.providerCode

    @property
    def model(self) -> str:
        return self.modelCode


class ModelRegistry:
    """In-memory, tenant-scoped model registry composed with ProviderRegistry."""

    def __init__(
        self,
        providerRegistry: ProviderRegistry,
        registrations: Iterable[ModelRegistration] = (),
    ) -> None:
        if not isinstance(providerRegistry, ProviderRegistry):
            raise AIModelRegistrationInvalid("A ProviderRegistry is required by ModelRegistry.")
        self.providerRegistry = providerRegistry
        self._registrations: dict[tuple[uuid.UUID, uuid.UUID, str], ModelRegistration] = {}
        for registration in registrations:
            if not isinstance(registration, ModelRegistration):
                raise AIModelRegistrationInvalid("Initial model registrations are invalid.")
            self.registerModel(
                registration.model,
                registration.providerCode,
                registeredAt=registration.registeredAt,
            )

    def registerModel(
        self,
        model: AIModel,
        providerCode: str | ProviderRegistration | None = None,
        *,
        replace: bool = False,
        registeredAt: datetime | None = None,
    ) -> ModelRegistration:
        if not isinstance(model, AIModel):
            raise AIModelRegistrationInvalid("Model definition is invalid.")
        normalizedProviderCode, providerRegistration = self._resolveOwnedProvider(model, providerCode)
        key = self._key(model.tenantId, model.providerId, model.code)
        if key in self._registrations and not replace:
            raise AIModelAlreadyRegistered(normalizedProviderCode, model.code)
        registration = ModelRegistration(
            model=model,
            providerCode=normalizedProviderCode,
            registeredAt=registeredAt or utcNow(),
        )
        # Keep the local variable explicit: registration is only valid because
        # the provider binding was validated against the model's owner.
        if providerRegistration.provider.id != model.providerId:
            raise AIModelProviderOwnershipInvalid("Model provider ownership changed during registration.")
        self._registrations[key] = registration
        return registration

    def register(
        self,
        model: AIModel,
        providerCode: str | ProviderRegistration | None = None,
        *,
        replace: bool = False,
    ) -> ModelRegistration:
        """Short alias for application composition roots."""

        return self.registerModel(model, providerCode, replace=replace)

    def getRegistration(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        modelCode: str,
        *,
        includeInactive: bool = True,
    ) -> ModelRegistration:
        tenant = requireUuid(tenantId, "tenantId")
        normalizedProviderCode = _normalizeCode(providerCode, "providerCode")
        normalizedModelCode = _normalizeCode(modelCode, "modelCode")
        # Lookup by stored provider code rather than only the current provider
        # UUID. This preserves management visibility after Provider replacement
        # or unregister without weakening the ownership check at registration.
        registration = next(
            (
                candidate
                for candidate in self._registrations.values()
                if candidate.tenantId == tenant
                and candidate.providerCode == normalizedProviderCode
                and candidate.modelCode == normalizedModelCode
            ),
            None,
        )
        # Be tolerant of the equivalent (modelCode, providerCode) positional
        # ordering while keeping provider-first as the documented contract.
        if registration is None:
            reverseProvider = normalizedModelCode
            reverseModel = normalizedProviderCode
            registration = next(
                (
                    candidate
                    for candidate in self._registrations.values()
                    if candidate.tenantId == tenant
                    and candidate.providerCode == reverseProvider
                    and candidate.modelCode == reverseModel
                ),
                None,
            )
        if registration is None or (not includeInactive and not registration.model.isActive):
            raise AIModelNotRegistered(normalizedModelCode, normalizedProviderCode)
        return registration

    def getModelRegistration(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        modelCode: str,
        *,
        includeInactive: bool = True,
    ) -> ModelRegistration:
        return self.getRegistration(
            tenantId,
            providerCode,
            modelCode,
            includeInactive=includeInactive,
        )

    def resolveModel(self, tenantId: uuid.UUID | str, providerCode: str, modelCode: str) -> AIModel:
        registration = self.getRegistration(tenantId, providerCode, modelCode)
        self._ensureOperational(registration)
        return registration.model

    def resolve(self, tenantId: uuid.UUID | str, providerCode: str, modelCode: str) -> AIModel:
        return self.resolveModel(tenantId, providerCode, modelCode)

    def resolveRegistration(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        modelCode: str,
    ) -> ModelRegistration:
        registration = self.getRegistration(tenantId, providerCode, modelCode)
        self._ensureOperational(registration)
        return registration

    def resolveModelByCode(
        self,
        tenantId: uuid.UUID | str,
        modelCode: str,
        providerCode: str | None = None,
    ) -> AIModel:
        tenant = requireUuid(tenantId, "tenantId")
        normalizedModelCode = _normalizeCode(modelCode, "modelCode")
        if providerCode:
            return self.resolveModel(tenant, providerCode, normalizedModelCode)
        matches = tuple(
            candidate
            for candidate in self._registrations.values()
            if candidate.tenantId == tenant and candidate.modelCode == normalizedModelCode
        )
        if not matches:
            raise AIModelNotRegistered(normalizedModelCode)
        if len(matches) > 1:
            raise AIModelAmbiguous(normalizedModelCode)
        self._ensureOperational(matches[0])
        return matches[0].model

    def resolveByCode(
        self,
        tenantId: uuid.UUID | str,
        modelCode: str,
        providerCode: str | None = None,
    ) -> AIModel:
        return self.resolveModelByCode(tenantId, modelCode, providerCode)

    def describeModel(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        modelCode: str,
        *,
        includeInactive: bool = True,
    ) -> ModelDescriptor:
        registration = self.getRegistration(
            tenantId,
            providerCode,
            modelCode,
            includeInactive=includeInactive,
        )
        _, providerIsActive = self._providerState(registration)
        return registration.descriptor(providerIsActive=providerIsActive)

    def listModels(
        self,
        tenantId: uuid.UUID | str,
        *,
        activeOnly: bool = True,
    ) -> tuple[ModelDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        descriptors: list[ModelDescriptor] = []
        for registration in self._registrations.values():
            if registration.tenantId != tenant:
                continue
            _, providerIsActive = self._providerState(registration)
            if activeOnly and (not registration.model.isActive or not providerIsActive):
                continue
            descriptors.append(registration.descriptor(providerIsActive=providerIsActive))
        return tuple(sorted(descriptors, key=lambda descriptor: (descriptor.providerCode, descriptor.code)))

    def activateModel(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        modelCode: str,
    ) -> ModelDescriptor:
        registration = self.getRegistration(tenantId, providerCode, modelCode)
        registration.model.isActive = True
        _, providerIsActive = self._providerState(registration)
        return registration.descriptor(providerIsActive=providerIsActive)

    def deactivateModel(
        self,
        tenantId: uuid.UUID | str,
        providerCode: str,
        modelCode: str,
    ) -> ModelDescriptor:
        registration = self.getRegistration(tenantId, providerCode, modelCode)
        registration.model.isActive = False
        _, providerIsActive = self._providerState(registration)
        return registration.descriptor(providerIsActive=providerIsActive)

    def unregisterModel(self, tenantId: uuid.UUID | str, providerCode: str, modelCode: str) -> None:
        registration = self.getRegistration(tenantId, providerCode, modelCode)
        self._registrations.pop(self._key(registration.tenantId, registration.providerId, registration.modelCode), None)

    def unregister(self, tenantId: uuid.UUID | str, providerCode: str, modelCode: str) -> None:
        self.unregisterModel(tenantId, providerCode, modelCode)

    def clear(self) -> None:
        """Test/composition-root helper; no persistence side effect exists in E."""

        self._registrations.clear()

    def route(
        self,
        request: ModelRoutingRequest,
        policy: ModelRoutingPolicy | None = None,
    ) -> RoutingDecision:
        if not isinstance(request, ModelRoutingRequest):
            raise AIRoutingPolicyInvalid("A ModelRoutingRequest is required.")
        if policy is None:
            policy = ModelRoutingPolicy()
        if not isinstance(policy, ModelRoutingPolicy):
            raise AIRoutingPolicyInvalid("A ModelRoutingPolicy is required.")
        candidates = self._eligible(request)
        if not candidates:
            raise AIRoutingNoMatch()
        candidates = tuple(sorted(candidates, key=self._sortCandidate))

        if policy.hasPreferredTarget:
            selected = self._firstMatching(candidates, ModelRouteTarget(policy.preferredProviderCode, policy.preferredModelCode))
            if selected is not None:
                return self._decision(selected, reason="preferred", usedFallback=False, rank=1)
            if not policy.allowFallback:
                raise AIRoutingNoMatch("The preferred model/provider is not eligible and fallback is disabled.")

        if policy.allowFallback:
            for rank, target in enumerate(policy.orderedFallbackTargets(), start=1):
                selected = self._firstMatching(candidates, target)
                if selected is not None:
                    return self._decision(selected, reason="fallback", usedFallback=True, rank=rank)

        if policy.hasDefaultTarget:
            selected = self._firstMatching(
                candidates,
                ModelRouteTarget(policy.defaultProviderCode, policy.defaultModelCode),
            )
            if selected is not None:
                return self._decision(selected, reason="default", usedFallback=bool(policy.hasPreferredTarget), rank=1)
            if not policy.allowFallback:
                raise AIRoutingNoMatch("The default model/provider is not eligible and fallback is disabled.")

        # With no explicit target, registry order is the documented stable
        # default. When fallback is enabled this is the final policy fallback;
        # it still does not execute or retry anything.
        return self._decision(
            candidates[0],
            reason="fallback-deterministic" if policy.allowFallback else "deterministic-default",
            usedFallback=bool(policy.allowFallback and (policy.hasPreferredTarget or policy.hasDefaultTarget)),
            rank=1,
        )

    def routeModel(
        self,
        request: ModelRoutingRequest,
        policy: ModelRoutingPolicy | None = None,
    ) -> RoutingDecision:
        return self.route(request, policy)

    def resolveRoute(
        self,
        request: ModelRoutingRequest,
        policy: ModelRoutingPolicy | None = None,
    ) -> RoutingDecision:
        return self.route(request, policy)

    def _eligible(
        self,
        request: ModelRoutingRequest,
    ) -> tuple[tuple[ModelRegistration, ProviderRegistration], ...]:
        eligible: list[tuple[ModelRegistration, ProviderRegistration]] = []
        for registration in self._registrations.values():
            if registration.tenantId != request.tenantId:
                continue
            providerRegistration, providerIsActive = self._providerState(registration)
            if providerRegistration is None or not providerIsActive or not registration.model.isActive:
                continue
            if self._matches(registration.model, providerRegistration.capabilities, request):
                eligible.append((registration, providerRegistration))
        return tuple(eligible)

    @staticmethod
    def _matches(
        model: AIModel,
        capabilities: ProviderCapabilities,
        request: ModelRoutingRequest,
    ) -> bool:
        if request.modelType and model.modelType != request.modelType:
            return False
        if request.capabilityCode and not model.supportsCapability(request.capabilityCode):
            return False
        if capabilities.maxContextWindow is not None and model.contextWindow > capabilities.maxContextWindow:
            return False
        if request.minimumContextWindow is not None:
            if model.contextWindow < request.minimumContextWindow:
                return False
            if capabilities.maxContextWindow is not None and capabilities.maxContextWindow < request.minimumContextWindow:
                return False

        requiredFeatures = list(request.requiredFeatures)
        if request.modelType == "EMBEDDING" or request.requiresEmbeddings:
            requiredFeatures.append("EMBEDDING")
            if not model.supportsEmbeddings:
                return False
        if request.modelType == "VISION" or request.requiresVision:
            requiredFeatures.append("VISION")
            if not model.supportsVision:
                return False
        if request.requiresStreaming:
            requiredFeatures.append("STREAMING")
            if not model.supportsStreaming:
                return False
        if request.requiresTools:
            requiredFeatures.append("TOOLS")
            if not model.supportsTools:
                return False

        if request.modelType in {"LLM", "VISION", "MULTIMODAL", "CLASSIFICATION", "SPEECH_TO_TEXT", "TEXT_TO_SPEECH", "CUSTOM"}:
            requiredFeatures.append("GENERATION")
        if request.modelType == "EMBEDDING" and not model.supportsEmbeddings:
            return False

        for feature in requiredFeatures:
            if feature == "STREAMING" and not model.supportsStreaming:
                return False
            if feature == "TOOLS" and not model.supportsTools:
                return False
            if feature == "VISION" and not model.supportsVision:
                return False
            if feature == "EMBEDDING" and not model.supportsEmbeddings:
                return False
            if not capabilities.supports(feature):
                return False
        return True

    @staticmethod
    def _sortCandidate(candidate: tuple[ModelRegistration, ProviderRegistration]) -> tuple[str, str, str, str]:
        registration, _ = candidate
        return (
            registration.providerCode,
            registration.modelCode,
            registration.model.modelType,
            str(registration.model.id),
        )

    @staticmethod
    def _firstMatching(
        candidates: tuple[tuple[ModelRegistration, ProviderRegistration], ...],
        target: ModelRouteTarget,
    ) -> tuple[ModelRegistration, ProviderRegistration] | None:
        for registration, providerRegistration in candidates:
            if target.providerCode and registration.providerCode != target.providerCode:
                continue
            if target.modelCode and registration.modelCode != target.modelCode:
                continue
            return registration, providerRegistration
        return None

    @staticmethod
    def _decision(
        selected: tuple[ModelRegistration, ProviderRegistration],
        *,
        reason: str,
        usedFallback: bool,
        rank: int,
    ) -> RoutingDecision:
        registration, providerRegistration = selected
        descriptor = registration.descriptor(providerIsActive=providerRegistration.provider.isActive)
        return RoutingDecision(
            tenantId=registration.tenantId,
            providerId=registration.providerId,
            providerCode=registration.providerCode,
            modelId=registration.modelId,
            modelCode=registration.modelCode,
            modelType=registration.model.modelType,
            reason=reason,
            usedFallback=usedFallback,
            rank=rank,
            descriptor=descriptor,
        )

    def _resolveOwnedProvider(
        self,
        model: AIModel,
        providerCode: str | ProviderRegistration | None,
    ) -> tuple[str, ProviderRegistration]:
        if isinstance(providerCode, ProviderRegistration):
            if providerCode.tenantId != model.tenantId:
                raise AIModelProviderOwnershipInvalid(
                    "Provider registration does not belong to the model tenant."
                )
            providerCode = providerCode.providerCode
        if providerCode is not None and str(providerCode).strip():
            normalizedProviderCode = _normalizeCode(providerCode, "providerCode")
            providerRegistration = self.providerRegistry.getRegistration(
                model.tenantId,
                normalizedProviderCode,
            )
            if providerRegistration.provider.id != model.providerId:
                raise AIModelProviderOwnershipInvalid(
                    "Model providerId does not belong to the requested tenant/provider binding."
                )
            return normalizedProviderCode, providerRegistration

        matches = [
            descriptor
            for descriptor in self.providerRegistry.listProviders(model.tenantId, activeOnly=False)
            if descriptor.providerId == model.providerId
        ]
        if len(matches) != 1:
            raise AIModelProviderOwnershipInvalid(
                "Model providerId cannot be resolved to exactly one provider owned by the model tenant."
            )
        return matches[0].code, self.providerRegistry.getRegistration(model.tenantId, matches[0].code)

    def _providerState(
        self,
        registration: ModelRegistration,
    ) -> tuple[ProviderRegistration | None, bool]:
        try:
            providerRegistration = self.providerRegistry.getRegistration(
                registration.tenantId,
                registration.providerCode,
            )
        except Exception:
            return None, False
        if providerRegistration.provider.id != registration.providerId:
            return providerRegistration, False
        return providerRegistration, providerRegistration.provider.isActive

    def _ensureOperational(self, registration: ModelRegistration) -> None:
        if not registration.model.isActive:
            raise AIModelInactive(registration.model.code)
        providerRegistration, providerIsActive = self._providerState(registration)
        if providerRegistration is None:
            raise AIModelProviderOwnershipInvalid("Model provider is no longer registered for its tenant.")
        if providerRegistration.provider.id != registration.providerId:
            raise AIModelProviderOwnershipInvalid("Model provider ownership does not match its tenant binding.")
        if not providerIsActive:
            raise AIProviderInactive(registration.providerCode)

    @staticmethod
    def _key(tenantId: uuid.UUID | str, providerId: uuid.UUID | str, modelCode: str) -> tuple[uuid.UUID, uuid.UUID, str]:
        return requireUuid(tenantId, "tenantId"), requireUuid(providerId, "providerId"), _normalizeCode(modelCode, "modelCode")


AIModelRegistry = ModelRegistry
InMemoryModelRegistry = ModelRegistry
RegisteredModel = ModelRegistration
ModelSelectionRequest = ModelRoutingRequest
RoutingRequest = ModelRoutingRequest
RoutingPolicy = ModelRoutingPolicy
ModelFallbackPolicy = ModelRoutingPolicy
ModelRoutingDecision = RoutingDecision
RoutingTarget = ModelRouteTarget

__all__ = [
    "AIModelRegistry",
    "InMemoryModelRegistry",
    "ModelDescriptor",
    "ModelFallbackPolicy",
    "ModelRegistration",
    "ModelRegistry",
    "ModelRouteTarget",
    "ModelRoutingDecision",
    "ModelRoutingPolicy",
    "ModelRoutingRequest",
    "ModelSelectionRequest",
    "RegisteredModel",
    "RoutingDecision",
    "RoutingPolicy",
    "RoutingRequest",
    "RoutingTarget",
]
