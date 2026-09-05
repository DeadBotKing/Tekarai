"""Phase 13-O integration tests — Django stores satisfy the audit ports.

Runs the ``AuditRecordStore``, ``GovernancePolicyStore``, and
``RetentionPurger`` contracts against a real SQLite database:
row↔entity mapping (hashes, JSON, explicit domain time), tenant scoping,
chain-head authority across store instances, retention counts and
rebasing, governance persistence, purge coverage of the Phase 13-N
tables, audit survival without foreign keys, and ``runtime_checkable``
protocol conformance. No external network or provider credentials are
involved.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.ai.domain.auditPorts import AuditRecordStore, GovernancePolicyStore, RetentionPurger
from apps.ai.domain.entities.auditRecords import AIAuditEntry, AIGovernancePolicy
from apps.ai.domain.exceptions import (
    AIAuditRecordNotFound,
    AIGovernancePolicyAlreadyRegistered,
    AIGovernancePolicyNotFound,
)
from apps.ai.domain.services.auditTrail import AuditEntryFilter, verifyAuditChain
from apps.ai.domain.valueObjects.auditTypes import GENESIS_HASH
from apps.ai.infrastructure.models import (
    AIAuditTrailModel,
    AIGovernancePolicyModel,
    AIQuotaCounterModel,
    AIQuotaPolicyModel,
    AIUsageAttemptModel,
)
from apps.ai.infrastructure.repositories.auditRepositories import (
    DjangoAuditRecordStore,
    DjangoGovernancePolicyStore,
    DjangoRetentionPurger,
    auditToEntity,
    governancePolicyToEntity,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


def makeEntry(tenantId: uuid.UUID, **overrides: object) -> AIAuditEntry:
    params: dict[str, object] = {
        "action": "REQUEST_CREATED",
        "occurredAt": CLOCK,
        "actorType": "USER",
        "actorId": uuid.uuid4(),
        "capabilityCode": "SUMMARIZATION",
        "correlationId": "corr-o-9",
        "contextSources": ["projects:task:9"],
        "detail": {"note": "contract"},
    }
    params.update(overrides)
    return AIAuditEntry(tenantId=tenantId, **params)  # type: ignore[arg-type]


def makePolicy(tenantId: uuid.UUID, **overrides: object) -> AIGovernancePolicy:
    params: dict[str, object] = {"name": "tenant-rules"}
    params.update(overrides)
    return AIGovernancePolicy(tenantId=tenantId, **params)  # type: ignore[arg-type]


class ProtocolConformanceTests(TestCase):
    def testDjangoStoresSatisfyRuntimeCheckablePorts(self) -> None:
        self.assertIsInstance(DjangoAuditRecordStore(), AuditRecordStore)
        self.assertIsInstance(DjangoGovernancePolicyStore(), GovernancePolicyStore)
        self.assertIsInstance(DjangoRetentionPurger(), RetentionPurger)


class AuditStoreMappingTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.store = DjangoAuditRecordStore()

    def testAppendPersistsMappingHashesAndDomainTime(self) -> None:
        attemptId = uuid.uuid4()
        stored = self.store.appendEntry(makeEntry(self.tenantId, attemptId=attemptId))
        row = AIAuditTrailModel.objects.get(id=stored.id)
        self.assertEqual(row.tenantId, self.tenantId)
        self.assertEqual(row.action, "REQUEST_CREATED")
        self.assertEqual(row.occurredAt, CLOCK)
        self.assertEqual(row.attemptId, attemptId)
        self.assertEqual(row.contextSources, ["projects:task:9"])
        self.assertEqual(row.detail, {"note": "contract"})
        self.assertEqual(row.prevHash, GENESIS_HASH)
        self.assertEqual(row.hash, stored.hash)
        self.assertTrue(row.hash)
        roundTripped = auditToEntity(row)
        self.assertEqual(roundTripped.prevHash, GENESIS_HASH)
        self.assertEqual(roundTripped.hash, stored.hash)
        self.assertEqual(roundTripped.contextSources, ("projects:task:9",))

    def testAppendChainsAcrossStoreInstances(self) -> None:
        first = DjangoAuditRecordStore().appendEntry(makeEntry(self.tenantId))
        second = DjangoAuditRecordStore().appendEntry(
            makeEntry(self.tenantId, action="REQUEST_STARTED")
        )
        self.assertEqual(second.prevHash, first.hash)
        self.assertEqual(DjangoAuditRecordStore().latestHash(self.tenantId), second.hash)
        entries = DjangoAuditRecordStore().listEntries(self.tenantId)
        self.assertEqual(verifyAuditChain(entries), 2)

    def testLatestHashIsGenesisForEmptyTenant(self) -> None:
        self.assertEqual(self.store.latestHash(uuid.uuid4()), GENESIS_HASH)

    def testGetEntryIsTenantScoped(self) -> None:
        stored = self.store.appendEntry(makeEntry(self.tenantId))
        self.assertEqual(self.store.getEntry(self.tenantId, stored.id).id, stored.id)
        with self.assertRaises(AIAuditRecordNotFound):
            self.store.getEntry(uuid.uuid4(), stored.id)
        with self.assertRaises(AIAuditRecordNotFound):
            self.store.getEntry(self.tenantId, uuid.uuid4())

    def testListEntriesFilters(self) -> None:
        actor = uuid.uuid4()
        requestId = uuid.uuid4()
        self.store.appendEntry(makeEntry(self.tenantId, actorId=actor, requestId=requestId))
        self.store.appendEntry(
            makeEntry(
                self.tenantId,
                action="USAGE_RECORDED",
                outcome="SUCCEEDED",
                occurredAt=CLOCK + timedelta(hours=1),
            )
        )
        self.store.appendEntry(
            makeEntry(
                self.tenantId,
                action="REQUEST_FAILED",
                outcome="FAILED",
                occurredAt=CLOCK + timedelta(hours=2),
            )
        )
        self.assertEqual(len(self.store.listEntries(self.tenantId)), 3)
        self.assertEqual(
            len(self.store.listEntries(self.tenantId, AuditEntryFilter(action="USAGE_RECORDED"))),
            1,
        )
        self.assertEqual(
            len(self.store.listEntries(self.tenantId, AuditEntryFilter(actorId=actor))), 1
        )
        self.assertEqual(
            len(self.store.listEntries(self.tenantId, AuditEntryFilter(requestId=requestId))), 1
        )
        self.assertEqual(
            len(self.store.listEntries(self.tenantId, AuditEntryFilter(outcome="FAILED"))), 1
        )
        windowed = self.store.listEntries(
            self.tenantId,
            AuditEntryFilter(since=CLOCK + timedelta(hours=1), until=CLOCK + timedelta(hours=2)),
        )
        self.assertEqual([entry.action for entry in windowed], ["USAGE_RECORDED"])
        self.assertEqual(self.store.listEntries(uuid.uuid4()), ())

    def testDeleteBeforeCountsAndKeepsBoundary(self) -> None:
        old = self.store.appendEntry(
            makeEntry(self.tenantId, occurredAt=CLOCK - timedelta(days=400))
        )
        edge = self.store.appendEntry(
            makeEntry(
                self.tenantId, action="REQUEST_STARTED", occurredAt=CLOCK - timedelta(days=365)
            )
        )
        deleted = self.store.deleteBefore(self.tenantId, CLOCK - timedelta(days=365))
        self.assertEqual(deleted, 1)
        remaining = self.store.listEntries(self.tenantId)
        self.assertEqual([entry.id for entry in remaining], [edge.id])
        self.assertFalse(AIAuditTrailModel.objects.filter(id=old.id).exists())
        self.assertEqual(verifyAuditChain(remaining), 1)

    def testDeleteBeforeRebasesSurvivorsToGenesis(self) -> None:
        self.store.appendEntry(makeEntry(self.tenantId, occurredAt=CLOCK - timedelta(days=400)))
        survivor = self.store.appendEntry(
            makeEntry(self.tenantId, action="REQUEST_STARTED", occurredAt=CLOCK)
        )
        self.store.deleteBefore(self.tenantId, CLOCK - timedelta(days=365))
        rebased = self.store.getEntry(self.tenantId, survivor.id)
        self.assertEqual(rebased.prevHash, GENESIS_HASH)
        self.assertEqual(verifyAuditChain(self.store.listEntries(self.tenantId)), 1)

    def testAppendRejectsNonEntries(self) -> None:
        with self.assertRaises(ValueError):
            self.store.appendEntry("not-an-entry")  # type: ignore[arg-type]


class GovernanceStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.store = DjangoGovernancePolicyStore()

    def testSaveGetUpdateRoundTrip(self) -> None:
        policy = makePolicy(
            self.tenantId,
            allowedProviders=["OPENAI"],
            disabledCapabilities=["EMBEDDING"],
            maxCostPerDay=Decimal("25"),
        )
        stored = self.store.savePolicy(policy)
        self.assertEqual(stored.id, policy.id)
        fetched = self.store.getPolicy(self.tenantId)
        self.assertEqual(fetched.allowedProviders, ("OPENAI",))
        self.assertEqual(fetched.disabledCapabilities, ("EMBEDDING",))
        self.assertEqual(fetched.maxCostPerDay, Decimal("25"))
        self.assertTrue(fetched.isActive)
        row = AIQuotaPolicyModel.objects  # unrelated N table stays untouched
        self.assertEqual(row.count(), 0)
        updated = self.store.updatePolicy(
            makePolicy(
                self.tenantId,
                id=stored.id,
                allowedProviders=["OPENAI", "OLLAMA"],
                maxCostPerDay=Decimal("30"),
            )
        )
        refetched = self.store.getPolicy(self.tenantId)
        self.assertEqual(refetched.allowedProviders, ("OPENAI", "OLLAMA"))
        self.assertEqual(updated.maxCostPerDay, refetched.maxCostPerDay)

    def testSavePolicyConflictsPerTenant(self) -> None:
        self.store.savePolicy(makePolicy(self.tenantId))
        with self.assertRaises(AIGovernancePolicyAlreadyRegistered):
            self.store.savePolicy(makePolicy(self.tenantId))

    def testGetPolicyIsTenantScoped(self) -> None:
        self.store.savePolicy(makePolicy(self.tenantId))
        with self.assertRaises(AIGovernancePolicyNotFound):
            self.store.getPolicy(uuid.uuid4())

    def testUpdatePolicyRequiresExistingRow(self) -> None:
        with self.assertRaises(AIGovernancePolicyNotFound):
            self.store.updatePolicy(makePolicy(self.tenantId))

    def testSetPolicyActiveFlipsState(self) -> None:
        self.store.savePolicy(makePolicy(self.tenantId))
        deactivated = self.store.setPolicyActive(self.tenantId, False)
        self.assertFalse(deactivated.isActive)
        reactivated = self.store.setPolicyActive(self.tenantId, True)
        self.assertTrue(reactivated.isActive)

    def testGovernanceMapperRoundTrips(self) -> None:
        stored = self.store.savePolicy(makePolicy(self.tenantId, name="mapped"))
        row = AIAuditTrailModel.objects  # sanity: audit table untouched by policy writes
        self.assertEqual(row.count(), 0)
        entity = governancePolicyToEntity(AIGovernancePolicyModel.objects.get(id=stored.id))
        self.assertEqual(entity.name, "mapped")
        self.assertEqual(entity.tenantId, self.tenantId)

    def testSavePolicyRejectsNonPolicies(self) -> None:
        with self.assertRaises(ValueError):
            self.store.savePolicy("not-a-policy")  # type: ignore[arg-type]


class RetentionPurgerTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.store = DjangoAuditRecordStore()
        self.purger = DjangoRetentionPurger()

    def testPurgeAuditBeforeCountsOnlyExpiredTenantRows(self) -> None:
        self.store.appendEntry(makeEntry(self.tenantId, occurredAt=CLOCK - timedelta(days=400)))
        self.store.appendEntry(makeEntry(self.tenantId, occurredAt=CLOCK))
        self.store.appendEntry(
            makeEntry(self.otherTenantId, occurredAt=CLOCK - timedelta(days=400))
        )
        deleted = self.purger.purgeAuditBefore(self.tenantId, CLOCK - timedelta(days=365))
        self.assertEqual(deleted, 1)
        self.assertEqual(len(self.store.listEntries(self.tenantId)), 1)
        self.assertEqual(len(self.store.listEntries(self.otherTenantId)), 1)
        self.assertEqual(verifyAuditChain(self.store.listEntries(self.tenantId)), 1)

    def testPurgeAttemptsBeforeCountsExpiredRows(self) -> None:
        from apps.ai.infrastructure.models import (
            AICapabilityModel,
            AIModelModel,
            AIProviderModel,
            AIRequestModel,
        )

        provider = AIProviderModel.objects.create(
            tenantId=self.tenantId, code="OPENAI", name="OpenAI", providerType="CLOUD"
        )
        model = AIModelModel.objects.create(
            tenantId=self.tenantId, provider=provider, code="GPT-X", name="GPT X"
        )
        capability = AICapabilityModel.objects.create(
            tenantId=self.tenantId, code="SUMMARIZATION", name="Summarization"
        )
        request = AIRequestModel.objects.create(
            tenantId=self.tenantId,
            capability=capability,
            requestType="GENERATE",
            status="RUNNING",
            correlationId="corr-purge",
        )
        AIUsageAttemptModel.objects.create(
            tenantId=self.tenantId,
            request=request,
            provider=provider,
            model=model,
            providerCode="OPENAI",
            modelCode="GPT-X",
        )
        deleted = self.purger.purgeAttemptsBefore(self.tenantId, CLOCK + timedelta(days=365 * 10))
        self.assertEqual(deleted, 1)
        self.assertEqual(AIUsageAttemptModel.objects.filter(tenantId=self.tenantId).count(), 0)
        kept = self.purger.purgeAttemptsBefore(self.tenantId, CLOCK - timedelta(days=365))
        self.assertEqual(kept, 0)

    def testPurgeCountersBeforeCountsExpiredWindows(self) -> None:
        from apps.ai.infrastructure.models import AIQuotaPolicyModel

        policy = AIQuotaPolicyModel.objects.create(
            tenantId=self.tenantId,
            scope="TENANT",
            scopeReference="",
            dimension="REQUESTS",
            window="DAY",
            limitValue=Decimal("100"),
        )
        AIQuotaCounterModel.objects.create(
            tenantId=self.tenantId,
            policy=policy,
            windowStart=CLOCK - timedelta(days=200),
            consumedRequests=3,
        )
        AIQuotaCounterModel.objects.create(
            tenantId=self.tenantId,
            policy=policy,
            windowStart=CLOCK,
            consumedRequests=1,
        )
        deleted = self.purger.purgeCountersBefore(self.tenantId, CLOCK - timedelta(days=90))
        self.assertEqual(deleted, 1)
        remaining = AIQuotaCounterModel.objects.filter(tenantId=self.tenantId)
        self.assertEqual(remaining.count(), 1)
        self.assertEqual(remaining.first().consumedRequests, 1)

    def testAuditSurvivesReferencedRowPurge(self) -> None:
        from apps.ai.infrastructure.models import (
            AICapabilityModel,
            AIModelModel,
            AIProviderModel,
            AIRequestModel,
        )

        provider = AIProviderModel.objects.create(
            tenantId=self.tenantId, code="OPENAI", name="OpenAI", providerType="CLOUD"
        )
        model = AIModelModel.objects.create(
            tenantId=self.tenantId, provider=provider, code="GPT-X", name="GPT X"
        )
        capability = AICapabilityModel.objects.create(
            tenantId=self.tenantId, code="SUMMARIZATION", name="Summarization"
        )
        request = AIRequestModel.objects.create(
            tenantId=self.tenantId,
            capability=capability,
            requestType="GENERATE",
            status="RUNNING",
            correlationId="corr-survive",
        )
        attempt = AIUsageAttemptModel.objects.create(
            tenantId=self.tenantId,
            request=request,
            provider=provider,
            model=model,
            providerCode="OPENAI",
            modelCode="GPT-X",
        )
        audit = self.store.appendEntry(
            makeEntry(self.tenantId, action="USAGE_RECORDED", attemptId=attempt.id)
        )
        purged = self.purger.purgeAttemptsBefore(self.tenantId, CLOCK + timedelta(days=365 * 10))
        self.assertEqual(purged, 1)
        survived = self.store.getEntry(self.tenantId, audit.id)
        self.assertEqual(survived.attemptId, attempt.id)
