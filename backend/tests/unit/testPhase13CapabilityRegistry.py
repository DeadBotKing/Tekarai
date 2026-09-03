"""Phase 13-F Capability Registry tests (pure Python, offline)."""

from __future__ import annotations

import unittest
import uuid
from dataclasses import FrozenInstanceError
from pathlib import Path

from apps.ai.domain.entities.aiRecords import AICapability, AIModel
from apps.ai.domain.exceptions import (
    AICapabilityAlreadyRegistered,
    AICapabilityInactive,
    AICapabilityModelNotSupported,
    AICapabilityNotRegistered,
    AICapabilityPolicyInvalid,
    AICapabilityRequestTypeUnsupported,
    AICapabilityRoutingNoMatch,
    AICapabilityRegistrationInvalid,
)
from apps.ai.domain.ports import DeterministicAIProvider
from apps.ai.domain.registries.capabilityRegistry import (
    AICapabilityRegistry,
    CapabilityDescriptor,
    CapabilityRegistry,
    CapabilityRoutingRequest,
    CapabilitySelectionRequest,
    RegisteredCapability,
)
from apps.ai.domain.registries.modelRegistry import ModelRegistry, ModelRoutingPolicy
from apps.ai.domain.registries.providerRegistry import ProviderRegistry
from apps.ai.domain.entities.aiRecords import AIProvider


class Phase13FCapabilityRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.providerRegistry = ProviderRegistry()
        self.provider = DeterministicAIProvider()
        self.providerDefinition = AIProvider(
            tenantId=self.tenantId,
            code="DETERMINISTIC",
            name="Offline provider",
            providerType="LOCAL",
            configurationReference="configuration-reference-only",
        )
        self.providerRegistry.register(self.providerDefinition, self.provider)
        self.modelRegistry = ModelRegistry(self.providerRegistry)
        self.capabilityRegistry = CapabilityRegistry(self.modelRegistry)

    def _capability(
        self,
        code: str = "SUMMARIZATION",
        *,
        tenantId: uuid.UUID | None = None,
        isActive: bool = True,
        policy: dict[str, object] | None = None,
    ) -> AICapability:
        return AICapability(
            tenantId=tenantId or self.tenantId,
            code=code,
            name=f"{code} capability",
            description="A tenant-scoped business capability",
            isActive=isActive,
            policy=policy or {},
        )

    def _model(
        self,
        code: str = "SUMMARY_MODEL",
        *,
        isActive: bool = True,
        inputCapability: tuple[str, ...] = ("SUMMARIZATION",),
    ) -> AIModel:
        return AIModel(
            tenantId=self.tenantId,
            providerId=self.providerDefinition.id,
            code=code,
            name=f"{code} model",
            modelType="LLM",
            inputCapability=inputCapability,
            isActive=isActive,
        )

    def testRegisterResolveDescribeAndTenantIsolation(self) -> None:
        capability = self._capability()
        registration = self.capabilityRegistry.registerCapability(capability)
        self.assertIsInstance(registration, RegisteredCapability)
        self.assertEqual(registration.tenantId, self.tenantId)
        self.assertEqual(registration.capabilityCode, "SUMMARIZATION")
        self.assertIs(self.capabilityRegistry.resolve(self.tenantId, "summarization"), capability)
        descriptor = self.capabilityRegistry.describeCapability(self.tenantId, "SUMMARIZATION")
        self.assertIsInstance(descriptor, CapabilityDescriptor)
        self.assertEqual(descriptor.supportedRequestTypes[0], "GENERATE")
        self.assertTrue(self.capabilityRegistry.supportsRequestType(self.tenantId, "SUMMARIZATION", "SUMMARIZE"))
        self.assertEqual(self.capabilityRegistry.listCapabilities(self.otherTenantId), ())
        with self.assertRaises(AICapabilityNotRegistered):
            self.capabilityRegistry.resolve(self.otherTenantId, "SUMMARIZATION")
        with self.assertRaises(FrozenInstanceError):
            descriptor.code = "OTHER"

    def testDuplicateReplaceAndSameCodeAcrossTenants(self) -> None:
        self.capabilityRegistry.register(self._capability("CLASSIFICATION"))
        with self.assertRaises(AICapabilityAlreadyRegistered):
            self.capabilityRegistry.register(self._capability("CLASSIFICATION"))
        replacement = self._capability("CLASSIFICATION", isActive=False)
        self.capabilityRegistry.register(replacement, replace=True)
        self.assertEqual(self.capabilityRegistry.listCapabilities(self.tenantId), ())
        other = self._capability("CLASSIFICATION", tenantId=self.otherTenantId)
        self.capabilityRegistry.registerCapability(other)
        self.assertEqual(len(self.capabilityRegistry.listCapabilities(self.otherTenantId)), 1)

    def testActivationAndExplicitRequestTypePolicy(self) -> None:
        inactive = self._capability("EXTRACTION", isActive=False)
        self.capabilityRegistry.registerCapability(inactive)
        with self.assertRaises(AICapabilityInactive):
            self.capabilityRegistry.resolveCapability(self.tenantId, "EXTRACTION")
        self.assertFalse(self.capabilityRegistry.supportsRequestType(self.tenantId, "EXTRACTION", "EXTRACT"))
        descriptor = self.capabilityRegistry.activateCapability(self.tenantId, "EXTRACTION")
        self.assertTrue(descriptor.isActive)

        restricted = self._capability(
            "DOCUMENT_ANALYSIS",
            policy={"allowedRequestTypes": ("ASK", "EXTRACT")},
        )
        self.capabilityRegistry.registerCapability(restricted)
        self.assertTrue(self.capabilityRegistry.supportsRequestType(self.tenantId, "DOCUMENT_ANALYSIS", "ASK"))
        self.assertFalse(self.capabilityRegistry.supportsRequestType(self.tenantId, "DOCUMENT_ANALYSIS", "SUMMARIZE"))
        restricted.policy["allowedRequestTypes"] = ("SUMMARIZE",)
        self.assertTrue(self.capabilityRegistry.supportsRequestType(self.tenantId, "DOCUMENT_ANALYSIS", "SUMMARIZE"))
        with self.assertRaises(AICapabilityRequestTypeUnsupported):
            self.capabilityRegistry.resolveForRequest(
                self.tenantId,
                "DOCUMENT_ANALYSIS",
                "ASK",
            )
        self.capabilityRegistry.deactivateCapability(self.tenantId, "DOCUMENT_ANALYSIS")
        self.assertEqual(self.capabilityRegistry.listCapabilities(self.tenantId), ((descriptor),))

    def testCapabilityPolicyValidationAndCustomCapability(self) -> None:
        with self.assertRaises(AICapabilityPolicyInvalid):
            self.capabilityRegistry.registerCapability(
                self._capability(
                    "PREDICTION",
                    policy={"allowedRequestTypes": ("UNKNOWN",)},
                )
            )
        empty = self._capability("RECOMMENDATION", policy={"allowedRequestTypes": ()})
        self.capabilityRegistry.registerCapability(empty)
        self.assertFalse(self.capabilityRegistry.supportsRequestType(self.tenantId, "RECOMMENDATION", "RECOMMEND"))
        custom = self._capability("CUSTOM_FINANCE_INSIGHT")
        self.capabilityRegistry.registerCapability(custom)
        self.assertEqual(self.capabilityRegistry.resolve(self.tenantId, "custom_finance_insight"), custom)

    def testCapabilityDescriptorAndRegistrationDoNotExposePolicyMetadata(self) -> None:
        capability = self._capability(
            "KNOWLEDGE_RETRIEVAL",
            policy={
                "allowedRequestTypes": ("ASK",),
                "internalMarker": "must-not-appear",
            },
        )
        registration = self.capabilityRegistry.registerCapability(capability)
        descriptor = registration.descriptor()
        self.assertNotIn("must-not-appear", repr(descriptor))
        self.assertNotIn("must-not-appear", repr(registration))
        self.assertNotIn("allowedRequestTypes", repr(descriptor))

    def testModelCapabilityListingUsesActiveTenantOwnedModels(self) -> None:
        capability = self._capability("SUMMARIZATION", policy={"allowedRequestTypes": ("SUMMARIZE",)})
        self.capabilityRegistry.registerCapability(capability)
        model = self._model()
        self.modelRegistry.registerModel(model, "DETERMINISTIC")
        listed = self.capabilityRegistry.listModelsForCapability(
            self.tenantId,
            "SUMMARIZATION",
            requestType="SUMMARIZE",
        )
        self.assertEqual(tuple(descriptor.code for descriptor in listed), ("SUMMARY_MODEL",))
        self.assertTrue(self.capabilityRegistry.modelSupportsCapability(self.tenantId, "SUMMARIZATION", model))
        otherModel = AIModel(
            tenantId=self.otherTenantId,
            providerId=self.providerDefinition.id,
            code="OTHER_MODEL",
            name="Other model",
        )
        self.assertFalse(self.capabilityRegistry.supportsModel(self.tenantId, "SUMMARIZATION", otherModel))
        with self.assertRaises(AICapabilityModelNotSupported):
            self.capabilityRegistry.modelSupportsCapability(self.tenantId, "SUMMARIZATION", object())

    def testCapabilityRoutingChecksCapabilityThenDelegatesToModelRouting(self) -> None:
        capability = self._capability("SUMMARIZATION", policy={"allowedRequestTypes": ("SUMMARIZE",)})
        self.capabilityRegistry.registerCapability(capability)
        self.modelRegistry.registerModel(self._model(), "DETERMINISTIC")
        request = CapabilityRoutingRequest(
            self.tenantId,
            "SUMMARIZATION",
            requestType="SUMMARIZE",
            modelType="LLM",
        )
        decision = self.capabilityRegistry.routeForCapability(request)
        self.assertEqual(decision.modelCode, "SUMMARY_MODEL")
        self.assertEqual(decision.tenantId, self.tenantId)
        self.assertIs(self.capabilityRegistry.resolveModelForCapability(request), self.modelRegistry.resolveModel(self.tenantId, "DETERMINISTIC", "SUMMARY_MODEL"))

        self.capabilityRegistry.deactivateCapability(self.tenantId, "SUMMARIZATION")
        with self.assertRaises(AICapabilityInactive):
            self.capabilityRegistry.routeForCapability(request)

    def testCapabilityRoutingNoMatchAndModelRegistryBoundary(self) -> None:
        capability = self._capability("SUMMARIZATION")
        self.capabilityRegistry.registerCapability(capability)
        self.modelRegistry.registerModel(self._model(inputCapability=("CLASSIFICATION",)), "DETERMINISTIC")
        request = CapabilitySelectionRequest(self.tenantId, "SUMMARIZATION", requestType="SUMMARIZE", modelType="LLM")
        with self.assertRaises(AICapabilityRoutingNoMatch):
            self.capabilityRegistry.routeForCapability(request)
        standalone = CapabilityRegistry()
        standalone.registerCapability(self._capability("EXTRACTION"))
        with self.assertRaises(AICapabilityRegistrationInvalid):
            standalone.listModelsForCapability(self.tenantId, "EXTRACTION")

    def testAliasesUnregisterClearAndPurity(self) -> None:
        self.assertIs(AICapabilityRegistry, CapabilityRegistry)
        self.capabilityRegistry.registerCapability(self._capability("TRANSLATION"))
        self.capabilityRegistry.unregister(self.tenantId, "TRANSLATION")
        with self.assertRaises(AICapabilityNotRegistered):
            self.capabilityRegistry.getRegistration(self.tenantId, "TRANSLATION")
        self.capabilityRegistry.registerCapability(self._capability("TRANSLATION"))
        self.capabilityRegistry.clear()
        self.assertEqual(self.capabilityRegistry.listCapabilities(self.tenantId, activeOnly=False), ())
        source = (Path(__file__).resolve().parents[2] / "apps/ai/domain/registries/capabilityRegistry.py").read_text(
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
