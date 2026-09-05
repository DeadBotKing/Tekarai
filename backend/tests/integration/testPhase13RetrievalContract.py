"""Phase 13-S integration tests — the whole knowledge stack over SQLite.

These tests exercise the seam between four sub-phases against real tables:
ingestion (R) writes chunks, embedding (Q) writes vectors, authorization
(K) decides visibility, and retrieval (S) reads through all of it. The
focus is lifecycle interaction rather than unit behaviour: what retrieval
sees after a reindex, an archive, a delete, a classification change, a
space swap, or a tenant boundary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from django.test import TestCase

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
    RagRequest,
    RetrievalApplicationService,
    RetrievalRequest,
    RetrievalSettings,
)
from apps.ai.domain.exceptions import AIRagUngrounded
from apps.ai.domain.services.authorizationService import (
    AuthorizationPrincipal,
    AuthorizationService,
    PermissionGrant,
)
from apps.ai.domain.valueObjects.embeddingTypes import VectorSpace
from apps.ai.domain.valueObjects.retrievalTypes import RetrievalPolicy
from apps.ai.infrastructure.models import (
    AIKnowledgeChunkRecordModel,
    AIStoredEmbeddingModel,
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

VOCABULARY = (
    "production",
    "maintenance",
    "safety",
    "packaging",
    "quality",
    "output",
    "downtime",
    "equipment",
    "training",
    "audit",
)

PRODUCTION_DOC = (
    "Line one reached ninety two percent of planned production output.\n\n"
    "Line two was halted twice for preventive maintenance downtime."
)
SAFETY_DOC = (
    "Operators must wear protective equipment inside the clean room.\n\n"
    "Safety training records are reviewed during every quality audit."
)


class BagOfWordsProvider:
    def embed(self, *, text: str, model: str, **kwargs: Any) -> list[float]:
        lowered = text.lower()
        vector = [float(lowered.count(word)) for word in VOCABULARY]
        if not any(vector):
            vector[0] = 0.001
        return vector

    def embedBatch(self, *, texts: Any, model: str, **kwargs: Any) -> list[list[float]]:
        return [self.embed(text=text, model=model) for text in texts]


class FixedResolver:
    def __init__(self, provider: BagOfWordsProvider) -> None:
        self.provider = provider

    def providerFor(self, tenantId: uuid.UUID, space: VectorSpace) -> BagOfWordsProvider:
        return self.provider


class StaticGenerator:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, *, prompt: str, model: str, **kwargs: Any) -> str:
        self.prompts.append(prompt)
        return "answer"


class KnowledgeStackTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.spaceStore = DjangoVectorSpaceStore()
        self.chunkStore = DjangoKnowledgeChunkStore()
        self.generator = StaticGenerator()
        self.embedding = EmbeddingApplicationService(
            self.spaceStore,
            DjangoEmbeddingStore(self.spaceStore),
            providerResolver=FixedResolver(BagOfWordsProvider()),
            settings=EmbeddingSettings(maxBatchSize=8, searchCandidateLimit=200),
            now=lambda: CLOCK,
        )
        for tenant in (self.tenantId, self.otherTenantId):
            self.embedding.defineVectorSpace(
                tenant,
                DefineVectorSpaceCommand(
                    code="KNOWLEDGE_SPACE",
                    modelCode="TEXT_EMBED_3",
                    dimensions=len(VOCABULARY),
                    providerCode="LOCAL",
                ),
            )
        self.knowledge = KnowledgeApplicationService(
            DjangoKnowledgeSourceStore(),
            self.chunkStore,
            embedder=self.embedding,
            settings=KnowledgeSettings(
                strategy="PARAGRAPH", chunkTokens=40, overlapTokens=0, minChunkTokens=0
            ),
            now=lambda: CLOCK,
        )
        self.authorization = AuthorizationService(now=lambda: CLOCK)
        self.subjectId = uuid.uuid4()
        self.principal = AuthorizationPrincipal(
            tenantId=self.tenantId, subjectId=self.subjectId, roles=("ANALYST",)
        )
        self.authorization.registerGrant(
            PermissionGrant(
                tenantId=self.tenantId,
                subjectId=self.subjectId,
                permissionCode="AI_CONTEXT_SOURCE_READ",
                resourceType="CONTEXT_SOURCE",
                allowedClassifications=("PUBLIC", "INTERNAL"),
            )
        )
        self.retrieval = RetrievalApplicationService(
            self.embedding,
            self.knowledge,
            permissionFilter=self.authorization,
            generator=self.generator,
            settings=RetrievalSettings(topK=5, candidateLimit=50, maxContextTokens=4000),
            now=lambda: CLOCK,
        )

    # -- helpers --------------------------------------------------------
    def ingest(
        self,
        entityId: str,
        content: str,
        *,
        classification: str = "INTERNAL",
        tenantId: uuid.UUID | None = None,
        spaceCode: str = "KNOWLEDGE_SPACE",
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
                spaceCode=spaceCode,
            ),
        )

    def ask(self, question: str, **overrides: Any) -> Any:
        params: dict[str, Any] = {
            "spaceCode": "KNOWLEDGE_SPACE",
            "question": question,
            "principal": self.principal,
        }
        params.update(overrides)
        return self.retrieval.retrieve(self.tenantId, RetrievalRequest(**params))

    def references(self, result: Any) -> set[str]:
        return {citation.sourceReference for citation in result.citations}


class EndToEndRetrievalTests(KnowledgeStackTestCase):
    def testIngestedDocumentBecomesRetrievableEvidence(self) -> None:
        self.ingest("production", PRODUCTION_DOC)
        result = self.ask("production output")
        self.assertTrue(result.isGrounded)
        self.assertEqual(self.references(result), {"DOCUMENTS:DOCUMENT:production"})
        self.assertIn("production output", result.prompt.contextText.lower())

    def testEveryCitationPointsAtARealStoredChunk(self) -> None:
        self.ingest("production", PRODUCTION_DOC)
        result = self.ask("maintenance downtime")
        for citation in result.citations:
            self.assertTrue(
                AIKnowledgeChunkRecordModel.objects.filter(
                    tenantId=self.tenantId, id=citation.chunkId
                ).exists()
            )

    def testEveryCitedChunkHasItsVector(self) -> None:
        self.ingest("safety", SAFETY_DOC)
        result = self.ask("protective equipment")
        for citation in result.citations:
            self.assertTrue(
                AIStoredEmbeddingModel.objects.filter(
                    tenantId=self.tenantId, sourceId=str(citation.chunkId)
                ).exists()
            )

    def testTheRightDocumentWinsAmongSeveral(self) -> None:
        self.ingest("production", PRODUCTION_DOC)
        self.ingest("safety", SAFETY_DOC)
        result = self.ask("safety training quality audit")
        self.assertEqual(result.citations[0].sourceReference, "DOCUMENTS:DOCUMENT:safety")

    def testGroundedAnswerRunsThroughTheWholeStack(self) -> None:
        self.ingest("production", PRODUCTION_DOC)
        answer = self.retrieval.answerQuestion(
            self.tenantId,
            RagRequest(
                spaceCode="KNOWLEDGE_SPACE",
                question="what was the production output?",
                principal=self.principal,
                modelCode="TEST_MODEL",
            ),
        )
        self.assertTrue(answer.isGrounded)
        self.assertIn("[1]", self.generator.prompts[-1])
        self.assertEqual(answer.answer, "answer")


class LifecycleInteractionTests(KnowledgeStackTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.created = self.ingest("production", PRODUCTION_DOC)

    def testReindexedContentIsImmediatelyRetrievable(self) -> None:
        self.knowledge.ingestSource(
            self.tenantId,
            IngestKnowledgeCommand(
                sourceDomain="DOCUMENTS",
                sourceEntityType="DOCUMENT",
                sourceEntityId="production",
                title="Document production",
                content=f"{PRODUCTION_DOC}\n\nLine three exceeded its packaging target.",
                spaceCode="KNOWLEDGE_SPACE",
            ),
        )
        result = self.ask("packaging target")
        self.assertIn("packaging", result.prompt.contextText.lower())

    def testRemovedParagraphDisappearsFromRetrieval(self) -> None:
        self.knowledge.ingestSource(
            self.tenantId,
            IngestKnowledgeCommand(
                sourceDomain="DOCUMENTS",
                sourceEntityType="DOCUMENT",
                sourceEntityId="production",
                title="Document production",
                content="Line one reached ninety two percent of planned production output.",
                spaceCode="KNOWLEDGE_SPACE",
            ),
        )
        result = self.ask("maintenance downtime")
        self.assertNotIn("maintenance downtime", result.prompt.contextText.lower())

    def testArchivedSourceLeavesNoEvidenceBehind(self) -> None:
        self.knowledge.archiveSource(self.tenantId, self.created.source.sourceId)
        result = self.ask("production output")
        self.assertEqual(result.candidateCount, 0)
        self.assertFalse(result.isGrounded)

    def testDeletedSourceLeavesNoEvidenceBehind(self) -> None:
        self.knowledge.deleteSource(self.tenantId, self.created.source.sourceId)
        result = self.ask("production output")
        self.assertEqual(result.candidateCount, 0)
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), 0)

    def testReclassifiedSourceFallsOutOfAnUnprivilegedView(self) -> None:
        self.knowledge.ingestSource(
            self.tenantId,
            IngestKnowledgeCommand(
                sourceDomain="DOCUMENTS",
                sourceEntityType="DOCUMENT",
                sourceEntityId="production",
                title="Document production",
                content=PRODUCTION_DOC,
                classification="RESTRICTED",
                spaceCode="KNOWLEDGE_SPACE",
                force=True,
            ),
        )
        result = self.ask("production output")
        self.assertGreater(result.candidateCount, 0)
        self.assertEqual(result.authorizedCount, 0)
        self.assertFalse(result.isGrounded)

    def testUngroundedAnswerIsRefusedAfterArchiving(self) -> None:
        self.knowledge.archiveSource(self.tenantId, self.created.source.sourceId)
        with self.assertRaises(AIRagUngrounded):
            self.retrieval.answerQuestion(
                self.tenantId,
                RagRequest(
                    spaceCode="KNOWLEDGE_SPACE",
                    question="what was the production output?",
                    principal=self.principal,
                ),
            )
        self.assertEqual(self.generator.prompts, [])


class SpaceAndTenantTests(KnowledgeStackTestCase):
    def testRetrievalIsScopedToOneVectorSpace(self) -> None:
        self.embedding.defineVectorSpace(
            self.tenantId,
            DefineVectorSpaceCommand(
                code="ARCHIVE_SPACE",
                modelCode="TEXT_EMBED_3",
                dimensions=len(VOCABULARY),
                providerCode="LOCAL",
            ),
        )
        self.ingest("production", PRODUCTION_DOC)
        self.ingest("safety", SAFETY_DOC, spaceCode="ARCHIVE_SPACE")
        vectorOnly = RetrievalPolicy(strategy="VECTOR", topK=5, candidateLimit=50)
        result = self.ask("protective equipment", policy=vectorOnly)
        self.assertNotIn("DOCUMENTS:DOCUMENT:safety", self.references(result))
        archived = self.retrieval.retrieve(
            self.tenantId,
            RetrievalRequest(
                spaceCode="ARCHIVE_SPACE",
                question="protective equipment",
                principal=self.principal,
                policy=vectorOnly,
            ),
        )
        self.assertEqual(self.references(archived), {"DOCUMENTS:DOCUMENT:safety"})

    def testAnotherTenantsKnowledgeIsInvisible(self) -> None:
        self.ingest("foreign", SAFETY_DOC, tenantId=self.otherTenantId)
        result = self.ask("protective equipment clean room")
        self.assertEqual(result.candidateCount, 0)
        self.assertFalse(result.isGrounded)

    def testTwoTenantsRetrieveTheirOwnCopyOfTheSameDocument(self) -> None:
        self.ingest("shared", PRODUCTION_DOC)
        self.ingest("shared", PRODUCTION_DOC, tenantId=self.otherTenantId)
        mine = self.ask("production output")
        self.assertTrue(mine.isGrounded)
        for citation in mine.citations:
            self.assertTrue(
                AIKnowledgeChunkRecordModel.objects.filter(
                    tenantId=self.tenantId, id=citation.chunkId
                ).exists()
            )


class ScaleAndOrderingTests(KnowledgeStackTestCase):
    def setUp(self) -> None:
        super().setUp()
        for index in range(12):
            topic = "production output" if index % 2 == 0 else "safety training"
            self.ingest(f"doc-{index}", f"Document {index} discusses {topic} in detail.")

    def testRankingIsStableAcrossIdenticalRuns(self) -> None:
        first = self.ask("production output")
        second = self.ask("production output")
        self.assertEqual(
            [citation.chunkId for citation in first.citations],
            [citation.chunkId for citation in second.citations],
        )

    def testTopKIsRespectedOverALargerCorpus(self) -> None:
        result = self.ask("production output", policy=RetrievalPolicy(topK=3, candidateLimit=50))
        self.assertEqual(len(result.citations), 3)
        self.assertGreaterEqual(result.candidateCount, 6)

    def testEveryCitedBlockMatchesTheTopic(self) -> None:
        result = self.ask("safety training", policy=RetrievalPolicy(topK=3, candidateLimit=50))
        for citation in result.citations:
            chunk = self.knowledge.describeChunk(self.tenantId, citation.chunkId)
            self.assertIn("safety training", chunk.text.lower())

    def testTraceCountsMatchTheStoredCorpus(self) -> None:
        result = self.ask("production output")
        self.assertEqual(result.trace.countFor("AUTHORIZE"), result.authorizedCount)
        self.assertEqual(result.authorizedCount, result.candidateCount)
        self.assertLessEqual(result.trace.countFor("CONTEXT"), result.trace.countFor("RERANK"))
