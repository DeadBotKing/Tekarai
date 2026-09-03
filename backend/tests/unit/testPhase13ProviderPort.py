"""Phase 13-C provider contract tests (pure Python, offline, no SDK)."""

from __future__ import annotations

import unittest
import uuid
from dataclasses import FrozenInstanceError
from pathlib import Path

from apps.ai.domain.ports import (
    AIProviderPort,
    DeterministicAIProvider,
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderRequestContext,
    requireProviderFeature,
    validateEmbeddingVector,
    validateGenerationResult,
)
from apps.sharedKernel.domain.errors import ValidationFailedError


class Phase13CProviderPortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = DeterministicAIProvider()
        self.tenantId = uuid.uuid4()
        self.requestId = uuid.uuid4()

    def testRequestContextIsTenantAndTraceAwareWithoutProviderSecrets(self) -> None:
        context = ProviderRequestContext(
            tenantId=str(self.tenantId),
            requestId=str(self.requestId),
            idempotencyKey="request-1",
        )
        self.assertEqual(context.tenantId, self.tenantId)
        self.assertEqual(context.requestId, self.requestId)
        self.assertTrue(context.correlationId)
        self.assertTrue(context.traceId)
        with self.assertRaises(FrozenInstanceError):
            context.traceId = "changed"

    def testGenerationRequestNormalizesAndValidatesProviderNeutralOptions(self) -> None:
        request = GenerationRequest(
            prompt="Summarize this project",
            model="local-test",
            responseFormat="json",
            context=ProviderRequestContext(tenantId=self.tenantId, idempotencyKey="request-2"),
        )
        self.assertEqual(request.responseFormat, "JSON")
        self.assertEqual(request.model, "local-test")
        with self.assertRaises(ValidationFailedError):
            GenerationRequest(prompt="", model="local-test")
        with self.assertRaises(ValidationFailedError):
            GenerationRequest(prompt="x", model="local-test", temperature=-1)
        with self.assertRaises(ValidationFailedError):
            GenerationRequest(prompt="x", model="local-test", responseFormat="XML")

    def testCapabilitiesAdvertiseFeaturesAndRejectUnsupportedOnes(self) -> None:
        capabilities = self.provider.capabilities
        self.assertEqual(capabilities.providerCode, "DETERMINISTIC")
        self.assertTrue(capabilities.supports("streaming"))
        self.assertTrue(capabilities.supports("structured_generation"))
        requireProviderFeature(capabilities, "embedding")
        with self.assertRaises(ValidationFailedError):
            requireProviderFeature(capabilities, "tools")
        with self.assertRaises(ValidationFailedError):
            ProviderCapabilities(providerCode="x", features=frozenset({"EMBEDDING"}), supportsJsonSchema=True)

    def testGenerationIsBackwardCompatibleAndCarriesNormalizedUsage(self) -> None:
        result = self.provider.generate(prompt="hello", model="test")
        self.assertIsInstance(result, GenerationResult)
        self.assertEqual(result.provider, "deterministic")
        self.assertEqual(result.model, "test")
        self.assertEqual(result.totalTokens, result.inputTokens + result.outputTokens)
        self.assertEqual(result.content, "[deterministic:test] hello")
        self.assertEqual(
            self.provider.generateRequest(GenerationRequest(prompt="hello", model="test")),
            result,
        )
        with self.assertRaises(ValidationFailedError):
            GenerationResult(inputTokens=-1)

    def testStructuredGenerationUsesSchemaAndContextTrace(self) -> None:
        context = ProviderRequestContext(
            tenantId=self.tenantId,
            requestId=self.requestId,
            correlationId="correlation-1",
            traceId="trace-1",
            idempotencyKey="request-3",
        )
        schema = {
            "type": "object",
            "required": ["summary", "confidence"],
            "properties": {
                "summary": {"type": "string"},
                "confidence": {"type": "number"},
            },
        }
        result = self.provider.generateStructured(
            prompt="Analyze",
            model="test",
            jsonSchema=schema,
            context=context,
        )
        self.assertEqual(result.structuredData["summary"], "deterministic:summary")
        self.assertEqual(result.structuredData["confidence"], 0)
        self.assertEqual(result.requestId, self.requestId)
        self.assertEqual(result.correlationId, "correlation-1")
        self.assertEqual(result.traceId, "trace-1")

    def testStreamingReconstructsTheSameNormalizedGeneration(self) -> None:
        context = ProviderRequestContext(tenantId=self.tenantId, idempotencyKey="request-4")
        chunks = list(self.provider.stream(prompt="hello world", model="test", context=context))
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunk.content for chunk in chunks), "[deterministic:test] hello world")
        self.assertFalse(any(chunk.isFinal for chunk in chunks[:-1]))
        self.assertTrue(chunks[-1].isFinal)
        self.assertEqual(chunks[-1].finishReason, "STOP")
        self.assertEqual(chunks[0].requestId, None)

    def testEmbeddingBatchTokenCountAndHealthStayProviderNeutral(self) -> None:
        vector = self.provider.embed(text="hello", model="test")
        self.assertEqual(len(vector), 8)
        self.assertEqual(vector, self.provider.embed(text="hello", model="test"))
        self.assertEqual(self.provider.embedBatch(texts=("hello", "world"), model="test"), [
            self.provider.embed(text="hello", model="test"),
            self.provider.embed(text="world", model="test"),
        ])
        self.assertEqual(self.provider.countTokens(text="one two", model="test"), 2)
        self.assertEqual(self.provider.countTokens(text="", model="test"), 0)
        health = self.provider.healthCheck(model="test")
        self.assertIsInstance(health, ProviderHealth)
        self.assertEqual(health.status, "HEALTHY")
        self.assertEqual(health.latencyMs, 0)

    def testContractValidationRejectsMismatchedResultsAndInvalidVectors(self) -> None:
        result = GenerationResult(model="model-a", provider="provider-a")
        self.assertIs(validateGenerationResult(result, expectedModel="model-a"), result)
        with self.assertRaises(ValidationFailedError):
            validateGenerationResult(result, expectedModel="model-b")
        self.assertEqual(validateEmbeddingVector((1, 2, 3)), (1.0, 2.0, 3.0))
        self.assertEqual(EmbeddingResult((1.0, 2.0)).dimensions, 2)
        with self.assertRaises(ValidationFailedError):
            EmbeddingResult(())

    def testPortIsAProtocolAndDomainPortHasNoFrameworkOrVendorImport(self) -> None:
        self.assertTrue(getattr(AIProviderPort, "_is_protocol", False))
        self.assertIsInstance(self.provider, AIProviderPort)
        source = (Path(__file__).resolve().parents[2] / "apps/ai/domain/ports.py").read_text(
            encoding="utf-8"
        )
        for forbidden in ("django", "rest_framework", "openai", "ollama", "azure", "anthropic", "requests", "httpx"):
            self.assertNotIn(f"import {forbidden}", source.lower())


if __name__ == "__main__":
    unittest.main()
