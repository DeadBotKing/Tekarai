"""Phase 13-I Prompt Platform and Versioning tests (pure Python, offline)."""

from __future__ import annotations

import unittest
import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

from apps.ai.domain.entities.aiRecords import AIPrompt, AIPromptVersion
from apps.ai.domain.exceptions import (
    AIPromptAlreadyRegistered,
    AIPromptLifecycleInvalid,
    AIPromptNotFound,
    AIPromptOutputSchemaInvalid,
    AIPromptTemplateInvalid,
    AIPromptVersionAlreadyRegistered,
    AIPromptVersionImmutable,
    AIPromptVersionNotFound,
)
from apps.ai.domain.services.promptPlatform import (
    AIPromptPlatformService,
    AIPromptRegistry,
    InMemoryPromptRegistry,
    PromptDescriptor,
    PromptPlatformService,
    PromptRegistry,
    PromptVersionDescriptor,
    PromptVersioningService,
    RenderedPrompt,
)


class Phase13IPromptPlatformTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.userId = uuid.uuid4()
        self.clock = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
        self.platform = PromptPlatformService(now=lambda: self.clock)
        self.prompt = self.platform.createPrompt(
            self.tenantId,
            "PROJECT_SUMMARY",
            "Project summary",
            description="Summarize an authorized project",
        )

    def testPromptAndVersionCreationActiveResolutionAndSafeDescriptors(self) -> None:
        version = self.platform.createVersion(
            self.tenantId,
            self.prompt.id,
            "Summarize {project_name} for {audience}.",
            variables=("project_name", "audience"),
            createdBy=self.userId,
            activate=True,
        )
        resolved = self.platform.getActiveVersion(self.tenantId, "project_summary")
        self.assertEqual(resolved.id, version.id)
        rendered = self.platform.render(
            self.tenantId,
            "PROJECT_SUMMARY",
            {"project_name": "Apollo", "audience": "leadership"},
        )
        self.assertIsInstance(rendered, RenderedPrompt)
        self.assertEqual(rendered.asText(), "Summarize Apollo for leadership.")
        descriptor = self.platform.describePrompt(self.tenantId, "PROJECT_SUMMARY")
        versionDescriptor = self.platform.describeVersion(self.tenantId, version.id)
        self.assertIsInstance(descriptor, PromptDescriptor)
        self.assertIsInstance(versionDescriptor, PromptVersionDescriptor)
        self.assertEqual(descriptor.activeVersion, 1)
        self.assertEqual(descriptor.versionCount, 1)
        self.assertEqual(versionDescriptor.variables, ("project_name", "audience"))
        self.assertNotIn("Summarize {project_name}", repr(descriptor))
        self.assertNotIn("leadership", repr(rendered))

    def testVersioningIsMonotonicAndPreviousVersionsCannotBeOverwritten(self) -> None:
        first = self.platform.createVersion(self.tenantId, self.prompt.id, "Version {value}", variables=("value",))
        second = self.platform.createVersion(
            self.tenantId,
            self.prompt.id,
            "Version two {value}",
            variables=("value",),
            version=2,
            activate=True,
        )
        third = self.platform.createVersion(self.tenantId, self.prompt.id, "Version three {value}", variables=("value",))
        self.assertEqual((first.version, second.version, third.version), (1, 2, 3))
        with self.assertRaises(AIPromptVersionAlreadyRegistered):
            self.platform.createVersion(self.tenantId, self.prompt.id, "Duplicate {value}", variables=("value",), version=2)
        with self.assertRaises(AIPromptLifecycleInvalid):
            self.platform.createVersion(self.tenantId, self.prompt.id, "Invalid version zero", version=0)
        with self.assertRaises(AIPromptVersionImmutable):
            self.platform.registerVersion(
                AIPromptVersion(
                    self.tenantId,
                    self.prompt.id,
                    2,
                    "Overwrite {value}",
                    variables=("value",),
                ),
                replace=True,
            )
        snapshot = self.platform.getVersion(self.tenantId, first.id)
        snapshot.template = "caller mutation must not alter registry"
        self.assertEqual(self.platform.getVersion(self.tenantId, first.id).template, "Version {value}")
        self.assertEqual(self.platform.listVersions(self.tenantId, self.prompt.id)[1].version, 2)

    def testActivationKeepsOneActiveVersionAndPromptLifecycleIsExplicit(self) -> None:
        first = self.platform.createVersion(self.tenantId, self.prompt.id, "One", activate=True)
        second = self.platform.createVersion(self.tenantId, self.prompt.id, "Two")
        self.platform.activateVersion(self.tenantId, self.prompt.id, second.id)
        self.assertFalse(self.platform.getVersion(self.tenantId, first.id).isActive)
        self.assertEqual(self.platform.getActiveVersion(self.tenantId, "PROJECT_SUMMARY").id, second.id)
        self.platform.deactivateVersion(self.tenantId, self.prompt.id, second.id)
        with self.assertRaises(AIPromptVersionNotFound):
            self.platform.getActiveVersion(self.tenantId, "PROJECT_SUMMARY")
        self.platform.activateVersion(self.tenantId, self.prompt.id, first.id)
        self.platform.deactivatePrompt(self.tenantId, "PROJECT_SUMMARY")
        with self.assertRaises(AIPromptLifecycleInvalid):
            self.platform.render(self.tenantId, "PROJECT_SUMMARY", {})
        self.platform.activatePrompt(self.tenantId, "PROJECT_SUMMARY")
        self.assertEqual(self.platform.render(self.tenantId, "PROJECT_SUMMARY", {}).asText(), "One")

    def testTemplateVariablesAreDeclaredAndRenderingIsRestricted(self) -> None:
        with self.assertRaises(AIPromptTemplateInvalid):
            self.platform.createVersion(self.tenantId, self.prompt.id, "Undeclared {name}")
        with self.assertRaises(AIPromptTemplateInvalid):
            self.platform.createVersion(self.tenantId, self.prompt.id, "Unsafe {user.name}", variables=("user",))
        with self.assertRaises(AIPromptTemplateInvalid):
            self.platform.createVersion(self.tenantId, self.prompt.id, "Unsafe {value!r}", variables=("value",))
        with self.assertRaises(AIPromptTemplateInvalid):
            self.platform.createVersion(self.tenantId, self.prompt.id, "Unsafe {value:>10}", variables=("value",))
        self.platform.createVersion(
            self.tenantId,
            self.prompt.id,
            "Literal {{value}} and {value}",
            variables=("value",),
            activate=True,
        )
        with self.assertRaises(AIPromptTemplateInvalid):
            self.platform.render(self.tenantId, "PROJECT_SUMMARY", {})
        with self.assertRaises(AIPromptTemplateInvalid):
            self.platform.render(self.tenantId, "PROJECT_SUMMARY", {"value": "ok", "extra": "not declared"})
        self.assertEqual(self.platform.render(self.tenantId, "PROJECT_SUMMARY", {"value": "ok"}).asText(), "Literal {value} and ok")

    def testPromptDuplicateAndSameCodeTenantIsolation(self) -> None:
        with self.assertRaises(AIPromptAlreadyRegistered):
            self.platform.createPrompt(self.tenantId, "PROJECT_SUMMARY", "Duplicate")
        other = self.platform.createPrompt(self.otherTenantId, "PROJECT_SUMMARY", "Other tenant")
        self.assertNotEqual(other.id, self.prompt.id)
        with self.assertRaises(AIPromptNotFound):
            self.platform.getPrompt(self.otherTenantId, "MISSING")
        with self.assertRaises(AIPromptNotFound):
            self.platform.getPrompt(self.otherTenantId, "PROJECT_SUMMARY_NOT_REGISTERED")
        self.assertEqual(len(self.platform.listPrompts(self.otherTenantId)), 1)
        with self.assertRaises(AIPromptNotFound):
            self.platform.getPromptById(self.otherTenantId, self.prompt.id)

    def testCrossTenantVersionAccessAndAssociationAreRejected(self) -> None:
        version = self.platform.createVersion(self.tenantId, self.prompt.id, "Hello")
        with self.assertRaises(AIPromptVersionNotFound):
            self.platform.getVersion(self.otherTenantId, version.id)
        with self.assertRaises(AIPromptNotFound):
            self.platform.createVersion(self.otherTenantId, self.prompt.id, "Wrong tenant")
        otherPrompt = self.platform.createPrompt(self.otherTenantId, "OTHER_PROMPT", "Other")
        with self.assertRaises(AIPromptNotFound):
            self.platform.activateVersion(self.tenantId, otherPrompt.id, version.id)
        with self.assertRaises(AIPromptVersionNotFound):
            self.platform.renderVersion(self.otherTenantId, version.id, {})

    def testOutputSchemaAndModelConstraintsAreValidatedAndFingerprintIsSafe(self) -> None:
        schema = {
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
            "additionalProperties": False,
        }
        version = self.platform.createVersion(
            self.tenantId,
            self.prompt.id,
            "Return {subject}",
            variables=("subject",),
            outputSchema=schema,
            modelConstraints={"modelType": "LLM", "minimumContextWindow": 1000},
        )
        descriptor = self.platform.describeVersion(self.tenantId, version.id)
        self.assertTrue(descriptor.hasOutputSchema)
        self.assertTrue(descriptor.outputSchemaFingerprint)
        self.assertTrue(descriptor.hasModelConstraints)
        self.assertNotIn("minimumContextWindow", repr(descriptor))
        with self.assertRaises(AIPromptOutputSchemaInvalid):
            self.platform.createVersion(
                self.tenantId,
                self.prompt.id,
                "Bad",
                outputSchema={"type": "unknown"},
            )
        with self.assertRaises(AIPromptLifecycleInvalid):
            self.platform.createVersion(
                self.tenantId,
                self.prompt.id,
                "Bad",
                modelConstraints={"api_key": "must-not-be-stored"},
            )

    def testRegisterExistingEntitiesReplacePromptAndExplicitActivation(self) -> None:
        promptId = uuid.uuid4()
        external = AIPrompt(
            self.otherTenantId,
            "EXTERNAL_PROMPT",
            "External",
            id=promptId,
            isActive=False,
        )
        registered = self.platform.registerPrompt(external)
        self.assertEqual(registered.id, promptId)
        replacement = AIPrompt(
            self.otherTenantId,
            "EXTERNAL_PROMPT",
            "External renamed",
            id=promptId,
            isActive=True,
        )
        self.platform.registerPrompt(replacement, replace=True)
        self.assertEqual(self.platform.getPrompt(self.otherTenantId, "EXTERNAL_PROMPT").name, "External renamed")
        version = AIPromptVersion(self.otherTenantId, promptId, 1, "External text")
        self.platform.registerVersion(version)
        with self.assertRaises(AIPromptVersionNotFound):
            self.platform.render(self.otherTenantId, "EXTERNAL_PROMPT", {})
        self.platform.activateVersion(self.otherTenantId, promptId, version.id)
        self.assertEqual(self.platform.render(self.otherTenantId, "EXTERNAL_PROMPT", {}).asText(), "External text")

    def testSafeCopiesAndAliases(self) -> None:
        promptSnapshot = self.platform.getPrompt(self.tenantId, "PROJECT_SUMMARY")
        promptSnapshot.name = "mutated copy"
        self.assertEqual(self.platform.getPrompt(self.tenantId, "PROJECT_SUMMARY").name, "Project summary")
        self.assertIs(AIPromptPlatformService, PromptPlatformService)
        self.assertIs(AIPromptRegistry, PromptPlatformService)
        self.assertIs(InMemoryPromptRegistry, PromptPlatformService)
        self.assertIs(PromptRegistry, PromptPlatformService)
        self.assertIs(PromptVersioningService, PromptPlatformService)
        descriptor = self.platform.describePrompt(self.tenantId, "PROJECT_SUMMARY")
        with self.assertRaises(FrozenInstanceError):
            descriptor.code = "OTHER"
        self.platform.clear()
        self.assertEqual(self.platform.listPrompts(self.tenantId), ())

    def testPureDomainBoundaryAndNoSecretOrProviderImports(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "apps/ai/domain/services/promptPlatform.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "django",
            "rest_framework",
            "redis",
            "requests",
            "httpx",
            "openai",
            "ollama",
            "azure",
            "anthropic",
            "boto3",
        ):
            self.assertNotIn(f"import {forbidden}", source.lower())
        self.assertNotIn("sk-", source.lower())
        self.assertNotIn("bearer ", source.lower())


if __name__ == "__main__":
    unittest.main()
