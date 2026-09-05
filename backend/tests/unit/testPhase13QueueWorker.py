"""Phase 13-P unit tests — async queue and event bus, fully offline.

Covers the closed job vocabularies and retry math, the in-memory queue
coordinator (idempotent submission, single-flight lease claiming,
heartbeat, settlement, cancellation, reads, tenant isolation), and the
in-process event bus (envelope validation, fan-out, failure isolation,
job-payload round trip).
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta

from apps.ai.domain.entities.jobRecords import AIJob
from apps.ai.domain.exceptions import (
    AIEventInvalid,
    AIIdempotencyConflict,
    AIJobInvalid,
    AIJobLeaseConflict,
    AIJobNotFound,
)
from apps.ai.domain.services.eventBus import AIEventEnvelope, EventBusService
from apps.ai.domain.services.jobQueue import (
    JobFilter,
    JobOutcome,
    JobQueueService,
    ensureJobOutcome,
    jobFingerprint,
)
from apps.ai.domain.valueObjects.queueTypes import (
    JOB_KINDS,
    JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    computeBackoff,
    ensureJobKind,
    ensureJobPriority,
    ensureJobStatus,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

START = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


class FixedClock:
    def __init__(self, start: datetime = START) -> None:
        self.moment = start

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, seconds: int) -> datetime:
        self.moment = self.moment + timedelta(seconds=seconds)
        return self.moment


class QueueVocabularyTests(unittest.TestCase):
    def testJobKindsAreClosedToEight(self) -> None:
        self.assertEqual(
            JOB_KINDS,
            (
                "DOCUMENT_ANALYSIS",
                "TRANSCRIPTION",
                "REPORT_GENERATION",
                "EMBEDDING",
                "INDEXING",
                "PREDICTION",
                "GENERIC",
                "EVENT_DISPATCH",
            ),
        )
        self.assertEqual(ensureJobKind("embedding"), "EMBEDDING")
        with self.assertRaises(ValidationFailedError):
            ensureJobKind("TRANSLATION")

    def testJobStatusesAreClosedToSix(self) -> None:
        self.assertEqual(len(JOB_STATUSES), 6)
        self.assertEqual(TERMINAL_JOB_STATUSES, ("SUCCEEDED", "FAILED", "CANCELLED", "DEAD"))
        self.assertEqual(ensureJobStatus("dead"), "DEAD")
        with self.assertRaises(ValidationFailedError):
            ensureJobStatus("STUCK")

    def testPriorityBounds(self) -> None:
        self.assertEqual(ensureJobPriority(0), 0)
        self.assertEqual(ensureJobPriority(9), 9)
        for bad in (-1, 10, True, "5", None):
            with self.assertRaises(ValidationFailedError, msg=str(bad)):
                ensureJobPriority(bad)  # type: ignore[arg-type]

    def testBackoffMath(self) -> None:
        self.assertEqual(computeBackoff(1, 30, 2.0, 600), 30)
        self.assertEqual(computeBackoff(2, 30, 2.0, 600), 60)
        self.assertEqual(computeBackoff(3, 30, 2.0, 600), 120)
        self.assertEqual(computeBackoff(6, 30, 2.0, 600), 600)
        with self.assertRaises(ValidationFailedError):
            computeBackoff(0, 30, 2.0, 600)
        with self.assertRaises(ValidationFailedError):
            computeBackoff(1, -1, 2.0, 600)
        with self.assertRaises(ValidationFailedError):
            computeBackoff(1, 30, 0.5, 600)

    def testJobOutcomeValidation(self) -> None:
        self.assertEqual(ensureJobOutcome("succeeded"), "SUCCEEDED")
        outcome = JobOutcome(outcome="FAILED", retryable=False, errorCode="E_X")
        self.assertEqual(outcome.errorCode, "E_X")
        with self.assertRaises(ValidationFailedError):
            ensureJobOutcome("RETRY")
        with self.assertRaises(ValueError):
            JobOutcome(outcome="SUCCEEDED", retryable="yes")  # type: ignore[arg-type]


class JobSubmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FixedClock()
        self.queue = JobQueueService(now=self.clock)
        self.tenant = uuid.uuid4()

    def testSubmitDefaults(self) -> None:
        job = self.queue.submit(self.tenant, "EMBEDDING", payload={"doc": "a"})
        self.assertEqual(job.status, "PENDING")
        self.assertEqual(job.attempts, 0)
        self.assertEqual(job.maxAttempts, 3)
        self.assertEqual(job.priority, 5)
        self.assertEqual(job.runAt, START)
        self.assertEqual(job.idempotencyKey, "")
        self.assertIsInstance(job, AIJob)

    def testIdempotentResubmitReturnsStoredJob(self) -> None:
        first = self.queue.submit(
            self.tenant, "EMBEDDING", payload={"doc": "a"}, idempotencyKey="k1"
        )
        second = self.queue.submit(
            self.tenant, "EMBEDDING", payload={"doc": "a"}, idempotencyKey="k1"
        )
        self.assertEqual(first.id, second.id)

    def testConflictingKeyRaises409(self) -> None:
        self.queue.submit(self.tenant, "EMBEDDING", payload={"doc": "a"}, idempotencyKey="k1")
        with self.assertRaises(AIIdempotencyConflict) as raised:
            self.queue.submit(self.tenant, "EMBEDDING", payload={"doc": "b"}, idempotencyKey="k1")
        self.assertEqual(raised.exception.code, "AI_IDEMPOTENCY_CONFLICT")
        self.assertEqual(raised.exception.httpStatus, 409)

    def testEmptyKeysDoNotCollide(self) -> None:
        first = self.queue.submit(self.tenant, "EMBEDDING")
        second = self.queue.submit(self.tenant, "EMBEDDING")
        self.assertNotEqual(first.id, second.id)

    def testKeysAreTenantScoped(self) -> None:
        first = self.queue.submit(
            self.tenant, "EMBEDDING", payload={"doc": "a"}, idempotencyKey="k1"
        )
        second = self.queue.submit(
            uuid.uuid4(), "EMBEDDING", payload={"doc": "a"}, idempotencyKey="k1"
        )
        self.assertNotEqual(first.id, second.id)

    def testInvalidKindIs422(self) -> None:
        with self.assertRaises(AIJobInvalid) as raised:
            self.queue.submit(self.tenant, "TRANSLATION")
        self.assertEqual(raised.exception.httpStatus, 422)


class ClaimLeaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FixedClock()
        self.queue = JobQueueService(now=self.clock)
        self.tenant = uuid.uuid4()

    def testClaimSetsRunningLeaseAndAttempt(self) -> None:
        job = self.queue.submit(self.tenant, "EMBEDDING")
        (claimed,) = self.queue.claimDue("w1", 120, 10)
        self.assertEqual(claimed.id, job.id)
        self.assertEqual(claimed.status, "RUNNING")
        self.assertEqual(claimed.claimedBy, "w1")
        self.assertEqual(claimed.attempts, 1)
        self.assertEqual(claimed.leaseExpiresAt, START + timedelta(seconds=120))

    def testClaimOrderingIsPriorityThenRunAt(self) -> None:
        low = self.queue.submit(self.tenant, "EMBEDDING", priority=1)
        high = self.queue.submit(self.tenant, "EMBEDDING", priority=9)
        (first, second) = self.queue.claimDue("w1", 60, 10)
        self.assertEqual(first.id, high.id)
        self.assertEqual(second.id, low.id)

    def testFutureRunAtIsNotClaimed(self) -> None:
        self.queue.submit(self.tenant, "EMBEDDING", runAt=START + timedelta(seconds=3600))
        self.assertEqual(self.queue.claimDue("w1", 60, 10), ())

    def testHeartbeatRequiresTheLease(self) -> None:
        job = self.queue.submit(self.tenant, "EMBEDDING")
        self.queue.claimDue("w1", 60, 10)
        with self.assertRaises(AIJobLeaseConflict) as raised:
            self.queue.heartbeat(self.tenant, job.id, "w2", 60)
        self.assertEqual(raised.exception.httpStatus, 409)
        extended = self.queue.heartbeat(self.tenant, job.id, "w1", 600)
        self.assertEqual(extended.leaseExpiresAt, START + timedelta(seconds=600))

    def testExpiredLeaseIsReclaimable(self) -> None:
        job = self.queue.submit(self.tenant, "EMBEDDING")
        self.queue.claimDue("w1", 60, 10)
        self.clock.advance(61)
        (reclaimed,) = self.queue.claimDue("w2", 60, 10)
        self.assertEqual(reclaimed.id, job.id)
        self.assertEqual(reclaimed.claimedBy, "w2")
        self.assertEqual(reclaimed.attempts, 2)

    def testMissingJobIs404(self) -> None:
        with self.assertRaises(AIJobNotFound) as raised:
            self.queue.getJob(self.tenant, uuid.uuid4())
        self.assertEqual(raised.exception.httpStatus, 404)


class SettleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FixedClock()
        self.queue = JobQueueService(now=self.clock)
        self.tenant = uuid.uuid4()

    def _claimed(self, **kwargs) -> AIJob:
        job = self.queue.submit(self.tenant, "EMBEDDING", **kwargs)
        (claimed,) = self.queue.claimDue("w1", 120, 10)
        self.assertEqual(claimed.id, job.id)
        return job

    def testCompleteRequiresTheLease(self) -> None:
        job = self._claimed()
        with self.assertRaises(AIJobLeaseConflict):
            self.queue.complete(self.tenant, job.id, "w2", summary={"ok": True})
        done = self.queue.complete(self.tenant, job.id, "w1", summary={"ok": True})
        self.assertEqual(done.status, "SUCCEEDED")
        self.assertEqual(done.resultSummary, {"ok": True})
        self.assertEqual(done.claimedBy, "")
        self.assertIsNone(done.leaseExpiresAt)
        self.assertTrue(done.isTerminal)

    def testRetryableFailureRequeuesWithBackoff(self) -> None:
        job = self._claimed()
        failed = self.queue.failJob(
            self.tenant,
            job.id,
            "w1",
            errorCode="E_BOOM",
            retryable=True,
            baseSeconds=30,
            multiplier=2.0,
            maxSeconds=600,
        )
        self.assertEqual(failed.status, "PENDING")
        self.assertEqual(failed.runAt, START + timedelta(seconds=30))
        self.assertEqual(failed.errorCode, "E_BOOM")
        self.assertEqual(failed.attempts, 1)

    def testExhaustedAttemptsDeadLetter(self) -> None:
        job = self._claimed(maxAttempts=1)
        dead = self.queue.failJob(self.tenant, job.id, "w1", errorCode="E_BOOM")
        self.assertEqual(dead.status, "DEAD")
        self.assertTrue(dead.isTerminal)

    def testUnretryableFailureSettlesFailed(self) -> None:
        job = self._claimed()
        failed = self.queue.failJob(
            self.tenant, job.id, "w1", errorCode="HANDLER_MISSING", retryable=False
        )
        self.assertEqual(failed.status, "FAILED")
        self.assertEqual(failed.errorCode, "HANDLER_MISSING")
        self.assertTrue(failed.isTerminal)

    def testCancelRules(self) -> None:
        pending = self.queue.submit(self.tenant, "EMBEDDING")
        cancelled = self.queue.cancelJob(self.tenant, pending.id)
        self.assertEqual(cancelled.status, "CANCELLED")
        with self.assertRaises(AIJobInvalid):
            self.queue.cancelJob(self.tenant, pending.id)
        running = self._claimed()
        with self.assertRaises(AIJobLeaseConflict):
            self.queue.cancelJob(self.tenant, running.id, workerId="w2")
        self.clock.advance(121)
        expired = self.queue.cancelJob(self.tenant, running.id, workerId="w2")
        self.assertEqual(expired.status, "CANCELLED")


class JobReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FixedClock()
        self.queue = JobQueueService(now=self.clock)
        self.tenant = uuid.uuid4()

    def testDescribeAndListFilters(self) -> None:
        first = self.queue.submit(self.tenant, "EMBEDDING", payload={"doc": "a"}, priority=7)
        self.queue.submit(self.tenant, "TRANSCRIPTION")
        other = self.queue.submit(uuid.uuid4(), "EMBEDDING")
        (claimed,) = self.queue.claimDue("w1", 60, 1)
        self.assertEqual(claimed.id, first.id)
        descriptor = self.queue.describeJob(self.tenant, first.id)
        self.assertEqual(descriptor.jobId, first.id)
        self.assertEqual(descriptor.kind, "EMBEDDING")
        self.assertEqual(descriptor.status, "RUNNING")
        self.assertEqual(descriptor.payload, {"doc": "a"})
        running = self.queue.listJobs(self.tenant, JobFilter(status="RUNNING"))
        self.assertEqual([item.jobId for item in running], [first.id])
        embedded = self.queue.listJobs(self.tenant, JobFilter(kind="EMBEDDING"))
        self.assertEqual(len(embedded), 1)
        everything = self.queue.listJobs(self.tenant)
        self.assertEqual(len(everything), 2)
        self.assertNotIn(other.id, [item.jobId for item in everything])

    def testForgetDropsHydratedCopiesAndKeyBindings(self) -> None:
        job = self.queue.submit(self.tenant, "EMBEDDING", payload={"doc": "a"}, idempotencyKey="k1")
        self.assertTrue(self.queue.forget(self.tenant, job.id))
        self.assertFalse(self.queue.forget(self.tenant, job.id))
        with self.assertRaises(AIJobNotFound):
            self.queue.getJob(self.tenant, job.id)
        fresh = self.queue.submit(
            self.tenant, "EMBEDDING", payload={"doc": "a"}, idempotencyKey="k1"
        )
        self.assertNotEqual(fresh.id, job.id)

    def testFingerprintIsStableAndScoped(self) -> None:
        first = self.queue.submit(
            self.tenant, "EMBEDDING", payload={"doc": "a"}, idempotencyKey="k1"
        )
        twin = self.queue.submit(
            self.tenant, "EMBEDDING", payload={"doc": "a"}, idempotencyKey="k1"
        )
        self.assertEqual(jobFingerprint(first), jobFingerprint(twin))
        other = self.queue.submit(
            uuid.uuid4(), "EMBEDDING", payload={"doc": "a"}, idempotencyKey="k1"
        )
        self.assertNotEqual(jobFingerprint(first), jobFingerprint(other))
        with self.assertRaises(ValueError):
            jobFingerprint("not-a-job")  # type: ignore[arg-type]


class EventBusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = EventBusService()
        self.tenant = uuid.uuid4()

    def testEnvelopeValidation(self) -> None:
        envelope = AIEventEnvelope(
            tenantId=self.tenant, eventName="USAGE_RECORDED", payload={"n": 1}
        )
        self.assertEqual(envelope.eventName, "USAGE_RECORDED")
        self.assertEqual(envelope.payload, {"n": 1})
        with self.assertRaises(ValidationFailedError):
            AIEventEnvelope(tenantId=self.tenant, eventName="SOMETHING_ELSE")
        with self.assertRaises(AIEventInvalid):
            AIEventEnvelope(
                tenantId=self.tenant,
                eventName="USAGE_RECORDED",
                payload=["nope"],  # type: ignore[arg-type]
            )

    def testFanoutReachesEverySubscriber(self) -> None:
        seen: list[str] = []

        class First:
            def handle(self, envelope: AIEventEnvelope) -> None:
                seen.append(f"first:{envelope.eventName}")

        class Second:
            def handle(self, envelope: AIEventEnvelope) -> None:
                seen.append(f"second:{envelope.eventName}")

        class Other:
            def handle(self, envelope: AIEventEnvelope) -> None:
                seen.append("other")

        self.bus.subscribe("USAGE_RECORDED", First())
        self.bus.subscribe("USAGE_RECORDED", Second())
        self.bus.subscribe("JOB_ENQUEUED", Other())
        envelope = AIEventEnvelope(tenantId=self.tenant, eventName="USAGE_RECORDED")
        report = self.bus.dispatch(envelope)
        self.assertEqual(seen, ["first:USAGE_RECORDED", "second:USAGE_RECORDED"])
        self.assertTrue(all(item.delivered for item in report.deliveries))
        self.assertEqual(report.envelopeId, envelope.envelopeId)

    def testFailingSubscriberDoesNotStopOthers(self) -> None:
        seen: list[str] = []

        class Bad:
            def handle(self, envelope: AIEventEnvelope) -> None:
                raise RuntimeError("boom")

        class Good:
            def handle(self, envelope: AIEventEnvelope) -> None:
                seen.append("good")

        self.bus.subscribe("USAGE_RECORDED", Bad())
        self.bus.subscribe("USAGE_RECORDED", Good())
        envelope = AIEventEnvelope(tenantId=self.tenant, eventName="USAGE_RECORDED")
        report = self.bus.dispatch(envelope)
        self.assertEqual(seen, ["good"])
        self.assertEqual(len(report.deliveries), 2)
        failed = [item for item in report.deliveries if not item.delivered]
        self.assertEqual(len(failed), 1)
        self.assertIn("boom", failed[0].error)

    def testJobPayloadRoundTrip(self) -> None:
        envelope = AIEventEnvelope(
            tenantId=self.tenant,
            eventName="USAGE_RECORDED",
            payload={"attemptId": "x"},
            correlationId="c",
            traceId="t",
        )
        rebuilt = AIEventEnvelope.fromJobPayload(envelope.toJobPayload())
        self.assertEqual(rebuilt.envelopeId, envelope.envelopeId)
        self.assertEqual(rebuilt.eventName, "USAGE_RECORDED")
        self.assertEqual(rebuilt.tenantId, self.tenant)
        self.assertEqual(rebuilt.payload, {"attemptId": "x"})
        self.assertEqual(rebuilt.correlationId, "c")
        with self.assertRaises(AIEventInvalid):
            AIEventEnvelope.fromJobPayload({"eventName": "USAGE_RECORDED"})
        with self.assertRaises(AIEventInvalid):
            AIEventEnvelope.fromJobPayload(["nope"])

    def testSubscribeDedupesAndUnsubscribes(self) -> None:
        seen: list[str] = []

        class Watcher:
            def handle(self, envelope: AIEventEnvelope) -> None:
                seen.append("hit")

        watcher = Watcher()
        self.bus.subscribe("USAGE_RECORDED", watcher)
        self.bus.subscribe("USAGE_RECORDED", watcher)
        self.assertEqual(self.bus.subscriberCount("USAGE_RECORDED"), 1)
        envelope = AIEventEnvelope(tenantId=self.tenant, eventName="USAGE_RECORDED")
        self.bus.dispatch(envelope)
        self.assertEqual(seen, ["hit"])
        self.bus.unsubscribe("USAGE_RECORDED", watcher)
        self.bus.dispatch(envelope)
        self.assertEqual(seen, ["hit"])
        with self.assertRaises(AIEventInvalid):
            self.bus.subscribe("USAGE_RECORDED", object())


if __name__ == "__main__":
    unittest.main()
