"""Django persistence for Phase 13-N metering ports.

Row↔entity mapping only — no business rule lives here. Every read is
tenant-scoped (a foreign identifier behaves as not-found), idempotent
replays return the stored attempt, and counter increments are atomic per
(policy, window) row so concurrent admissions never lose consumption.

Currency validation stays a domain responsibility (the enforcement
service rejects mismatches before these stores are touched); the counter
store additionally refuses to mix currencies inside one row.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F

from apps.ai.domain.entities.aiRecords import requireUuid
from apps.ai.domain.entities.usageRecords import AIQuotaCounter, AIQuotaPolicy, AIUsageAttempt
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIIdempotencyConflict,
    AIModelNotRegistered,
    AIQuotaPolicyAlreadyRegistered,
    AIQuotaPolicyNotFound,
    AIUsageAttemptAlreadyRegistered,
    AIUsageAttemptNotFound,
)
from apps.ai.domain.services.usageMetering import attemptFingerprint
from apps.ai.domain.valueObjects.aiTypes import CostRate, TokenUsage
from apps.ai.domain.valueObjects.usageTypes import asUtc
from apps.ai.infrastructure.models import (
    AIModelModel,
    AIQuotaCounterModel,
    AIQuotaPolicyModel,
    AIUsageAttemptModel,
)


def attemptToEntity(row: AIUsageAttemptModel) -> AIUsageAttempt:
    return AIUsageAttempt(
        tenantId=row.tenantId,
        requestId=row.request_id,
        providerId=row.provider_id,
        modelId=row.model_id,
        providerCode=row.providerCode,
        modelCode=row.modelCode,
        usage=TokenUsage(inputTokens=row.inputTokens, outputTokens=row.outputTokens),
        latencyMs=row.totalTimeMs,
        queueTimeMs=row.queueTimeMs,
        contextBuildTimeMs=row.contextBuildTimeMs,
        providerTimeMs=row.providerTimeMs,
        validationTimeMs=row.validationTimeMs,
        id=row.id,
        operationId=row.operationId,
        attemptNumber=row.attemptNumber,
        capabilityCode=row.capabilityCode,
        requestedBy=row.requestedBy,
        costAmount=row.estimatedCost,
        costCurrency=row.currency,
        outcome=row.outcome,
        errorCode=row.errorCode,
        idempotencyKey=row.idempotencyKey,
        correlationId=row.correlationId,
        traceId=row.traceId,
        createdAt=row.createdAt,
    )


def policyToEntity(row: AIQuotaPolicyModel) -> AIQuotaPolicy:
    return AIQuotaPolicy(
        tenantId=row.tenantId,
        scope=row.scope,
        scopeReference=row.scopeReference,
        dimension=row.dimension,
        window=row.window,
        limitValue=row.limitValue,
        id=row.id,
        currency=row.currency,
        description=row.description,
        isActive=row.isActive,
        createdAt=row.createdAt,
        updatedAt=row.updatedAt,
    )


def counterToEntity(row: AIQuotaCounterModel) -> AIQuotaCounter:
    return AIQuotaCounter(
        tenantId=row.tenantId,
        policyId=row.policy_id,
        windowStart=row.windowStart,
        id=row.id,
        consumedRequests=row.consumedRequests,
        consumedInputTokens=row.consumedInputTokens,
        consumedOutputTokens=row.consumedOutputTokens,
        consumedCost=row.consumedCost,
        currency=row.currency,
        updatedAt=row.updatedAt,
    )


class DjangoUsageAttemptStore:
    """``UsageAttemptStore`` over the ``aiUsageAttempts`` table."""

    def saveAttempt(self, attempt: AIUsageAttempt) -> AIUsageAttempt:
        if not isinstance(attempt, AIUsageAttempt):
            raise ValueError("Attempt store requires an AIUsageAttempt.")
        fingerprint = attemptFingerprint(attempt)
        with transaction.atomic():
            if attempt.idempotencyKey:
                existing = AIUsageAttemptModel.objects.filter(
                    tenantId=attempt.tenantId,
                    idempotencyKey=attempt.idempotencyKey,
                ).first()
                if existing is not None:
                    if existing.fingerprint == fingerprint:
                        return attemptToEntity(existing)
                    raise AIIdempotencyConflict(
                        "The tenant-scoped usage idempotency key is already bound to another attempt."
                    )
            try:
                row = AIUsageAttemptModel.objects.create(
                    id=attempt.id,
                    tenantId=attempt.tenantId,
                    request_id=attempt.requestId,
                    operationId=attempt.operationId,
                    attemptNumber=attempt.attemptNumber,
                    provider_id=attempt.providerId,
                    model_id=attempt.modelId,
                    providerCode=attempt.providerCode,
                    modelCode=attempt.modelCode,
                    capabilityCode=attempt.capabilityCode,
                    requestedBy=attempt.requestedBy,
                    inputTokens=attempt.usage.inputTokens,
                    outputTokens=attempt.usage.outputTokens,
                    totalTokens=attempt.totalTokens,
                    estimatedCost=attempt.costAmount,
                    currency=attempt.costCurrency,
                    queueTimeMs=attempt.queueTimeMs,
                    contextBuildTimeMs=attempt.contextBuildTimeMs,
                    providerTimeMs=attempt.providerTimeMs,
                    validationTimeMs=attempt.validationTimeMs,
                    totalTimeMs=attempt.totalTimeMs,
                    outcome=attempt.outcome,
                    errorCode=attempt.errorCode,
                    idempotencyKey=attempt.idempotencyKey,
                    fingerprint=fingerprint,
                    correlationId=attempt.correlationId,
                    traceId=attempt.traceId,
                )
            except IntegrityError as exc:
                raise AIUsageAttemptAlreadyRegistered(str(attempt.requestId)) from exc
            return attemptToEntity(row)

    def getAttempt(self, tenantId: uuid.UUID, attemptId: uuid.UUID) -> AIUsageAttempt:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(attemptId, "attemptId")
        try:
            row = AIUsageAttemptModel.objects.get(tenantId=tenant, id=identifier)
        except AIUsageAttemptModel.DoesNotExist as exc:
            raise AIUsageAttemptNotFound(str(identifier)) from exc
        return attemptToEntity(row)

    def listAttempts(
        self,
        tenantId: uuid.UUID,
        *,
        requestId: uuid.UUID | str | None = None,
        outcome: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[AIUsageAttempt, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        queryset = AIUsageAttemptModel.objects.filter(tenantId=tenant)
        if requestId is not None:
            queryset = queryset.filter(request_id=requireUuid(requestId, "requestId"))
        if outcome:
            queryset = queryset.filter(outcome=str(outcome).strip().upper())
        if since is not None:
            queryset = queryset.filter(createdAt__gte=asUtc(since))
        if until is not None:
            queryset = queryset.filter(createdAt__lt=asUtc(until))
        return tuple(attemptToEntity(row) for row in queryset.order_by("createdAt", "id"))

    def findByIdempotencyKey(
        self, tenantId: uuid.UUID, idempotencyKey: str
    ) -> AIUsageAttempt | None:
        tenant = requireUuid(tenantId, "tenantId")
        key = str(idempotencyKey or "").strip()
        if not key:
            return None
        row = AIUsageAttemptModel.objects.filter(tenantId=tenant, idempotencyKey=key).first()
        return attemptToEntity(row) if row is not None else None


class DjangoQuotaPolicyStore:
    """``QuotaPolicyStore`` over the ``aiQuotaPolicies`` table."""

    def savePolicy(self, policy: AIQuotaPolicy) -> AIQuotaPolicy:
        if not isinstance(policy, AIQuotaPolicy):
            raise ValueError("Policy store requires an AIQuotaPolicy.")
        try:
            with transaction.atomic():
                row = AIQuotaPolicyModel.objects.create(
                    id=policy.id,
                    tenantId=policy.tenantId,
                    scope=policy.scope,
                    scopeReference=policy.scopeReference,
                    dimension=policy.dimension,
                    window=policy.window,
                    limitValue=policy.limitValue,
                    currency=policy.currency,
                    description=policy.description,
                    isActive=policy.isActive,
                )
        except IntegrityError as exc:
            raise AIQuotaPolicyAlreadyRegistered(
                f"Quota policy {policy.scope}/{policy.dimension}/{policy.window} is already defined."
            ) from exc
        return policyToEntity(row)

    def getPolicy(self, tenantId: uuid.UUID, policyId: uuid.UUID) -> AIQuotaPolicy:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(policyId, "policyId")
        try:
            row = AIQuotaPolicyModel.objects.get(tenantId=tenant, id=identifier)
        except AIQuotaPolicyModel.DoesNotExist as exc:
            raise AIQuotaPolicyNotFound(str(identifier)) from exc
        return policyToEntity(row)

    def listActivePolicies(self, tenantId: uuid.UUID) -> tuple[AIQuotaPolicy, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        rows = AIQuotaPolicyModel.objects.filter(tenantId=tenant, isActive=True).order_by(
            "createdAt", "id"
        )
        return tuple(policyToEntity(row) for row in rows)

    def setPolicyActive(
        self, tenantId: uuid.UUID, policyId: uuid.UUID, isActive: bool
    ) -> AIQuotaPolicy:
        policy = self.getPolicy(tenantId, policyId)
        if policy.isActive == bool(isActive):
            return policy
        if bool(isActive):
            policy.activate()
        else:
            policy.deactivate()
        AIQuotaPolicyModel.objects.filter(tenantId=policy.tenantId, id=policy.id).update(
            isActive=policy.isActive
        )
        return self.getPolicy(tenantId, policyId)


class DjangoQuotaCounterStore:
    """``QuotaCounterStore`` over the ``aiQuotaCounters`` table."""

    def loadCounter(
        self,
        tenantId: uuid.UUID,
        policyId: uuid.UUID,
        windowStart: datetime,
    ) -> AIQuotaCounter | None:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(policyId, "policyId")
        row = AIQuotaCounterModel.objects.filter(
            tenantId=tenant,
            policy_id=identifier,
            windowStart=asUtc(windowStart),
        ).first()
        return counterToEntity(row) if row is not None else None

    def saveCounter(self, counter: AIQuotaCounter) -> AIQuotaCounter:
        if not isinstance(counter, AIQuotaCounter):
            raise ValueError("Counter store requires an AIQuotaCounter.")
        with transaction.atomic():
            row, _ = AIQuotaCounterModel.objects.update_or_create(
                policy_id=counter.policyId,
                windowStart=asUtc(counter.windowStart),
                defaults={
                    "tenantId": counter.tenantId,
                    "consumedRequests": counter.consumedRequests,
                    "consumedInputTokens": counter.consumedInputTokens,
                    "consumedOutputTokens": counter.consumedOutputTokens,
                    "consumedCost": counter.consumedCost,
                    "currency": counter.currency,
                },
            )
            return counterToEntity(row)

    def addConsumption(
        self,
        tenantId: uuid.UUID,
        policyId: uuid.UUID,
        windowStart: datetime,
        *,
        requests: int = 0,
        inputTokens: int = 0,
        outputTokens: int = 0,
        costAmount: Decimal | int | str = Decimal("0"),
        currency: str = "USD",
    ) -> AIQuotaCounter:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(policyId, "policyId")
        start = asUtc(windowStart)
        amount = Decimal(str(costAmount))
        deltas = (requests, inputTokens, outputTokens)
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in deltas
        ):
            raise ValueError("Consumption deltas must be non-negative integers.")
        if amount < 0:
            raise ValueError("Consumption cost cannot be negative.")
        normalizedCurrency = str(currency or "").strip().upper()
        if len(normalizedCurrency) != 3 or not normalizedCurrency.isalpha():
            raise ValueError("Consumption currency must be an ISO-4217 code.")
        with transaction.atomic():
            try:
                row = AIQuotaCounterModel.objects.select_for_update().get(
                    policy_id=identifier, windowStart=start
                )
                if row.tenantId != tenant:
                    raise AIQuotaPolicyNotFound(str(identifier))
                if row.currency != normalizedCurrency:
                    raise AIConfigurationError(
                        "Quota counter currency must stay stable inside one window."
                    )
            except AIQuotaCounterModel.DoesNotExist:
                try:
                    with transaction.atomic():
                        row = AIQuotaCounterModel.objects.create(
                            tenantId=tenant,
                            policy_id=identifier,
                            windowStart=start,
                            currency=normalizedCurrency,
                        )
                except IntegrityError:
                    row = AIQuotaCounterModel.objects.select_for_update().get(
                        policy_id=identifier, windowStart=start
                    )
                    if row.tenantId != tenant:
                        raise AIQuotaPolicyNotFound(str(identifier)) from None
                    if row.currency != normalizedCurrency:
                        raise AIConfigurationError(
                            "Quota counter currency must stay stable inside one window."
                        ) from None
            AIQuotaCounterModel.objects.filter(id=row.id).update(
                consumedRequests=F("consumedRequests") + requests,
                consumedInputTokens=F("consumedInputTokens") + inputTokens,
                consumedOutputTokens=F("consumedOutputTokens") + outputTokens,
                consumedCost=F("consumedCost") + amount,
            )
            row.refresh_from_db()
            return counterToEntity(row)


class DjangoCostRateResolver:
    """``CostRateResolver`` reading billable rates from ``aiModels``.

    Model rates are denominated in the platform metering currency
    (``AI_USAGE_DEFAULT_CURRENCY``); the application layer wires it here so
    attempt costs and cost caps always share one currency.
    """

    def __init__(self, *, currency: str = "USD") -> None:
        normalized = str(currency or "").strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("Rate currency must be an ISO-4217 code.")
        self.currency = normalized

    def rateFor(self, tenantId: uuid.UUID, modelId: uuid.UUID) -> CostRate:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(modelId, "modelId")
        try:
            row = AIModelModel.objects.get(tenantId=tenant, id=identifier)
        except AIModelModel.DoesNotExist as exc:
            raise AIModelNotRegistered(str(identifier)) from exc
        if not row.isActive:
            from apps.ai.domain.exceptions import AIModelInactive

            raise AIModelInactive(row.code)
        return CostRate(row.inputCostPer1k, row.outputCostPer1k, self.currency)


__all__ = [
    "DjangoCostRateResolver",
    "DjangoQuotaCounterStore",
    "DjangoQuotaPolicyStore",
    "DjangoUsageAttemptStore",
    "attemptToEntity",
    "counterToEntity",
    "policyToEntity",
]
