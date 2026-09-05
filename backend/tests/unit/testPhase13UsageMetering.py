"""Phase 13-N usage, cost, latency, and quota tests (pure Python, offline).

Covers the §26 usage/cost recording contract, the §27 latency split, §34
aggregates (totals, average, p95), quota policy matching and enforcement
(§29/§42), the §43 error surface, tenant isolation, and idempotent
recording — without Django, network, or provider credentials.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from apps.ai.domain.entities.usageRecords import (
    AIQuotaCounter,
    AIQuotaPolicy,
    AIUsageAttempt,
    costForAttempt,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AICostLimitExceeded,
    AIIdempotencyConflict,
    AIQuotaExceeded,
    AIQuotaPolicyAlreadyRegistered,
    AIQuotaPolicyInvalid,
    AIQuotaPolicyNotFound,
    AIUsageAttemptAlreadyRegistered,
    AIUsageAttemptNotFound,
)
from apps.ai.domain.services.quotaEnforcement import (
    QuotaEnforcementService,
    raiseForDenial,
)
from apps.ai.domain.services.usageMetering import (
    CostCalculator,
    UsageMeteringService,
    latencyStatistics,
)
from apps.ai.domain.valueObjects.aiTypes import CostRate, Money, TokenUsage
from apps.ai.domain.valueObjects.usageTypes import (
    LatencyBreakdown,
    UsageAttribution,
    windowEnd,
    windowStart,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


def makeMetering(now: datetime = CLOCK) -> UsageMeteringService:
    return UsageMeteringService(now=lambda: now)


def makeEnforcement(now: datetime = CLOCK) -> QuotaEnforcementService:
    return QuotaEnforcementService(now=lambda: now)


def sampleIds() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


class WindowMathTests(unittest.TestCase):
    def testMinuteHourDayTruncation(self) -> None:
        moment = datetime(2026, 9, 5, 14, 37, 22, 123456, tzinfo=UTC)
        self.assertEqual(windowStart(moment, "MINUTE"), datetime(2026, 9, 5, 14, 37, tzinfo=UTC))
        self.assertEqual(windowStart(moment, "HOUR"), datetime(2026, 9, 5, 14, 0, tzinfo=UTC))
        self.assertEqual(windowStart(moment, "DAY"), datetime(2026, 9, 5, 0, 0, tzinfo=UTC))

    def testWeekStartsOnMonday(self) -> None:
        friday = datetime(2026, 9, 4, 23, 59, tzinfo=UTC)
        monday = datetime(2026, 8, 31, 0, 0, tzinfo=UTC)
        self.assertEqual(windowStart(friday, "WEEK"), monday)
        self.assertEqual(windowStart(monday, "WEEK"), monday)

    def testMonthBoundariesAndYearRollover(self) -> None:
        moment = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
        self.assertEqual(windowStart(moment, "MONTH"), datetime(2026, 1, 1, tzinfo=UTC))
        december = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
        self.assertEqual(
            windowEnd(windowStart(december, "MONTH"), "MONTH"),
            datetime(2027, 1, 1, tzinfo=UTC),
        )
        self.assertEqual(
            windowEnd(windowStart(moment, "DAY"), "DAY"), datetime(2026, 1, 16, tzinfo=UTC)
        )

    def testNaiveDatetimesAreTreatedAsUtc(self) -> None:
        naive = datetime(2026, 9, 5, 14, 37, 22)
        self.assertEqual(windowStart(naive, "HOUR"), datetime(2026, 9, 5, 14, 0, tzinfo=UTC))

    def testInvalidWindowRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            windowStart(CLOCK, "FORTNIGHT")


class MeteringValueObjectTests(unittest.TestCase):
    def testLatencyBreakdownTotalsItsParts(self) -> None:
        breakdown = LatencyBreakdown(queueMs=5, contextBuildMs=7, providerMs=120, validationMs=3)
        self.assertEqual(breakdown.totalMs, 135)

    def testLatencyBreakdownRejectsNegativeAndBool(self) -> None:
        with self.assertRaises(ValidationFailedError):
            LatencyBreakdown(providerMs=-1)
        with self.assertRaises(ValidationFailedError):
            LatencyBreakdown(queueMs=True)

    def testUsageAttributionNormalizesCodes(self) -> None:
        attribution = UsageAttribution(
            capabilityCode="text_generation",
            modelCode="gpt-x ",
            providerCode=" openai",
            departmentCode="pharma ",
        )
        self.assertEqual(attribution.capabilityCode, "TEXT_GENERATION")
        self.assertEqual(attribution.modelCode, "GPT-X")
        self.assertEqual(attribution.providerCode, "OPENAI")
        self.assertEqual(attribution.departmentCode, "PHARMA")

    def testQuotaEnumsRejectUnknownValues(self) -> None:
        policyKwargs: dict[str, object] = {
            "tenantId": uuid.uuid4(),
            "scope": "TENANT",
            "scopeReference": "",
            "dimension": "REQUESTS",
            "window": "DAY",
            "limitValue": 10,
        }
        for fieldName, badValue in (
            ("scope", "GALAXY"),
            ("dimension", "VIBES"),
            ("window", "FORTNIGHT"),
        ):
            candidate = dict(policyKwargs)
            candidate[fieldName] = badValue
            with self.assertRaises((ValidationFailedError, ValueError), msg=fieldName):
                AIQuotaPolicy(**candidate)  # type: ignore[arg-type]


class AttemptEntityTests(unittest.TestCase):
    def testMinimalAttemptRecord(self) -> None:
        tenantId, requestId, providerId, modelId = sampleIds()
        attempt = AIUsageAttempt(
            tenantId=tenantId,
            requestId=requestId,
            providerId=providerId,
            modelId=modelId,
            providerCode="openai",
            modelCode="gpt-x",
            usage=TokenUsage(inputTokens=100, outputTokens=25),
        )
        self.assertEqual(attempt.totalTokens, 125)
        self.assertEqual(attempt.totalTimeMs, 0)
        self.assertEqual(attempt.outcome, "SUCCEEDED")
        self.assertEqual(attempt.attemptNumber, 1)

    def testAttemptTotalsPreferExplicitLatency(self) -> None:
        tenantId, requestId, providerId, modelId = sampleIds()
        attempt = AIUsageAttempt(
            tenantId=tenantId,
            requestId=requestId,
            providerId=providerId,
            modelId=modelId,
            providerCode="OPENAI",
            modelCode="GPT-X",
            usage=TokenUsage(inputTokens=10, outputTokens=5),
            latencyMs=999,
            queueTimeMs=1,
            providerTimeMs=2,
        )
        self.assertEqual(attempt.totalTimeMs, 999)

    def testAttemptRejectsNegativeTokens(self) -> None:
        with self.assertRaises(ValidationFailedError):
            TokenUsage(inputTokens=-1, outputTokens=0)

    def testAttemptRejectsBadOutcomeAndAttemptNumber(self) -> None:
        tenantId, requestId, providerId, modelId = sampleIds()
        with self.assertRaises(ValidationFailedError):
            AIUsageAttempt(
                tenantId=tenantId,
                requestId=requestId,
                providerId=providerId,
                modelId=modelId,
                providerCode="OPENAI",
                modelCode="GPT-X",
                usage=TokenUsage(inputTokens=1, outputTokens=1),
                outcome="MAYBE",
            )
        with self.assertRaises(ValueError):
            AIUsageAttempt(
                tenantId=tenantId,
                requestId=requestId,
                providerId=providerId,
                modelId=modelId,
                providerCode="OPENAI",
                modelCode="GPT-X",
                usage=TokenUsage(inputTokens=1, outputTokens=1),
                attemptNumber=0,
            )

    def testAttemptRequiresProviderAndModelCodes(self) -> None:
        tenantId, requestId, providerId, modelId = sampleIds()
        with self.assertRaises(ValueError):
            AIUsageAttempt(
                tenantId=tenantId,
                requestId=requestId,
                providerId=providerId,
                modelId=modelId,
                providerCode="",
                modelCode="GPT-X",
                usage=TokenUsage(inputTokens=1, outputTokens=1),
            )

    def testAttemptRejectsBadCurrency(self) -> None:
        tenantId, requestId, providerId, modelId = sampleIds()
        with self.assertRaises(ValueError):
            AIUsageAttempt(
                tenantId=tenantId,
                requestId=requestId,
                providerId=providerId,
                modelId=modelId,
                providerCode="OPENAI",
                modelCode="GPT-X",
                usage=TokenUsage(inputTokens=1, outputTokens=1),
                costAmount=Decimal("1.5"),
                costCurrency="XX",
            )

    def testAttemptCostAndAttribution(self) -> None:
        tenantId, requestId, providerId, modelId = sampleIds()
        userId = uuid.uuid4()
        attempt = AIUsageAttempt(
            tenantId=tenantId,
            requestId=requestId,
            providerId=providerId,
            modelId=modelId,
            providerCode="OPENAI",
            modelCode="GPT-X",
            capabilityCode="SUMMARIZATION",
            requestedBy=userId,
            usage=TokenUsage(inputTokens=100, outputTokens=50),
            costAmount=Decimal("0.0045"),
            costCurrency="usd",
        )
        self.assertEqual(attempt.cost(), Money(Decimal("0.0045"), "USD"))
        attribution = attempt.attribution()
        self.assertEqual(attribution.modelCode, "GPT-X")
        self.assertEqual(attribution.capabilityCode, "SUMMARIZATION")
        self.assertEqual(attribution.userId, str(userId))


class QuotaPolicyEntityTests(unittest.TestCase):
    def testTenantPolicyCarriesNoReference(self) -> None:
        policy = AIQuotaPolicy(
            tenantId=uuid.uuid4(),
            scope="tenant",
            scopeReference="",
            dimension="requests",
            window="day",
            limitValue=100,
        )
        self.assertEqual(policy.scope, "TENANT")
        self.assertEqual(policy.limit(), 100)
        self.assertEqual(policy.windowStartFor(CLOCK), datetime(2026, 9, 5, tzinfo=UTC))

    def testReferenceRulesPerScope(self) -> None:
        tenantId = uuid.uuid4()
        with self.assertRaises(ValueError):
            AIQuotaPolicy(
                tenantId=tenantId,
                scope="TENANT",
                scopeReference="SOMETHING",
                dimension="REQUESTS",
                window="DAY",
                limitValue=1,
            )
        with self.assertRaises(ValueError):
            AIQuotaPolicy(
                tenantId=tenantId,
                scope="USER",
                scopeReference="",
                dimension="REQUESTS",
                window="DAY",
                limitValue=1,
            )

    def testPolicyRejectsNonPositiveAndFractionalLimits(self) -> None:
        tenantId = uuid.uuid4()
        for badLimit in (0, -5, "0", "abc"):
            with self.assertRaises(ValueError, msg=str(badLimit)):
                AIQuotaPolicy(
                    tenantId=tenantId,
                    scope="TENANT",
                    scopeReference="",
                    dimension="TOTAL_TOKENS",
                    window="DAY",
                    limitValue=badLimit,
                )
        with self.assertRaises(ValueError):
            AIQuotaPolicy(
                tenantId=tenantId,
                scope="TENANT",
                scopeReference="",
                dimension="REQUESTS",
                window="DAY",
                limitValue="1.5",
            )
        costPolicy = AIQuotaPolicy(
            tenantId=tenantId,
            scope="TENANT",
            scopeReference="",
            dimension="COST",
            window="MONTH",
            limitValue="12.50",
            currency="eur",
        )
        self.assertEqual(costPolicy.limit(), Decimal("12.50"))
        self.assertEqual(costPolicy.currency, "EUR")

    def testPolicyMatchingPerScope(self) -> None:
        tenantId = uuid.uuid4()
        userId = uuid.uuid4()
        full = UsageAttribution(
            capabilityCode="SUMMARIZATION",
            modelCode="GPT-X",
            providerCode="OPENAI",
            userId=str(userId),
            departmentCode="PHARMA",
            projectId="PRJ-1",
        )
        cases = (
            ("TENANT", "", True),
            ("USER", str(userId), True),
            ("USER", str(uuid.uuid4()), False),
            ("DEPARTMENT", "PHARMA", True),
            ("PROJECT", "PRJ-1", True),
            ("CAPABILITY", "SUMMARIZATION", True),
            ("CAPABILITY", "TRANSLATION", False),
            ("MODEL", "GPT-X", True),
            ("MODEL", "OTHER", False),
        )
        for scope, reference, expected in cases:
            with self.subTest(scope=scope):
                policy = AIQuotaPolicy(
                    tenantId=tenantId,
                    scope=scope,
                    scopeReference=reference,
                    dimension="REQUESTS",
                    window="DAY",
                    limitValue=5,
                )
                self.assertEqual(policy.matches(full), expected)

    def testPolicyDeactivateAndActivate(self) -> None:
        policy = AIQuotaPolicy(
            tenantId=uuid.uuid4(),
            scope="TENANT",
            scopeReference="",
            dimension="REQUESTS",
            window="DAY",
            limitValue=5,
        )
        policy.deactivate(now=CLOCK)
        self.assertFalse(policy.isActive)
        policy.activate(now=CLOCK)
        self.assertTrue(policy.isActive)


class QuotaCounterEntityTests(unittest.TestCase):
    def _counter(self, dimension: str = "TOTAL_TOKENS") -> tuple[AIQuotaPolicy, AIQuotaCounter]:
        policy = AIQuotaPolicy(
            tenantId=uuid.uuid4(),
            scope="TENANT",
            scopeReference="",
            dimension=dimension,
            window="DAY",
            limitValue=100,
        )
        counter = AIQuotaCounter(
            tenantId=policy.tenantId,
            policyId=policy.id,
            windowStart=policy.windowStartFor(CLOCK),
        )
        return policy, counter

    def testAddConsumptionAccumulates(self) -> None:
        policy, counter = self._counter()
        counter.addConsumption(
            TokenUsage(inputTokens=30, outputTokens=20), Money(Decimal("1"), "USD")
        )
        counter.addConsumption(
            TokenUsage(inputTokens=10, outputTokens=0), Money(Decimal("2"), "USD")
        )
        self.assertEqual(counter.consumedRequests, 2)
        self.assertEqual(counter.consumedFor("INPUT_TOKENS"), 40)
        self.assertEqual(counter.consumedFor("TOTAL_TOKENS"), 60)
        self.assertEqual(counter.consumedFor("COST"), Decimal("3"))
        self.assertEqual(counter.remainingFor(policy), 40)

    def testRemainingFloorsAtZero(self) -> None:
        policy, counter = self._counter()
        counter.consumedInputTokens = 500
        self.assertEqual(counter.remainingFor(policy), 0)

    def testExhaustionPerDimension(self) -> None:
        policy, counter = self._counter()
        usage = TokenUsage(inputTokens=60, outputTokens=41)
        self.assertTrue(counter.isExhaustedBy(policy, usage, Money(Decimal("0"), "USD")))
        self.assertFalse(
            counter.isExhaustedBy(
                policy, TokenUsage(inputTokens=60, outputTokens=40), Money(Decimal("0"), "USD")
            )
        )

    def testCounterRejectsForeignPolicy(self) -> None:
        _, counter = self._counter()
        foreign = AIQuotaPolicy(
            tenantId=counter.tenantId,
            scope="TENANT",
            scopeReference="",
            dimension="REQUESTS",
            window="DAY",
            limitValue=1,
        )
        with self.assertRaises(ValueError):
            counter.remainingFor(foreign)
        with self.assertRaises(ValueError):
            counter.isExhaustedBy(foreign, TokenUsage(1, 0), Money(Decimal("0"), "USD"))

    def testCounterRejectsCurrencyMixing(self) -> None:
        _, counter = self._counter()
        with self.assertRaises(ValueError):
            counter.addConsumption(TokenUsage(1, 0), Money(Decimal("1"), "EUR"))


class CostCalculatorTests(unittest.TestCase):
    def testCalculateFromRate(self) -> None:
        rate = CostRate(Decimal("0.01"), Decimal("0.03"))
        cost = CostCalculator.calculate(TokenUsage(inputTokens=1000, outputTokens=500), rate)
        self.assertEqual(cost, Money(Decimal("0.025"), "USD"))

    def testCostForAttemptHelper(self) -> None:
        rate = CostRate(Decimal("1"), Decimal("2"), "EUR")
        cost = costForAttempt(TokenUsage(inputTokens=2000, outputTokens=0), rate)
        self.assertEqual(cost, Money(Decimal("2"), "EUR"))

    def testTotalRequiresSingleCurrency(self) -> None:
        total = CostCalculator.total([Money(Decimal("1"), "USD"), Money(Decimal("2"), "USD")])
        self.assertEqual(total, Money(Decimal("3"), "USD"))
        self.assertEqual(CostCalculator.total([]), Money(Decimal("0"), "USD"))
        with self.assertRaises(AIConfigurationError):
            CostCalculator.total([Money(Decimal("1"), "USD"), Money(Decimal("1"), "EUR")])

    def testAssertWithinLimit(self) -> None:
        limit = Money(Decimal("5"), "USD")
        okCost = CostCalculator.assertWithinLimit(Money(Decimal("5"), "USD"), limit)
        self.assertEqual(okCost.amount, Decimal("5"))
        with self.assertRaises(AICostLimitExceeded):
            CostCalculator.assertWithinLimit(Money(Decimal("5.01"), "USD"), limit)
        with self.assertRaises(AIConfigurationError):
            CostCalculator.assertWithinLimit(Money(Decimal("1"), "EUR"), limit)

    def testCostLimitExceededIsAQuotaError(self) -> None:
        self.assertTrue(issubclass(AICostLimitExceeded, AIQuotaExceeded))
        error = AICostLimitExceeded("too expensive")
        self.assertEqual(error.code, "AI_COST_LIMIT_EXCEEDED")
        self.assertEqual(error.httpStatus, 429)


class LatencyStatisticsTests(unittest.TestCase):
    def testEmptySamplesYieldZeros(self) -> None:
        stats = latencyStatistics([])
        self.assertEqual(
            (stats.count, stats.totalMs, stats.averageMs, stats.p95Ms, stats.maxMs), (0, 0, 0, 0, 0)
        )

    def testSingleSample(self) -> None:
        stats = latencyStatistics([42])
        self.assertEqual((stats.count, stats.averageMs, stats.p95Ms, stats.maxMs), (1, 42, 42, 42))

    def testP95UsesNearestRank(self) -> None:
        stats = latencyStatistics(list(range(1, 101)))
        self.assertEqual(stats.count, 100)
        self.assertEqual(stats.p95Ms, 95)
        self.assertEqual(stats.maxMs, 100)
        self.assertEqual(stats.averageMs, 50)

    def testNegativeSamplesRejected(self) -> None:
        with self.assertRaises(ValueError):
            latencyStatistics([10, -1])


class MeteringServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.requestId = uuid.uuid4()
        self.providerId = uuid.uuid4()
        self.modelId = uuid.uuid4()
        self.metering = makeMetering()

    def _record(self, **overrides: object) -> object:
        params: dict[str, object] = {
            "providerCode": "OPENAI",
            "modelCode": "GPT-X",
            "inputTokens": 100,
            "outputTokens": 50,
            "costAmount": Decimal("0.004"),
            "costCurrency": "USD",
            "providerTimeMs": 120,
            "capabilityCode": "SUMMARIZATION",
            "correlationId": "corr-1",
            "traceId": "trace-1",
        }
        params.update(overrides)
        return self.metering.recordAttempt(
            self.tenantId,
            self.requestId,
            self.providerId,
            self.modelId,
            **params,  # type: ignore[arg-type]
        )

    def testRecordAndDescribeAttempt(self) -> None:
        attempt = self._record()
        descriptor = self.metering.describeAttempt(self.tenantId, attempt.id)
        self.assertEqual(descriptor.totalTokens, 150)
        self.assertEqual(descriptor.costAmount, Decimal("0.004"))
        self.assertEqual(descriptor.totalTimeMs, 120)
        self.assertEqual(descriptor.providerCode, "OPENAI")
        self.assertEqual(descriptor.correlationId, "corr-1")
        self.assertNotIn("prompt", repr(descriptor).lower())

    def testRecordIsIdempotentForSameFingerprint(self) -> None:
        first = self._record(idempotencyKey="usage-key-1")
        second = self._record(idempotencyKey="usage-key-1")
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.metering.listAttempts(self.tenantId)), 1)

    def testReusedKeyWithDifferentFingerprintConflicts(self) -> None:
        self._record(idempotencyKey="usage-key-2", inputTokens=100)
        with self.assertRaises(AIIdempotencyConflict):
            self._record(idempotencyKey="usage-key-2", inputTokens=101)

    def testIdempotencyKeysAreTenantScoped(self) -> None:
        self._record(idempotencyKey="shared-key")
        other = makeMetering()
        attempt = other.recordAttempt(
            self.otherTenantId,
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            providerCode="OPENAI",
            modelCode="GPT-X",
            inputTokens=1,
            outputTokens=1,
            idempotencyKey="shared-key",
        )
        self.assertIsNotNone(attempt.id)

    def testDuplicateAttemptNumberWithoutKeyRejected(self) -> None:
        self._record(attemptNumber=1)
        with self.assertRaises(AIUsageAttemptAlreadyRegistered):
            self._record(attemptNumber=1)

    def testFailedAttemptsRecordedWithErrorCode(self) -> None:
        attempt = self._record(outcome="FAILED", errorCode="AI_PROVIDER_UNAVAILABLE")
        self.assertEqual(attempt.outcome, "FAILED")
        failed = self.metering.listAttempts(self.tenantId, outcome="FAILED")
        self.assertEqual(len(failed), 1)
        succeeded = self.metering.listAttempts(self.tenantId, outcome="SUCCEEDED")
        self.assertEqual(len(succeeded), 0)

    def testCrossTenantReadsRaiseNotFound(self) -> None:
        attempt = self._record()
        with self.assertRaises(AIUsageAttemptNotFound):
            self.metering.getAttempt(self.otherTenantId, attempt.id)
        with self.assertRaises(AIUsageAttemptNotFound):
            self.metering.requestRollup(self.otherTenantId, self.requestId)

    def testListAttemptsFiltersByRequest(self) -> None:
        self._record()
        otherRequest = uuid.uuid4()
        self.metering.recordAttempt(
            self.tenantId,
            otherRequest,
            self.providerId,
            self.modelId,
            providerCode="OPENAI",
            modelCode="GPT-X",
            inputTokens=5,
            outputTokens=5,
        )
        self.assertEqual(len(self.metering.listAttempts(self.tenantId)), 2)
        filtered = self.metering.listAttempts(self.tenantId, requestId=self.requestId)
        self.assertEqual(len(filtered), 1)

    def testRequestRollupAggregatesAttempts(self) -> None:
        self._record(attemptNumber=1, inputTokens=100, outputTokens=50, costAmount=Decimal("0.004"))
        self._record(
            attemptNumber=2,
            inputTokens=200,
            outputTokens=0,
            costAmount=Decimal("0.002"),
            outcome="FAILED",
            errorCode="AI_REQUEST_TIMEOUT",
            providerTimeMs=30,
        )
        rollup = self.metering.requestRollup(self.tenantId, self.requestId)
        self.assertEqual(rollup.attempts, 2)
        self.assertEqual((rollup.succeeded, rollup.failed), (1, 1))
        self.assertEqual(rollup.totalTokens, 350)
        self.assertEqual(rollup.costAmount, Decimal("0.006"))
        self.assertEqual(rollup.totalTimeMs, 150)

    def testRequestRollupRejectsMixedCurrencies(self) -> None:
        self._record(attemptNumber=1, costCurrency="USD")
        self._record(attemptNumber=2, costCurrency="EUR", costAmount=Decimal("1"))
        with self.assertRaises(AIConfigurationError):
            self.metering.requestRollup(self.tenantId, self.requestId)

    def testRequestRollupMissingRequestRaises(self) -> None:
        with self.assertRaises(AIUsageAttemptNotFound):
            self.metering.requestRollup(self.tenantId, uuid.uuid4())

    def testSummarizeTotalsAndBreakdowns(self) -> None:
        self._record(capabilityCode="SUMMARIZATION", modelCode="GPT-X", providerCode="OPENAI")
        self._record(
            attemptNumber=2,
            capabilityCode="TRANSLATION",
            modelCode="GPT-X",
            providerCode="OPENAI",
            inputTokens=10,
            outputTokens=10,
        )
        summary = self.metering.summarize(self.tenantId)
        self.assertEqual(summary.attempts, 2)
        self.assertEqual(summary.totalTokens, 170)
        self.assertEqual(
            {item.key for item in summary.byCapability}, {"SUMMARIZATION", "TRANSLATION"}
        )
        self.assertEqual(len(summary.byModel), 1)
        self.assertEqual(summary.byModel[0].key, "GPT-X")
        self.assertEqual(summary.latency.count, 2)

    def testSummarizeFiltersByCodesAndTimeRange(self) -> None:
        self._record(capabilityCode="SUMMARIZATION")
        later = makeMetering(now=CLOCK + timedelta(days=1))
        later.importAttempt(
            self.metering.getAttempt(
                self.tenantId, self.metering.listAttempts(self.tenantId)[0].attemptId
            )
        )
        filtered = self.metering.summarize(self.tenantId, capabilityCode="TRANSLATION")
        self.assertEqual(filtered.attempts, 0)
        ranged = self.metering.summarize(self.tenantId, since=CLOCK + timedelta(hours=1))
        self.assertEqual(ranged.attempts, 0)

    def testSummarizeRejectsMixedCurrencies(self) -> None:
        self._record(attemptNumber=1, costCurrency="USD")
        self._record(attemptNumber=2, costCurrency="EUR")
        with self.assertRaises(AIConfigurationError):
            self.metering.summarize(self.tenantId)

    def testEventCarrierHasNoContentOrSecrets(self) -> None:
        attempt = self._record()
        event = self.metering.buildUsageRecordedEvent(attempt)
        payload = repr(event)
        self.assertEqual(event.totalTokens, 150)
        self.assertEqual(event.costCurrency, "USD")
        self.assertNotIn("prompt", payload.lower())
        self.assertNotIn("secret", payload.lower())

    def testImportAttemptHydratesReads(self) -> None:
        attempt = self._record()
        fresh = makeMetering()
        fresh.importAttempt(attempt)
        self.assertEqual(fresh.requestRollup(self.tenantId, self.requestId).attempts, 1)


class EnforcementServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.userId = uuid.uuid4()
        self.enforcement = makeEnforcement()

    def _attribution(self, **overrides: object) -> UsageAttribution:
        params: dict[str, object] = {
            "capabilityCode": "SUMMARIZATION",
            "modelCode": "GPT-X",
            "providerCode": "OPENAI",
            "userId": str(self.userId),
        }
        params.update(overrides)
        return UsageAttribution(**params)  # type: ignore[arg-type]

    def _usage(self, totalTokens: int = 100) -> TokenUsage:
        return TokenUsage(inputTokens=totalTokens, outputTokens=0)

    def _cost(self, amount: str = "0") -> Money:
        return Money(Decimal(amount), "USD")

    def testDefineAndDescribePolicy(self) -> None:
        policy = self.enforcement.definePolicy(
            self.tenantId, "TENANT", "", "TOTAL_TOKENS", "DAY", 1000, description="daily cap"
        )
        descriptor = self.enforcement.describePolicy(self.tenantId, policy.id)
        self.assertEqual(descriptor.scope, "TENANT")
        self.assertEqual(descriptor.limitValue, Decimal("1000"))
        self.assertTrue(descriptor.isActive)

    def testDuplicateAxisRejected(self) -> None:
        self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 10)
        with self.assertRaises(AIQuotaPolicyAlreadyRegistered):
            self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 99)

    def testInvalidPolicyMappedToPolicyInvalid(self) -> None:
        with self.assertRaises(AIQuotaPolicyInvalid):
            self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 0)
        with self.assertRaises(AIQuotaPolicyInvalid):
            self.enforcement.definePolicy(self.tenantId, "NOPE", "", "REQUESTS", "DAY", 1)

    def testListPoliciesPrecedenceOrder(self) -> None:
        self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 100)
        self.enforcement.definePolicy(
            self.tenantId, "USER", str(self.userId), "REQUESTS", "DAY", 10
        )
        policies = self.enforcement.listPolicies(self.tenantId)
        self.assertEqual([item.scope for item in policies], ["USER", "TENANT"])

    def testUpdateDeactivateActivatePolicy(self) -> None:
        policy = self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 10)
        updated = self.enforcement.updatePolicyLimit(self.tenantId, policy.id, 20)
        self.assertEqual(updated.limit(), 20)
        self.enforcement.deactivatePolicy(self.tenantId, policy.id)
        self.assertEqual(self.enforcement.listPolicies(self.tenantId, activeOnly=True), ())
        self.enforcement.activatePolicy(self.tenantId, policy.id)
        self.assertEqual(len(self.enforcement.listPolicies(self.tenantId, activeOnly=True)), 1)

    def testCrossTenantPolicyReadsRaiseNotFound(self) -> None:
        policy = self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 10)
        with self.assertRaises(AIQuotaPolicyNotFound):
            self.enforcement.getPolicy(self.otherTenantId, policy.id)

    def testInactivePoliciesNeverMatch(self) -> None:
        policy = self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 1)
        self.enforcement.deactivatePolicy(self.tenantId, policy.id)
        consumption = self.enforcement.checkAndConsume(
            self.tenantId, self._attribution(), self._usage(), self._cost()
        )
        self.assertEqual(consumption.consumed, ())

    def testCheckAndConsumeAccumulates(self) -> None:
        self.enforcement.definePolicy(self.tenantId, "TENANT", "", "TOTAL_TOKENS", "DAY", 1000)
        self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 10)
        consumption = self.enforcement.checkAndConsume(
            self.tenantId, self._attribution(), self._usage(100), self._cost("0.01")
        )
        self.assertEqual(len(consumption.consumed), 2)
        byDimension = {item.dimension: item.consumed for item in consumption.consumed}
        self.assertEqual(byDimension["TOTAL_TOKENS"], 100)
        self.assertEqual(byDimension["REQUESTS"], 1)

    def testDenialLeavesNoPartialConsumption(self) -> None:
        generous = self.enforcement.definePolicy(
            self.tenantId, "TENANT", "", "TOTAL_TOKENS", "DAY", 100000
        )
        self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 1)
        self.enforcement.checkAndConsume(
            self.tenantId, self._attribution(), self._usage(10), self._cost()
        )
        with self.assertRaises(AIQuotaExceeded):
            self.enforcement.checkAndConsume(
                self.tenantId, self._attribution(), self._usage(10), self._cost()
            )
        counter = self.enforcement.counterForWindow(
            self.tenantId, generous.id, generous.windowStartFor(CLOCK)
        )
        assert counter is not None
        self.assertEqual(counter.consumedRequests, 1)
        self.assertEqual(counter.consumedTotalTokens, 10)

    def testMostSpecificDenialReportedFirst(self) -> None:
        self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 1)
        self.enforcement.definePolicy(self.tenantId, "USER", str(self.userId), "REQUESTS", "DAY", 1)
        self.enforcement.checkAndConsume(
            self.tenantId, self._attribution(), self._usage(1), self._cost()
        )
        evaluation = self.enforcement.evaluate(
            self.tenantId, self._attribution(), self._usage(1), self._cost()
        )
        self.assertFalse(evaluation.allowed)
        self.assertEqual(evaluation.denials[0].scope, "USER")

    def testCostDenialRaisesCostLimitExceeded(self) -> None:
        self.enforcement.definePolicy(
            self.tenantId, "TENANT", "", "COST", "MONTH", "1.00", currency="USD"
        )
        with self.assertRaises(AICostLimitExceeded):
            self.enforcement.checkAndConsume(
                self.tenantId, self._attribution(), self._usage(5000), self._cost("2.50")
            )

    def testCurrencyMismatchFailsClosed(self) -> None:
        self.enforcement.definePolicy(
            self.tenantId, "TENANT", "", "COST", "MONTH", "100", currency="EUR"
        )
        with self.assertRaises(AIConfigurationError):
            self.enforcement.checkAndConsume(
                self.tenantId, self._attribution(), self._usage(10), self._cost("1")
            )

    def testConsumptionIsOutcomeAgnostic(self) -> None:
        self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 5)
        failed = TokenUsage(inputTokens=50, outputTokens=0)
        self.enforcement.checkAndConsume(
            self.tenantId, self._attribution(), failed, self._cost("0.02")
        )
        remaining = self.enforcement.peekRemaining(self.tenantId, self._attribution())
        self.assertEqual(remaining[0].remaining, 4)

    def testWindowRolloverStartsFreshCounter(self) -> None:
        policy = self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 1)
        self.enforcement.checkAndConsume(
            self.tenantId, self._attribution(), self._usage(1), self._cost()
        )
        nextDay = makeEnforcement(now=CLOCK + timedelta(days=1))
        nextDay.importPolicy(policy)
        oldCounter = self.enforcement.counterForWindow(
            self.tenantId, policy.id, policy.windowStartFor(CLOCK)
        )
        assert oldCounter is not None
        nextDay.importCounter(oldCounter)
        consumption = nextDay.checkAndConsume(
            self.tenantId,
            self._attribution(),
            self._usage(1),
            self._cost(),
            now=CLOCK + timedelta(days=1),
        )
        self.assertEqual(len(consumption.consumed), 1)

    def testPeekRemainingDoesNotMutate(self) -> None:
        policy = self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 7)
        remaining = self.enforcement.peekRemaining(self.tenantId, self._attribution())
        self.assertEqual(remaining[0].remaining, 7)
        self.assertEqual(remaining[0].windowStart, policy.windowStartFor(CLOCK))
        self.assertIsNone(
            self.enforcement.counterForWindow(
                self.tenantId, policy.id, policy.windowStartFor(CLOCK)
            )
        )

    def testEvaluateDryRunLeavesNoCounters(self) -> None:
        policy = self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 7)
        evaluation = self.enforcement.evaluate(
            self.tenantId, self._attribution(), self._usage(5), self._cost()
        )
        self.assertTrue(evaluation.allowed)
        self.assertEqual(evaluation.denials, ())
        self.assertIsNone(
            self.enforcement.counterForWindow(
                self.tenantId, policy.id, policy.windowStartFor(CLOCK)
            )
        )

    def testRaiseForDenialIsSingleSourced(self) -> None:
        self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 1)
        self.enforcement.checkAndConsume(
            self.tenantId, self._attribution(), self._usage(1), self._cost()
        )
        evaluation = self.enforcement.evaluate(
            self.tenantId, self._attribution(), self._usage(1), self._cost()
        )
        with self.assertRaises(AIQuotaExceeded):
            raiseForDenial(evaluation.denials[0])

    def testImportPolicyAndCounterHydration(self) -> None:
        policy = self.enforcement.definePolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 3)
        self.enforcement.checkAndConsume(
            self.tenantId, self._attribution(), self._usage(1), self._cost()
        )
        fresh = makeEnforcement()
        fresh.importPolicy(policy)
        counter = self.enforcement.counterForWindow(
            self.tenantId, policy.id, policy.windowStartFor(CLOCK)
        )
        assert counter is not None
        fresh.importCounter(counter)
        remaining = fresh.peekRemaining(self.tenantId, self._attribution())
        self.assertEqual(remaining[0].remaining, 2)
