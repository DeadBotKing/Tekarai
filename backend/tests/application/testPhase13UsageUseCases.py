"""Phase 13-N application tests — metering pipeline over a real SQLite test DB.

Covers the admission dry run, the record→persist→consume→publish pipeline,
idempotent re-recording, quota/token/cost denials, tenant isolation, and
the §26 reportable reads, orchestrated through ``UsageApplicationService``
with the Django stores from Phase 13-N.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.ai.application.services.usageService import (
    RecordUsageAttemptCommand,
    UsageApplicationService,
    UsageMeteringSettings,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AICostLimitExceeded,
    AIIdempotencyConflict,
    AIModelNotRegistered,
    AIQuotaExceeded,
    AIQuotaPolicyNotFound,
    AITokenLimitExceeded,
)
from apps.ai.domain.meteringPorts import InMemoryUsageEventSink
from apps.ai.domain.valueObjects.aiTypes import Money
from apps.ai.domain.valueObjects.usageTypes import UsageAttribution
from apps.ai.infrastructure.models import (
    AICapabilityModel,
    AIModelModel,
    AIProviderModel,
    AIQuotaCounterModel,
    AIRequestModel,
    AIUsageAttemptModel,
)
from apps.ai.infrastructure.repositories.usageRepositories import (
    DjangoCostRateResolver,
    DjangoQuotaCounterStore,
    DjangoQuotaPolicyStore,
    DjangoUsageAttemptStore,
)


def unlimitedSettings() -> UsageMeteringSettings:
    return UsageMeteringSettings(
        enabled=True,
        defaultTokenLimit=0,
        defaultCostLimit=Money(Decimal("0"), "USD"),
        retentionDays=90,
    )


class Phase13NUsageBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.userId = uuid.uuid4()
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
            correlationId="corr-n-1",
        )
        self.sink = InMemoryUsageEventSink()
        self.service = UsageApplicationService(
            DjangoUsageAttemptStore(),
            DjangoQuotaPolicyStore(),
            DjangoQuotaCounterStore(),
            DjangoCostRateResolver(currency="USD"),
            self.sink,
            meteringSettings=unlimitedSettings(),
        )

    def _command(self, **overrides: object) -> RecordUsageAttemptCommand:
        params: dict[str, object] = {
            "requestId": self.request.id,
            "modelId": self.model.id,
            "providerId": self.provider.id,
            "providerCode": "OPENAI",
            "modelCode": "GPT-X",
            "capabilityCode": "SUMMARIZATION",
            "requestedBy": self.userId,
            "userId": str(self.userId),
            "inputTokens": 100,
            "outputTokens": 50,
            "providerTimeMs": 120,
            "correlationId": "corr-n-1",
            "traceId": "trace-n-1",
        }
        params.update(overrides)
        return RecordUsageAttemptCommand(**params)  # type: ignore[arg-type]

    def _attribution(self) -> UsageAttribution:
        return UsageAttribution(
            capabilityCode="SUMMARIZATION",
            modelCode="GPT-X",
            providerCode="OPENAI",
            userId=str(self.userId),
        )


class RecordPipelineTests(Phase13NUsageBase):
    def testRecordPersistsAttemptCountersAndEvent(self) -> None:
        recorded = self.service.recordProviderAttempt(self.tenantId, self._command())
        self.assertEqual(recorded.attempt.totalTokens, 150)
        self.assertEqual(recorded.attempt.costAmount, Decimal("0.0025"))
        self.assertEqual(recorded.attempt.costCurrency, "USD")
        self.assertEqual(AIUsageAttemptModel.objects.filter(tenantId=self.tenantId).count(), 1)
        self.assertEqual(len(self.sink.events), 1)
        event = self.sink.events[0]
        self.assertEqual(event.attemptId, recorded.attempt.id)
        self.assertEqual(event.totalTokens, 150)
        rollup = self.service.requestRollup(self.tenantId, self.request.id)
        self.assertEqual(rollup.attempts, 1)
        self.assertEqual(rollup.costAmount, Decimal("0.0025"))

    def testRecordConsumesMatchingPoliciesAtomically(self) -> None:
        self.service.defineQuotaPolicy(self.tenantId, "TENANT", "", "TOTAL_TOKENS", "DAY", 10000)
        self.service.defineQuotaPolicy(
            self.tenantId, "USER", str(self.userId), "REQUESTS", "DAY", 10
        )
        recorded = self.service.recordProviderAttempt(self.tenantId, self._command())
        self.assertEqual(len(recorded.counters), 2)
        remaining = {
            (item.scope, item.dimension): item.remaining
            for item in self.service.remainingQuotas(self.tenantId, self._attribution())
        }
        self.assertEqual(remaining[("TENANT", "TOTAL_TOKENS")], 9850)
        self.assertEqual(remaining[("USER", "REQUESTS")], 9)

    def testIdempotentRerecordReturnsSameAttemptAndConsumesOnce(self) -> None:
        self.service.defineQuotaPolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 10)
        first = self.service.recordProviderAttempt(
            self.tenantId, self._command(idempotencyKey="n-key-1")
        )
        second = self.service.recordProviderAttempt(
            self.tenantId, self._command(idempotencyKey="n-key-1")
        )
        self.assertEqual(first.attempt.id, second.attempt.id)
        self.assertEqual(AIUsageAttemptModel.objects.filter(tenantId=self.tenantId).count(), 1)
        remaining = self.service.remainingQuotas(self.tenantId, self._attribution())
        self.assertEqual(remaining[0].remaining, 9)
        self.assertEqual(len(self.sink.events), 1)
        self.assertEqual(second.event.attemptId, first.attempt.id)

    def testReusedKeyWithDifferentContentConflicts(self) -> None:
        self.service.recordProviderAttempt(self.tenantId, self._command(idempotencyKey="n-key-9"))
        with self.assertRaises(AIIdempotencyConflict):
            self.service.recordProviderAttempt(
                self.tenantId, self._command(idempotencyKey="n-key-9", inputTokens=999)
            )
        self.assertEqual(AIUsageAttemptModel.objects.filter(tenantId=self.tenantId).count(), 1)

    def testFailedAttemptStillConsumesQuota(self) -> None:
        self.service.defineQuotaPolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 10)
        recorded = self.service.recordProviderAttempt(
            self.tenantId,
            self._command(outcome="FAILED", errorCode="AI_PROVIDER_UNAVAILABLE"),
        )
        self.assertEqual(recorded.attempt.outcome, "FAILED")
        remaining = self.service.remainingQuotas(self.tenantId, self._attribution())
        self.assertEqual(remaining[0].remaining, 9)

    def testSecondAttemptDeniedWhenQuotaExhausted(self) -> None:
        self.service.defineQuotaPolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 1)
        self.service.recordProviderAttempt(self.tenantId, self._command(attemptNumber=1))
        with self.assertRaises(AIQuotaExceeded):
            self.service.recordProviderAttempt(self.tenantId, self._command(attemptNumber=2))
        self.assertEqual(AIUsageAttemptModel.objects.filter(tenantId=self.tenantId).count(), 1)
        self.assertEqual(AIQuotaCounterModel.objects.filter(tenantId=self.tenantId).count(), 1)

    def testTokenCapDeniesBeforePersistence(self) -> None:
        capped = UsageApplicationService(
            DjangoUsageAttemptStore(),
            DjangoQuotaPolicyStore(),
            DjangoQuotaCounterStore(),
            DjangoCostRateResolver(currency="USD"),
            self.sink,
            meteringSettings=UsageMeteringSettings(
                enabled=True,
                defaultTokenLimit=100,
                defaultCostLimit=Money(Decimal("0"), "USD"),
                retentionDays=90,
            ),
        )
        with self.assertRaises(AITokenLimitExceeded):
            capped.recordProviderAttempt(self.tenantId, self._command())
        self.assertEqual(AIUsageAttemptModel.objects.count(), 0)
        self.assertEqual(len(self.sink.events), 0)

    def testCostCapDeniesBeforePersistence(self) -> None:
        capped = UsageApplicationService(
            DjangoUsageAttemptStore(),
            DjangoQuotaPolicyStore(),
            DjangoQuotaCounterStore(),
            DjangoCostRateResolver(currency="USD"),
            self.sink,
            meteringSettings=UsageMeteringSettings(
                enabled=True,
                defaultTokenLimit=0,
                defaultCostLimit=Money(Decimal("0.001"), "USD"),
                retentionDays=90,
            ),
        )
        with self.assertRaises(AICostLimitExceeded):
            capped.recordProviderAttempt(self.tenantId, self._command())
        self.assertEqual(AIUsageAttemptModel.objects.count(), 0)

    def testPerCallInputCapDenies(self) -> None:
        with self.assertRaises(AITokenLimitExceeded):
            self.service.recordProviderAttempt(self.tenantId, self._command(maxInputTokens=50))

    def testUnknownModelFailsClosed(self) -> None:
        with self.assertRaises(AIModelNotRegistered):
            self.service.recordProviderAttempt(self.tenantId, self._command(modelId=uuid.uuid4()))

    def testDisabledMeteringFailsClosed(self) -> None:
        disabled = UsageApplicationService(
            DjangoUsageAttemptStore(),
            DjangoQuotaPolicyStore(),
            DjangoQuotaCounterStore(),
            DjangoCostRateResolver(currency="USD"),
            self.sink,
            meteringSettings=UsageMeteringSettings(
                enabled=False,
                defaultTokenLimit=0,
                defaultCostLimit=Money(Decimal("0"), "USD"),
                retentionDays=90,
            ),
        )
        with self.assertRaises(AIConfigurationError):
            disabled.recordProviderAttempt(self.tenantId, self._command())


class AdmissionTests(Phase13NUsageBase):
    def testAdmissionGrantsWithoutMutating(self) -> None:
        self.service.defineQuotaPolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 5)
        grant = self.service.admitRequest(
            self.tenantId, self._attribution(), estimatedInputTokens=100, estimatedOutputTokens=50
        )
        self.assertEqual(grant.remaining[0].remaining, 5)
        self.assertEqual(AIUsageAttemptModel.objects.count(), 0)
        self.assertEqual(AIQuotaCounterModel.objects.count(), 0)

    def testAdmissionDeniesExhaustedQuota(self) -> None:
        self.service.defineQuotaPolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 1)
        self.service.recordProviderAttempt(self.tenantId, self._command(attemptNumber=1))
        with self.assertRaises(AIQuotaExceeded):
            self.service.admitRequest(self.tenantId, self._attribution())


class TenantIsolationTests(Phase13NUsageBase):
    def testPoliciesAndUsageDoNotLeakAcrossTenants(self) -> None:
        self.service.defineQuotaPolicy(self.tenantId, "TENANT", "", "REQUESTS", "DAY", 1)
        self.service.recordProviderAttempt(self.tenantId, self._command())
        self.assertEqual(self.service.listAttempts(self.otherTenantId), ())
        self.assertEqual(self.service.usageSummary(self.otherTenantId).attempts, 0)
        self.assertEqual(self.service.remainingQuotas(self.otherTenantId, self._attribution()), ())
        policyId = self.service.listQuotaPolicies(self.tenantId)[0].policyId
        with self.assertRaises(AIQuotaPolicyNotFound):
            self.service.deactivateQuotaPolicy(self.otherTenantId, policyId)


class PolicyAdministrationTests(Phase13NUsageBase):
    def testDefineListAndDeactivatePolicy(self) -> None:
        policy = self.service.defineQuotaPolicy(
            self.tenantId, "CAPABILITY", "SUMMARIZATION", "TOTAL_TOKENS", "DAY", 5000
        )
        policies = self.service.listQuotaPolicies(self.tenantId)
        self.assertEqual(len(policies), 1)
        self.assertEqual(policies[0].policyId, policy.id)
        self.service.deactivateQuotaPolicy(self.tenantId, policy.id)
        self.assertEqual(self.service.listQuotaPolicies(self.tenantId), ())
        recorded = self.service.recordProviderAttempt(self.tenantId, self._command())
        self.assertEqual(recorded.counters, ())


class ReportingTests(Phase13NUsageBase):
    def testSummaryAndRollupReads(self) -> None:
        self.service.recordProviderAttempt(self.tenantId, self._command(attemptNumber=1))
        self.service.recordProviderAttempt(
            self.tenantId, self._command(attemptNumber=2, capabilityCode="TRANSLATION")
        )
        summary = self.service.usageSummary(self.tenantId)
        self.assertEqual(summary.attempts, 2)
        self.assertEqual(summary.totalTokens, 300)
        self.assertEqual(
            {item.key for item in summary.byCapability}, {"SUMMARIZATION", "TRANSLATION"}
        )
        self.assertEqual(summary.latency.count, 2)
        rollup = self.service.requestRollup(self.tenantId, self.request.id)
        self.assertEqual(rollup.attempts, 2)
        firstAttemptId = self.service.listAttempts(self.tenantId)[0].attemptId
        descriptor = self.service.describeAttempt(self.tenantId, firstAttemptId)
        self.assertEqual(descriptor.totalTokens, 150)
