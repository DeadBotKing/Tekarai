"""Django persistence for the Phase 13-P async job ledger.

Row↔entity mapping only — no business rule lives here. Every read is
tenant-scoped (a foreign identifier behaves as not-found). Empty
idempotency keys are stored as ``none:<jobId>`` sentinels so the plain
``(tenantId, idempotencyKey)`` unique constraint holds on every backend;
the mapping translates sentinels back to ``""``.

``claimRow`` is safe for concurrent workers without row locks: it
selects due candidates, then applies one guarded ``UPDATE`` (still
``PENDING``, lease free) so exactly one worker wins each row, and
finally reads back only the rows this claim won.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Q

from apps.ai.domain.entities.aiRecords import requireUuid
from apps.ai.domain.entities.jobRecords import AIJob
from apps.ai.domain.exceptions import AIJobInvalid, AIJobNotFound
from apps.ai.domain.valueObjects.usageTypes import asUtc
from apps.ai.infrastructure.models import AIJobModel

_EMPTY_KEY_PREFIX = "none:"


def _rowKey(idempotencyKey: str, jobId: uuid.UUID) -> str:
    key = str(idempotencyKey or "").strip()
    if key:
        return key
    return f"{_EMPTY_KEY_PREFIX}{jobId}"


def _entityKey(rowKey: str) -> str:
    if rowKey.startswith(_EMPTY_KEY_PREFIX):
        return ""
    return rowKey


def jobToEntity(row: AIJobModel) -> AIJob:
    """Map a ledger row to its domain entity (sentinel-aware)."""

    return AIJob(
        tenantId=row.tenantId,
        kind=row.kind,
        id=row.id,
        requestId=row.requestId,
        payload=dict(row.payload or {}),
        idempotencyKey=_entityKey(row.idempotencyKey or ""),
        status=row.status,
        priority=row.priority,
        attempts=row.attempts,
        maxAttempts=row.maxAttempts,
        runAt=row.runAt,
        claimedBy=row.claimedBy or "",
        leaseExpiresAt=row.leaseExpiresAt,
        resultSummary=dict(row.resultSummary or {}),
        errorCode=row.errorCode or "",
        correlationId=row.correlationId or "",
        traceId=row.traceId or "",
        createdAt=row.createdAt,
        updatedAt=row.updatedAt,
    )


def _applyEntity(row: AIJobModel, job: AIJob, moment: datetime) -> None:
    row.kind = job.kind
    row.requestId = job.requestId
    row.payload = dict(job.payload)
    row.idempotencyKey = _rowKey(job.idempotencyKey, job.id)
    row.status = job.status
    row.priority = job.priority
    row.attempts = job.attempts
    row.maxAttempts = job.maxAttempts
    row.runAt = job.runAt
    row.claimedBy = job.claimedBy
    row.leaseExpiresAt = job.leaseExpiresAt
    row.resultSummary = dict(job.resultSummary)
    row.errorCode = job.errorCode
    row.correlationId = job.correlationId
    row.traceId = job.traceId
    row.updatedAt = moment


class DjangoJobStore:
    """``JobStore`` over the ``aiJobs`` table."""

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def save(self, job: AIJob) -> AIJob:
        if not isinstance(job, AIJob):
            raise AIJobInvalid("Job persistence requires an AIJob.")
        row = AIJobModel(
            id=job.id,
            tenantId=job.tenantId,
            kind=job.kind,
            requestId=job.requestId,
            payload=dict(job.payload),
            idempotencyKey=_rowKey(job.idempotencyKey, job.id),
            status=job.status,
            priority=job.priority,
            attempts=job.attempts,
            maxAttempts=job.maxAttempts,
            runAt=job.runAt,
            claimedBy=job.claimedBy,
            leaseExpiresAt=job.leaseExpiresAt,
            resultSummary=dict(job.resultSummary),
            errorCode=job.errorCode,
            correlationId=job.correlationId,
            traceId=job.traceId,
        )
        try:
            with transaction.atomic():
                row.save(force_insert=True)
        except IntegrityError:
            # A concurrent submit won the tenant-scoped key; the follow-up
            # read runs outside the poisoned transaction.
            existing = AIJobModel.objects.filter(
                tenantId=job.tenantId, idempotencyKey=_rowKey(job.idempotencyKey, job.id)
            ).first()
            if existing is None:
                raise
            return jobToEntity(existing)
        return jobToEntity(row)

    def update(self, job: AIJob) -> AIJob:
        if not isinstance(job, AIJob):
            raise AIJobInvalid("Job persistence requires an AIJob.")
        moment = asUtc(job.updatedAt)
        with transaction.atomic():
            try:
                row = AIJobModel.objects.get(id=job.id, tenantId=job.tenantId)
            except AIJobModel.DoesNotExist:
                raise AIJobNotFound(str(job.id)) from None
            _applyEntity(row, job, moment)
            try:
                row.save()
            except IntegrityError as exc:
                raise AIJobInvalid(f"Job update conflicts: {exc}") from exc
            return jobToEntity(row)

    def claimRow(
        self,
        tenantId: uuid.UUID | None,
        workerId: str,
        leaseSeconds: int,
        limit: int,
        now: datetime,
    ) -> tuple[AIJob, ...]:
        holder = str(workerId or "").strip()
        if not holder:
            raise AIJobInvalid("Claiming requires a worker id.")
        if not isinstance(leaseSeconds, int) or isinstance(leaseSeconds, bool):
            raise AIJobInvalid("Job lease seconds must be a positive integer.")
        if leaseSeconds < 1 or not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise AIJobInvalid("Claim inputs are out of range.")
        moment = asUtc(now)
        leaseEnds = moment + timedelta(seconds=leaseSeconds)
        tenant = requireUuid(tenantId, "tenantId") if tenantId is not None else None
        with transaction.atomic():
            candidates = AIJobModel.objects.filter(
                status__in=("PENDING", "RUNNING"), runAt__lte=moment
            ).filter(Q(leaseExpiresAt__isnull=True) | Q(leaseExpiresAt__lte=moment))
            if tenant is not None:
                candidates = candidates.filter(tenantId=tenant)
            candidateIds = list(
                candidates.order_by("-priority", "runAt", "createdAt", "id").values_list(
                    "id", flat=True
                )[:limit]
            )
            if not candidateIds:
                return ()
            AIJobModel.objects.filter(
                id__in=candidateIds, status__in=("PENDING", "RUNNING")
            ).filter(Q(leaseExpiresAt__isnull=True) | Q(leaseExpiresAt__lte=moment)).update(
                status="RUNNING",
                attempts=F("attempts") + 1,
                claimedBy=holder,
                leaseExpiresAt=leaseEnds,
                updatedAt=moment,
            )
            won = list(
                AIJobModel.objects.filter(
                    id__in=candidateIds, claimedBy=holder, leaseExpiresAt=leaseEnds
                ).order_by("-priority", "runAt", "createdAt", "id")
            )
            return tuple(jobToEntity(row) for row in won)

    # ------------------------------------------------------------------
    # Reads (all tenant-scoped; foreign rows behave as not-found)
    # ------------------------------------------------------------------
    def get(self, tenantId: uuid.UUID, jobId: uuid.UUID) -> AIJob | None:
        row = AIJobModel.objects.filter(id=jobId, tenantId=tenantId).first()
        return jobToEntity(row) if row is not None else None

    def findByIdempotencyKey(self, tenantId: uuid.UUID, idempotencyKey: str) -> AIJob | None:
        key = str(idempotencyKey or "").strip()
        if not key:
            return None
        row = AIJobModel.objects.filter(tenantId=tenantId, idempotencyKey=key).first()
        return jobToEntity(row) if row is not None else None

    def listTenantJobs(self, tenantId: uuid.UUID) -> tuple[AIJob, ...]:
        rows = AIJobModel.objects.filter(tenantId=tenantId).order_by("createdAt", "id")
        return tuple(jobToEntity(row) for row in rows)

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------
    def deleteJobsBefore(
        self, tenantId: uuid.UUID | None, cutoff: datetime, statuses: tuple[str, ...]
    ) -> int:
        moment = asUtc(cutoff)
        query = AIJobModel.objects.filter(status__in=tuple(statuses), createdAt__lt=moment)
        if tenantId is not None:
            query = query.filter(tenantId=requireUuid(tenantId, "tenantId"))
        deleted, _ = query.delete()
        return int(deleted)


__all__ = [
    "DjangoJobStore",
    "jobToEntity",
]
