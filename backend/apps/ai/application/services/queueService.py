"""Async execution application service for Phase 13-P.

``QueueApplicationService`` wires the pure ``JobQueueService`` coordinator
to a ``JobStore`` and to the worker loop:

- ``submitJob`` / ``cancelJob`` / ``describeJob`` / ``listJobs`` /
  ``heartbeatJob`` / ``purgeJobRetention`` — store-first operations; the
  store is the source of truth and the in-memory coordinator is refreshed
  from it, so concurrent workers never act on stale copies;
- ``registerHandler`` / ``runOnce`` / ``runUntilIdle`` / ``tick`` — the
  worker loop: atomic claim, optional governance pre-check, handler
  execution, settlement, and a ``JOB_*`` audit per transition;
- ``QueuedEventBus`` (durable ``EventBusPort``) and
  ``QueuedUsageEventSink`` (the N→P bridge) plus ``AuditEventSubscriber``
  (the P→O bridge for ``USAGE_RECORDED`` envelopes).

The O audit/governance service is optional and injected: without it the
worker still executes jobs, only the audit/governance steps are skipped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from apps.ai.application.services.auditService import AuditApplicationService
from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.auditRecords import GovernanceRequest
from apps.ai.domain.entities.jobRecords import AIJob
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIError,
    AIEventInvalid,
    AIGovernanceDenied,
    AIIdempotencyConflict,
    AIJobInvalid,
    AIJobNotFound,
)
from apps.ai.domain.meteringPorts import UsageEventSink
from apps.ai.domain.queuePorts import EventBusPort, JobHandler, JobStore
from apps.ai.domain.services.eventBus import AIEventEnvelope, EventBusService
from apps.ai.domain.services.jobQueue import (
    JobDescriptor,
    JobFilter,
    JobOutcome,
    JobQueueService,
    ensureJobOutcome,
    jobFingerprint,
)
from apps.ai.domain.services.usageMetering import AIUsageRecorded
from apps.ai.domain.valueObjects.auditTypes import ensureAuditAction
from apps.ai.domain.valueObjects.queueTypes import (
    DEFAULT_JOB_PRIORITY,
    TERMINAL_JOB_STATUSES,
    ensureJobKind,
)
from apps.ai.domain.valueObjects.usageTypes import asUtc

JOB_AUDIT_ACTIONS = (
    "JOB_ENQUEUED",
    "JOB_STARTED",
    "JOB_COMPLETED",
    "JOB_FAILED",
)

_EVENT_DISPATCH_KIND = "EVENT_DISPATCH"


@dataclass(frozen=True)
class QueueSettings:
    """Worker/queue knobs (contract §P.10); worker identity included."""

    enabled: bool = True
    retentionDays: int = 30
    defaultMaxAttempts: int = 3
    claimLimit: int = 10
    leaseSeconds: int = 120
    retryBaseSeconds: int = 30
    retryMultiplier: float = 2.0
    retryMaxSeconds: int = 600
    workerId: str = "aiWorker"

    @classmethod
    def fromDjangoSettings(cls, settings: Any) -> QueueSettings:
        get = getattr(settings, "AI_QUEUE_ENABLED", True)
        return cls(
            enabled=bool(get),
            retentionDays=int(getattr(settings, "AI_QUEUE_RETENTION_DAYS", 30)),
            defaultMaxAttempts=int(getattr(settings, "AI_QUEUE_DEFAULT_MAX_ATTEMPTS", 3)),
            claimLimit=int(getattr(settings, "AI_QUEUE_CLAIM_LIMIT", 10)),
            leaseSeconds=int(getattr(settings, "AI_WORKER_LEASE_SECONDS", 120)),
            retryBaseSeconds=int(getattr(settings, "AI_WORKER_RETRY_BASE_SECONDS", 30)),
            retryMultiplier=float(getattr(settings, "AI_WORKER_RETRY_MULTIPLIER", 2.0)),
            retryMaxSeconds=int(getattr(settings, "AI_WORKER_RETRY_MAX_SECONDS", 600)),
            workerId=str(getattr(settings, "AI_WORKER_ID", "aiWorker") or "aiWorker"),
        )


@dataclass(frozen=True)
class SubmitJobCommand:
    tenantId: uuid.UUID | str
    kind: str
    payload: dict[str, Any] | None = None
    idempotencyKey: str = ""
    priority: int = DEFAULT_JOB_PRIORITY
    maxAttempts: int | None = None
    runAt: datetime | None = None
    requestId: uuid.UUID | str | None = None
    correlationId: str = ""
    traceId: str = ""


@dataclass(frozen=True)
class WorkReport:
    workerId: str
    claimed: int
    succeeded: int
    retried: int
    failed: int
    dead: int
    audited: int


class QueueApplicationService:
    """Queue facade plus worker loop over an injected ``JobStore``."""

    def __init__(
        self,
        jobStore: JobStore,
        *,
        queue: JobQueueService | None = None,
        eventBus: EventBusService | None = None,
        auditService: AuditApplicationService | None = None,
        queueSettings: QueueSettings | None = None,
        workerId: str = "",
        now: Any = utcNow,
    ) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self._store = jobStore
        self._queue = queue or JobQueueService(now=now)
        self._bus = eventBus or EventBusService()
        self._audit = auditService
        self._settings = queueSettings or QueueSettings()
        self._workerId = str(workerId or "").strip() or self._settings.workerId
        self._handlers: dict[str, JobHandler] = {}
        self._now = now

    # ------------------------------------------------------------------
    # Queue operations (store-first; the store is the source of truth)
    # ------------------------------------------------------------------
    def submitJob(self, command: SubmitJobCommand) -> JobDescriptor:
        self._requireQueueEnabled()
        if not isinstance(command, SubmitJobCommand):
            raise AIJobInvalid("Submission requires a SubmitJobCommand.")
        tenant = requireUuid(command.tenantId, "tenantId")
        maxAttempts = command.maxAttempts
        if maxAttempts is None:
            maxAttempts = self._settings.defaultMaxAttempts
        key = str(command.idempotencyKey or "").strip()
        payload = dict(command.payload) if command.payload is not None else {}
        if key:
            existing = self._store.findByIdempotencyKey(tenant, key)
            if existing is not None and existing.tenantId == tenant:
                if self._requestFingerprint(tenant, command.kind, payload, key) != jobFingerprint(
                    existing
                ):
                    raise AIIdempotencyConflict(
                        "The tenant-scoped job idempotency key is already bound to another job."
                    )
                refreshed = self._queue.importJob(existing)
                self._auditTransition(refreshed, "JOB_ENQUEUED")
                return self._queue.describeJob(tenant, refreshed.id)
        job = self._queue.submit(
            tenant,
            command.kind,
            payload=payload,
            idempotencyKey=key,
            priority=command.priority,
            maxAttempts=maxAttempts,
            runAt=command.runAt,
            requestId=command.requestId,
            correlationId=command.correlationId,
            traceId=command.traceId,
        )
        stored = self._store.save(job)
        refreshed = self._queue.importJob(stored)
        self._auditTransition(refreshed, "JOB_ENQUEUED")
        return self._queue.describeJob(tenant, refreshed.id)

    def cancelJob(
        self,
        tenantId: uuid.UUID | str,
        jobId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> JobDescriptor:
        self._requireQueueEnabled()
        tenant = requireUuid(tenantId, "tenantId")
        moment = asUtc(now) if now is not None else self._now()
        stored = self._store.get(tenant, requireUuid(jobId, "jobId"))
        if stored is None or stored.tenantId != tenant:
            raise AIJobNotFound(str(jobId))
        job = self._queue.importJob(stored)
        try:
            settled = self._queue.cancelJob(tenant, job.id, workerId=self._workerId, now=moment)
        except AIError:
            raise
        except Exception as exc:
            raise AIJobInvalid(str(exc)) from exc
        updated = self._store.update(settled)
        refreshed = self._queue.importJob(updated)
        self._auditTransition(refreshed, "JOB_FAILED", errorCode="CANCELLED")
        return self._queue.describeJob(tenant, refreshed.id)

    def describeJob(self, tenantId: uuid.UUID | str, jobId: uuid.UUID | str) -> JobDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        stored = self._store.get(tenant, requireUuid(jobId, "jobId"))
        if stored is None or stored.tenantId != tenant:
            raise AIJobNotFound(str(jobId))
        refreshed = self._queue.importJob(stored)
        return self._queue.describeJob(tenant, refreshed.id)

    def getJobRecord(self, tenantId: uuid.UUID | str, jobId: uuid.UUID | str) -> AIJob:
        tenant = requireUuid(tenantId, "tenantId")
        stored = self._store.get(tenant, requireUuid(jobId, "jobId"))
        if stored is None or stored.tenantId != tenant:
            raise AIJobNotFound(str(jobId))
        return self._queue.importJob(stored)

    def listJobs(
        self, tenantId: uuid.UUID | str, jobFilter: JobFilter | None = None
    ) -> tuple[JobDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        for stored in self._store.listTenantJobs(tenant):
            if stored.tenantId == tenant:
                self._queue.importJob(stored)
        return self._queue.listJobs(tenant, jobFilter)

    def heartbeatJob(
        self,
        tenantId: uuid.UUID | str,
        jobId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> JobDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        moment = asUtc(now) if now is not None else self._now()
        stored = self._store.get(tenant, requireUuid(jobId, "jobId"))
        if stored is None or stored.tenantId != tenant:
            raise AIJobNotFound(str(jobId))
        job = self._queue.importJob(stored)
        try:
            extended = self._queue.heartbeat(
                tenant, job.id, self._workerId, self._settings.leaseSeconds, now=moment
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIJobInvalid(str(exc)) from exc
        updated = self._store.update(extended)
        refreshed = self._queue.importJob(updated)
        return self._queue.describeJob(tenant, refreshed.id)

    def purgeJobRetention(
        self,
        tenantId: uuid.UUID | str,
        *,
        retentionDays: int | None = None,
        now: datetime | None = None,
    ) -> int:
        tenant = requireUuid(tenantId, "tenantId")
        days = self._settings.retentionDays if retentionDays is None else retentionDays
        if not isinstance(days, int) or isinstance(days, bool) or days < 0:
            raise AIJobInvalid("Job retention days must be a non-negative integer.")
        moment = asUtc(now) if now is not None else self._now()
        cutoff = moment - timedelta(days=days)
        doomed = [
            descriptor
            for descriptor in self.listJobs(tenant)
            if descriptor.status in TERMINAL_JOB_STATUSES and descriptor.createdAt < cutoff
        ]
        purged = self._store.deleteJobsBefore(tenant, cutoff, TERMINAL_JOB_STATUSES)
        for descriptor in doomed:
            self._queue.forget(tenant, descriptor.jobId)
        if self._audit is not None:
            self._audit.logAudit(
                tenant,
                "RETENTION_PURGED",
                occurredAt=moment,
                actorType="SYSTEM",
                actorId=None,
                detail={"scope": "AI_JOBS", "purgedJobs": purged, "retentionDays": days},
            )
        return purged

    # ------------------------------------------------------------------
    # Worker loop
    # ------------------------------------------------------------------
    def registerHandler(self, handler: JobHandler) -> JobHandler:
        kind = ensureJobKind(handler.kind())
        if kind == _EVENT_DISPATCH_KIND:
            raise AIJobInvalid("The event-dispatch kind is owned by the worker.")
        self._handlers[kind] = handler
        return handler

    def runOnce(
        self,
        *,
        tenantId: uuid.UUID | str | None = None,
        limit: int | None = None,
        now: datetime | None = None,
    ) -> WorkReport:
        self._requireQueueEnabled()
        tenant = requireUuid(tenantId, "tenantId") if tenantId is not None else None
        batch = self._settings.claimLimit if limit is None else limit
        if not isinstance(batch, int) or isinstance(batch, bool) or batch < 1:
            raise AIJobInvalid("Claim limit must be a positive integer.")
        moment = asUtc(now) if now is not None else self._now()
        claimed = self._store.claimRow(
            tenant, self._workerId, self._settings.leaseSeconds, batch, moment
        )
        succeeded = retried = failed = dead = audited = 0
        for stored in claimed:
            if tenant is not None and stored.tenantId != tenant:
                continue
            job = self._queue.importJob(stored)
            self._auditTransition(job, "JOB_STARTED")
            audited += 1 if self._audit is not None else 0
            outcome, errorCode, summary = self._executeJob(job, moment)
            settled = self._settleJob(job, outcome, errorCode, summary, moment)
            self._store.update(settled)
            refreshed = self._queue.importJob(settled)
            if outcome == "SUCCEEDED":
                succeeded += 1
                self._auditTransition(refreshed, "JOB_COMPLETED")
            elif refreshed.status == "PENDING":
                retried += 1
                self._auditTransition(refreshed, "JOB_FAILED", errorCode=errorCode)
            elif refreshed.status == "DEAD":
                dead += 1
                self._auditTransition(refreshed, "JOB_FAILED", errorCode=errorCode)
            else:
                failed += 1
                self._auditTransition(refreshed, "JOB_FAILED", errorCode=errorCode)
            audited += 1 if self._audit is not None else 0
        return WorkReport(
            workerId=self._workerId,
            claimed=len(claimed),
            succeeded=succeeded,
            retried=retried,
            failed=failed,
            dead=dead,
            audited=audited,
        )

    def runUntilIdle(
        self,
        *,
        tenantId: uuid.UUID | str | None = None,
        limit: int | None = None,
        maxPasses: int = 100,
        now: datetime | None = None,
    ) -> WorkReport:
        if not isinstance(maxPasses, int) or isinstance(maxPasses, bool) or maxPasses < 1:
            raise AIJobInvalid("Worker max passes must be a positive integer.")
        total = WorkReport(
            workerId=self._workerId,
            claimed=0,
            succeeded=0,
            retried=0,
            failed=0,
            dead=0,
            audited=0,
        )
        for _ in range(maxPasses):
            report = self.runOnce(tenantId=tenantId, limit=limit, now=now)
            total = WorkReport(
                workerId=self._workerId,
                claimed=total.claimed + report.claimed,
                succeeded=total.succeeded + report.succeeded,
                retried=total.retried + report.retried,
                failed=total.failed + report.failed,
                dead=total.dead + report.dead,
                audited=total.audited + report.audited,
            )
            if report.claimed == 0:
                break
        return total

    def tick(
        self,
        *,
        tenantId: uuid.UUID | str | None = None,
        limit: int | None = None,
        now: datetime | None = None,
    ) -> WorkReport:
        """One bounded worker pass for the management command (Phase 9 pattern)."""

        return self.runOnce(tenantId=tenantId, limit=limit, now=now)

    # ------------------------------------------------------------------
    # Execution internals
    # ------------------------------------------------------------------
    def _executeJob(self, job: AIJob, moment: datetime) -> tuple[str, str, dict[str, Any]]:
        if job.kind == _EVENT_DISPATCH_KIND:
            return self._dispatchEventJob(job)
        handler = self._handlers.get(job.kind)
        if handler is None:
            return ("FAILED", "HANDLER_MISSING", {})
        if self._audit is not None and self._jobCarriesGovernanceCodes(job):
            grant = self._evaluateJobGovernance(job, moment)
            if grant == "DENIED":
                return ("FAILED", "GOVERNANCE_DENIED", {})
            if grant == "ERROR":
                return ("FAILED", "GOVERNANCE_ERROR", {})
        try:
            outcome = handler.execute(job)
        except AIError as exc:
            return ("RETRY", exc.code or "HANDLER_FAILED", {})
        except Exception as exc:
            return ("RETRY", f"{type(exc).__name__}".upper() or "HANDLER_FAILED", {})
        if not isinstance(outcome, JobOutcome):
            return ("FAILED", "HANDLER_INVALID_OUTCOME", {})
        try:
            normalized = ensureJobOutcome(outcome.outcome)
        except Exception:
            return ("FAILED", "HANDLER_INVALID_OUTCOME", {})
        summary = dict(outcome.summary) if outcome.summary is not None else {}
        if normalized == "SUCCEEDED":
            return ("SUCCEEDED", "", summary)
        if not outcome.retryable:
            return ("FAILED", outcome.errorCode or "HANDLER_FAILED", summary)
        return ("RETRY", outcome.errorCode or "HANDLER_FAILED", summary)

    def _settleJob(
        self,
        job: AIJob,
        outcome: str,
        errorCode: str,
        summary: dict[str, Any],
        moment: datetime,
    ) -> AIJob:
        if outcome == "SUCCEEDED":
            return self._queue.complete(
                job.tenantId, job.id, self._workerId, summary=summary, now=moment
            )
        if outcome == "RETRY":
            return self._queue.failJob(
                job.tenantId,
                job.id,
                self._workerId,
                errorCode=errorCode,
                retryable=True,
                baseSeconds=self._settings.retryBaseSeconds,
                multiplier=self._settings.retryMultiplier,
                maxSeconds=self._settings.retryMaxSeconds,
                now=moment,
            )
        return self._queue.failJob(
            job.tenantId,
            job.id,
            self._workerId,
            errorCode=errorCode,
            retryable=False,
            baseSeconds=self._settings.retryBaseSeconds,
            multiplier=self._settings.retryMultiplier,
            maxSeconds=self._settings.retryMaxSeconds,
            now=moment,
        )

    def _dispatchEventJob(self, job: AIJob) -> tuple[str, str, dict[str, Any]]:
        try:
            envelope = AIEventEnvelope.fromJobPayload(job.payload)
        except AIError:
            return ("FAILED", "EVENT_INVALID", {})
        if envelope.tenantId != job.tenantId:
            return ("FAILED", "EVENT_TENANT_MISMATCH", {})
        report = self._bus.dispatch(envelope)
        failures = [item for item in report.deliveries if not item.delivered]
        summary = {
            "envelopeId": str(envelope.envelopeId),
            "eventName": envelope.eventName,
            "delivered": len(report.deliveries) - len(failures),
            "failed": len(failures),
        }
        if failures:
            return ("RETRY", "SUBSCRIBER_FAILED", summary)
        return ("SUCCEEDED", "", summary)

    # ------------------------------------------------------------------
    # Governance pre-check (optional; deny dead-ends without retry)
    # ------------------------------------------------------------------
    @staticmethod
    def _jobCarriesGovernanceCodes(job: AIJob) -> bool:
        payload = job.payload if isinstance(job.payload, dict) else {}
        return any(
            str(payload.get(field) or "").strip()
            for field in ("capabilityCode", "providerCode", "modelCode")
        )

    def _evaluateJobGovernance(self, job: AIJob, moment: datetime) -> str:
        assert self._audit is not None
        payload = job.payload if isinstance(job.payload, dict) else {}
        try:
            grant = self._audit.evaluateGovernance(
                GovernanceRequest(
                    tenantId=job.tenantId,
                    capabilityCode=str(payload.get("capabilityCode") or ""),
                    providerCode=str(payload.get("providerCode") or ""),
                    modelCode=str(payload.get("modelCode") or ""),
                    correlationId=job.correlationId,
                    traceId=job.traceId,
                    requestId=job.requestId,
                ),
                now=moment,
            )
        except AIGovernanceDenied:
            return "DENIED"
        except Exception:
            return "ERROR"
        return "ALLOWED" if grant.decision.allowed else "DENIED"

    # ------------------------------------------------------------------
    # Audit transitions (optional; references only — never the payload)
    # ------------------------------------------------------------------
    def _auditTransition(self, job: AIJob, action: str, *, errorCode: str = "") -> None:
        if self._audit is None:
            return
        normalized = ensureAuditAction(action)
        if normalized not in JOB_AUDIT_ACTIONS:
            raise AIJobInvalid(f"Job audit action is not a job lifecycle action: {action}")
        self._audit.logAudit(
            job.tenantId,
            normalized,
            occurredAt=self._now(),
            actorType="SYSTEM",
            actorId=None,
            requestId=job.requestId,
            capabilityCode="",
            correlationId=job.correlationId,
            traceId=job.traceId,
            errorCode=errorCode,
            detail={
                "jobId": str(job.id),
                "kind": job.kind,
                "status": job.status,
                "attempts": job.attempts,
                "maxAttempts": job.maxAttempts,
                "idempotencyKey": job.idempotencyKey,
            },
        )

    def _requireQueueEnabled(self) -> None:
        if not self._settings.enabled:
            raise AIConfigurationError("The AI queue is disabled by configuration.")

    @staticmethod
    def _requestFingerprint(tenant: uuid.UUID, kind: str, payload: dict[str, Any], key: str) -> str:
        try:
            transient = AIJob(tenantId=tenant, kind=kind, payload=payload, idempotencyKey=key)
        except AIError:
            raise
        except Exception as exc:
            raise AIJobInvalid(str(exc)) from exc
        return jobFingerprint(transient)


class QueuedEventBus(EventBusPort):
    """Durable event publication: publish = enqueue an ``EVENT_DISPATCH`` job."""

    def __init__(self, queueService: QueueApplicationService) -> None:
        self._queueService = queueService

    @property
    def queueService(self) -> QueueApplicationService:
        return self._queueService

    def publish(self, envelope: AIEventEnvelope, **kwargs: Any) -> AIJob:
        if not isinstance(envelope, AIEventEnvelope):
            raise AIEventInvalid("Publication requires an AIEventEnvelope.")
        idempotencyKey = str(kwargs.get("idempotencyKey") or f"event:{envelope.envelopeId}")
        priority = kwargs.get("priority", DEFAULT_JOB_PRIORITY)
        maxAttempts = kwargs.get("maxAttempts", None)
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise AIEventInvalid("Event publication priority must be an integer.")
        if maxAttempts is not None and (
            not isinstance(maxAttempts, int) or isinstance(maxAttempts, bool)
        ):
            raise AIEventInvalid("Event publication max attempts must be an integer.")
        descriptor = self._queueService.submitJob(
            SubmitJobCommand(
                tenantId=envelope.tenantId,
                kind=_EVENT_DISPATCH_KIND,
                payload=envelope.toJobPayload(),
                idempotencyKey=idempotencyKey,
                priority=priority,
                maxAttempts=maxAttempts,
                correlationId=envelope.correlationId,
                traceId=envelope.traceId,
            )
        )
        return self._queueService.getJobRecord(descriptor.tenantId, descriptor.jobId)


class QueuedUsageEventSink(UsageEventSink):
    """The N→P bridge: a §36 ``AIUsageRecorded`` carrier becomes an envelope."""

    def __init__(self, eventBus: EventBusPort) -> None:
        self._eventBus = eventBus

    @property
    def eventBus(self) -> EventBusPort:
        return self._eventBus

    def publish(self, event: AIUsageRecorded) -> None:
        if not isinstance(event, AIUsageRecorded):
            raise ValueError("Usage sink publication requires an AIUsageRecorded carrier.")
        operationId = event.operationId
        envelope = AIEventEnvelope(
            tenantId=event.tenantId,
            eventName="USAGE_RECORDED",
            occurredAt=event.recordedAt,
            payload={
                "tenantId": str(event.tenantId),
                "attemptId": str(event.attemptId),
                "requestId": str(event.requestId),
                "operationId": str(operationId) if operationId is not None else "",
                "capabilityCode": event.capabilityCode,
                "providerCode": event.providerCode,
                "modelCode": event.modelCode,
                "inputTokens": event.inputTokens,
                "outputTokens": event.outputTokens,
                "totalTokens": event.totalTokens,
                "costAmount": str(event.costAmount),
                "costCurrency": event.costCurrency,
                "totalTimeMs": event.totalTimeMs,
                "outcome": event.outcome,
                "correlationId": event.correlationId,
                "traceId": event.traceId,
                "recordedAt": event.recordedAt.isoformat(),
            },
            correlationId=event.correlationId,
            traceId=event.traceId,
        )
        self._eventBus.publish(envelope, idempotencyKey=f"event:{envelope.envelopeId}")


class AuditEventSubscriber:
    """The P→O bridge: ``USAGE_RECORDED`` envelopes enter the audit trail."""

    eventName = "USAGE_RECORDED"

    def __init__(self, auditService: AuditApplicationService) -> None:
        self._auditService = auditService

    @property
    def auditService(self) -> AuditApplicationService:
        return self._auditService

    def handle(self, envelope: AIEventEnvelope) -> None:
        if not isinstance(envelope, AIEventEnvelope):
            raise AIEventInvalid("Audit subscription requires an AIEventEnvelope.")
        if envelope.eventName != self.eventName:
            return
        payload = envelope.payload
        operationRaw = str(payload.get("operationId") or "").strip()
        tenantRaw = payload.get("tenantId")
        attemptRaw = payload.get("attemptId")
        requestRaw = payload.get("requestId")
        if (
            not isinstance(tenantRaw, (str, uuid.UUID))
            or not isinstance(attemptRaw, (str, uuid.UUID))
            or not isinstance(requestRaw, (str, uuid.UUID))
        ):
            raise AIEventInvalid("Usage envelope identity is missing.")
        event = AIUsageRecorded(
            tenantId=requireUuid(tenantRaw, "tenantId"),
            attemptId=requireUuid(attemptRaw, "attemptId"),
            requestId=requireUuid(requestRaw, "requestId"),
            operationId=requireUuid(operationRaw, "operationId") if operationRaw else None,
            providerCode=str(payload.get("providerCode") or ""),
            modelCode=str(payload.get("modelCode") or ""),
            capabilityCode=str(payload.get("capabilityCode") or ""),
            inputTokens=int(payload.get("inputTokens") or 0),
            outputTokens=int(payload.get("outputTokens") or 0),
            totalTokens=int(payload.get("totalTokens") or 0),
            costAmount=Decimal(str(payload.get("costAmount") or "0")),
            costCurrency=str(payload.get("costCurrency") or ""),
            totalTimeMs=int(payload.get("totalTimeMs") or 0),
            outcome=str(payload.get("outcome") or ""),
            correlationId=str(payload.get("correlationId") or ""),
            traceId=str(payload.get("traceId") or ""),
            recordedAt=asUtc(datetime.fromisoformat(str(payload.get("recordedAt")))),
        )
        self._auditService.ingestUsageRecorded(event)


def registerAuditSubscriber(
    eventBus: EventBusService, auditService: AuditApplicationService
) -> AuditEventSubscriber:
    """Subscribe the audit trail to ``USAGE_RECORDED`` envelopes."""

    subscriber = AuditEventSubscriber(auditService)
    eventBus.subscribe(subscriber.eventName, subscriber)
    return subscriber


QueueWorkerService = QueueApplicationService
AIWorkerService = QueueApplicationService

__all__ = [
    "AIWorkerService",
    "AuditEventSubscriber",
    "JOB_AUDIT_ACTIONS",
    "QueueApplicationService",
    "QueueSettings",
    "QueueWorkerService",
    "QueuedEventBus",
    "QueuedUsageEventSink",
    "SubmitJobCommand",
    "WorkReport",
    "registerAuditSubscriber",
]
