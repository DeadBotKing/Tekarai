"""Phase 13-P application tests — queue and worker over a real SQLite test DB.

Covers idempotent submission (across service instances), the fail-closed
queue switch, the worker loop (success, retry-then-success, exhaustion,
missing handler, governance deny, cancellation, heartbeat, retention),
and durable event transport (cross-instance delivery, idempotent
publish, corrupt payloads, tenant mismatch, subscriber failure, chained
publishes, and the N→P→O usage end-to-end) — all orchestrated through
``QueueApplicationService`` with an in-memory ``JobStore`` double and
the real Django audit stores from Phase 13-O.
"""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.test import TestCase

from apps.ai.application.services.auditService import (
    AuditApplicationService,
    AuditSettings,
    GovernancePolicyCommand,
)
from apps.ai.application.services.queueService import (
    QueueApplicationService,
    QueuedEventBus,
    QueuedUsageEventSink,
    QueueSettings,
    SubmitJobCommand,
    registerAuditSubscriber,
)
from apps.ai.domain.entities.jobRecords import AIJob
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIIdempotencyConflict,
    AIJobLeaseConflict,
    AIJobNotFound,
)
from apps.ai.domain.services.eventBus import AIEventEnvelope, EventBusService
from apps.ai.domain.services.jobQueue import JobFilter, JobOutcome
from apps.ai.domain.services.usageMetering import AIUsageRecorded
from apps.ai.domain.valueObjects.aiTypes import Money
from apps.ai.infrastructure.repositories.auditRepositories import (
    DjangoAuditRecordStore,
    DjangoGovernancePolicyStore,
    DjangoRetentionPurger,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


class InMemoryJobStore:
    """Honest ``JobStore`` double: copies across the boundary like Django."""

    def __init__(self) -> None:
        self._rows: dict[tuple[uuid.UUID, uuid.UUID], AIJob] = {}

    def save(self, job: AIJob) -> AIJob:
        self._rows[(job.tenantId, job.id)] = copy.deepcopy(job)
        return copy.deepcopy(job)

    def get(self, tenantId: uuid.UUID, jobId: uuid.UUID) -> AIJob | None:
        job = self._rows.get((tenantId, jobId))
        return copy.deepcopy(job) if job is not None else None

    def findByIdempotencyKey(self, tenantId: uuid.UUID, idempotencyKey: str) -> AIJob | None:
        key = str(idempotencyKey or "").strip()
        if not key:
            return None
        for (rowTenant, _), job in self._rows.items():
            if rowTenant == tenantId and job.idempotencyKey == key:
                return copy.deepcopy(job)
        return None

    def claimRow(
        self,
        tenantId: uuid.UUID | None,
        workerId: str,
        leaseSeconds: int,
        limit: int,
        now: datetime,
    ) -> tuple[AIJob, ...]:
        due = [
            job
            for (rowTenant, _), job in self._rows.items()
            if (tenantId is None or rowTenant == tenantId)
            and job.status in ("PENDING", "RUNNING")
            and job.runAt <= now
            and (job.leaseExpiresAt is None or job.leaseExpiresAt <= now)
        ]
        due.sort(key=lambda job: (-job.priority, job.runAt, job.createdAt, str(job.id)))
        claimed: list[AIJob] = []
        for job in due[:limit]:
            job.status = "RUNNING"
            job.attempts += 1
            job.claimedBy = workerId
            job.leaseExpiresAt = now + timedelta(seconds=leaseSeconds)
            job.updatedAt = now
            claimed.append(copy.deepcopy(job))
        return tuple(claimed)

    def update(self, job: AIJob) -> AIJob:
        self._rows[(job.tenantId, job.id)] = copy.deepcopy(job)
        return copy.deepcopy(job)

    def listTenantJobs(self, tenantId: uuid.UUID) -> tuple[AIJob, ...]:
        rows = [job for (rowTenant, _), job in self._rows.items() if rowTenant == tenantId]
        rows.sort(key=lambda job: (job.createdAt, str(job.id)))
        return tuple(copy.deepcopy(job) for job in rows)

    def deleteJobsBefore(
        self, tenantId: uuid.UUID | None, cutoff: datetime, statuses: tuple[str, ...]
    ) -> int:
        victims = [
            key
            for key, job in self._rows.items()
            if (tenantId is None or key[0] == tenantId)
            and job.status in statuses
            and job.createdAt < cutoff
        ]
        for key in victims:
            del self._rows[key]
        return len(victims)


class FunctionHandler:
    """Minimal ``JobHandler`` double recording executions."""

    def __init__(self, kind: str, behavior: Any) -> None:
        self._kind = kind
        self._behavior = behavior
        self.calls: list[AIJob] = []

    def kind(self) -> str:
        return self._kind

    def execute(self, job: AIJob) -> JobOutcome:
        self.calls.append(job)
        if callable(self._behavior):
            return self._behavior(job)
        if isinstance(self._behavior, BaseException):
            raise self._behavior
        return self._behavior


def queueSettings(**overrides: Any) -> QueueSettings:
    params: dict[str, Any] = {
        "enabled": True,
        "retentionDays": 30,
        "defaultMaxAttempts": 3,
        "claimLimit": 10,
        "leaseSeconds": 120,
        "retryBaseSeconds": 30,
        "retryMultiplier": 2.0,
        "retryMaxSeconds": 600,
        "workerId": "w-app",
    }
    params.update(overrides)
    return QueueSettings(**params)


def auditSettings(**overrides: Any) -> AuditSettings:
    params: dict[str, Any] = {
        "enabled": True,
        "retentionDays": 365,
        "usageRetentionDays": 90,
        "includeRestrictedDetail": False,
        "governanceEnabled": True,
        "defaultMaxCostPerDay": Money(Decimal("0"), "USD"),
    }
    params.update(overrides)
    return AuditSettings(**params)


class Phase13PQueueBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.store = InMemoryJobStore()
        self.audit = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=auditSettings(),
            now=lambda: CLOCK,
        )
        self.service = QueueApplicationService(
            self.store,
            auditService=self.audit,
            queueSettings=queueSettings(),
            workerId="w-app",
            now=lambda: CLOCK,
        )

    def _submit(self, **overrides: Any) -> Any:
        params: dict[str, Any] = {"tenantId": self.tenantId, "kind": "GENERIC"}
        params.update(overrides)
        return self.service.submitJob(SubmitJobCommand(**params))

    def _actions(self, tenantId: uuid.UUID | None = None) -> list[str]:
        entries = self.audit.listAuditEntries(tenantId or self.tenantId)
        return [entry.action for entry in entries]


class WorkerSubmissionTests(Phase13PQueueBase):
    def testSubmitPersistsAndAuditsEnqueued(self) -> None:
        descriptor = self._submit(
            payload={"task": "summarize"},
            idempotencyKey="job-1",
            requestId=uuid.uuid4(),
        )
        self.assertEqual(descriptor.status, "PENDING")
        self.assertEqual(descriptor.kind, "GENERIC")
        stored = self.service.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(stored.payload, {"task": "summarize"})
        self.assertIn("JOB_ENQUEUED", self._actions())

    def testIdempotentResubmitAcrossServiceInstances(self) -> None:
        first = self._submit(payload={"n": 1}, idempotencyKey="job-1")
        sibling = QueueApplicationService(
            self.store,
            auditService=self.audit,
            queueSettings=queueSettings(),
            workerId="w-other",
            now=lambda: CLOCK,
        )
        second = sibling.submitJob(
            SubmitJobCommand(
                tenantId=self.tenantId,
                kind="GENERIC",
                payload={"n": 1},
                idempotencyKey="job-1",
            )
        )
        self.assertEqual(first.jobId, second.jobId)
        self.assertEqual(len(self.service.listJobs(self.tenantId)), 1)

    def testConflictingResubmitRaises409(self) -> None:
        self._submit(payload={"n": 1}, idempotencyKey="job-1")
        with self.assertRaises(AIIdempotencyConflict):
            self._submit(payload={"n": 2}, idempotencyKey="job-1")

    def testDisabledQueueIsFailClosed(self) -> None:
        closed = QueueApplicationService(
            self.store,
            auditService=self.audit,
            queueSettings=queueSettings(enabled=False),
            workerId="w-app",
            now=lambda: CLOCK,
        )
        with self.assertRaises(AIConfigurationError):
            closed.submitJob(SubmitJobCommand(tenantId=self.tenantId, kind="GENERIC"))
        with self.assertRaises(AIConfigurationError):
            closed.runOnce()

    def testReadsAreTenantScoped(self) -> None:
        descriptor = self._submit()
        with self.assertRaises(AIJobNotFound):
            self.service.describeJob(self.otherTenantId, descriptor.jobId)
        self.assertEqual(self.service.listJobs(self.otherTenantId), ())


class WorkerExecutionTests(Phase13PQueueBase):
    def testRunOnceSucceedsAndAuditsTransitions(self) -> None:
        handler = FunctionHandler("GENERIC", JobOutcome(outcome="SUCCEEDED", summary={"pages": 3}))
        self.service.registerHandler(handler)
        descriptor = self._submit()
        report = self.service.runOnce()
        self.assertEqual((report.claimed, report.succeeded, report.audited), (1, 1, 2))
        settled = self.service.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.status, "SUCCEEDED")
        self.assertEqual(settled.resultSummary, {"pages": 3})
        actions = self._actions()
        self.assertIn("JOB_STARTED", actions)
        self.assertIn("JOB_COMPLETED", actions)

    def testRetryThenSuccess(self) -> None:
        attempts: list[int] = []

        def flaky(job: AIJob) -> JobOutcome:
            attempts.append(job.attempts)
            if len(attempts) == 1:
                raise RuntimeError("transient")
            return JobOutcome(outcome="SUCCEEDED", summary={})

        self.service.registerHandler(FunctionHandler("GENERIC", flaky))
        descriptor = self._submit()
        first = self.service.runOnce()
        self.assertEqual((first.claimed, first.retried), (1, 1))
        waiting = self.service.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(waiting.status, "PENDING")
        self.assertEqual(waiting.runAt, CLOCK + timedelta(seconds=30))
        idle = self.service.runOnce()
        self.assertEqual(idle.claimed, 0)
        later = self.service.runOnce(now=CLOCK + timedelta(seconds=31))
        self.assertEqual((later.claimed, later.succeeded), (1, 1))
        settled = self.service.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.attempts, 2)
        self.assertEqual(attempts, [1, 2])

    def testExhaustionDeadLetters(self) -> None:
        self.service.registerHandler(FunctionHandler("GENERIC", RuntimeError("always")))
        descriptor = self._submit(maxAttempts=1)
        report = self.service.runOnce()
        self.assertEqual((report.claimed, report.dead), (1, 1))
        settled = self.service.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.status, "DEAD")
        failures = self.audit.listAuditEntries(self.tenantId)
        failed = [entry for entry in failures if entry.action == "JOB_FAILED"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].errorCode, "RUNTIMEERROR")

    def testMissingHandlerSettlesFailedWithoutRetry(self) -> None:
        descriptor = self._submit(kind="EMBEDDING")
        report = self.service.runOnce()
        self.assertEqual((report.claimed, report.failed), (1, 1))
        settled = self.service.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.status, "FAILED")
        self.assertEqual(settled.errorCode, "HANDLER_MISSING")
        self.assertEqual(self.service.runOnce().claimed, 0)

    def testGovernanceDenyDeadEndsBeforeTheHandler(self) -> None:
        self.audit.defineGovernancePolicy(
            self.tenantId,
            GovernancePolicyCommand(name="tenant-rules", disabledCapabilities=("EMBEDDING",)),
        )
        handler = FunctionHandler("EMBEDDING", JobOutcome(outcome="SUCCEEDED"))
        self.service.registerHandler(handler)
        descriptor = self._submit(kind="EMBEDDING", payload={"capabilityCode": "EMBEDDING"})
        report = self.service.runOnce()
        self.assertEqual((report.claimed, report.failed), (1, 1))
        settled = self.service.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.status, "FAILED")
        self.assertEqual(settled.errorCode, "GOVERNANCE_DENIED")
        self.assertEqual(handler.calls, [])

    def testCancelAuditsAndSkipsExecution(self) -> None:
        handler = FunctionHandler("GENERIC", JobOutcome(outcome="SUCCEEDED"))
        self.service.registerHandler(handler)
        descriptor = self._submit()
        cancelled = self.service.cancelJob(self.tenantId, descriptor.jobId)
        self.assertEqual(cancelled.status, "CANCELLED")
        report = self.service.runOnce()
        self.assertEqual(report.claimed, 0)
        self.assertEqual(handler.calls, [])
        failures = [
            entry
            for entry in self.audit.listAuditEntries(self.tenantId)
            if entry.action == "JOB_FAILED"
        ]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].errorCode, "CANCELLED")

    def testHeartbeatExtendsTheLease(self) -> None:
        beat = CLOCK + timedelta(seconds=61)
        descriptor = self._submit()
        self.store.claimRow(self.tenantId, "w-foreign", 60, 10, CLOCK)
        with self.assertRaises(AIJobLeaseConflict):
            self.service.heartbeatJob(self.tenantId, descriptor.jobId, now=beat)
        self.store.claimRow(self.tenantId, "w-app", 60, 10, beat)
        extended = self.service.heartbeatJob(self.tenantId, descriptor.jobId, now=beat)
        self.assertEqual(extended.claimedBy, "w-app")
        self.assertEqual(extended.leaseExpiresAt, beat + timedelta(seconds=120))

    def testPurgeRetentionKeepsActiveJobs(self) -> None:
        handler = FunctionHandler("GENERIC", JobOutcome(outcome="SUCCEEDED"))
        self.service.registerHandler(handler)
        old = self._submit()
        stored = self.store.get(self.tenantId, old.jobId)
        assert stored is not None
        stored.createdAt = CLOCK - timedelta(days=40)
        self.store.update(stored)
        self.service.runOnce()
        recent = self._submit()
        purged = self.service.purgeJobRetention(self.tenantId, retentionDays=30)
        self.assertEqual(purged, 1)
        remaining = [item.jobId for item in self.service.listJobs(self.tenantId)]
        self.assertEqual(remaining, [recent.jobId])
        audits = self.audit.listAuditEntries(self.tenantId)
        purges = [entry for entry in audits if entry.action == "RETENTION_PURGED"]
        self.assertEqual(len(purges), 1)


class EventTransportTests(Phase13PQueueBase):
    def _envelope(self, **overrides: Any) -> AIEventEnvelope:
        params: dict[str, Any] = {
            "tenantId": self.tenantId,
            "eventName": "USAGE_RECORDED",
            "payload": {"n": 1},
        }
        params.update(overrides)
        return AIEventEnvelope(**params)

    def testQueuedBusDeliversDurablyAcrossInstances(self) -> None:
        seen: list[str] = []

        class Watcher:
            def handle(self, envelope: AIEventEnvelope) -> None:
                seen.append(envelope.eventName)

        first = QueueApplicationService(
            self.store,
            auditService=self.audit,
            queueSettings=queueSettings(),
            workerId="w-publisher",
            now=lambda: CLOCK,
        )
        QueuedEventBus(first).publish(self._envelope())
        workerBus = EventBusService()
        workerBus.subscribe("USAGE_RECORDED", Watcher())
        second = QueueApplicationService(
            self.store,
            eventBus=workerBus,
            auditService=self.audit,
            queueSettings=queueSettings(),
            workerId="w-consumer",
            now=lambda: CLOCK,
        )
        report = second.runUntilIdle()
        self.assertEqual(seen, ["USAGE_RECORDED"])
        self.assertEqual((report.claimed, report.succeeded), (1, 1))

    def testEventPublishIsIdempotent(self) -> None:
        envelope = self._envelope()
        bus = QueuedEventBus(self.service)
        first = bus.publish(envelope)
        second = bus.publish(envelope)
        self.assertEqual(first.id, second.id)
        jobs = self.service.listJobs(self.tenantId, JobFilter(kind="EVENT_DISPATCH"))
        self.assertEqual(len(jobs), 1)

    def testCorruptEventPayloadDeadEndsWithoutRetry(self) -> None:
        descriptor = self._submit(kind="EVENT_DISPATCH", payload={"eventName": "USAGE_RECORDED"})
        report = self.service.runOnce()
        self.assertEqual((report.claimed, report.failed), (1, 1))
        settled = self.service.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.status, "FAILED")
        self.assertEqual(settled.errorCode, "EVENT_INVALID")

    def testTenantMismatchDeadEnds(self) -> None:
        foreign = AIEventEnvelope(tenantId=self.otherTenantId, eventName="USAGE_RECORDED")
        descriptor = self._submit(kind="EVENT_DISPATCH", payload=foreign.toJobPayload())
        report = self.service.runOnce()
        self.assertEqual((report.claimed, report.failed), (1, 1))
        settled = self.service.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.errorCode, "EVENT_TENANT_MISMATCH")

    def testFailingSubscriberRetriesThenSucceeds(self) -> None:
        state = {"broken": True}

        class FlakyAudit:
            def handle(self, envelope: AIEventEnvelope) -> None:
                if state["broken"]:
                    raise RuntimeError("sink down")

        workerBus = EventBusService()
        workerBus.subscribe("USAGE_RECORDED", FlakyAudit())
        worker = QueueApplicationService(
            self.store,
            eventBus=workerBus,
            auditService=self.audit,
            queueSettings=queueSettings(),
            workerId="w-app",
            now=lambda: CLOCK,
        )
        QueuedEventBus(self.service).publish(self._envelope())
        first = worker.runOnce()
        self.assertEqual((first.claimed, first.retried), (1, 1))
        state["broken"] = False
        second = worker.runOnce(now=CLOCK + timedelta(seconds=31))
        self.assertEqual((second.claimed, second.succeeded), (1, 1))

    def testRunUntilIdleDrainsChainedPublishes(self) -> None:
        bus = QueuedEventBus(self.service)

        def chain(job: AIJob) -> JobOutcome:
            bus.publish(self._envelope(payload={"chained": True}))
            return JobOutcome(outcome="SUCCEEDED", summary={})

        self.service.registerHandler(FunctionHandler("GENERIC", chain))
        self._submit()
        report = self.service.runUntilIdle()
        self.assertEqual(report.claimed, 2)
        self.assertEqual(report.succeeded, 2)
        kinds = [item.kind for item in self.service.listJobs(self.tenantId)]
        self.assertIn("EVENT_DISPATCH", kinds)

    def testUsageSinkToAuditEndToEnd(self) -> None:
        workerBus = EventBusService()
        registerAuditSubscriber(workerBus, self.audit)
        worker = QueueApplicationService(
            self.store,
            eventBus=workerBus,
            auditService=self.audit,
            queueSettings=queueSettings(),
            workerId="w-app",
            now=lambda: CLOCK,
        )
        event = AIUsageRecorded(
            tenantId=self.tenantId,
            attemptId=uuid.uuid4(),
            requestId=uuid.uuid4(),
            operationId=None,
            providerCode="OPENAI",
            modelCode="GPT-X",
            capabilityCode="SUMMARIZATION",
            inputTokens=100,
            outputTokens=50,
            totalTokens=150,
            costAmount=Decimal("0.004"),
            costCurrency="USD",
            totalTimeMs=120,
            outcome="SUCCEEDED",
            correlationId="corr-p-1",
            traceId="trace-p-1",
            recordedAt=CLOCK,
        )
        QueuedUsageEventSink(QueuedEventBus(self.service)).publish(event)
        report = worker.runUntilIdle()
        self.assertEqual((report.claimed, report.succeeded), (1, 1))
        actions = self._actions()
        self.assertIn("USAGE_RECORDED", actions)
        self.assertIn("JOB_ENQUEUED", actions)
        self.assertIn("JOB_STARTED", actions)
        self.assertIn("JOB_COMPLETED", actions)
