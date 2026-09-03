"""Phase 13-B domain tests (pure Python; no Django/database/provider needed)."""

from __future__ import annotations

import unittest
import uuid
from dataclasses import FrozenInstanceError
from decimal import Decimal

from apps.ai.domain.entities.aiRecords import (
    AIAgent,
    AIAgentExecution,
    AIAuditRecord,
    AICapability,
    AICost,
    AIEmbedding,
    AIEvaluation,
    AIFeedback,
    AIKnowledgeChunk,
    AIKnowledgeItem,
    AIMemory,
    AIModel,
    AIOperation,
    AIPrompt,
    AIPromptVersion,
    AIProvider,
    AIRetrieval,
    AIRequest,
    AIResponse,
    AITool,
    AIToolExecution,
    AIUsage,
)
from apps.ai.domain.exceptions import AIContextTooLarge, AIToolDenied
from apps.ai.domain.policies.aiPolicies import ContextPolicy, ProviderPolicy, QuotaPolicy, ToolPolicy
from apps.ai.domain.services.aiRules import (
    buildContext,
    calculateCost,
    ensureStructuredOutput,
    estimateTokens,
    idempotencyFingerprint,
    nextRetryAt,
    redact,
    retryDelay,
)
from apps.ai.domain.valueObjects.aiTypes import (
    ContextSource,
    CostRate,
    DataClassification,
    MemoryScope,
    ModelType,
    OutputClassification,
    RequestStatus,
    RetryPolicy,
    TokenUsage,
)


class Phase13BDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.userId = uuid.uuid4()
        self.provider = AIProvider(self.tenantId, "LOCAL", "Local Provider", "LOCAL")
        self.model = AIModel(self.tenantId, self.provider.id, "TEST_MODEL", "Test Model")
        self.capability = AICapability(self.tenantId, "TEXT_GENERATION", "Text generation")

    def testValueObjectsValidateAndNormalizeDomainValues(self) -> None:
        self.assertEqual(str(ModelType("llm")), "LLM")
        self.assertEqual(str(DataClassification("internal")), "INTERNAL")
        with self.assertRaises(FrozenInstanceError):
            ModelType("LLM").value = "VISION"
        self.assertEqual(str(OutputClassification("ADVISORY")), "ADVISORY")
        self.assertEqual(str(MemoryScope("AGENT")), "AGENT")
        self.assertEqual(TokenUsage(2, 3).totalTokens, 5)
        self.assertEqual(CostRate(Decimal("1"), Decimal("2")).calculate(TokenUsage(1000, 500)).amount, Decimal("2.00000000"))
        with self.assertRaises(Exception):
            ModelType("UNKNOWN")

    def testProviderModelCapabilityAreTenantScopedAndProviderIndependent(self) -> None:
        self.assertEqual(self.provider.code, "LOCAL")
        self.assertEqual(self.model.providerId, self.provider.id)
        self.assertTrue(self.capability.accepts("GENERATE"))
        otherTenant = uuid.uuid4()
        self.assertNotEqual(self.provider.tenantId, otherTenant)
        with self.assertRaises(Exception):
            AIModel(self.tenantId, self.provider.id, "bad code", "Invalid")

    def testOperationAndRequestStateMachinesAreExplicit(self) -> None:
        operation = AIOperation(self.tenantId, "GENERATE", requestedBy=self.userId)
        operation.transitionTo("RUNNING")
        operation.transitionTo("COMPLETED")
        self.assertEqual(operation.status, "COMPLETED")
        request = AIRequest(self.tenantId, self.capability.id, "GENERATE", requestedBy=self.userId)
        request.transitionTo("QUEUED")
        request.transitionTo("RUNNING")
        request.transitionTo("FAILED", errorCode="AI_PROVIDER_UNAVAILABLE")
        request.recordRetry()
        self.assertEqual(request.status, "QUEUED")
        self.assertEqual(request.retryCount, 1)
        with self.assertRaises(ValueError):
            request.transitionTo("COMPLETED")

    def testResponseRequiresConsistentTokensAndOutputClassification(self) -> None:
        request = AIRequest(self.tenantId, self.capability.id, "GENERATE")
        response = AIResponse(
            self.tenantId,
            request.id,
            self.model.id,
            self.provider.id,
            inputTokens=3,
            outputTokens=2,
            content="ok",
        )
        self.assertEqual(response.totalTokens, 5)
        with self.assertRaises(ValueError):
            AIResponse(self.tenantId, request.id, self.model.id, self.provider.id, totalTokens=99)

    def testPromptVersionIsImmutableByVersionAndRendersOnlyDeclaredVariables(self) -> None:
        prompt = AIPrompt(self.tenantId, "PROJECT_ANALYSIS", "Project analysis")
        version = AIPromptVersion(self.tenantId, prompt.id, 1, "Hello {name}", variables=("name",))
        prompt.activateVersion(version.id)
        self.assertEqual(version.render({"name": "Ada"}), "Hello Ada")
        with self.assertRaises(ValueError):
            version.render({})
        self.assertEqual(prompt.activeVersionId, version.id)

    def testContextSourcesCarryClassificationAndContextIsBounded(self) -> None:
        sources = (
            ContextSource("projects", "Project", "p1", "public text", "PUBLIC", True),
            ContextSource("hr", "Employee", "e1", "secret text", "RESTRICTED", True),
            ContextSource("tasks", "Task", "t1", "denied text", "INTERNAL", False),
        )
        content, allowed, tokens = buildContext(sources, ContextPolicy())
        self.assertEqual(content, "public text")
        self.assertEqual(len(allowed), 1)
        self.assertGreater(tokens, 0)
        with self.assertRaises(AIContextTooLarge):
            buildContext((ContextSource("x", "X", "1", "long"),), ContextPolicy(maxCharacters=1))

    def testMemoryKnowledgeEmbeddingAndRetrievalAreTenantAware(self) -> None:
        memory = AIMemory(self.tenantId, "AGENT", "tone", {"formal": True}, self.userId)
        nextMemory = memory.nextVersion({"formal": False})
        self.assertEqual(nextMemory.version, 2)
        item = AIKnowledgeItem(self.tenantId, "documents", "Document", "d1", "Doc", "content")
        item.transitionTo("INDEXING")
        item.transitionTo("READY")
        chunk = AIKnowledgeChunk(self.tenantId, item.id, 0, "content", tokenCount=2)
        embedding = AIEmbedding(self.tenantId, "KnowledgeChunk", str(chunk.id), self.model.id, (0.1, 0.2), chunk.id)
        retrieval = AIRetrieval(self.tenantId, uuid.uuid4(), "query", (chunk,))
        retrieval.authorize((chunk,))
        retrieval.select(1)
        self.assertEqual(embedding.dimensions, 2)
        self.assertEqual(retrieval.selectedCandidates, (chunk,))

    def testUsageCostFeedbackEvaluationAndAuditRespectContracts(self) -> None:
        request = AIRequest(self.tenantId, self.capability.id, "GENERATE")
        usage = AIUsage(self.tenantId, request.id, self.provider.id, self.model.id, TokenUsage(1000, 500))
        cost = AICost(self.tenantId, request.id, usage.id, usage.cost(CostRate(Decimal("1"), Decimal("2"))))
        feedback = AIFeedback(self.tenantId, request.id, uuid.uuid4(), rating=5, sentiment="POSITIVE")
        evaluation = AIEvaluation(self.tenantId, request.id, "MANUAL", metrics={"accuracy": 1.0})
        audit = AIAuditRecord(self.tenantId, request.id, "GENERATE", self.userId, resultClassification="ADVISORY")
        self.assertEqual(cost.currency, "USD")
        self.assertEqual(feedback.rating, 5)
        self.assertEqual(evaluation.metrics["accuracy"], 1.0)
        self.assertTrue(audit.redacted)

    def testToolAndAgentExecutionRequireValidLifecycle(self) -> None:
        tool = AITool(self.tenantId, "SEARCH_PROJECT", "Search project", "Searches authorized projects", requiredPermission="project.view")
        execution = AIToolExecution(self.tenantId, uuid.uuid4(), tool.id, {"q": "x"})
        execution.transitionTo("RUNNING")
        execution.transitionTo("SUCCEEDED")
        agent = AIAgent(self.tenantId, "PROJECT_AGENT", "Project agent", "Analyze projects")
        agentExecution = AIAgentExecution(self.tenantId, agent.id, self.userId, {"projectId": "p1"})
        agentExecution.transitionTo("RUNNING")
        agentExecution.transitionTo("COMPLETED")
        self.assertEqual(execution.status, "SUCCEEDED")
        self.assertEqual(agentExecution.status, "COMPLETED")

    def testPureRulesCoverSchemaRetryQuotaPolicyAndSecrets(self) -> None:
        schema = {"type": "object", "required": ["summary"], "properties": {"summary": {"type": "string"}}}
        self.assertEqual(ensureStructuredOutput({"summary": "ok"}, schema), {"summary": "ok"})
        with self.assertRaises(Exception):
            ensureStructuredOutput({"summary": 1}, schema)
        policy = RetryPolicy(maxAttempts=3, initialDelaySeconds=30, multiplier=2, maxDelaySeconds=60)
        self.assertEqual(retryDelay(policy, 1), 30)
        self.assertEqual(retryDelay(policy, 3), 60)
        self.assertGreater(nextRetryAt(policy, 1).timestamp(), 0)
        self.assertEqual(calculateCost(TokenUsage(1000, 1000), CostRate(Decimal("1"), Decimal("3"))), Decimal("4.00000000"))
        self.assertEqual(estimateTokens("1234"), 1)
        self.assertNotIn("do-not-log", str(redact({"secret": "do-not-log"})))
        self.assertNotEqual(idempotencyFingerprint(str(self.tenantId), "GENERATE", "a"), idempotencyFingerprint(str(uuid.uuid4()), "GENERATE", "a"))
        self.assertTrue(ProviderPolicy(externalAllowed=False).permits("LOCAL", "TEST", ["PUBLIC"]))
        QuotaPolicy(dailyTokenLimit=10).checkTokens(5, 5)
        with self.assertRaises(AIToolDenied):
            ToolPolicy(frozenset({"x"})).permits("x")


if __name__ == "__main__":
    unittest.main()
