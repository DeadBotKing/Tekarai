"""Phase 13-H Response and Structured Output tests (pure Python, offline)."""

from __future__ import annotations

import unittest
import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

from apps.ai.domain.entities.aiRecords import AIResponse
from apps.ai.domain.exceptions import (
    AIPermissionDenied,
    AIResponseAlreadyRegistered,
    AIResponseInvalid,
    AIResponseNotFound,
    AIResponseRequestInvalid,
    AIStructuredOutputInvalid,
    AIStructuredSchemaInvalid,
)
from apps.ai.domain.services.requestLifecycle import RequestLifecycleService
from apps.ai.domain.services.responseLifecycle import (
    AIResponseLifecycle,
    AIResponseService,
    ResponseDescriptor,
    ResponseLifecycleService,
    StructuredOutput,
    StructuredOutputSchema,
    StructuredOutputValidator,
    ValidationIssue,
    normalizeStructuredOutput,
)


class Phase13HResponseLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.modelId = uuid.uuid4()
        self.providerId = uuid.uuid4()
        self.clock = datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC)
        self.requests = RequestLifecycleService(now=lambda: self.clock)
        self.request = self.requests.createRequest(
            self.tenantId,
            uuid.uuid4(),
            "GENERATE",
            correlationId="corr-h",
            traceId="trace-h",
        )
        self.responses = AIResponseService(requestLifecycle=self.requests, now=lambda: self.clock)

    def _schema(self) -> StructuredOutputSchema:
        return StructuredOutputSchema(
            {
                "type": "object",
                "required": ["summary", "risks"],
                "additionalProperties": False,
                "properties": {
                    "summary": {"type": "string", "minLength": 1},
                    "risks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 3,
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
            name="project-summary",
            version="2",
        )

    def testSchemaIsImmutableAndStructuredOutputNormalizesJson(self) -> None:
        schema = self._schema()
        self.assertIsInstance(schema, StructuredOutputValidator)
        self.assertEqual(schema.asDict()["properties"]["summary"]["type"], "string")
        with self.assertRaises(FrozenInstanceError):
            schema.name = "changed"
        output = self.responses.validateStructuredOutput(
            '{"summary":"All good","risks":["none"],"confidence":0.8}',
            schema,
        )
        self.assertIsInstance(output, StructuredOutput)
        self.assertEqual(output.asDict()["summary"], "All good")
        self.assertEqual(output.schemaFingerprint, schema.fingerprint())
        self.assertTrue(output.validated)
        with self.assertRaises(TypeError):
            output.data["summary"] = "changed"
        self.assertEqual(normalizeStructuredOutput({"ok": True}), {"ok": True})

    def testSchemaValidationReturnsSafeExplainableIssues(self) -> None:
        schema = self._schema()
        issues = schema.validate({"summary": "", "risks": ["a", "b", "c", "d"]})
        self.assertTrue(all(isinstance(issue, ValidationIssue) for issue in issues))
        self.assertTrue(any(issue.path == "$.summary" and issue.keyword == "minLength" for issue in issues))
        self.assertTrue(any(issue.path == "$.risks" and issue.keyword == "maxItems" for issue in issues))
        with self.assertRaises(AIStructuredOutputInvalid) as raised:
            self.responses.validateStructuredOutput(
                {"summary": "ok", "risks": [], "internalSecret": "not returned"},
                schema,
            )
        self.assertTrue(raised.exception.issues)
        self.assertNotIn("not returned", str(raised.exception))

    def testSchemaSupportsNestedCombinatorsAndArrayItems(self) -> None:
        schema = StructuredOutputSchema(
            {
                "type": "object",
                "required": ["items"],
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "integer", "minimum": 1},
                            ]
                        },
                    }
                },
            }
        )
        self.assertEqual(schema.validate({"items": ["x", 2]}), ())
        self.assertTrue(any(issue.path == "$.items[0]" for issue in schema.validate({"items": [False]})))
        with self.assertRaises(AIStructuredSchemaInvalid):
            StructuredOutputSchema({"type": "not-a-json-type"})
        with self.assertRaises(AIStructuredSchemaInvalid):
            StructuredOutputSchema({"properties": {"x": {"pattern": "["}}})

    def testCreateTextResponseAndTraceableSafeDescriptor(self) -> None:
        response = self.responses.createResponse(
            self.tenantId,
            self.request.id,
            self.modelId,
            self.providerId,
            content="safe answer",
            inputTokens=4,
            outputTokens=6,
            latencyMs=18,
        )
        self.assertIsInstance(response, AIResponse)
        descriptor = self.responses.describeResponse(self.tenantId, response.id)
        self.assertIsInstance(descriptor, ResponseDescriptor)
        self.assertTrue(descriptor.contentPresent)
        self.assertFalse(descriptor.hasStructuredData)
        self.assertFalse(descriptor.structuredOutputValidated)
        self.assertEqual(descriptor.totalTokens, 10)
        self.assertEqual(descriptor.correlationId, "corr-h")
        self.assertEqual(descriptor.traceId, "trace-h")
        self.assertNotIn("safe answer", repr(descriptor))
        self.assertIs(self.responses.get(self.tenantId, response.id), response)

    def testCreateStructuredResponseValidatesBeforeRegistration(self) -> None:
        schema = self._schema()
        response = self.responses.createResponse(
            self.tenantId,
            self.request.id,
            self.modelId,
            self.providerId,
            structuredData='{"summary":"Ready","risks":[],"confidence":1}',
            structuredOutputSchema=schema,
        )
        self.assertEqual(response.structuredData["summary"], "Ready")
        descriptor = self.responses.describeResponse(self.tenantId, response.id)
        self.assertTrue(descriptor.hasStructuredData)
        self.assertTrue(descriptor.structuredOutputValidated)
        self.assertEqual(descriptor.structuredSchemaFingerprint, schema.fingerprint())
        with self.assertRaises(AIStructuredOutputInvalid):
            self.responses.createResponse(
                self.tenantId,
                self.request.id,
                self.modelId,
                self.providerId,
                structuredData={"summary": 99, "risks": []},
                structuredOutputSchema=schema,
            )
        self.assertEqual(self.responses.responseCount(self.tenantId), 1)

    def testValidationFailedResponseDoesNotRetainInvalidPayload(self) -> None:
        response = self.responses.createResponse(
            self.tenantId,
            self.request.id,
            self.modelId,
            self.providerId,
            status="VALIDATION_FAILED",
            structuredData={"summary": 99},
            structuredOutputSchema=self._schema(),
        )
        self.assertEqual(response.status, "VALIDATION_FAILED")
        self.assertEqual(response.structuredData, {})
        self.assertEqual(response.errorCode, "AI_STRUCTURED_OUTPUT_INVALID")
        descriptor = self.responses.describeResponse(self.tenantId, response.id)
        self.assertTrue(descriptor.hasStructuredData)
        self.assertFalse(descriptor.structuredOutputValidated)
        self.assertEqual(descriptor.errorCode, "AI_STRUCTURED_OUTPUT_INVALID")

    def testFailedAndAuthoritativeResponseRules(self) -> None:
        failed = self.responses.createResponse(
            self.tenantId,
            self.request.id,
            self.modelId,
            self.providerId,
            status="FAILED",
            errorCode="provider_timeout",
        )
        self.assertEqual(failed.errorCode, "PROVIDER_TIMEOUT")
        with self.assertRaises(AIResponseInvalid):
            self.responses.createResponse(
                self.tenantId,
                self.request.id,
                self.modelId,
                self.providerId,
                status="FAILED",
            )
        with self.assertRaises(AIPermissionDenied):
            self.responses.createResponse(
                self.tenantId,
                self.request.id,
                self.modelId,
                self.providerId,
                content="authoritative",
                outputClassification="AUTHORITATIVE",
            )
        authorized = self.responses.createResponse(
            self.tenantId,
            self.request.id,
            self.modelId,
            self.providerId,
            content="authoritative",
            outputClassification="AUTHORITATIVE",
            authorized=True,
        )
        self.assertEqual(authorized.outputClassification, "AUTHORITATIVE")

    def testRequestTenantAndLifecycleOwnershipAreEnforced(self) -> None:
        with self.assertRaises(AIResponseRequestInvalid):
            self.responses.createResponse(
                self.otherTenantId,
                self.request.id,
                self.modelId,
                self.providerId,
                content="cross tenant",
            )
        self.requests.cancelRequest(self.tenantId, self.request.id)
        with self.assertRaises(AIResponseRequestInvalid):
            self.responses.createResponse(
                self.tenantId,
                self.request.id,
                self.modelId,
                self.providerId,
                content="late response",
            )
        with self.assertRaises(AIResponseRequestInvalid):
            self.responses.registerResponse(
                AIResponse(
                    self.otherTenantId,
                    self.request.id,
                    self.modelId,
                    self.providerId,
                    content="cross tenant",
                )
            )

    def testDuplicateResponseIdsAndTenantScopedListing(self) -> None:
        responseId = uuid.uuid4()
        first = self.responses.createResponse(
            self.tenantId,
            self.request.id,
            self.modelId,
            self.providerId,
            content="one",
            responseId=responseId,
        )
        with self.assertRaises(AIResponseAlreadyRegistered):
            self.responses.createResponse(
                self.tenantId,
                self.request.id,
                self.modelId,
                self.providerId,
                content="two",
                responseId=first.id,
            )
        second = self.responses.createResponse(
            self.tenantId,
            self.request.id,
            self.modelId,
            self.providerId,
            status="FAILED",
            errorCode="failed",
        )
        self.assertEqual(self.responses.responseCount(self.tenantId, self.request.id), 2)
        self.assertEqual(len(self.responses.listResponses(self.tenantId, status="FAILED")), 1)
        self.assertEqual(self.responses.listResponses(self.otherTenantId), ())
        with self.assertRaises(AIResponseNotFound):
            self.responses.getResponse(self.otherTenantId, first.id)

    def testDirectRegistrationKeepsBEntityContractAndNoImplicitRequestMutation(self) -> None:
        response = AIResponse(
            self.tenantId,
            self.request.id,
            self.modelId,
            self.providerId,
            content="direct",
            inputTokens=2,
            outputTokens=3,
        )
        self.responses.register(response)
        self.assertEqual(self.request.status, "PENDING")
        with self.assertRaises(AIResponseInvalid):
            self.responses.registerResponse(object())  # type: ignore[arg-type]

    def testPureDomainBoundaryAndNoSecretOrProviderImports(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "apps/ai/domain/services/responseLifecycle.py").read_text(
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
        self.assertNotIn("api_key", source.lower())
        self.assertNotIn("secret_key", source.lower())
        self.assertIs(AIResponseLifecycle, AIResponseService)
        self.assertIs(ResponseLifecycleService, AIResponseService)


if __name__ == "__main__":
    unittest.main()
