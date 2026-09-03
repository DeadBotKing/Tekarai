"""Phase 13-E Model Registry and Routing tests (pure Python, offline)."""

from __future__ import annotations

import unittest
import uuid
from dataclasses import FrozenInstanceError
from pathlib import Path

from apps.ai.domain.entities.aiRecords import AIModel, AIProvider
from apps.ai.domain.exceptions import (
    AIModelAlreadyRegistered,
    AIModelAmbiguous,
    AIModelInactive,
    AIModelProviderOwnershipInvalid,
    AIProviderInactive,
    AIRoutingNoMatch,
    AIRoutingPolicyInvalid,
)
from apps.ai.domain.ports import DeterministicAIProvider, MODEL_FEATURES, ProviderCapabilities
from apps.ai.domain.registries.modelRegistry import (
    AIModelRegistry,
    ModelDescriptor,
    ModelRegistry,
    ModelRouteTarget,
    ModelRoutingPolicy,
    ModelRoutingRequest,
    RoutingPolicy,
)
from apps.ai.domain.registries.providerRegistry import ProviderRegistry


class RichProvider(DeterministicAIProvider):
    providerCode = "RICH"
    capabilities = ProviderCapabilities(
        providerCode=providerCode,
        features=frozenset(MODEL_FEATURES),
        maxContextWindow=32_000,
    )


class LimitedProvider(DeterministicAIProvider):
    providerCode = "LIMITED"
    capabilities = ProviderCapabilities(
        providerCode=providerCode,
        features=frozenset({"GENERATION"}),
        maxContextWindow=4_096,
    )


class Phase13EModelRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.providerRegistry = ProviderRegistry()
        self.rich = RichProvider()
        self.limited = LimitedProvider()
        self.richDefinition = self._provider(self.tenantId, "RICH")
        self.limitedDefinition = self._provider(self.tenantId, "LIMITED")
        self.providerRegistry.register(self.richDefinition, self.rich)
        self.providerRegistry.register(self.limitedDefinition, self.limited)
        self.registry = ModelRegistry(self.providerRegistry)

    def _provider(self, tenantId: uuid.UUID, code: str) -> AIProvider:
        return AIProvider(
            tenantId=tenantId,
            code=code,
            name=f"{code} provider",
            providerType="LOCAL",
            configurationReference="configuration-reference-only",
            metadata={"internal": "must not be exposed"},
        )

    def _model(
        self,
        code: str,
        *,
        providerId: uuid.UUID | None = None,
        tenantId: uuid.UUID | None = None,
        modelType: str = "LLM",
        contextWindow: int = 8_192,
        inputCapability: tuple[str, ...] = (),
        supportsStreaming: bool = False,
        supportsTools: bool = False,
        supportsEmbeddings: bool = False,
        supportsVision: bool = False,
        isActive: bool = True,
    ) -> AIModel:
        return AIModel(
            tenantId=tenantId or self.tenantId,
            providerId=providerId or self.richDefinition.id,
            code=code,
            name=f"{code} model",
            modelType=modelType,
            contextWindow=contextWindow,
            inputCapability=inputCapability,
            supportsStreaming=supportsStreaming,
            supportsTools=supportsTools,
            supportsEmbeddings=supportsEmbeddings,
            supportsVision=supportsVision,
            isActive=isActive,
            metadata={"private": "do-not-expose"},
        )

    def testRegistrationResolutionDescriptorAndTenantIsolation(self) -> None:
        model = self._model("PRIMARY")
        registration = self.registry.registerModel(model, "RICH")
        self.assertEqual(registration.providerCode, "RICH")
        self.assertIs(self.registry.resolveModel(self.tenantId, "RICH", "PRIMARY"), model)
        self.assertIs(self.registry.resolve(self.tenantId, "PRIMARY", "RICH"), model)
        descriptor = self.registry.describeModel(self.tenantId, "RICH", "PRIMARY")
        self.assertIsInstance(descriptor, ModelDescriptor)
        self.assertEqual(descriptor.tenantId, self.tenantId)
        self.assertEqual(descriptor.providerId, self.richDefinition.id)
        self.assertTrue(descriptor.providerIsActive)
        self.assertNotIn("do-not-expose", repr(descriptor))
        self.assertNotIn("configuration-reference-only", repr(descriptor))
        self.assertNotIn("do-not-expose", repr(registration))
        with self.assertRaises(FrozenInstanceError):
            descriptor.code = "OTHER"
        self.assertEqual(self.registry.listModels(self.otherTenantId), ())
        with self.assertRaises(Exception):
            self.registry.resolveModel(self.otherTenantId, "RICH", "PRIMARY")

    def testDuplicateIsScopedToTenantProviderAndModelCodeWithExplicitReplace(self) -> None:
        first = self._model("DUPLICATE")
        self.registry.register(first, "RICH")
        with self.assertRaises(AIModelAlreadyRegistered):
            self.registry.registerModel(self._model("DUPLICATE"), "RICH")
        replacement = self._model("DUPLICATE", contextWindow=16_384)
        self.registry.registerModel(replacement, "RICH", replace=True)
        self.assertIs(self.registry.resolveModel(self.tenantId, "RICH", "DUPLICATE"), replacement)
        # The same code is valid for another provider and another tenant.
        self.registry.registerModel(self._model("DUPLICATE", providerId=self.limitedDefinition.id), "LIMITED")
        otherProvider = self._provider(self.otherTenantId, "RICH")
        self.providerRegistry.register(otherProvider, RichProvider())
        self.registry.registerModel(
            self._model("DUPLICATE", tenantId=self.otherTenantId, providerId=otherProvider.id),
            "RICH",
        )
        self.assertEqual(len(self.registry.listModels(self.tenantId)), 2)
        self.assertEqual(len(self.registry.listModels(self.otherTenantId)), 1)

    def testProviderOwnershipAndRegistrationAreEnforced(self) -> None:
        wrongOwner = self._model("WRONG_OWNER", providerId=self.limitedDefinition.id)
        with self.assertRaises(AIModelProviderOwnershipInvalid):
            self.registry.registerModel(wrongOwner, "RICH")
        with self.assertRaises(AIModelProviderOwnershipInvalid):
            self.registry.registerModel(self._model("UNRESOLVED"), "LIMITED")
        # Provider code can be derived only when the provider ID maps uniquely.
        derived = self._model("DERIVED")
        self.registry.registerModel(derived)
        self.assertIs(self.registry.resolveModel(self.tenantId, "RICH", "DERIVED"), derived)

    def testModelAndProviderActivationBlockOperationalResolution(self) -> None:
        inactive = self._model("INACTIVE", isActive=False)
        self.registry.registerModel(inactive, "RICH")
        with self.assertRaises(AIModelInactive):
            self.registry.resolveModel(self.tenantId, "RICH", "INACTIVE")
        self.assertEqual(self.registry.listModels(self.tenantId), ())
        descriptor = self.registry.activateModel(self.tenantId, "RICH", "INACTIVE")
        self.assertTrue(descriptor.isActive)
        self.assertIs(self.registry.resolveModel(self.tenantId, "RICH", "INACTIVE"), inactive)
        self.providerRegistry.deactivateProvider(self.tenantId, "RICH")
        with self.assertRaises(AIProviderInactive):
            self.registry.resolveModel(self.tenantId, "RICH", "INACTIVE")
        self.assertEqual(self.registry.listModels(self.tenantId), ())
        management = self.registry.listModels(self.tenantId, activeOnly=False)
        self.assertEqual(len(management), 1)
        self.assertFalse(management[0].providerIsActive)

    def testLookupWithoutProviderIsAmbiguousWhenTenantSharesModelCode(self) -> None:
        self.registry.registerModel(self._model("SHARED"), "RICH")
        self.registry.registerModel(
            self._model("SHARED", providerId=self.limitedDefinition.id),
            "LIMITED",
        )
        with self.assertRaises(AIModelAmbiguous):
            self.registry.resolveModelByCode(self.tenantId, "SHARED")
        self.assertEqual(self.registry.resolveModelByCode(self.tenantId, "SHARED", "RICH").code, "SHARED")

    def testRoutingIsDeterministicAndReturnsTraceableNonSensitiveDecision(self) -> None:
        # Provider ordering is lexical and model ordering is lexical within a provider.
        self.registry.registerModel(self._model("ZETA"), "RICH")
        self.registry.registerModel(self._model("ALPHA"), "RICH")
        request = ModelRoutingRequest(self.tenantId, modelType="LLM")
        first = self.registry.route(request)
        second = self.registry.resolveRoute(request)
        self.assertEqual(first, second)
        self.assertEqual(first.providerCode, "RICH")
        self.assertEqual(first.modelCode, "ALPHA")
        self.assertEqual(first.reason, "deterministic-default")
        self.assertFalse(first.usedFallback)
        self.assertEqual(first.tenantId, self.tenantId)
        self.assertEqual(first.descriptor.modelId, first.modelId)
        self.assertNotIn("do-not-expose", repr(first))

    def testRoutingChecksTypeCapabilityFlagsProviderFeaturesAndContextWindow(self) -> None:
        capable = self._model(
            "CAPABLE",
            inputCapability=("SUMMARIZATION",),
            contextWindow=16_000,
            supportsStreaming=True,
            supportsTools=True,
            supportsEmbeddings=True,
            supportsVision=True,
        )
        self.registry.registerModel(capable, "RICH")
        self.registry.registerModel(
            self._model("EMBED", modelType="EMBEDDING", supportsEmbeddings=True),
            "RICH",
        )
        self.assertEqual(
            self.registry.route(
                ModelRoutingRequest(
                    self.tenantId,
                    modelType="LLM",
                    capabilityCode="SUMMARIZATION",
                    requiresStreaming=True,
                    requiresTools=True,
                    requiresVision=True,
                    minimumContextWindow=16_000,
                )
            ).modelCode,
            "CAPABLE",
        )
        self.assertEqual(
            self.registry.route(
                ModelRoutingRequest(self.tenantId, modelType="EMBEDDING", requiresEmbeddings=True)
            ).modelCode,
            "EMBED",
        )
        with self.assertRaises(AIRoutingNoMatch):
            self.registry.route(ModelRoutingRequest(self.tenantId, modelType="LLM", minimumContextWindow=64_000))

    def testRoutingProviderFeatureMismatchIsRejectedEvenWhenModelFlagIsTrue(self) -> None:
        limitedModel = self._model(
            "LIMITED_MODEL",
            providerId=self.limitedDefinition.id,
            supportsStreaming=True,
            supportsTools=True,
        )
        self.registry.registerModel(limitedModel, "LIMITED")
        with self.assertRaises(AIRoutingNoMatch):
            self.registry.route(
                ModelRoutingRequest(self.tenantId, modelType="LLM", requiresStreaming=True),
                ModelRoutingPolicy(preferredProviderCode="LIMITED"),
            )
        with self.assertRaises(AIRoutingNoMatch):
            self.registry.route(
                ModelRoutingRequest(self.tenantId, modelType="LLM", requiresTools=True),
                ModelRoutingPolicy(preferredProviderCode="LIMITED"),
            )

    def testPreferredDefaultAndOrderedFallbackPolicyAreExplicit(self) -> None:
        self.registry.registerModel(self._model("PRIMARY"), "RICH")
        self.registry.registerModel(self._model("SECONDARY"), "RICH")
        strict = ModelRoutingPolicy(preferredModelCode="MISSING")
        with self.assertRaises(AIRoutingNoMatch):
            self.registry.route(ModelRoutingRequest(self.tenantId, modelType="LLM"), strict)
        fallback = RoutingPolicy(
            preferredModelCode="MISSING",
            fallbackTargets=(ModelRouteTarget(providerCode="RICH", modelCode="SECONDARY"),),
            allowFallback=True,
        )
        decision = self.registry.route(ModelRoutingRequest(self.tenantId, modelType="LLM"), fallback)
        self.assertEqual(decision.modelCode, "SECONDARY")
        self.assertEqual(decision.reason, "fallback")
        self.assertTrue(decision.usedFallback)
        default = ModelRoutingPolicy(defaultProviderCode="RICH", defaultModelCode="PRIMARY")
        self.assertEqual(
            self.registry.route(ModelRoutingRequest(self.tenantId, modelType="LLM"), default).modelCode,
            "PRIMARY",
        )

    def testRoutingNeverCrossesTenantOrUsesInactiveProvider(self) -> None:
        self.registry.registerModel(self._model("LOCAL"), "RICH")
        self.providerRegistry.deactivateProvider(self.tenantId, "RICH")
        with self.assertRaises(AIRoutingNoMatch):
            self.registry.route(ModelRoutingRequest(self.tenantId, modelType="LLM"))
        with self.assertRaises(AIRoutingNoMatch):
            self.registry.route(ModelRoutingRequest(self.otherTenantId, modelType="LLM"))

    def testRoutingInputAndPolicyValidationAreExplicit(self) -> None:
        with self.assertRaises(AIRoutingPolicyInvalid):
            ModelRoutingRequest(self.tenantId, requiredFeatures=("UNKNOWN_FEATURE",))
        with self.assertRaises(AIRoutingPolicyInvalid):
            ModelRoutingRequest(self.tenantId, minimumContextWindow=0)
        with self.assertRaises(AIRoutingPolicyInvalid):
            ModelRoutingPolicy(
                fallbackProviderCodes=("AA", "BB"),
                fallbackModelCodes=("ONE", "TWO", "THREE"),
                allowFallback=True,
            ).orderedFallbackTargets()
        with self.assertRaises(AIRoutingPolicyInvalid):
            ModelRouteTarget()

    def testAliasesAndDomainPurityAreStable(self) -> None:
        self.assertIs(AIModelRegistry, ModelRegistry)
        source = (Path(__file__).resolve().parents[2] / "apps/ai/domain/registries/modelRegistry.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "django",
            "rest_framework",
            "channels",
            "redis",
            "requests",
            "httpx",
            "openai",
            "ollama",
            "azure",
            "anthropic",
        ):
            self.assertNotIn(f"import {forbidden}", source.lower())


if __name__ == "__main__":
    unittest.main()
