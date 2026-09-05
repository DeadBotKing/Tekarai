"""Pure async job queue coordinator for Phase 13-P.

``JobQueueService`` is a tenant-scoped in-memory coordinator for durable
AI jobs (§35). Submission is idempotent per tenant-scoped
``idempotencyKey`` (the same contract as the Phase 13-G/N services):
repeating a key with the same fingerprint returns the stored job, while
a reused key with different content raises ``AIIdempotencyConflict``.

Claiming is single-flight: a ``PENDING`` job whose time has come and
whose lease is free moves to ``RUNNING`` under exactly one worker. Lease
expiry makes a stuck job claimable again (the P-level timeout; execution
timeouts belong to sub-phase M).

Failure semantics: a retryable failure with attempts left requeues to
``PENDING`` with exponential backoff; exhausted attempts dead-letter to
``DEAD`` (poison, operator attention); deterministic refusals
(unretryable outcome, missing handler, governance deny, invalid event)
settle to ``FAILED``. ``SUCCEEDED``/``FAILED``/``CANCELLED``/``DEAD`` are
terminal.

The service is provider-agnostic and persistence-free; an application
adapter hydrates jobs from its store and persists transitions (the same
split as the Phase 13-G/N/O coordinators).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.jobRecords import AIJob
from apps.ai.domain.exceptions import (
    AIError,
    AIIdempotencyConflict,
    AIJobAlreadyRegistered,
    AIJobInvalid,
    AIJobLeaseConflict,
    AIJobNotFound,
)
from apps.ai.domain.valueObjects.queueTypes import (
    DEFAULT_JOB_PRIORITY,
    TERMINAL_JOB_STATUSES,
    computeBackoff,
    ensureJobKind,
    ensureJobPriority,
    ensureJobStatus,
)
from apps.ai.domain.valueObjects.usageTypes import asUtc
from apps.sharedKernel.domain.errors import ValidationFailedError

JOB_OUTCOMES = (
    "SUCCEEDED",
    "FAILED",
)


def _canonicalValue(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalValue(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalValue(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonicalValue(item) for item in value), key=repr)
    if isinstance(value, (uuid.UUID, datetime)):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return str(value)
    except Exception:
        return repr(value)


def _jobFingerprint(
    *, tenantId: uuid.UUID, kind: str, payload: Mapping[str, Any], idempotencyKey: str
) -> str:
    identity = {
        "tenantId": str(tenantId),
        "kind": kind,
        "payload": _canonicalValue(dict(payload)),
        "idempotencyKey": idempotencyKey,
    }
    encoded = json.dumps(identity, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def jobFingerprint(job: AIJob) -> str:
    """Stable tenant-scoped identity of a job for idempotent stores."""

    if not isinstance(job, AIJob):
        raise ValueError("Fingerprint requires an AIJob.")
    return _jobFingerprint(
        tenantId=job.tenantId,
        kind=job.kind,
        payload=job.payload,
        idempotencyKey=job.idempotencyKey,
    )


def ensureJobOutcome(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in JOB_OUTCOMES:
        raise ValidationFailedError("Unknown job outcome.", fieldErrors={"outcome": normalized})
    return normalized


@dataclass(frozen=True)
class JobOutcome:
    """Handler verdict for one execution: terminal outcome plus retry hint."""

    outcome: str
    retryable: bool = True
    errorCode: str = ""
    summary: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", ensureJobOutcome(self.outcome))
        if not isinstance(self.retryable, bool):
            raise ValueError("Job outcome retry hint must be boolean.")
        object.__setattr__(self, "errorCode", str(self.errorCode or "").strip().upper())
        if self.summary is not None and not isinstance(self.summary, dict):
            raise ValueError("Job outcome summary must be a mapping.")


@dataclass(frozen=True)
class JobDescriptor:
    """Job read model for workers and future APIs (internal — never audited whole)."""

    tenantId: uuid.UUID
    jobId: uuid.UUID
    kind: str
    status: str
    priority: int
    attempts: int
    maxAttempts: int
    runAt: datetime
    claimedBy: str
    leaseExpiresAt: datetime | None
    requestId: uuid.UUID | None
    payload: dict[str, Any]
    resultSummary: dict[str, Any]
    errorCode: str
    correlationId: str
    traceId: str
    createdAt: datetime
    updatedAt: datetime


@dataclass(frozen=True)
class JobFilter:
    """Read filter for job listings; tenant is always mandatory."""

    status: str | None = None
    kind: str | None = None
    requestId: uuid.UUID | str | None = None
    since: datetime | None = None
    until: datetime | None = None


class JobQueueService:
    """Tenant-scoped in-memory coordinator for the async job ledger."""

    def __init__(self, *, now: Any = utcNow) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self._now = now
        self._jobs: dict[tuple[uuid.UUID, uuid.UUID], AIJob] = {}
        self._idempotency: dict[tuple[uuid.UUID, str], tuple[str, uuid.UUID]] = {}

    # ------------------------------------------------------------------
    # Submission (idempotent per tenant-scoped key)
    # ------------------------------------------------------------------
    def submit(
        self,
        tenantId: uuid.UUID | str,
        kind: str,
        *,
        payload: dict[str, Any] | None = None,
        idempotencyKey: str = "",
        priority: int = DEFAULT_JOB_PRIORITY,
        maxAttempts: int = 3,
        runAt: datetime | None = None,
        requestId: uuid.UUID | str | None = None,
        correlationId: str = "",
        traceId: str = "",
        jobId: uuid.UUID | str | None = None,
    ) -> AIJob:
        tenant = requireUuid(tenantId, "tenantId")
        try:
            normalizedKind = ensureJobKind(kind)
        except AIError:
            raise
        except Exception as exc:
            raise AIJobInvalid(str(exc)) from exc
        normalizedKey = str(idempotencyKey or "").strip()
        normalizedPayload = dict(payload) if payload is not None else {}
        fingerprint = _jobFingerprint(
            tenantId=tenant,
            kind=normalizedKind,
            payload=normalizedPayload,
            idempotencyKey=normalizedKey,
        )
        if normalizedKey:
            previous = self._idempotency.get((tenant, normalizedKey))
            if previous is not None:
                previousFingerprint, previousJobId = previous
                if previousFingerprint == fingerprint:
                    return self._jobs[(tenant, previousJobId)]
                raise AIIdempotencyConflict(
                    "The tenant-scoped job idempotency key is already bound to another job."
                )
        try:
            job = AIJob(
                tenantId=tenant,
                kind=normalizedKind,
                id=requireUuid(jobId, "jobId") if jobId is not None else uuid.uuid4(),
                requestId=requireUuid(requestId, "requestId") if requestId is not None else None,
                payload=normalizedPayload,
                idempotencyKey=normalizedKey,
                status="PENDING",
                priority=ensureJobPriority(priority),
                attempts=0,
                maxAttempts=self._coerceMaxAttempts(maxAttempts),
                runAt=asUtc(runAt) if runAt is not None else self._now(),
                correlationId=correlationId,
                traceId=traceId,
                createdAt=self._now(),
                updatedAt=self._now(),
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIJobInvalid(str(exc)) from exc
        key = (tenant, job.id)
        if key in self._jobs:
            raise AIJobAlreadyRegistered(str(job.id))
        self._jobs[key] = job
        if normalizedKey:
            self._idempotency[(tenant, normalizedKey)] = (fingerprint, job.id)
        return job

    def importJob(self, job: AIJob) -> AIJob:
        """Load a persisted job (application hydration) without re-validating rules.

        Later imports win: a freshly claimed or re-read row replaces the
        stored copy, so workers never settle a stale snapshot.
        """

        if not isinstance(job, AIJob):
            raise ValueError("Only AIJob records can be imported.")
        key = (job.tenantId, job.id)
        self._jobs[key] = job
        if job.idempotencyKey:
            self._idempotency.setdefault(
                (job.tenantId, job.idempotencyKey), (jobFingerprint(job), job.id)
            )
        return job

    # ------------------------------------------------------------------
    # Claiming (single-flight under a lease)
    # ------------------------------------------------------------------
    def claimDue(
        self,
        workerId: str,
        leaseSeconds: int,
        limit: int = 10,
        *,
        tenantId: uuid.UUID | str | None = None,
        now: datetime | None = None,
    ) -> tuple[AIJob, ...]:
        holder = str(workerId or "").strip()
        if not holder:
            raise AIJobInvalid("Claiming requires a worker id.")
        lease = self._coerceLeaseSeconds(leaseSeconds)
        batch = self._coerceLimit(limit)
        moment = asUtc(now) if now is not None else self._now()
        tenant = requireUuid(tenantId, "tenantId") if tenantId is not None else None
        due = [
            job
            for (jobTenant, _), job in self._jobs.items()
            if (tenant is None or jobTenant == tenant)
            and job.status in ("PENDING", "RUNNING")
            and job.runAt <= moment
            and (job.leaseExpiresAt is None or job.leaseExpiresAt <= moment)
        ]
        due.sort(key=lambda job: (-job.priority, job.runAt, job.createdAt, str(job.id)))
        claimed: list[AIJob] = []
        for job in due[:batch]:
            job.status = "RUNNING"
            job.attempts += 1
            job.claimedBy = holder
            job.leaseExpiresAt = moment + timedelta(seconds=lease)
            job.updatedAt = moment
            claimed.append(job)
        return tuple(claimed)

    def heartbeat(
        self,
        tenantId: uuid.UUID | str,
        jobId: uuid.UUID | str,
        workerId: str,
        leaseSeconds: int,
        *,
        now: datetime | None = None,
    ) -> AIJob:
        job = self.getJob(tenantId, jobId)
        moment = asUtc(now) if now is not None else self._now()
        if job.status != "RUNNING" or not job.leaseHeldBy(workerId, moment):
            raise AIJobLeaseConflict(f"Job {job.id} is not held by this worker.")
        job.leaseExpiresAt = moment + timedelta(seconds=self._coerceLeaseSeconds(leaseSeconds))
        job.updatedAt = moment
        return job

    # ------------------------------------------------------------------
    # Settlement
    # ------------------------------------------------------------------
    def complete(
        self,
        tenantId: uuid.UUID | str,
        jobId: uuid.UUID | str,
        workerId: str,
        *,
        summary: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> AIJob:
        job = self.getJob(tenantId, jobId)
        moment = asUtc(now) if now is not None else self._now()
        if job.status != "RUNNING" or not job.leaseHeldBy(workerId, moment):
            raise AIJobLeaseConflict(f"Job {job.id} is not held by this worker.")
        job.status = "SUCCEEDED"
        job.resultSummary = dict(summary) if summary is not None else {}
        job.errorCode = ""
        job.claimedBy = ""
        job.leaseExpiresAt = None
        job.updatedAt = moment
        return job

    def failJob(
        self,
        tenantId: uuid.UUID | str,
        jobId: uuid.UUID | str,
        workerId: str,
        *,
        errorCode: str = "",
        retryable: bool = True,
        baseSeconds: int = 30,
        multiplier: float = 2.0,
        maxSeconds: int = 600,
        now: datetime | None = None,
    ) -> AIJob:
        job = self.getJob(tenantId, jobId)
        moment = asUtc(now) if now is not None else self._now()
        if job.status != "RUNNING" or not job.leaseHeldBy(workerId, moment):
            raise AIJobLeaseConflict(f"Job {job.id} is not held by this worker.")
        job.errorCode = str(errorCode or "").strip().upper()
        if retryable and job.attempts < job.maxAttempts:
            delay = computeBackoff(job.attempts, baseSeconds, multiplier, maxSeconds)
            job.status = "PENDING"
            job.runAt = moment + timedelta(seconds=delay)
            job.claimedBy = ""
            job.leaseExpiresAt = None
        elif job.attempts >= job.maxAttempts:
            job.status = "DEAD"
            job.claimedBy = ""
            job.leaseExpiresAt = None
        else:
            job.status = "FAILED"
            job.claimedBy = ""
            job.leaseExpiresAt = None
        job.updatedAt = moment
        return job

    def cancelJob(
        self,
        tenantId: uuid.UUID | str,
        jobId: uuid.UUID | str,
        *,
        workerId: str = "",
        now: datetime | None = None,
    ) -> AIJob:
        job = self.getJob(tenantId, jobId)
        moment = asUtc(now) if now is not None else self._now()
        if job.status in TERMINAL_JOB_STATUSES:
            raise AIJobInvalid(f"Job {job.id} is already terminal.")
        if (
            job.status == "RUNNING"
            and job.leaseExpiresAt is not None
            and job.leaseExpiresAt > moment
            and (not workerId or not job.leaseHeldBy(workerId, moment))
        ):
            raise AIJobLeaseConflict(f"Job {job.id} is held under a live lease.")
        job.status = "CANCELLED"
        job.claimedBy = ""
        job.leaseExpiresAt = None
        job.updatedAt = moment
        return job

    def forget(self, tenantId: uuid.UUID | str, jobId: uuid.UUID | str) -> bool:
        # Drop a hydrated job (post-purge cleanup); later imports reload it.
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(jobId, "jobId")
        key = (tenant, identifier)
        if key not in self._jobs:
            return False
        del self._jobs[key]
        stale = [
            mapKey
            for mapKey, (_, boundId) in self._idempotency.items()
            if mapKey[0] == tenant and boundId == identifier
        ]
        for mapKey in stale:
            del self._idempotency[mapKey]
        return True

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def getJob(self, tenantId: uuid.UUID | str, jobId: uuid.UUID | str) -> AIJob:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(jobId, "jobId")
        job = self._jobs.get((tenant, identifier))
        if job is None:
            raise AIJobNotFound(str(identifier))
        return job

    def describeJob(self, tenantId: uuid.UUID | str, jobId: uuid.UUID | str) -> JobDescriptor:
        job = self.getJob(tenantId, jobId)
        return JobDescriptor(
            tenantId=job.tenantId,
            jobId=job.id,
            kind=job.kind,
            status=job.status,
            priority=job.priority,
            attempts=job.attempts,
            maxAttempts=job.maxAttempts,
            runAt=job.runAt,
            claimedBy=job.claimedBy,
            leaseExpiresAt=job.leaseExpiresAt,
            requestId=job.requestId,
            payload=dict(job.payload),
            resultSummary=dict(job.resultSummary),
            errorCode=job.errorCode,
            correlationId=job.correlationId,
            traceId=job.traceId,
            createdAt=job.createdAt,
            updatedAt=job.updatedAt,
        )

    def listJobs(
        self, tenantId: uuid.UUID | str, jobFilter: JobFilter | None = None
    ) -> tuple[JobDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        active = jobFilter or JobFilter()
        try:
            status = ensureJobStatus(active.status) if active.status else None
            kind = ensureJobKind(active.kind) if active.kind else None
        except AIError:
            raise
        except Exception as exc:
            raise AIJobInvalid(str(exc)) from exc
        request = (
            requireUuid(active.requestId, "requestId") if active.requestId is not None else None
        )
        since = asUtc(active.since) if active.since is not None else None
        until = asUtc(active.until) if active.until is not None else None
        selected = [
            job
            for (jobTenant, _), job in self._jobs.items()
            if jobTenant == tenant
            and (status is None or job.status == status)
            and (kind is None or job.kind == kind)
            and (request is None or job.requestId == request)
            and (since is None or job.createdAt >= since)
            and (until is None or job.createdAt < until)
        ]
        selected.sort(key=lambda job: (job.createdAt, str(job.id)))
        return tuple(self.describeJob(tenant, job.id) for job in selected)

    # ------------------------------------------------------------------
    # Internal invariants
    # ------------------------------------------------------------------
    @staticmethod
    def _coerceMaxAttempts(value: int) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise AIJobInvalid("Job max attempts must be a positive integer.")
        return value

    @staticmethod
    def _coerceLeaseSeconds(value: int) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise AIJobInvalid("Job lease seconds must be a positive integer.")
        return value

    @staticmethod
    def _coerceLimit(value: int) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise AIJobInvalid("Claim limit must be a positive integer.")
        return value


AIJobQueue = JobQueueService
InMemoryJobQueue = JobQueueService
AIQueueService = JobQueueService

__all__ = [
    "AIJobQueue",
    "AIQueueService",
    "InMemoryJobQueue",
    "JOB_OUTCOMES",
    "JobDescriptor",
    "JobFilter",
    "JobOutcome",
    "JobQueueService",
    "ensureJobOutcome",
    "jobFingerprint",
]
