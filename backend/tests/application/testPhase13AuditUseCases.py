"""Phase 13-O application tests — audit and governance over a real SQLite test DB.

Covers governance policy administration (with its own definition/update
audits), allow/deny evaluation (with decision audits carrying the rule
snapshot), secret scrubbing and the RESTRICTED rule at persistence time,
usage/quota ingestion, tenant-isolated reads, chain verification, audit
and usage retention purges (with self-reporting meta records), the
fail-closed configuration switches, and the in-process N→O event sink —
all orchestrated through ``AuditApplicationService`` with the Django
stores from Phase 13-O.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.ai.application.services.auditService import (
    AuditApplicationService,
    AuditSettings,
    AuditUsageEventSink,
    GovernancePolicyCommand,
)
from apps.ai.domain.entities.auditRecords import GovernanceRequest
from apps.ai.domain.entities.usageRecords import AIQuotaPolicy, AIUsageAttempt
from apps.ai.domain.exceptions import (
    AIAuditRecordInvalid,
    AIAuditTrailTampered,
    AIConfigurationError,
    AIGovernanceDenied,
    AIGovernancePolicyAlreadyRegistered,
    AIUsageAttemptNotFound,
)
from apps.ai.domain.services.auditTrail import AuditEntryFilter
from apps.ai.domain.services.quotaEnforcement import PolicyDenial
from apps.ai.domain.services.usageMetering import AIUsageRecorded
from apps.ai.domain.valueObjects.aiTypes import Money, TokenUsage
from apps.ai.infrastructure.models import (
    AIAuditTrailModel,
    AICapabilityModel,
    AIModelModel,
    AIProviderModel,
    AIRequestModel,
)
from apps.ai.infrastructure.repositories.auditRepositories import (
    DjangoAuditRecordStore,
    DjangoGovernancePolicyStore,
    DjangoRetentionPurger,
)
from apps.ai.infrastructure.repositories.usageRepositories import (
    DjangoQuotaCounterStore,
    DjangoQuotaPolicyStore,
    DjangoUsageAttemptStore,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


def auditSettings(**overrides: object) -> AuditSettings:
    params: dict[str, object] = {
        "enabled": True,
        "retentionDays": 365,
        "usageRetentionDays": 90,
        "includeRestrictedDetail": False,
        "governanceEnabled": True,
        "defaultMaxCostPerDay": Money(Decimal("0"), "USD"),
    }
    params.update(overrides)
    return AuditSettings(**params)  # type: ignore[arg-type]


class Phase13OAuditBase(TestCase):
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
            correlationId="corr-o-1",
        )
        self.service = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=auditSettings(),
            now=lambda: CLOCK,
        )

    def _governanceRequest(self, **overrides: object) -> GovernanceRequest:
        params: dict[str, object] = {
            "tenantId": self.tenantId,
            "capabilityCode": "SUMMARIZATION",
            "providerCode": "OPENAI",
            "modelCode": "GPT-X",
            "actorType": "USER",
            "actorId": self.userId,
            "correlationId": "corr-o-1",
        }
        params.update(overrides)
        return GovernanceRequest(**params)  # type: ignore[arg-type]

    def _usageEvent(self, **overrides: object) -> AIUsageRecorded:
        params: dict[str, object] = {
            "tenantId": self.tenantId,
            "attemptId": uuid.uuid4(),
            "requestId": self.request.id,
            "operationId": None,
            "providerCode": "OPENAI",
            "modelCode": "GPT-X",
            "capabilityCode": "SUMMARIZATION",
            "inputTokens": 100,
            "outputTokens": 50,
            "totalTokens": 150,
            "costAmount": Decimal("0.004"),
            "costCurrency": "USD",
            "totalTimeMs": 120,
            "outcome": "SUCCEEDED",
            "correlationId": "corr-o-1",
            "traceId": "trace-o-1",
            "recordedAt": CLOCK,
        }
        params.update(overrides)
        return AIUsageRecorded(**params)  # type: ignore[arg-type]


class GovernanceAdministrationTests(Phase13OAuditBase):
    def testDefinePolicyPersistsAndAuditsDefinition(self) -> None:
        policy = self.service.defineGovernancePolicy(
            self.tenantId,
            GovernancePolicyCommand(
                name="tenant-rules",
                allowedProviders=("OPENAI",),
                disabledCapabilities=("EMBEDDING",),
                maxCostPerDay=Decimal("25"),
            ),
            actorType="USER",
            actorId=self.userId,
        )
        self.assertEqual(policy.tenantId, self.tenantId)
        self.assertEqual(policy.allowedProviders, ("OPENAI",))
        audits = self.service.listAuditEntries(
            self.tenantId, AuditEntryFilter(action="GOVERNANCE_POLICY_DEFINED")
        )
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].outcome, "DEFINED")
        self.assertEqual(audits[0].policyId, policy.id)
        self.assertEqual(audits[0].actorId, self.userId)

    def testDefinePolicyDuplicateConflicts(self) -> None:
        self.service.defineGovernancePolicy(self.tenantId, GovernancePolicyCommand())
        with self.assertRaises(AIGovernancePolicyAlreadyRegistered):
            self.service.defineGovernancePolicy(self.tenantId, GovernancePolicyCommand())

    def testUpdatePolicyPersistsAndAuditsUpdate(self) -> None:
        policy = self.service.defineGovernancePolicy(self.tenantId, GovernancePolicyCommand())
        updated = self.service.updateGovernancePolicy(
            self.tenantId, disabledCapabilities=["EMBEDDING"]
        )
        self.assertEqual(updated.id, policy.id)
        self.assertEqual(updated.disabledCapabilities, ("EMBEDDING",))
        audits = self.service.listAuditEntries(
            self.tenantId, AuditEntryFilter(action="GOVERNANCE_POLICY_UPDATED")
        )
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].outcome, "UPDATED")

    def testDeactivatePolicyFlipsStateAndAudits(self) -> None:
        self.service.defineGovernancePolicy(self.tenantId, GovernancePolicyCommand())
        deactivated = self.service.deactivateGovernancePolicy(self.tenantId)
        self.assertFalse(deactivated.isActive)
        described = self.service.describeGovernancePolicy(self.tenantId)
        self.assertFalse(described.isActive)

    def testDescribePolicyFallsBackToPlatformDefault(self) -> None:
        described = self.service.describeGovernancePolicy(self.tenantId)
        self.assertEqual(described.name, "platform-default")
        self.assertEqual(described.maxCostPerDay, Decimal("0"))


class GovernanceEvaluationTests(Phase13OAuditBase):
    def testEvaluateAllowAppendsAllowAuditWithRuleSnapshot(self) -> None:
        self.service.defineGovernancePolicy(
            self.tenantId, GovernancePolicyCommand(allowedProviders=("OPENAI",))
        )
        grant = self.service.evaluateGovernance(self._governanceRequest())
        self.assertTrue(grant.decision.allowed)
        self.assertEqual(len(grant.decision.reasons), 5)
        audits = self.service.listAuditEntries(
            self.tenantId, AuditEntryFilter(action="GOVERNANCE_ALLOW")
        )
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].outcome, "ALLOWED")
        row = AIAuditTrailModel.objects.get(tenantId=self.tenantId, action="GOVERNANCE_ALLOW")
        self.assertEqual(row.outcome, "ALLOWED")
        self.assertEqual(row.detail["decision"], "ALLOW")
        self.assertEqual(row.detail["policySource"], "tenant")
        self.assertEqual(row.detail["rules"]["allowedProviders"], ["OPENAI"])
        self.assertEqual(len(row.detail["reasons"]), 5)
        self.assertEqual(grant.auditId, row.id)

    def testEvaluateDenyRaisesAndAppendsDenyAudit(self) -> None:
        self.service.defineGovernancePolicy(
            self.tenantId, GovernancePolicyCommand(disabledCapabilities=("SUMMARIZATION",))
        )
        with self.assertRaises(AIGovernanceDenied):
            self.service.evaluateGovernance(self._governanceRequest())
        audits = self.service.listAuditEntries(
            self.tenantId, AuditEntryFilter(action="GOVERNANCE_DENY")
        )
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].outcome, "DENIED")
        row = AIAuditTrailModel.objects.get(tenantId=self.tenantId, action="GOVERNANCE_DENY")
        self.assertEqual(row.detail["decision"], "DENY")
        self.assertIn("SUMMARIZATION", row.detail["reasons"][0]["message"])

    def testEvaluateUsesPlatformDefaultBudgetWithoutTenantPolicy(self) -> None:
        budgeted = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=auditSettings(defaultMaxCostPerDay=Money(Decimal("10"), "USD")),
            now=lambda: CLOCK,
        )
        with self.assertRaises(AIGovernanceDenied):
            budgeted.evaluateGovernance(
                self._governanceRequest(
                    daySpend=Money(Decimal("9"), "USD"),
                    estimatedCost=Money(Decimal("2"), "USD"),
                )
            )
        row = AIAuditTrailModel.objects.get(tenantId=self.tenantId, action="GOVERNANCE_DENY")
        self.assertEqual(row.detail["policySource"], "platform-default")


class AuditWriteTests(Phase13OAuditBase):
    def testLogAuditScrubsSecretsBeforePersist(self) -> None:
        entry = self.service.logAudit(
            self.tenantId,
            "REQUEST_CREATED",
            actorType="USER",
            actorId=self.userId,
            requestId=self.request.id,
            capabilityCode="SUMMARIZATION",
            contextSources=["projects:task:7"],
            detail={"api_key": "sk-live", "prompt": "hello", "nested": {"token": "t"}},
        )
        row = AIAuditTrailModel.objects.get(id=entry.id)
        self.assertEqual(row.detail["api_key"], "[REDACTED]")
        self.assertEqual(row.detail["prompt"], "hello")
        self.assertEqual(row.detail["nested"], {"token": "[REDACTED]"})
        self.assertEqual(row.contextSources, ["projects:task:7"])

    def testLogAuditRedactsRestrictedWithoutOptIn(self) -> None:
        entry = self.service.logAudit(
            self.tenantId,
            "REQUEST_CREATED",
            classification="RESTRICTED",
            detail={"note": "secret plan"},
        )
        row = AIAuditTrailModel.objects.get(id=entry.id)
        self.assertTrue(row.detail["redacted"])
        self.assertEqual(row.classification, "RESTRICTED")

    def testLogAuditRejectsUnknownAction(self) -> None:
        with self.assertRaises(AIAuditRecordInvalid):
            self.service.logAudit(self.tenantId, "HACK_THE_PLANET")

    def testIngestUsageRecordedCarriesCountsWithoutContent(self) -> None:
        entry = self.service.ingestUsageRecorded(self._usageEvent())
        row = AIAuditTrailModel.objects.get(id=entry.id)
        self.assertEqual(row.action, "USAGE_RECORDED")
        self.assertEqual(row.detail["totalTokens"], 150)
        self.assertEqual(row.detail["costAmount"], "0.004")
        self.assertNotIn("prompt", row.detail)
        self.assertNotIn("content", row.detail)

    def testLogQuotaDenialRecordsDenial(self) -> None:
        denial = PolicyDenial(
            policyId=uuid.uuid4(),
            scope="TENANT",
            dimension="REQUESTS",
            window="DAY",
            windowStart=CLOCK,
            limitValue=Decimal("10"),
            consumed=10,
        )
        entry = self.service.logQuotaDenial(
            self.tenantId, denial, requestId=self.request.id, correlationId="corr-o-1"
        )
        row = AIAuditTrailModel.objects.get(id=entry.id)
        self.assertEqual(row.action, "QUOTA_DENIED")
        self.assertEqual(row.outcome, "DENIED")
        self.assertEqual(row.detail["dimension"], "REQUESTS")
        self.assertEqual(row.detail["consumed"], "10")

    def testAuditUsageEventSinkPublishesToLedger(self) -> None:
        sink = AuditUsageEventSink(self.service)
        sink.publish(self._usageEvent())
        self.assertEqual(
            AIAuditTrailModel.objects.filter(
                tenantId=self.tenantId, action="USAGE_RECORDED"
            ).count(),
            1,
        )
        with self.assertRaises(ValueError):
            sink.publish("not-an-event")  # type: ignore[arg-type]


class AuditReadTests(Phase13OAuditBase):
    def testListEntriesFiltersAndIsolatesTenants(self) -> None:
        self.service.logAudit(self.tenantId, "REQUEST_CREATED", requestId=self.request.id)
        self.service.logAudit(self.tenantId, "USAGE_RECORDED", outcome="SUCCEEDED")
        self.service.logAudit(self.otherTenantId, "REQUEST_CREATED")
        self.assertEqual(len(self.service.listAuditEntries(self.tenantId)), 2)
        self.assertEqual(len(self.service.listAuditEntries(self.otherTenantId)), 1)
        filtered = self.service.listAuditEntries(
            self.tenantId, AuditEntryFilter(action="USAGE_RECORDED")
        )
        self.assertEqual(len(filtered), 1)
        byRequest = self.service.listAuditEntries(
            self.tenantId, AuditEntryFilter(requestId=self.request.id)
        )
        self.assertEqual(len(byRequest), 1)
        windowed = self.service.listAuditEntries(
            self.tenantId,
            AuditEntryFilter(since=CLOCK + timedelta(seconds=1)),
        )
        self.assertEqual(windowed, ())

    def testVerifyChainDetectsTamperedRow(self) -> None:
        entry = self.service.logAudit(self.tenantId, "REQUEST_CREATED")
        self.service.logAudit(self.tenantId, "REQUEST_STARTED")
        self.assertEqual(self.service.verifyTenantChain(self.tenantId), 2)
        AIAuditTrailModel.objects.filter(id=entry.id).update(detail={"tampered": True})
        with self.assertRaises(AIAuditTrailTampered):
            self.service.verifyTenantChain(self.tenantId)


class RetentionTests(Phase13OAuditBase):
    def testPurgeAuditRetentionKeepsMetaRecordAndVerifies(self) -> None:
        old = self.service.logAudit(
            self.tenantId, "REQUEST_CREATED", occurredAt=CLOCK - timedelta(days=400)
        )
        recent = self.service.logAudit(self.tenantId, "REQUEST_STARTED")
        purged = self.service.purgeAuditRetention(self.tenantId, retentionDays=365)
        self.assertEqual(purged.auditDeleted, 1)
        self.assertEqual(purged.attemptsDeleted, 0)
        remaining = self.service.listAuditEntries(self.tenantId)
        remainingIds = {entry.entryId for entry in remaining}
        self.assertNotIn(old.id, remainingIds)
        self.assertIn(recent.id, remainingIds)
        self.assertIn(purged.auditId, remainingIds)
        meta = AIAuditTrailModel.objects.get(id=purged.auditId)
        self.assertEqual(meta.action, "RETENTION_PURGED")
        self.assertEqual(meta.detail["deleted"], 1)
        self.assertEqual(meta.detail["retentionDays"], 365)
        self.assertEqual(self.service.verifyTenantChain(self.tenantId), 2)

    def testPurgeUsageRetentionRemovesOldRowsButKeepsAudit(self) -> None:
        attemptStore = DjangoUsageAttemptStore()
        attempt = attemptStore.saveAttempt(
            AIUsageAttempt(
                tenantId=self.tenantId,
                requestId=self.request.id,
                providerId=self.provider.id,
                modelId=self.model.id,
                providerCode="OPENAI",
                modelCode="GPT-X",
                usage=TokenUsage(inputTokens=10, outputTokens=5),
                idempotencyKey="retention-key",
            )
        )
        policyStore = DjangoQuotaPolicyStore()
        policy = policyStore.savePolicy(
            AIQuotaPolicy(
                tenantId=self.tenantId,
                scope="TENANT",
                scopeReference="",
                dimension="REQUESTS",
                window="DAY",
                limitValue=Decimal("100"),
            )
        )
        DjangoQuotaCounterStore().addConsumption(
            self.tenantId, policy.id, CLOCK - timedelta(days=200), requests=1, currency="USD"
        )
        audit = self.service.logAudit(
            self.tenantId, "USAGE_RECORDED", attemptId=attempt.id, requestId=self.request.id
        )
        future = CLOCK + timedelta(days=200)
        purged = self.service.purgeUsageRetention(self.tenantId, now=future)
        self.assertEqual(purged.attemptsDeleted, 1)
        self.assertEqual(purged.countersDeleted, 1)
        with self.assertRaises(AIUsageAttemptNotFound):
            attemptStore.getAttempt(self.tenantId, attempt.id)
        # The audit ledger survives: references are plain UUIDs with no FK cascade.
        survived = self.service.listAuditEntries(
            self.tenantId, AuditEntryFilter(action="USAGE_RECORDED")
        )
        self.assertEqual([entry.entryId for entry in survived], [audit.id])
        meta = AIAuditTrailModel.objects.get(id=purged.auditId)
        self.assertEqual(meta.detail["attemptsDeleted"], 1)
        self.assertEqual(meta.detail["countersDeleted"], 1)


class ConfigurationGateTests(Phase13OAuditBase):
    def testDisabledAuditFailsClosed(self) -> None:
        service = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=auditSettings(enabled=False),
            now=lambda: CLOCK,
        )
        with self.assertRaises(AIConfigurationError):
            service.logAudit(self.tenantId, "REQUEST_CREATED")
        with self.assertRaises(AIConfigurationError):
            service.evaluateGovernance(self._governanceRequest())

    def testDisabledGovernanceFailsClosed(self) -> None:
        service = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=auditSettings(governanceEnabled=False),
            now=lambda: CLOCK,
        )
        with self.assertRaises(AIConfigurationError):
            service.defineGovernancePolicy(self.tenantId, GovernancePolicyCommand())
        with self.assertRaises(AIConfigurationError):
            service.evaluateGovernance(self._governanceRequest())
