"""Phase 13-V integration tests — ``DjangoFeedbackStore`` over real SQLite.

Covers the ``aiFeedbackEntries`` persistence contract: signal round trips
with their provenance, the fingerprint lookup and its tenant-scoped
uniqueness (which is what makes submission idempotent), the filtered
listings the summary and trend windows are built on, the domain clock
winning over ``auto_now_add``, lifecycle updates, the status backlog, and
the retention sweep that only removes settled signals.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.ai.domain.entities.feedbackRecords import AIFeedbackEntry
from apps.ai.domain.exceptions import AIFeedbackInvalid
from apps.ai.domain.valueObjects.feedbackTypes import feedbackFingerprint
from apps.ai.infrastructure.models import AIFeedbackEntryModel
from apps.ai.infrastructure.repositories.feedbackRepositories import (
    DjangoFeedbackStore,
    feedbackToEntity,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


class DjangoFeedbackStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.userId = uuid.uuid4()
        self.store = DjangoFeedbackStore()

    def entry(self, **overrides: object) -> AIFeedbackEntry:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "requestId": overrides.pop("requestId", uuid.uuid4()),
            "responseId": overrides.pop("responseId", uuid.uuid4()),
            "userId": overrides.pop("userId", self.userId),
            "kind": "RATING",
            "rating": 2,
            "reason": "UNGROUNDED",
            "correction": "the right answer",
            "question": "what was the production output",
            "comment": "missed the number",
            "modelCode": "GPT_TEST",
            "promptVersion": "3",
            "capabilityCode": "QUESTION_ANSWERING",
            "metadata": {"origin": "test"},
            "createdAt": overrides.pop("createdAt", CLOCK),
            "updatedAt": overrides.pop("updatedAt", CLOCK),
        }
        params.update(overrides)
        return AIFeedbackEntry(**params)

    # -- round trip -----------------------------------------------------
    def testRoundTripPreservesTheWholeSignal(self) -> None:
        stored = self.store.saveEntry(self.entry())
        loaded = self.store.getEntry(self.tenantId, stored.id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.kind, "RATING")
        self.assertEqual(loaded.rating, 2)
        self.assertEqual(loaded.sentiment, "NEGATIVE")
        self.assertEqual(loaded.reason, "UNGROUNDED")
        self.assertEqual(loaded.correction, "the right answer")
        self.assertEqual(loaded.question, "what was the production output")
        self.assertEqual(loaded.targetKey, "GPT_TEST@3")
        self.assertEqual(loaded.capabilityCode, "QUESTION_ANSWERING")
        self.assertEqual(loaded.metadata, {"origin": "test"})
        self.assertEqual(loaded.status, "NEW")

    def testTheDomainClockWinsOverAutoNowAdd(self) -> None:
        stored = self.store.saveEntry(self.entry(createdAt=CLOCK - timedelta(days=3)))
        self.assertEqual(stored.createdAt, CLOCK - timedelta(days=3))
        row = AIFeedbackEntryModel.objects.get(id=stored.id)
        self.assertEqual(row.createdAt, CLOCK - timedelta(days=3))

    def testUnknownSignalReadsAsNone(self) -> None:
        self.assertIsNone(self.store.getEntry(self.tenantId, uuid.uuid4()))

    def testReadsAreTenantScoped(self) -> None:
        stored = self.store.saveEntry(self.entry())
        self.assertIsNone(self.store.getEntry(self.otherTenantId, stored.id))
        self.assertIsNone(self.store.findByFingerprint(self.otherTenantId, stored.fingerprint))

    # -- fingerprint ----------------------------------------------------
    def testFingerprintLookupFindsTheSlot(self) -> None:
        stored = self.store.saveEntry(self.entry())
        found = self.store.findByFingerprint(self.tenantId, stored.fingerprint)
        assert found is not None
        self.assertEqual(found.id, stored.id)

    def testOneSignalPerFingerprintIsEnforcedByTheDatabase(self) -> None:
        request, response = uuid.uuid4(), uuid.uuid4()
        self.store.saveEntry(self.entry(requestId=request, responseId=response))
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.store.saveEntry(self.entry(requestId=request, responseId=response))

    def testTheSameFingerprintMayExistInTwoTenants(self) -> None:
        request, response = uuid.uuid4(), uuid.uuid4()
        self.store.saveEntry(self.entry(requestId=request, responseId=response))
        self.store.saveEntry(
            self.entry(requestId=request, responseId=response, tenantId=self.otherTenantId)
        )
        self.assertEqual(AIFeedbackEntryModel.objects.count(), 2)

    def testFingerprintMatchesTheDomainHelper(self) -> None:
        request, response = uuid.uuid4(), uuid.uuid4()
        stored = self.store.saveEntry(self.entry(requestId=request, responseId=response))
        self.assertEqual(
            stored.fingerprint,
            feedbackFingerprint(request, self.userId, "RATING", responseId=response),
        )

    # -- listings -------------------------------------------------------
    def testListingFiltersByStatus(self) -> None:
        first = self.store.saveEntry(self.entry())
        self.store.saveEntry(self.entry())
        first.accept(now=CLOCK)
        self.store.updateEntry(first)
        self.assertEqual(len(self.store.listEntries(self.tenantId, statuses=("ACCEPTED",))), 1)
        self.assertEqual(len(self.store.listEntries(self.tenantId, statuses=("NEW",))), 1)

    def testListingFiltersBySentimentAndModel(self) -> None:
        self.store.saveEntry(self.entry(rating=5, reason="", correction=""))
        self.store.saveEntry(self.entry(modelCode="OTHER_MODEL"))
        positive = self.store.listEntries(self.tenantId, sentiments=("POSITIVE",))
        self.assertEqual(len(positive), 1)
        scoped = self.store.listEntries(self.tenantId, modelCode="other_model")
        self.assertEqual(len(scoped), 1)

    def testListingFiltersByRequest(self) -> None:
        request = uuid.uuid4()
        self.store.saveEntry(self.entry(requestId=request))
        self.store.saveEntry(self.entry())
        self.assertEqual(len(self.store.listEntries(self.tenantId, requestId=request)), 1)

    def testListingFiltersByTimeWindow(self) -> None:
        self.store.saveEntry(self.entry(createdAt=CLOCK - timedelta(days=10)))
        self.store.saveEntry(self.entry(createdAt=CLOCK - timedelta(days=1)))
        recent = self.store.listEntries(self.tenantId, since=CLOCK - timedelta(days=7), until=CLOCK)
        self.assertEqual(len(recent), 1)

    def testListingIsOrderedOldestFirstAndBounded(self) -> None:
        for offset in (3, 1, 2):
            self.store.saveEntry(self.entry(createdAt=CLOCK - timedelta(days=offset)))
        rows = self.store.listEntries(self.tenantId)
        self.assertEqual(
            [row.createdAt for row in rows],
            sorted(row.createdAt for row in rows),
        )
        self.assertEqual(len(self.store.listEntries(self.tenantId, limit=2)), 2)

    def testListingIsTenantScoped(self) -> None:
        self.store.saveEntry(self.entry())
        self.store.saveEntry(self.entry(tenantId=self.otherTenantId))
        self.assertEqual(len(self.store.listEntries(self.tenantId)), 1)

    def testStatusBacklogCountsEveryState(self) -> None:
        first = self.store.saveEntry(self.entry())
        self.store.saveEntry(self.entry())
        first.reject("duplicate", now=CLOCK)
        self.store.updateEntry(first)
        backlog = self.store.countByStatus(self.tenantId)
        self.assertEqual(backlog, {"NEW": 1, "REJECTED": 1})
        self.assertEqual(self.store.countByStatus(self.otherTenantId), {})

    # -- updates --------------------------------------------------------
    def testUpdatePersistsTheTriageState(self) -> None:
        stored = self.store.saveEntry(self.entry())
        stored.accept(reviewerId=self.userId, now=CLOCK)
        updated = self.store.updateEntry(stored)
        self.assertEqual(updated.status, "ACCEPTED")
        self.assertEqual(updated.triagedBy, self.userId)
        self.assertEqual(updated.triagedAt, CLOCK)

    def testUpdatePersistsPromotion(self) -> None:
        stored = self.store.saveEntry(self.entry())
        stored.promote("FEEDBACK_001", suiteCode="FEEDBACK_GOLDEN", now=CLOCK)
        updated = self.store.updateEntry(stored)
        self.assertEqual(updated.status, "PROMOTED")
        self.assertEqual(updated.promotedCaseCode, "FEEDBACK_001")
        self.assertEqual(updated.suiteCode, "FEEDBACK_GOLDEN")

    def testUpdatePersistsARevision(self) -> None:
        stored = self.store.saveEntry(self.entry(rating=1))
        stored.revise(rating=5, now=CLOCK + timedelta(minutes=1))
        updated = self.store.updateEntry(stored)
        self.assertEqual(updated.rating, 5)
        self.assertEqual(updated.sentiment, "POSITIVE")
        self.assertEqual(updated.updatedAt, CLOCK + timedelta(minutes=1))

    def testUpdatingAnUnknownRowIsRefused(self) -> None:
        with self.assertRaises(AIFeedbackInvalid):
            self.store.updateEntry(self.entry())

    # -- retention ------------------------------------------------------
    def testRetentionRemovesSettledSignalsOnly(self) -> None:
        pending = self.store.saveEntry(self.entry(createdAt=CLOCK - timedelta(days=900)))
        settled = self.store.saveEntry(self.entry(createdAt=CLOCK - timedelta(days=900)))
        settled.reject("duplicate", now=CLOCK)
        self.store.updateEntry(settled)
        removed = self.store.deleteEntriesBefore(self.tenantId, CLOCK - timedelta(days=30))
        self.assertEqual(removed, 1)
        self.assertTrue(AIFeedbackEntryModel.objects.filter(id=pending.id).exists())

    def testRetentionSparesRecentSettledSignals(self) -> None:
        settled = self.store.saveEntry(self.entry(createdAt=CLOCK))
        settled.reject("duplicate", now=CLOCK)
        self.store.updateEntry(settled)
        self.assertEqual(
            self.store.deleteEntriesBefore(self.tenantId, CLOCK - timedelta(days=30)), 0
        )

    def testRetentionCanRunAcrossAllTenants(self) -> None:
        for tenant in (self.tenantId, self.otherTenantId):
            entry = self.store.saveEntry(
                self.entry(tenantId=tenant, createdAt=CLOCK - timedelta(days=900))
            )
            entry.promote("CASE", now=CLOCK)
            self.store.updateEntry(entry)
        self.assertEqual(self.store.deleteEntriesBefore(None, CLOCK - timedelta(days=30)), 2)

    # -- mapping --------------------------------------------------------
    def testMapperProducesAValidatedEntity(self) -> None:
        stored = self.store.saveEntry(self.entry())
        row = AIFeedbackEntryModel.objects.get(id=stored.id)
        entity = feedbackToEntity(row)
        self.assertIsInstance(entity, AIFeedbackEntry)
        self.assertEqual(entity.suggestedMetric(), "GROUNDEDNESS")
        self.assertEqual(entity.fingerprint, stored.fingerprint)

    def testANonRatingSignalRoundTripsWithoutARating(self) -> None:
        stored = self.store.saveEntry(
            self.entry(kind="FLAG", rating=None, reason="UNSAFE", correction="")
        )
        loaded = self.store.getEntry(self.tenantId, stored.id)
        assert loaded is not None
        self.assertIsNone(loaded.rating)
        self.assertEqual(loaded.sentiment, "NEGATIVE")
        self.assertEqual(loaded.suggestedMetric(), "SAFETY")
