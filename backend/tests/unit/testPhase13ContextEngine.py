"""Phase 13-J Context Engine and Context Builder tests (pure Python, offline)."""

from __future__ import annotations

import hashlib
import unittest
import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path

from apps.ai.domain.entities.aiRecords import AIContext
from apps.ai.domain.exceptions import (
    AIContextAlreadyRegistered,
    AIContextNotFound,
    AIContextPolicyInvalid,
    AIContextSourceInvalid,
    AIContextTenantMismatch,
)
from apps.ai.domain.policies.aiPolicies import ContextPolicy
from apps.ai.domain.services.contextEngine import (
    AIContextBuilder,
    AIContextEngine,
    ContextBuilder,
    ContextDescriptor,
    ContextEngine,
    ContextService,
    ContextSourceCandidate,
    InMemoryContextEngine,
    REDACTED_RESTRICTED_TEXT,
)
from apps.ai.domain.services.aiRules import estimateTokens
from apps.ai.domain.valueObjects.aiTypes import ContextSource


class Phase13JContextEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.requestId = uuid.uuid4()
        self.otherRequestId = uuid.uuid4()
        self.clock = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
        self.builder = ContextBuilder(now=lambda: self.clock)
        self.engine = ContextEngine(builder=self.builder)

    def source(
        self,
        entityId: str,
        content: str,
        *,
        tenantId: uuid.UUID | None = None,
        classification: str = "INTERNAL",
        authorized: bool = True,
        metadata: dict[str, object] | None = None,
    ) -> ContextSourceCandidate:
        return ContextSourceCandidate(
            tenantId=tenantId or self.tenantId,
            sourceDomain="projects",
            sourceEntityType="document",
            sourceEntityId=entityId,
            content=content,
            classification=classification,
            authorized=authorized,
            metadata=metadata,
        )

    def testBuildsRealAIContextWithDeterministicOrderCountsAndSafeFingerprint(self) -> None:
        result = self.builder.build(
            self.tenantId,
            self.requestId,
            [self.source("1", "Alpha"), self.source("2", "Beta")],
        )
        self.assertIsInstance(result.context, AIContext)
        self.assertEqual(result.context.tenantId, self.tenantId)
        self.assertEqual(result.context.requestId, self.requestId)
        self.assertEqual(result.context.content, "Alpha\n\nBeta")
        self.assertEqual(result.context.tokenCount, estimateTokens("Alpha\n\nBeta"))
        self.assertEqual(result.descriptor.sourceCount, 2)
        self.assertEqual(result.descriptor.includedSourceKeys, (
            ("projects", "document", "1"),
            ("projects", "document", "2"),
        ))
        self.assertEqual(
            result.descriptor.contentFingerprint,
            hashlib.sha256(result.context.content.encode("utf-8")).hexdigest(),
        )
        self.assertNotIn("Alpha", repr(result.descriptor))
        self.assertIsInstance(result.descriptor, ContextDescriptor)
        with self.assertRaises(FrozenInstanceError):
            result.descriptor.sourceCount = 4

    def testAuthorizationClassificationAndExternalBoundaryAreAppliedBeforeAssembly(self) -> None:
        policy = ContextPolicy(
            allowedClassifications=("PUBLIC", "RESTRICTED"),
            allowExternalProvider=False,
            redactRestricted=True,
        )
        result = self.builder.build(
            self.tenantId,
            self.requestId,
            [
                self.source("public", "public", classification="PUBLIC"),
                self.source("denied", "must not enter", authorized=False),
                self.source("internal", "internal", classification="INTERNAL"),
                self.source("restricted", "secret body", classification="RESTRICTED"),
            ],
            policy,
        )
        self.assertEqual(result.context.content, f"public\n\n{REDACTED_RESTRICTED_TEXT}")
        self.assertTrue(result.context.redacted)
        self.assertEqual(result.context.sources[1].content, REDACTED_RESTRICTED_TEXT)
        reasons = {item.sourceEntityId: item.exclusionReason for item in result.excludedSources}
        self.assertEqual(reasons["denied"], "NOT_AUTHORIZED")
        self.assertEqual(reasons["internal"], "CLASSIFICATION_NOT_PERMITTED")
        self.assertNotIn("must not enter", repr(result.excludedSources))

        external = self.builder.build(
            self.tenantId,
            self.requestId,
            [self.source("public", "public", classification="PUBLIC")],
            ContextPolicy(allowedClassifications=("PUBLIC",), allowExternalProvider=False),
            externalProvider=True,
        )
        self.assertEqual(external.context.content, "")
        self.assertEqual(external.excludedSources[0].exclusionReason, "EXTERNAL_PROVIDER_NOT_PERMITTED")
        allowedExternal = self.builder.build(
            self.tenantId,
            self.requestId,
            [self.source("public", "public", classification="PUBLIC")],
            ContextPolicy(allowedClassifications=("PUBLIC",), allowExternalProvider=True),
            externalProvider=True,
        )
        self.assertEqual(allowedExternal.context.content, "public")

    def testPermissionPredicateIsAppliedAndPredicateFailureDoesNotLeakSource(self) -> None:
        result = self.builder.build(
            self.tenantId,
            self.requestId,
            [self.source("keep", "keep"), self.source("drop", "private content")],
            permissionFilter=lambda item: item.sourceEntityId == "keep",
        )
        self.assertEqual(result.context.content, "keep")
        self.assertEqual(result.excludedSources[0].exclusionReason, "PERMISSION_FILTERED")
        with self.assertRaises(AIContextPolicyInvalid):
            self.builder.build(
                self.tenantId,
                self.requestId,
                [self.source("secret", "not exposed")],
                permissionFilter=lambda item: 1 / 0,
            )

    def testDeduplicatesEmptySourcesAndEnforcesSourceCharacterAndTokenBudgets(self) -> None:
        duplicate = self.source("same", "first")
        result = self.builder.build(
            self.tenantId,
            self.requestId,
            [
                duplicate,
                self.source("same", "second"),
                self.source("empty", ""),
                self.source("third", "third"),
            ],
            ContextPolicy(maxSources=1, maxCharacters=20, maxTokens=10),
        )
        self.assertEqual(result.context.content, "first")
        reasons = {item.sourceEntityId: item.exclusionReason for item in result.excludedSources}
        self.assertEqual(reasons["same"], "DUPLICATE_SOURCE")
        self.assertEqual(reasons["empty"], "EMPTY_CONTENT")
        self.assertEqual(reasons["third"], "MAX_SOURCES")

        byCharacters = self.builder.build(
            self.tenantId,
            self.requestId,
            [self.source("long", "1234567890")],
            ContextPolicy(maxCharacters=5),
        )
        self.assertEqual(byCharacters.context.content, "")
        self.assertEqual(byCharacters.excludedSources[0].exclusionReason, "MAX_CHARACTERS")

        byTokens = self.builder.build(
            self.tenantId,
            self.requestId,
            [self.source("tokens", "one two three four")],
            ContextPolicy(maxTokens=1),
        )
        self.assertEqual(byTokens.context.content, "")
        self.assertEqual(byTokens.excludedSources[0].exclusionReason, "MAX_TOKENS")

    def testTenantScopedSourceIsRequiredAndCrossTenantSourcesAreRejected(self) -> None:
        with self.assertRaises(AIContextSourceInvalid):
            self.builder.build(self.tenantId, self.requestId, [ContextSource("d", "t", "1", "raw")])
        with self.assertRaises(AIContextTenantMismatch):
            self.builder.build(
                self.tenantId,
                self.requestId,
                [self.source("cross", "cross tenant", tenantId=self.otherTenantId)],
            )
        with self.assertRaises(AIContextSourceInvalid):
            ContextSourceCandidate(self.tenantId, "", "type", "id", "content")
        with self.assertRaises(AIContextSourceInvalid):
            ContextSourceCandidate(self.tenantId, "domain", "type", "id", "content", classification="UNKNOWN")

    def testSensitiveMetadataIsRedactedAndNotPresentInContextEntityOrDescriptors(self) -> None:
        result = self.builder.build(
            self.tenantId,
            self.requestId,
            [
                self.source(
                    "metadata",
                    "safe content",
                    metadata={
                        "api_key": "sk-secret",
                        "nested": {"password": "pw", "safe": "value"},
                    },
                )
            ],
        )
        metadata = result.context.sources[0].metadata
        self.assertIsNotNone(metadata)
        self.assertNotIn("api_key", metadata)
        self.assertNotIn("password", metadata["nested"])
        self.assertEqual(metadata["nested"]["safe"], "value")
        self.assertNotIn("sk-secret", repr(result))
        self.assertNotIn("password", repr(result))

    def testEngineRegistersTenantAwareContextsProtectsSnapshotsAndProvidesSafeLookup(self) -> None:
        contextId = uuid.uuid4()
        result = self.engine.buildContext(
            self.tenantId,
            self.requestId,
            [self.source("1", "snapshot", metadata={"safe": "original"})],
            contextId=contextId,
        )
        caller = result.context
        caller.content = "caller mutation"
        caller.sources = ()
        fetched = self.engine.getContext(self.tenantId, contextId)
        self.assertEqual(fetched.content, "snapshot")
        self.assertEqual(len(fetched.sources), 1)
        fetched.content = "second mutation"
        fetched.sources[0].metadata["safe"] = "mutated"
        stable = self.engine.getContext(self.tenantId, contextId)
        self.assertEqual(stable.content, "snapshot")
        self.assertEqual(stable.sources[0].metadata["safe"], "original")
        with self.assertRaises(AIContextAlreadyRegistered):
            self.engine.registerContext(result.context)
        with self.assertRaises(AIContextNotFound):
            self.engine.getContext(self.otherTenantId, contextId)
        with self.assertRaises(AIContextNotFound):
            self.engine.getContext(self.tenantId, uuid.uuid4())

    def testEngineSupportsTenantAwareRequestLookupAndDescriptorListing(self) -> None:
        first = self.engine.buildContext(self.tenantId, self.requestId, [self.source("1", "one")])
        self.engine.buildContext(self.tenantId, self.otherRequestId, [self.source("2", "two")])
        self.engine.buildContext(
            self.otherTenantId,
            self.requestId,
            [self.source("3", "other", tenantId=self.otherTenantId)],
        )
        self.assertEqual(self.engine.latestForRequest(self.tenantId, self.requestId).context.id, first.context.id)
        self.assertIsNone(self.engine.latestForRequest(self.otherTenantId, self.otherRequestId))
        self.assertEqual(len(self.engine.listContexts(self.tenantId)), 2)
        self.assertEqual(len(self.engine.listContexts(self.tenantId, requestId=self.requestId)), 1)
        self.assertEqual(len(self.engine.listContexts(self.otherTenantId)), 1)
        descriptor = self.engine.describeContext(self.tenantId, first.context.id)
        self.assertFalse(hasattr(descriptor, "content"))

    def testRegisterExistingContextValidatesTenantDescriptorAndRejectsUnscopedSources(self) -> None:
        context = AIContext(
            tenantId=self.tenantId,
            requestId=self.requestId,
            content="existing",
            tokenCount=estimateTokens("existing"),
            createdAt=self.clock,
        )
        registered = ContextEngine(now=lambda: self.clock).registerContext(context)
        self.assertEqual(registered.id, context.id)
        populated = AIContext(
            tenantId=self.tenantId,
            requestId=self.requestId,
            sources=(ContextSource("d", "t", "1", "existing"),),
            content="existing",
            tokenCount=estimateTokens("existing"),
            createdAt=self.clock,
        )
        with self.assertRaises(AIContextSourceInvalid):
            ContextEngine(now=lambda: self.clock).registerContext(populated)
        badDescriptor = ContextDescriptor(
            tenantId=self.otherTenantId,
            requestId=self.requestId,
            contextId=context.id,
            sourceCount=1,
            includedSourceKeys=(("d", "t", "1"),),
            excludedSourceCount=0,
            contentLength=8,
            tokenCount=1,
            contentFingerprint="x",
            redacted=True,
            externalProvider=False,
            createdAt=self.clock,
        )
        with self.assertRaises(AIContextTenantMismatch):
            ContextEngine(now=lambda: self.clock).registerContext(context, descriptor=badDescriptor)

    def testAliasesClearAndPurityBoundary(self) -> None:
        self.assertIs(AIContextBuilder, ContextBuilder)
        self.assertIs(AIContextEngine, ContextEngine)
        self.assertIs(ContextService, ContextEngine)
        self.assertIs(InMemoryContextEngine, ContextEngine)
        self.engine.buildContext(self.tenantId, self.requestId, [self.source("1", "one")])
        self.engine.clear()
        self.assertEqual(self.engine.listContexts(self.tenantId), ())
        source = (Path(__file__).resolve().parents[2] / "apps/ai/domain/services/contextEngine.py").read_text(
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
