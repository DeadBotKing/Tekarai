"""Phase 13-P integration tests — ``DjangoJobStore`` contract over SQLite.

Covers the ledger round trip (including the empty-key sentinel), the
idempotent save, tenant-scoped reads, atomic single-flight claiming
(ordering, lease guards, expiry reclaim, cross-tenant mode), updates,
and retention deletes — all against the real ``aiJobs`` table.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from django.test import TestCase

from apps.ai.domain.entities.jobRecords import AIJob
from apps.ai.domain.exceptions import AIJobInvalid, AIJobNotFound
from apps.ai.infrastructure.models import AIJobModel
from apps.ai.infrastructure.repositories.queueRepositories import (
    DjangoJobStore,
    jobToEntity,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


def makeJob(tenantId: uuid.UUID, **overrides) -> AIJob:
    params: dict = {"tenantId": tenantId, "kind": "EMBEDDING", "runAt": CLOCK}
    params.update(overrides)
    return AIJob(**params)


class DjangoJobStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.store = DjangoJobStore()

    def testSaveGetRoundTrip(self) -> None:
        job = makeJob(
            self.tenantId,
            payload={"doc": "a"},
            idempotencyKey="k1",
            priority=7,
            maxAttempts=5,
            requestId=uuid.uuid4(),
            correlationId="c1",
            traceId="t1",
        )
        stored = self.store.save(job)
        fetched = self.store.get(self.tenantId, job.id)
        assert fetched is not None
        self.assertEqual(fetched.id, job.id)
        self.assertEqual(fetched.kind, "EMBEDDING")
        self.assertEqual(fetched.payload, {"doc": "a"})
        self.assertEqual(fetched.idempotencyKey, "k1")
        self.assertEqual(fetched.priority, 7)
        self.assertEqual(fetched.maxAttempts, 5)
        self.assertEqual(fetched.requestId, job.requestId)
        self.assertEqual(fetched.status, "PENDING")
        self.assertEqual(stored.id, job.id)

    def testEmptyKeysUseSentinelsAndNeverMatch(self) -> None:
        first = self.store.save(makeJob(self.tenantId))
        second = self.store.save(makeJob(self.tenantId))
        self.assertNotEqual(first.id, second.id)
        rows = AIJobModel.objects.filter(tenantId=self.tenantId)
        self.assertEqual(rows.count(), 2)
        for row in rows:
            self.assertTrue(row.idempotencyKey.startswith("none:"))
        self.assertEqual(jobToEntity(rows.first()).idempotencyKey if rows.first() else None, "")
        self.assertIsNone(self.store.findByIdempotencyKey(self.tenantId, ""))

    def testDuplicateKeySaveReturnsExisting(self) -> None:
        first = self.store.save(makeJob(self.tenantId, idempotencyKey="k1"))
        twin = makeJob(self.tenantId, idempotencyKey="k1", payload={"other": True})
        second = self.store.save(twin)
        self.assertEqual(second.id, first.id)
        self.assertEqual(second.payload, {})
        found = self.store.findByIdempotencyKey(self.tenantId, "k1")
        assert found is not None
        self.assertEqual(found.id, first.id)

    def testReadsAreTenantScoped(self) -> None:
        job = self.store.save(makeJob(self.tenantId, idempotencyKey="k1"))
        self.assertIsNone(self.store.get(self.otherTenantId, job.id))
        self.assertIsNone(self.store.findByIdempotencyKey(self.otherTenantId, "k1"))
        self.assertEqual(self.store.listTenantJobs(self.otherTenantId), ())

    def testUpdatePersistsTransitions(self) -> None:
        job = self.store.save(makeJob(self.tenantId))
        job.status = "RUNNING"
        job.attempts = 1
        job.claimedBy = "w1"
        job.leaseExpiresAt = CLOCK + timedelta(seconds=60)
        job.resultSummary = {"pages": 2}
        job.errorCode = "E_X"
        updated = self.store.update(job)
        self.assertEqual(updated.status, "RUNNING")
        self.assertEqual(updated.attempts, 1)
        self.assertEqual(updated.resultSummary, {"pages": 2})
        fetched = self.store.get(self.tenantId, job.id)
        assert fetched is not None
        self.assertEqual(fetched.claimedBy, "w1")
        self.assertEqual(fetched.errorCode, "E_X")

    def testUpdateMissingRaises404(self) -> None:
        with self.assertRaises(AIJobNotFound):
            self.store.update(makeJob(self.tenantId))

    def testSaveRejectsNonJobs(self) -> None:
        with self.assertRaises(AIJobInvalid):
            self.store.save("not-a-job")  # type: ignore[arg-type]

    def testClaimRowOrdersAndClaimsOnce(self) -> None:
        low = self.store.save(makeJob(self.tenantId, priority=1))
        early = self.store.save(
            makeJob(self.tenantId, priority=5, runAt=CLOCK - timedelta(seconds=10))
        )
        late = self.store.save(makeJob(self.tenantId, priority=5))
        high = self.store.save(makeJob(self.tenantId, priority=9))
        future = self.store.save(makeJob(self.tenantId, runAt=CLOCK + timedelta(seconds=3600)))
        claimed = self.store.claimRow(self.tenantId, "w1", 60, 10, CLOCK)
        self.assertEqual([job.id for job in claimed], [high.id, early.id, late.id, low.id])
        first = claimed[0]
        self.assertEqual(first.status, "RUNNING")
        self.assertEqual(first.attempts, 1)
        self.assertEqual(first.claimedBy, "w1")
        self.assertEqual(first.leaseExpiresAt, CLOCK + timedelta(seconds=60))
        self.assertEqual(self.store.claimRow(self.tenantId, "w1", 60, 10, CLOCK), ())
        pending = self.store.get(self.tenantId, future.id)
        assert pending is not None
        self.assertEqual(pending.status, "PENDING")

    def testClaimRowRespectsTenantFilter(self) -> None:
        mine = self.store.save(makeJob(self.tenantId))
        self.store.save(makeJob(self.otherTenantId))
        (claimed,) = self.store.claimRow(self.tenantId, "w1", 60, 10, CLOCK)
        self.assertEqual(claimed.id, mine.id)
        other = self.store.get(self.otherTenantId, claimed.id)
        self.assertIsNone(other)

    def testClaimRowWithoutTenantClaimsAcrossTenants(self) -> None:
        self.store.save(makeJob(self.tenantId))
        self.store.save(makeJob(self.otherTenantId))
        claimed = self.store.claimRow(None, "w1", 60, 10, CLOCK)
        self.assertEqual(len(claimed), 2)

    def testExpiredLeaseIsReclaimedWithAttemptBump(self) -> None:
        job = self.store.save(makeJob(self.tenantId))
        (first,) = self.store.claimRow(self.tenantId, "w1", 60, 10, CLOCK)
        self.assertEqual(first.id, job.id)
        later = CLOCK + timedelta(seconds=61)
        (reclaimed,) = self.store.claimRow(self.tenantId, "w2", 120, 10, later)
        self.assertEqual(reclaimed.id, job.id)
        self.assertEqual(reclaimed.claimedBy, "w2")
        self.assertEqual(reclaimed.attempts, 2)
        self.assertEqual(reclaimed.leaseExpiresAt, later + timedelta(seconds=120))

    def testClaimRowValidatesInputs(self) -> None:
        with self.assertRaises(AIJobInvalid):
            self.store.claimRow(self.tenantId, "", 60, 10, CLOCK)
        with self.assertRaises(AIJobInvalid):
            self.store.claimRow(self.tenantId, "w1", 0, 10, CLOCK)
        with self.assertRaises(AIJobInvalid):
            self.store.claimRow(self.tenantId, "w1", 60, 0, CLOCK)

    def testListTenantJobsIsOrderedAndIsolated(self) -> None:
        first = self.store.save(makeJob(self.tenantId))
        second = self.store.save(makeJob(self.tenantId))
        self.store.save(makeJob(self.otherTenantId))
        listed = self.store.listTenantJobs(self.tenantId)
        self.assertEqual([item.id for item in listed], [first.id, second.id])

    def testDeleteJobsBeforeRemovesOnlyTerminalOldRows(self) -> None:
        oldDone = self.store.save(makeJob(self.tenantId))
        oldDone.status = "SUCCEEDED"
        self.store.update(oldDone)
        AIJobModel.objects.filter(id=oldDone.id).update(createdAt=CLOCK - timedelta(days=40))
        oldActive = self.store.save(makeJob(self.tenantId))
        AIJobModel.objects.filter(id=oldActive.id).update(createdAt=CLOCK - timedelta(days=40))
        freshDone = self.store.save(makeJob(self.tenantId))
        freshDone.status = "DEAD"
        self.store.update(freshDone)
        purged = self.store.deleteJobsBefore(
            self.tenantId, CLOCK - timedelta(days=30), ("SUCCEEDED", "FAILED", "DEAD")
        )
        self.assertEqual(purged, 1)
        self.assertIsNone(self.store.get(self.tenantId, oldDone.id))
        self.assertIsNotNone(self.store.get(self.tenantId, oldActive.id))
        self.assertIsNotNone(self.store.get(self.tenantId, freshDone.id))

    def testDeleteJobsBeforeWithoutTenantPurgesGlobally(self) -> None:
        first = self.store.save(makeJob(self.tenantId))
        first.status = "CANCELLED"
        self.store.update(first)
        AIJobModel.objects.filter(id=first.id).update(createdAt=CLOCK - timedelta(days=40))
        purged = self.store.deleteJobsBefore(None, CLOCK - timedelta(days=30), ("CANCELLED",))
        self.assertEqual(purged, 1)
