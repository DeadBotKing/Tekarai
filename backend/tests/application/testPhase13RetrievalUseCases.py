"""Phase 13-S application tests — retrieval and RAG over the real stack.

Everything below the provider is real: knowledge sources and chunks come
from Phase 13-R ingestion, vectors from Phase 13-Q, permission decisions
from the Phase 13-K ``AuthorizationService`` with genuine grants, and the
audit entries from the Phase 13-O ledger. Only the embedding provider and
the answer generator are deterministic offline doubles.

Covers the three candidate strategies, the ordering guarantee (a principal
without a grant sees nothing), classification-aware filtering, reranking
end to end, context budgeting and citations, the fail-closed grounding
rule, tenant isolation, the disabled switch, the audit trail, and the
degradation path when a chunk is purged between search and hydration.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from django.test import TestCase

from apps.ai.application.services.auditService import AuditApplicationService, AuditSettings
from apps.ai.application.services.embeddingService import (
    DefineVectorSpaceCommand,
    EmbeddingApplicationService,
    EmbeddingSettings,
)
from apps.ai.application.services.knowledgeService import (
    IngestKnowledgeCommand,
    KnowledgeApplicationService,
    KnowledgeSettings,
)
from apps.ai.application.services.retrievalService import (
    AUDIT_RAG_ANSWERED,
    AUDIT_RETRIEVAL_DENIED,
    AUDIT_RETRIEVAL_EXECUTED,
    RagRequest,
    RetrievalApplicationService,
    RetrievalRequest,
    RetrievalSettings,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIRagUngrounded,
    AIRetrievalInvalid,
)
from apps.ai.domain.services.authorizationService import (
    AuthorizationPrincipal,
    AuthorizationService,
    PermissionGrant,
)
from apps.ai.domain.valueObjects.embeddingTypes import VectorSpace
from apps.ai.domain.valueObjects.retrievalTypes import RetrievalPolicy
from apps.ai.infrastructure.repositories.auditRepositories import (
    DjangoAuditRecordStore,
    DjangoGovernancePolicyStore,
    DjangoRetentionPurger,
)
from apps.ai.infrastructure.repositories.embeddingRepositories import (
    DjangoEmbeddingStore,
    DjangoVectorSpaceStore,
)
from apps.ai.infrastructure.repositories.knowledgeRepositories import (
    DjangoKnowledgeChunkStore,
    DjangoKnowledgeSourceStore,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)

PRODUCTION_DOC = (
    "Line one reached ninety two percent of planned production output.\n\n"
    "Line two was halted twice for preventive maintenance downtime.\n\n"
    "Line three exceeded its packaging target by four percent."
)
SAFETY_DOC = (
    "All operators must wear protective equipment inside the clean room.\n\n"
    "Safety incidents are reported to the quality department within one hour."
)


class TokenProvider:
    """Deterministic bag-of-words embedding: shared words ⇒ closer vectors."""

    VOCABULARY = (
        "production",
        "maintenance",
        "safety",
        "packaging",
        "quality",
        "output",
        "downtime",
        "equipment",
    )

    def __init__(self) -> None:
        self.calls = 0

    def vectorFor(self, text: str) -> list[float]:
        lowered = text.lower()
        vector = [float(lowered.count(word)) for word in self.VOCABULARY]
        if not any(vector):
            vector[0] = 0.001
        return vector

    def embed(self, *, text: str, model: str, **kwargs: Any) -> list[float]:
        self.calls += 1
        return self.vectorFor(text)

    def embedBatch(self, *, texts: Any, model: str, **kwargs: Any) -> list[list[float]]:
        materialized = list(texts)
        self.calls += len(materialized)
        return [self.vectorFor(text) for text in materialized]


class FixedResolver:
    def __init__(self, provider: TokenProvider) -> None:
        self.provider = provider

    def providerFor(self, tenantId: uuid.UUID, space: VectorSpace) -> TokenProvider:
        return self.provider


class EchoGenerator:
    """Answer generator double that proves the prompt reached the provider."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.models: list[str] = []

    def generate(self, *, prompt: str, model: str, **kwargs: Any) -> str:
        self.prompts.append(prompt)
        self.models.append(model)
        blocks = prompt.count("\n\n[") + (1 if "[1]" in prompt else 0)
        return f"Grounded answer from {blocks} block(s)."


class RetrievalTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.provider = TokenProvider()
        self.generator = EchoGenerator()

        spaceStore = DjangoVectorSpaceStore()
        self.embedding = EmbeddingApplicationService(
            spaceStore,
            DjangoEmbeddingStore(spaceStore),
            providerResolver=FixedResolver(self.provider),
            settings=EmbeddingSettings(maxBatchSize=8, searchCandidateLimit=200),
            now=lambda: CLOCK,
        )
        for tenant in (self.tenantId, self.otherTenantId):
            self.embedding.defineVectorSpace(
                tenant,
                DefineVectorSpaceCommand(
                    code="KNOWLEDGE_SPACE",
                    modelCode="TEXT_EMBED_3",
                    dimensions=len(TokenProvider.VOCABULARY),
                    providerCode="LOCAL",
                ),
            )
        self.knowledge = KnowledgeApplicationService(
            DjangoKnowledgeSourceStore(),
            DjangoKnowledgeChunkStore(),
            embedder=self.embedding,
            settings=KnowledgeSettings(
                strategy="PARAGRAPH", chunkTokens=40, overlapTokens=0, minChunkTokens=0
            ),
            now=lambda: CLOCK,
        )
        self.audit = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=AuditSettings(enabled=True, retentionDays=365),
            now=lambda: CLOCK,
        )
        self.authorization = AuthorizationService(now=lambda: CLOCK)
        self.subjectId = uuid.uuid4()
        self.principal = AuthorizationPrincipal(
            tenantId=self.tenantId, subjectId=self.subjectId, roles=("ANALYST",)
        )
        self.service = self.buildService()

    # -- helpers --------------------------------------------------------
    def buildService(self, **overrides: Any) -> RetrievalApplicationService:
        settings = RetrievalSettings(
            enabled=overrides.pop("enabled", True),
            strategy=overrides.pop("strategy", "HYBRID"),
            topK=overrides.pop("topK", 3),
            candidateLimit=overrides.pop("candidateLimit", 50),
            rerank=overrides.pop("rerank", "LEXICAL_BOOST"),
            maxContextTokens=overrides.pop("maxContextTokens", 2000),
            maxContextSources=overrides.pop("maxContextSources", 5),
            requireGrounding=overrides.pop("requireGrounding", True),
        )
        return RetrievalApplicationService(
            self.embedding,
            self.knowledge,
            permissionFilter=overrides.pop("permissionFilter", self.authorization),
            generator=overrides.pop("generator", self.generator),
            settings=settings,
            auditLogger=overrides.pop("auditLogger", self.audit),
            now=lambda: CLOCK,
        )

    def ingest(
        self,
        entityId: str,
        content: str,
        *,
        classification: str = "INTERNAL",
        tenantId: uuid.UUID | None = None,
    ) -> Any:
        return self.knowledge.ingestSource(
            tenantId or self.tenantId,
            IngestKnowledgeCommand(
                sourceDomain="DOCUMENTS",
                sourceEntityType="DOCUMENT",
                sourceEntityId=entityId,
                title=f"Document {entityId}",
                content=content,
                classification=classification,
                spaceCode="KNOWLEDGE_SPACE",
            ),
        )

    def grantAll(self, *, classifications: tuple[str, ...] = ("PUBLIC", "INTERNAL")) -> None:
        self.authorization.registerGrant(
            PermissionGrant(
                tenantId=self.tenantId,
                subjectId=self.subjectId,
                permissionCode="AI_CONTEXT_SOURCE_READ",
                resourceType="CONTEXT_SOURCE",
                allowedClassifications=classifications,
            )
        )

    def grantDocument(self, entityId: str) -> None:
        self.authorization.registerGrant(
            PermissionGrant(
                tenantId=self.tenantId,
                subjectId=self.subjectId,
                permissionCode="AI_CONTEXT_SOURCE_READ",
                resourceType="CONTEXT_SOURCE",
                sourceDomain="DOCUMENTS",
                sourceEntityType="DOCUMENT",
                sourceEntityId=entityId,
                allowedClassifications=("PUBLIC", "INTERNAL"),
            )
        )

    def request(self, question: str, **overrides: Any) -> RetrievalRequest:
        params: dict[str, Any] = {
            "spaceCode": "KNOWLEDGE_SPACE",
            "question": question,
            "principal": self.principal,
        }
        params.update(overrides)
        return RetrievalRequest(**params)

    def auditActions(self) -> list[str]:
        return [entry.action for entry in self.audit.listAuditEntries(self.tenantId)]


class PermissionBoundaryTests(RetrievalTestCase):
    """The rule §20 exists for: filtering happens before context exists."""

    def setUp(self) -> None:
        super().setUp()
        self.ingest("production", PRODUCTION_DOC)
        self.ingest("safety", SAFETY_DOC)

    def testPrincipalWithoutAnyGrantGetsNothing(self) -> None:
        result = self.service.retrieve(self.tenantId, self.request("production output"))
        self.assertGreater(result.candidateCount, 0)
        self.assertEqual(result.authorizedCount, 0)
        self.assertEqual(result.deniedCount, result.candidateCount)
        self.assertEqual(result.citations, ())
        self.assertEqual(result.prompt.contextText, "")
        self.assertFalse(result.isGrounded)

    def testGrantedPrincipalSeesEvidence(self) -> None:
        self.grantAll()
        result = self.service.retrieve(self.tenantId, self.request("production output"))
        self.assertGreater(result.authorizedCount, 0)
        self.assertTrue(result.isGrounded)
        self.assertIn("production", result.prompt.contextText.lower())

    def testGrantScopedToOneDocumentHidesTheOther(self) -> None:
        self.grantDocument("production")
        result = self.service.retrieve(
            self.tenantId, self.request("production output safety equipment")
        )
        references = {citation.sourceReference for citation in result.citations}
        self.assertEqual(references, {"DOCUMENTS:DOCUMENT:production"})
        self.assertGreater(result.deniedCount, 0)

    def testRestrictedClassificationIsFilteredOut(self) -> None:
        self.ingest(
            "secret", "Confidential production margin analysis.", classification="RESTRICTED"
        )
        self.grantAll(classifications=("PUBLIC", "INTERNAL"))
        result = self.service.retrieve(self.tenantId, self.request("production margin analysis"))
        references = {citation.sourceReference for citation in result.citations}
        self.assertNotIn("DOCUMENTS:DOCUMENT:secret", references)

    def testMissingFilterFailsClosedInsteadOfServingEverything(self) -> None:
        service = self.buildService(permissionFilter=None)
        with self.assertRaises(AIConfigurationError):
            service.retrieve(self.tenantId, self.request("production output"))

    def testDeniedRetrievalIsAuditedAsDenied(self) -> None:
        self.service.retrieve(self.tenantId, self.request("production output"))
        self.assertIn(AUDIT_RETRIEVAL_DENIED, self.auditActions())

    def testAllowedRetrievalIsAuditedAsExecuted(self) -> None:
        self.grantAll()
        self.service.retrieve(self.tenantId, self.request("production output"))
        self.assertIn(AUDIT_RETRIEVAL_EXECUTED, self.auditActions())
        self.assertEqual(self.audit.verifyTenantChain(self.tenantId), len(self.auditActions()))

    def testPrincipalFromAnotherTenantIsRefused(self) -> None:
        foreign = AuthorizationPrincipal(tenantId=self.otherTenantId, subjectId=uuid.uuid4())
        with self.assertRaises(AIRetrievalInvalid):
            self.service.retrieve(self.tenantId, self.request("output", principal=foreign))

    def testMissingPrincipalIsRefused(self) -> None:
        with self.assertRaises(AIRetrievalInvalid):
            self.service.retrieve(self.tenantId, self.request("output", principal=None))


class StrategyTests(RetrievalTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ingest("production", PRODUCTION_DOC)
        self.ingest("safety", SAFETY_DOC)
        self.grantAll()

    def testVectorStrategyEmbedsTheQuery(self) -> None:
        service = self.buildService(strategy="VECTOR")
        before = self.provider.calls
        result = service.retrieve(self.tenantId, self.request("maintenance downtime"))
        self.assertGreater(self.provider.calls, before)
        self.assertTrue(result.trace.has("EMBED"))
        self.assertEqual(result.trace.countFor("EMBED"), 1)
        self.assertGreater(result.authorizedCount, 0)

    def testLexicalStrategySkipsEmbeddingEntirely(self) -> None:
        service = self.buildService(strategy="LEXICAL")
        before = self.provider.calls
        result = service.retrieve(self.tenantId, self.request("preventive maintenance downtime"))
        self.assertEqual(self.provider.calls, before)
        self.assertEqual(result.trace.countFor("EMBED"), 0)
        self.assertTrue(result.isGrounded)
        self.assertIn("maintenance", result.prompt.contextText.lower())

    def testHybridStrategyMergesBothSources(self) -> None:
        result = self.service.retrieve(self.tenantId, self.request("packaging target"))
        self.assertTrue(result.isGrounded)
        self.assertIn("packaging", result.prompt.contextText.lower())

    def testExactKeywordQuestionRanksItsParagraphFirst(self) -> None:
        result = self.service.retrieve(
            self.tenantId, self.request("protective equipment clean room")
        )
        self.assertIn("protective equipment", result.prompt.contextText.lower())
        self.assertEqual(result.citations[0].sourceReference, "DOCUMENTS:DOCUMENT:safety")

    def testTopKBoundsTheEvidence(self) -> None:
        service = self.buildService(topK=1)
        result = service.retrieve(self.tenantId, self.request("production maintenance safety"))
        self.assertEqual(len(result.citations), 1)

    def testMmrRerankIsAcceptedEndToEnd(self) -> None:
        service = self.buildService(rerank="MMR")
        result = service.retrieve(self.tenantId, self.request("production output"))
        self.assertTrue(result.isGrounded)

    def testContextBudgetLimitsTheAssembledBlocks(self) -> None:
        service = self.buildService(maxContextTokens=12, topK=5)
        result = service.retrieve(self.tenantId, self.request("production maintenance packaging"))
        self.assertLessEqual(len(result.citations), 2)
        self.assertLessEqual(result.prompt.tokenCount, 40)

    def testEmptyQuestionIsRejected(self) -> None:
        with self.assertRaises(AIRetrievalInvalid):
            self.service.retrieve(self.tenantId, self.request("   "))

    def testWrongRequestTypeIsRejected(self) -> None:
        with self.assertRaises(AIRetrievalInvalid):
            self.service.retrieve(self.tenantId, "just a question")  # type: ignore[arg-type]

    def testDisabledPipelineRefusesToServe(self) -> None:
        service = self.buildService(enabled=False)
        with self.assertRaises(AIConfigurationError):
            service.retrieve(self.tenantId, self.request("production"))


class TraceTests(RetrievalTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ingest("production", PRODUCTION_DOC)
        self.grantAll()

    def testTraceRecordsTheWholePipelineInOrder(self) -> None:
        result = self.service.retrieve(self.tenantId, self.request("production output"))
        stages = [record.stage for record in result.trace.stages]
        self.assertEqual(
            stages, ["EMBED", "CANDIDATES", "RESOLVE", "AUTHORIZE", "RERANK", "CONTEXT"]
        )
        self.assertLess(stages.index("AUTHORIZE"), stages.index("CONTEXT"))

    def testTraceSummaryCarriesNoContent(self) -> None:
        result = self.service.retrieve(self.tenantId, self.request("production output"))
        rendered = str(result.trace.summary())
        self.assertNotIn("ninety two percent", rendered)
        self.assertIn("AUTHORIZE", rendered)

    def testCountsAreConsistentWithTheTrace(self) -> None:
        result = self.service.retrieve(self.tenantId, self.request("production output"))
        self.assertEqual(result.trace.countFor("AUTHORIZE"), result.authorizedCount)
        self.assertEqual(result.trace.countFor("CONTEXT"), len(result.citations))

    def testPurgedChunkDegradesTheResultInsteadOfBreakingIt(self) -> None:
        source = self.knowledge.findSource(self.tenantId, "DOCUMENTS", "DOCUMENT", "production")
        chunks = self.knowledge.listChunks(self.tenantId, source.sourceId)
        DjangoKnowledgeChunkStore().deleteChunks(self.tenantId, (chunks[0].chunkId,))
        result = self.service.retrieve(self.tenantId, self.request("production output"))
        self.assertNotIn(
            str(chunks[0].chunkId), [str(citation.chunkId) for citation in result.citations]
        )
        self.assertTrue(result.trace.has("RESOLVE"))


class RagTests(RetrievalTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ingest("production", PRODUCTION_DOC)

    def ragRequest(self, question: str, **overrides: Any) -> RagRequest:
        params: dict[str, Any] = {
            "spaceCode": "KNOWLEDGE_SPACE",
            "question": question,
            "principal": self.principal,
            "modelCode": "TEST_MODEL",
        }
        params.update(overrides)
        return RagRequest(**params)

    def testGroundedAnswerCarriesItsCitations(self) -> None:
        self.grantAll()
        answer = self.service.answerQuestion(
            self.tenantId, self.ragRequest("what happened to production output?")
        )
        self.assertTrue(answer.isGrounded)
        self.assertGreater(len(answer.citations), 0)
        self.assertEqual(answer.modelCode, "TEST_MODEL")
        self.assertIn("Grounded answer", answer.answer)
        self.assertIn(AUDIT_RAG_ANSWERED, self.auditActions())

    def testThePromptSentToTheProviderContainsNumberedEvidence(self) -> None:
        self.grantAll()
        self.service.answerQuestion(self.tenantId, self.ragRequest("production output?"))
        prompt = self.generator.prompts[-1]
        self.assertIn("[1]", prompt)
        self.assertIn("Question: production output?", prompt)
        self.assertIn("Cite the blocks", prompt)

    def testUngroundedQuestionIsRefusedRatherThanAnswered(self) -> None:
        with self.assertRaises(AIRagUngrounded):
            self.service.answerQuestion(self.tenantId, self.ragRequest("production output?"))
        self.assertEqual(self.generator.prompts, [])
        self.assertIn(AUDIT_RAG_ANSWERED, self.auditActions())

    def testGroundingCanBeRelaxedDeliberately(self) -> None:
        service = self.buildService(requireGrounding=False)
        answer = service.answerQuestion(
            self.tenantId,
            self.ragRequest(
                "production output?", policy=RetrievalPolicy(requireGrounding=False, topK=3)
            ),
        )
        self.assertFalse(answer.isGrounded)
        self.assertIn("no authorized context", self.generator.prompts[-1])

    def testCustomInstructionReachesTheProvider(self) -> None:
        self.grantAll()
        self.service.answerQuestion(
            self.tenantId,
            self.ragRequest("production output?", instruction="Reply in Persian only."),
        )
        self.assertIn("Reply in Persian only.", self.generator.prompts[-1])

    def testMissingGeneratorFailsClosed(self) -> None:
        self.grantAll()
        service = self.buildService(generator=None)
        with self.assertRaises(AIConfigurationError):
            service.answerQuestion(self.tenantId, self.ragRequest("production output?"))

    def testWrongRequestTypeIsRejected(self) -> None:
        with self.assertRaises(AIRetrievalInvalid):
            self.service.answerQuestion(self.tenantId, "question")  # type: ignore[arg-type]

    def testAnswerKeepsTheRetrievalResultForInspection(self) -> None:
        self.grantAll()
        answer = self.service.answerQuestion(self.tenantId, self.ragRequest("production output?"))
        self.assertEqual(answer.retrieval.requestId, answer.requestId)
        self.assertTrue(answer.retrieval.trace.has("CONTEXT"))


class IsolationTests(RetrievalTestCase):
    def testOneTenantNeverSeesAnotherTenantsKnowledge(self) -> None:
        self.ingest("production", PRODUCTION_DOC)
        self.ingest("foreign", SAFETY_DOC, tenantId=self.otherTenantId)
        self.grantAll()
        result = self.service.retrieve(
            self.tenantId, self.request("protective equipment clean room")
        )
        references = {citation.sourceReference for citation in result.citations}
        self.assertNotIn("DOCUMENTS:DOCUMENT:foreign", references)

    def testRetrievalOnAnEmptyTenantReturnsNothingGracefully(self) -> None:
        self.grantAll()
        result = self.service.retrieve(self.tenantId, self.request("anything at all"))
        self.assertEqual(result.candidateCount, 0)
        self.assertEqual(result.authorizedCount, 0)
        self.assertFalse(result.isGrounded)
        self.assertEqual(result.trace.countFor("CANDIDATES"), 0)
