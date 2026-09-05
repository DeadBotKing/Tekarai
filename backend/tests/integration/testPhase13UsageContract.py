"""Phase 13-N integration tests — Django stores satisfy the metering ports.

Runs the ``UsageAttemptStore``, ``QuotaPolicyStore``, ``QuotaCounterStore``,
and ``CostRateResolver`` contracts against a real SQLite database: row↔entity
mapping, tenant scoping, idempotent replays, atomic counter increments, and
``runtime_checkable`` protocol conformance. No external network or provider
credentials are involved.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.ai.domain.entities.usageRecords import AIQuotaCounter, AIQuotaPolicy, AIUsageAttempt
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIIdempotencyConflict,
    AIModelInactive,
    AIModelNotRegistered,
    AIQuotaPolicyAlreadyRegistered,
    AIQuotaPolicyNotFound,
    AIUsageAttemptAlreadyRegistered,
    AIUsageAttemptNotFound,
)
from apps.ai.domain.meteringPorts import (
    CostRateResolver,
    QuotaCounterStore,
    QuotaPolicyStore,
    UsageAttemptStore,
    UsageEventSink,
)
from apps.ai.domain.services.usageMetering import attemptFingerprint
from apps.ai.domain.valueObjects.aiTypes import CostRate, Money, TokenUsage
from apps.ai.infrastructure.models import (
    AICapabilityModel,
    AIModelModel,
    AIProviderModel,
    AIRequestModel,
)
from apps.ai.infrastructure.repositories.usageRepositories import (
    DjangoCostRateResolver,
    DjangoQuotaCounterStore,
    DjangoQuotaPolicyStore,
    DjangoUsageAttemptStore,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


def makeAttempt(
    tenantId: uuid.UUID,
    requestId: uuid.UUID,
    providerId: uuid.UUID,
    modelId: uuid.UUID,
    **overrides: object,
) -> AIUsageAttempt:
    params: dict[str, object] = {
        "providerCode": "OPENAI",
        "modelCode": "GPT-X",
        "usage": TokenUsage(inputTokens=100, outputTokens=50),
        "costAmount": Decimal("0.004"),
        "costCurrency": "USD",
        "providerTimeMs": 120,
        "createdAt": CLOCK,
    }
    params.update(overrides)
    return AIUsageAttempt(
        tenantId=tenantId,
        requestId=requestId,
        providerId=providerId,
        modelId=modelId,
        **params,  # type: ignore[arg-type]
    )


def makePolicy(tenantId: uuid.UUID, **overrides: object) -> AIQuotaPolicy:
    params: dict[str, object] = {
        "scope": "TENANT",
        "scopeReference": "",
        "dimension": "TOTAL_TOKENS",
        "window": "DAY",
        "limitValue": Decimal("1000"),
        "createdAt": CLOCK,
        "updatedAt": CLOCK,
    }
    params.update(overrides)
    return AIQuotaPolicy(tenantId=tenantId, **params)  # type: ignore[arg-type]


class UsageContractBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.provider = AIProviderModel.objects.create(
            tenantId=self.tenantId, code="OPENAI", name="OpenAI", providerType="CLOUD"
        )
        self.model = AIModelModel.objects.create(
            tenantId=self.tenantId,
            provider=self.provider,
            code="GPT-X",
            name="GPT X",
            inputCostPer1k=Decimal("0.01"),
            outputCostPer1k=Decimal("0.03"),
        )
        self.capability = AICapabilityModel.objects.create(
            tenantId=self.tenantId, code="SUMMARIZATION", name="Summarization"
        )
        self.request = AIRequestModel.objects.create(
            tenantId=self.tenantId,
            capability=self.capability,
            requestType="GENERATE",
            status="RUNNING",
            correlationId="corr-contract-1",
        )
        self.attempts = DjangoUsageAttemptStore()
        self.policies = DjangoQuotaPolicyStore()
        self.counters = DjangoQuotaCounterStore()
        self.resolver = DjangoCostRateResolver(currency="USD")

    def _attempt(self, **overrides: object) -> AIUsageAttempt:
        return makeAttempt(
            self.tenantId, self.request.id, self.provider.id, self.model.id, **overrides
        )


class AttemptStoreContractTests(UsageContractBase):
    def testSaveAndGetRoundTrip(self) -> None:
        stored = self.attempts.saveAttempt(self._attempt())
        fetched = self.attempts.getAttempt(self.tenantId, stored.id)
        self.assertEqual(fetched.totalTokens, 150)
        self.assertEqual(fetched.cost(), Money(Decimal("0.004"), "USD"))
        self.assertEqual(fetched.totalTimeMs, 120)
        self.assertEqual(fetched.providerCode, "OPENAI")

    def testCrossTenantGetRaisesNotFound(self) -> None:
        stored = self.attempts.saveAttempt(self._attempt())
        with self.assertRaises(AIUsageAttemptNotFound):
            self.attempts.getAttempt(self.otherTenantId, stored.id)

    def testListFiltersAndOrdering(self) -> None:
        first = self.attempts.saveAttempt(self._attempt(attemptNumber=1))
        secondRequest = AIRequestModel.objects.create(
            tenantId=self.tenantId,
            capability=self.capability,
            requestType="ASK",
            status="RUNNING",
            correlationId="corr-contract-2",
        )
        second = self.attempts.saveAttempt(
            makeAttempt(
                self.tenantId, secondRequest.id, self.provider.id, self.model.id, outcome="FAILED"
            )
        )
        self.assertEqual(
            [item.id for item in self.attempts.listAttempts(self.tenantId)], [first.id, second.id]
        )
        self.assertEqual(
            len(self.attempts.listAttempts(self.tenantId, requestId=self.request.id)), 1
        )
        self.assertEqual(len(self.attempts.listAttempts(self.tenantId, outcome="FAILED")), 1)
        # Row timestamps use persistence time (auto_now_add); filter against the
        # wall clock, not the domain CLOCK fixture.
        wallNow = datetime.now(tz=UTC)
        self.assertEqual(
            len(self.attempts.listAttempts(self.tenantId, since=wallNow + timedelta(days=1))), 0
        )
        self.assertEqual(
            len(self.attempts.listAttempts(self.tenantId, until=wallNow - timedelta(days=1))), 0
        )
        self.assertEqual(
            len(self.attempts.listAttempts(self.tenantId, since=wallNow - timedelta(days=1))), 2
        )

    def testIdempotentReplayReturnsStoredRow(self) -> None:
        first = self.attempts.saveAttempt(self._attempt(idempotencyKey="contract-key-1"))
        second = self.attempts.saveAttempt(self._attempt(idempotencyKey="contract-key-1"))
        self.assertEqual(first.id, second.id)

    def testReusedKeyWithDifferentContentConflicts(self) -> None:
        self.attempts.saveAttempt(self._attempt(idempotencyKey="contract-key-2"))
        other = self._attempt(
            idempotencyKey="contract-key-2", usage=TokenUsage(inputTokens=999, outputTokens=0)
        )
        with self.assertRaises(AIIdempotencyConflict):
            self.attempts.saveAttempt(other)

    def testDuplicateAttemptNumberRejected(self) -> None:
        self.attempts.saveAttempt(self._attempt(attemptNumber=1))
        with self.assertRaises(AIUsageAttemptAlreadyRegistered):
            self.attempts.saveAttempt(self._attempt(attemptNumber=1))

    def testFindByIdempotencyKey(self) -> None:
        stored = self.attempts.saveAttempt(self._attempt(idempotencyKey="contract-key-3"))
        found = self.attempts.findByIdempotencyKey(self.tenantId, "contract-key-3")
        assert found is not None
        self.assertEqual(found.id, stored.id)
        self.assertIsNone(self.attempts.findByIdempotencyKey(self.tenantId, "missing-key"))
        self.assertIsNone(self.attempts.findByIdempotencyKey(self.tenantId, ""))
        self.assertIsNone(self.attempts.findByIdempotencyKey(self.otherTenantId, "contract-key-3"))


class PolicyStoreContractTests(UsageContractBase):
    def testSaveGetAndListActive(self) -> None:
        stored = self.policies.savePolicy(makePolicy(self.tenantId))
        fetched = self.policies.getPolicy(self.tenantId, stored.id)
        self.assertEqual(fetched.limit(), 1000)
        self.assertEqual(len(self.policies.listActivePolicies(self.tenantId)), 1)
        self.assertEqual(self.policies.listActivePolicies(self.otherTenantId), ())

    def testDuplicateAxisRejected(self) -> None:
        self.policies.savePolicy(makePolicy(self.tenantId))
        with self.assertRaises(AIQuotaPolicyAlreadyRegistered):
            self.policies.savePolicy(makePolicy(self.tenantId))

    def testCrossTenantGetRaisesNotFound(self) -> None:
        stored = self.policies.savePolicy(makePolicy(self.tenantId))
        with self.assertRaises(AIQuotaPolicyNotFound):
            self.policies.getPolicy(self.otherTenantId, stored.id)

    def testSetPolicyActiveTogglesVisibility(self) -> None:
        stored = self.policies.savePolicy(makePolicy(self.tenantId))
        deactivated = self.policies.setPolicyActive(self.tenantId, stored.id, False)
        self.assertFalse(deactivated.isActive)
        self.assertEqual(self.policies.listActivePolicies(self.tenantId), ())
        reactivated = self.policies.setPolicyActive(self.tenantId, stored.id, True)
        self.assertTrue(reactivated.isActive)
        self.assertEqual(len(self.policies.listActivePolicies(self.tenantId)), 1)


class CounterStoreContractTests(UsageContractBase):
    def _policyId(self) -> uuid.UUID:
        return self.policies.savePolicy(makePolicy(self.tenantId)).id

    def testLoadMissingCounterReturnsNone(self) -> None:
        self.assertIsNone(
            self.counters.loadCounter(self.tenantId, uuid.uuid4(), CLOCK),
        )

    def testSaveCounterUpsertsAbsoluteValues(self) -> None:
        policyId = self._policyId()
        start = datetime(2026, 9, 5, tzinfo=UTC)
        counter = AIQuotaCounter(
            tenantId=self.tenantId, policyId=policyId, windowStart=start, consumedRequests=3
        )
        stored = self.counters.saveCounter(counter)
        self.assertEqual(stored.consumedRequests, 3)
        stored.consumedRequests = 7
        updated = self.counters.saveCounter(stored)
        self.assertEqual(updated.consumedRequests, 7)

    def testAddConsumptionCreatesAndIncrements(self) -> None:
        policyId = self._policyId()
        start = datetime(2026, 9, 5, tzinfo=UTC)
        first = self.counters.addConsumption(
            self.tenantId,
            policyId,
            start,
            requests=1,
            inputTokens=100,
            outputTokens=50,
            costAmount=Decimal("0.5"),
            currency="USD",
        )
        self.assertEqual(first.consumedRequests, 1)
        self.assertEqual(first.consumedTotalTokens, 150)
        self.assertEqual(first.consumedCost, Decimal("0.5"))
        second = self.counters.addConsumption(
            self.tenantId,
            policyId,
            start,
            requests=1,
            inputTokens=10,
            outputTokens=0,
            costAmount=Decimal("0.1"),
            currency="USD",
        )
        self.assertEqual(second.consumedRequests, 2)
        self.assertEqual(second.consumedTotalTokens, 160)
        self.assertEqual(second.consumedCost, Decimal("0.6"))

    def testAddConsumptionRejectsNegativeDeltasAndBadCurrency(self) -> None:
        policyId = self._policyId()
        start = datetime(2026, 9, 5, tzinfo=UTC)
        with self.assertRaises(ValueError):
            self.counters.addConsumption(self.tenantId, policyId, start, requests=-1)
        with self.assertRaises(ValueError):
            self.counters.addConsumption(
                self.tenantId, policyId, start, costAmount=Decimal("-1"), currency="USD"
            )
        with self.assertRaises(ValueError):
            self.counters.addConsumption(self.tenantId, policyId, start, currency="XX")

    def testCounterCurrencyStaysStableInsideWindow(self) -> None:
        policyId = self._policyId()
        start = datetime(2026, 9, 5, tzinfo=UTC)
        self.counters.addConsumption(self.tenantId, policyId, start, currency="USD")
        with self.assertRaises(AIConfigurationError):
            self.counters.addConsumption(self.tenantId, policyId, start, currency="EUR")

    def testCounterTenantMismatchBehavesAsNotFound(self) -> None:
        policyId = self._policyId()
        start = datetime(2026, 9, 5, tzinfo=UTC)
        self.counters.addConsumption(self.tenantId, policyId, start, currency="USD")
        with self.assertRaises(AIQuotaPolicyNotFound):
            self.counters.addConsumption(self.otherTenantId, policyId, start, currency="USD")


class ResolverContractTests(UsageContractBase):
    def testRateForReadsModelRates(self) -> None:
        rate = self.resolver.rateFor(self.tenantId, self.model.id)
        self.assertEqual(rate, CostRate(Decimal("0.01"), Decimal("0.03"), "USD"))

    def testMissingModelRaisesNotRegistered(self) -> None:
        with self.assertRaises(AIModelNotRegistered):
            self.resolver.rateFor(self.tenantId, uuid.uuid4())

    def testInactiveModelRaisesInactive(self) -> None:
        self.model.isActive = False
        self.model.save(update_fields=["isActive"])
        with self.assertRaises(AIModelInactive):
            self.resolver.rateFor(self.tenantId, self.model.id)

    def testCrossTenantModelReadsRaiseNotRegistered(self) -> None:
        with self.assertRaises(AIModelNotRegistered):
            self.resolver.rateFor(self.otherTenantId, self.model.id)

    def testResolverRejectsBadCurrency(self) -> None:
        with self.assertRaises(ValueError):
            DjangoCostRateResolver(currency="XX")


class PortConformanceTests(UsageContractBase):
    def testDjangoStoresSatisfyTheProtocols(self) -> None:
        self.assertIsInstance(self.attempts, UsageAttemptStore)
        self.assertIsInstance(self.policies, QuotaPolicyStore)
        self.assertIsInstance(self.counters, QuotaCounterStore)
        self.assertIsInstance(self.resolver, CostRateResolver)

    def testEventSinkProtocolConformance(self) -> None:
        from apps.ai.domain.meteringPorts import InMemoryUsageEventSink

        sink = InMemoryUsageEventSink()
        self.assertIsInstance(sink, UsageEventSink)
        with self.assertRaises(ValueError):
            sink.publish(object())  # type: ignore[arg-type]

    def testFingerprintIsStableAndSensitive(self) -> None:
        attempt = self._attempt()
        self.assertEqual(attemptFingerprint(attempt), attemptFingerprint(attempt))
        changed = self._attempt(
            usage=TokenUsage(inputTokens=101, outputTokens=50),
        )
        self.assertNotEqual(attemptFingerprint(attempt), attemptFingerprint(changed))
        with self.assertRaises(ValueError):
            attemptFingerprint(object())  # type: ignore[arg-type]
