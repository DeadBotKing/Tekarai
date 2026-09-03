"""Phase 13-D Provider Registry tests (pure Python and offline)."""

from __future__ import annotations

import unittest
import uuid
from dataclasses import FrozenInstanceError
from pathlib import Path

from apps.ai.domain.entities.aiRecords import AIProvider
from apps.ai.domain.exceptions import (
    AIProviderAlreadyRegistered,
    AIProviderInactive,
    AIProviderNotRegistered,
    AIProviderRegistrationInvalid,
)
from apps.ai.domain.ports import DeterministicAIProvider, ProviderCapabilities
from apps.ai.domain.registries.providerRegistry import (
    AIProviderRegistry,
    InMemoryProviderRegistry,
    ProviderRegistration,
    ProviderRegistry,
)


class MismatchedProvider(DeterministicAIProvider):
    providerCode = "OTHER"


class BrokenProvider:
    """Intentionally incomplete object for runtime Port validation."""


class Phase13DProviderRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.provider = DeterministicAIProvider()
        self.registry = ProviderRegistry()

    def _definition(self, tenantId: uuid.UUID | None = None, code: str = "DETERMINISTIC") -> AIProvider:
        return AIProvider(
            tenantId=tenantId or self.tenantId,
            code=code,
            name="Offline Deterministic",
            providerType="LOCAL",
            configurationReference="secret-ref-only",
            metadata={"notForPersistence": True},
        )

    def testRegisterResolveAndDescribeAreTenantScoped(self) -> None:
        registration = self.registry.registerProvider(self._definition(), self.provider)
        descriptor = registration.descriptor()
        self.assertIsInstance(registration, ProviderRegistration)
        self.assertEqual(descriptor.tenantId, self.tenantId)
        self.assertEqual(descriptor.code, "DETERMINISTIC")
        self.assertEqual(self.registry.resolve(self.tenantId, "deterministic"), self.provider)
        self.assertEqual(self.registry.describeProvider(self.tenantId, "DETERMINISTIC"), descriptor)
        self.assertEqual(self.registry.listProviders(self.tenantId), (descriptor,))
        self.assertEqual(self.registry.listProviders(self.otherTenantId), ())
        with self.assertRaises(AIProviderNotRegistered):
            self.registry.resolve(self.otherTenantId, "DETERMINISTIC")

    def testDuplicateRegistrationRequiresExplicitReplace(self) -> None:
        self.registry.register(self._definition(), self.provider)
        with self.assertRaises(AIProviderAlreadyRegistered):
            self.registry.register(self._definition(), self.provider)
        replacement = DeterministicAIProvider()
        replaced = self.registry.register(self._definition(), replacement, replace=True)
        self.assertIs(self.registry.resolve(self.tenantId, "DETERMINISTIC"), replacement)
        self.assertEqual(replaced.providerCode, "DETERMINISTIC")

    def testRegistrationRejectsBrokenOrMismatchedAdapters(self) -> None:
        with self.assertRaises(AIProviderRegistrationInvalid):
            self.registry.register(self._definition(), BrokenProvider())
        with self.assertRaises(AIProviderRegistrationInvalid):
            self.registry.register(self._definition(), MismatchedProvider())
        wrongCapabilities = DeterministicAIProvider()
        wrongCapabilities.capabilities = ProviderCapabilities(providerCode="OTHER")
        with self.assertRaises(AIProviderRegistrationInvalid):
            self.registry.register(self._definition(), wrongCapabilities)

    def testActivationDeactivationAndActiveListingAreExplicit(self) -> None:
        self.registry.register(self._definition(), self.provider)
        self.registry.deactivateProvider(self.tenantId, "DETERMINISTIC")
        self.assertEqual(self.registry.listProviders(self.tenantId), ())
        self.assertEqual(len(self.registry.listProviders(self.tenantId, activeOnly=False)), 1)
        with self.assertRaises(AIProviderInactive):
            self.registry.resolveProvider(self.tenantId, "DETERMINISTIC")
        descriptor = self.registry.activateProvider(self.tenantId, "DETERMINISTIC")
        self.assertTrue(descriptor.isActive)
        self.assertIs(self.registry.resolveProvider(self.tenantId, "DETERMINISTIC"), self.provider)

    def testCapabilityAndHealthDelegationStayWithinRegisteredTenant(self) -> None:
        self.registry.register(self._definition(), self.provider)
        self.assertTrue(self.registry.supports(self.tenantId, "DETERMINISTIC", "STREAMING"))
        self.assertFalse(self.registry.supports(self.tenantId, "DETERMINISTIC", "TOOLS"))
        health = self.registry.healthCheck(self.tenantId, "DETERMINISTIC", model="test")
        self.assertEqual(health.status, "HEALTHY")
        with self.assertRaises(AIProviderNotRegistered):
            self.registry.healthCheck(self.otherTenantId, "DETERMINISTIC")

    def testDescriptorsAreNonSensitiveAndImmutable(self) -> None:
        self.registry.register(self._definition(), self.provider)
        descriptor = self.registry.describeProvider(self.tenantId, "DETERMINISTIC")
        self.assertNotIn("secret-ref-only", repr(descriptor))
        self.assertNotIn("notForPersistence", repr(descriptor))
        with self.assertRaises(FrozenInstanceError):
            descriptor.code = "OTHER"

    def testAliasesConstructorUnregisterAndClearWork(self) -> None:
        self.assertIs(AIProviderRegistry, ProviderRegistry)
        self.assertIs(InMemoryProviderRegistry, ProviderRegistry)
        registration = ProviderRegistration(self._definition(), self.provider)
        registry = ProviderRegistry((registration,))
        self.assertEqual(len(registry.listProviders(self.tenantId)), 1)
        registry.unregister(self.tenantId, "DETERMINISTIC")
        with self.assertRaises(AIProviderNotRegistered):
            registry.getRegistration(self.tenantId, "DETERMINISTIC")
        registry.register(self._definition(), self.provider)
        registry.clear()
        self.assertEqual(registry.listProviders(self.tenantId, activeOnly=False), ())

    def testRegistryModuleIsFrameworkAndVendorFree(self) -> None:
        source = (
            Path(__file__).resolve().parents[2] / "apps/ai/domain/registries/providerRegistry.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("django", "rest_framework", "channels", "redis", "openai", "ollama", "azure", "anthropic"):
            self.assertNotIn(f"import {forbidden}", source.lower())


if __name__ == "__main__":
    unittest.main()
