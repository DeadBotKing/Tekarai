"""Phase 13-O unit tests — audit ledger and governance, fully offline.

Covers the closed vocabularies, audit entry validation, the secret
scrubber and RESTRICTED rule, the hash chain (linking, determinism,
tamper and fork detection), the in-memory trail service (append-only,
filters, retention cutoff, tenant isolation), the governance policy
entity, and the fixed-order governance evaluation with its budget rule.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from apps.ai.domain.entities.auditRecords import (
    AIAuditEntry,
    AIGovernancePolicy,
    GovernanceRequest,
)
from apps.ai.domain.exceptions import (
    AIAuditRecordInvalid,
    AIAuditRecordNotFound,
    AIAuditTrailTampered,
    AIConfigurationError,
    AIGovernanceDenied,
    AIGovernancePolicyAlreadyRegistered,
    AIGovernancePolicyInvalid,
    AIGovernancePolicyNotFound,
)
from apps.ai.domain.services.auditTrail import (
    AuditEntryFilter,
    AuditTrailService,
    auditEntryHash,
    scrubDetail,
    verifyAuditChain,
)
from apps.ai.domain.services.governance import GovernanceService, raiseForDecision
from apps.ai.domain.valueObjects.aiTypes import Money
from apps.ai.domain.valueObjects.auditTypes import (
    ACTOR_TYPES,
    AUDIT_ACTIONS,
    AUDIT_OUTCOMES,
    GENESIS_HASH,
    ensureActorType,
    ensureAuditAction,
    ensureAuditOutcome,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


def makeRequest(tenantId: uuid.UUID, **overrides: object) -> GovernanceRequest:
    params: dict[str, object] = {
        "capabilityCode": "SUMMARIZATION",
        "providerCode": "OPENAI",
        "modelCode": "GPT-X",
    }
    params.update(overrides)
    return GovernanceRequest(tenantId=tenantId, **params)  # type: ignore[arg-type]


class AuditVocabularyTests(unittest.TestCase):
    def testAuditActionsCoverSection36PlusGovernanceNeeds(self) -> None:
        self.assertEqual(len(AUDIT_ACTIONS), 30)
        for action in (
            "REQUEST_CREATED",
            "REQUEST_STARTED",
            "REQUEST_COMPLETED",
            "REQUEST_FAILED",
            "RESPONSE_GENERATED",
            "MODEL_CHANGED",
            "PROMPT_VERSION_ACTIVATED",
            "USAGE_RECORDED",
            "FEEDBACK_RECEIVED",
            "GOVERNANCE_ALLOW",
            "GOVERNANCE_DENY",
            "GOVERNANCE_POLICY_DEFINED",
            "GOVERNANCE_POLICY_UPDATED",
            "QUOTA_DENIED",
            "RETENTION_PURGED",
            "JOB_ENQUEUED",
            "JOB_STARTED",
            "JOB_COMPLETED",
            "JOB_FAILED",
            # Phase 13-Q amendment: vector space and embedding lifecycle.
            "VECTOR_SPACE_DEFINED",
            "VECTOR_SPACE_DEACTIVATED",
            "EMBEDDING_CREATED",
            "EMBEDDING_DELETED",
            # Phase 13-R amendment: knowledge ingestion lifecycle.
            "KNOWLEDGE_INGESTED",
            "KNOWLEDGE_REINDEXED",
            "KNOWLEDGE_ARCHIVED",
            "KNOWLEDGE_PURGED",
            # Phase 13-S amendment: retrieval and RAG read path.
            "RETRIEVAL_EXECUTED",
            "RETRIEVAL_DENIED",
            "RAG_ANSWERED",
        ):
            self.assertIn(action, AUDIT_ACTIONS)

    def testActorTypesAndOutcomesAreClosed(self) -> None:
        self.assertEqual(tuple(ACTOR_TYPES), ("USER", "SYSTEM", "SERVICE", "API_KEY"))
        self.assertEqual(
            tuple(AUDIT_OUTCOMES),
            (
                "RECORDED",
                "ALLOWED",
                "DENIED",
                "SUCCEEDED",
                "FAILED",
                "DEFINED",
                "UPDATED",
                "PURGED",
            ),
        )

    def testUnknownVocabularyValuesRaise(self) -> None:
        with self.assertRaises(ValidationFailedError):
            ensureAuditAction("HACK_THE_PLANET")
        with self.assertRaises(ValidationFailedError):
            ensureActorType("GHOST")
        with self.assertRaises(ValidationFailedError):
            ensureAuditOutcome("MAYBE")


class AuditEntryTests(unittest.TestCase):
    def testEntryNormalizesCodesAndReferences(self) -> None:
        tenant = uuid.uuid4()
        actor = uuid.uuid4()
        entry = AIAuditEntry(
            tenantId=tenant,
            action="request_created",
            actorType="user",
            actorId=actor,
            capabilityCode="summarization",
            classification="restricted",
            contextSources=["projects:task:42"],
            detail={"note": "hi"},
        )
        self.assertEqual(entry.action, "REQUEST_CREATED")
        self.assertEqual(entry.actorType, "USER")
        self.assertEqual(entry.capabilityCode, "SUMMARIZATION")
        self.assertEqual(entry.classification, "RESTRICTED")
        self.assertEqual(entry.contextSources, ("projects:task:42",))
        self.assertEqual(entry.occurredAt.tzinfo, UTC)

    def testEntryRejectsBadShapes(self) -> None:
        tenant = uuid.uuid4()
        with self.assertRaises((ValidationFailedError, ValueError)):
            AIAuditEntry(tenantId=tenant, action="NOPE")
        with self.assertRaises((ValidationFailedError, ValueError)):
            AIAuditEntry(tenantId=tenant, action="REQUEST_CREATED", classification="TOP_SECRET")
        with self.assertRaises((ValidationFailedError, ValueError)):
            AIAuditEntry(tenantId=tenant, action="REQUEST_CREATED", detail=["not-a-mapping"])  # type: ignore[arg-type]
        with self.assertRaises((ValidationFailedError, ValueError)):
            AIAuditEntry(tenantId=tenant, action="REQUEST_CREATED", contextSources=[""])
        with self.assertRaises((ValidationFailedError, ValueError)):
            AIAuditEntry(tenantId="not-a-uuid", action="REQUEST_CREATED")  # type: ignore[arg-type]


class ScrubDetailTests(unittest.TestCase):
    def testSecretKeysAreRedactedRecursively(self) -> None:
        payload = {
            "api_key": "sk-live-123",
            "nested": {"password": "hunter2", "safe": "keep", "items": [{"token": "abc"}]},
            "Authorization": "Bearer xyz",
            "count": 3,
        }
        scrubbed = scrubDetail(payload)
        self.assertEqual(scrubbed["api_key"], "[REDACTED]")
        self.assertEqual(scrubbed["nested"]["password"], "[REDACTED]")
        self.assertEqual(scrubbed["nested"]["safe"], "keep")
        self.assertEqual(scrubbed["nested"]["items"], [{"token": "[REDACTED]"}])
        self.assertEqual(scrubbed["Authorization"], "[REDACTED]")
        self.assertEqual(scrubbed["count"], 3)

    def testRestrictedDetailIsReplacedWithoutOptIn(self) -> None:
        scrubbed = scrubDetail({"note": "secret plan"}, classification="RESTRICTED")
        self.assertEqual(
            scrubbed, {"redacted": True, "reason": "RESTRICTED detail requires an explicit opt-in."}
        )

    def testRestrictedDetailSurvivesWithExplicitOptIn(self) -> None:
        scrubbed = scrubDetail(
            {"note": "ok", "api_key": "x"},
            classification="RESTRICTED",
            allowRestrictedDetail=True,
        )
        self.assertEqual(scrubbed, {"note": "ok", "api_key": "[REDACTED]"})

    def testNonMappingPayloadsStayJsonSafe(self) -> None:
        self.assertEqual(scrubDetail(None), None)
        self.assertEqual(scrubDetail(7), 7)
        self.assertEqual(scrubDetail(("a", {"secret": "s"})), ["a", {"secret": "[REDACTED]"}])

    def testDeepNestingIsCapped(self) -> None:
        payload: object = {"level": "deep"}
        for _ in range(20):
            payload = {"nested": payload}
        scrubbed = scrubDetail(payload)
        cursor: object = scrubbed
        for _ in range(13):
            assert isinstance(cursor, dict)
            cursor = cursor["nested"]
        self.assertEqual(cursor, "[REDACTED]")


class AuditChainTests(unittest.TestCase):
    def testHashIsDeterministicForSameInputs(self) -> None:
        tenant = uuid.uuid4()
        first = AIAuditEntry(tenantId=tenant, action="REQUEST_CREATED", occurredAt=CLOCK)
        second = AIAuditEntry(tenantId=tenant, action="REQUEST_CREATED", occurredAt=CLOCK)
        self.assertEqual(
            auditEntryHash(tenant, GENESIS_HASH, first),
            auditEntryHash(tenant, GENESIS_HASH, second),
        )

    def testHashBindsTenantPrevHashAndPayload(self) -> None:
        tenant = uuid.uuid4()
        entry = AIAuditEntry(tenantId=tenant, action="REQUEST_CREATED", occurredAt=CLOCK)
        baseline = auditEntryHash(tenant, GENESIS_HASH, entry)
        self.assertNotEqual(auditEntryHash(uuid.uuid4(), GENESIS_HASH, entry), baseline)
        self.assertNotEqual(auditEntryHash(tenant, "OTHER", entry), baseline)
        entry.detail = {"changed": True}
        self.assertNotEqual(auditEntryHash(tenant, GENESIS_HASH, entry), baseline)

    def testEmptyChainVerifiesToZero(self) -> None:
        self.assertEqual(verifyAuditChain([]), 0)

    def testMutatedPayloadIsDetected(self) -> None:
        service = AuditTrailService(now=lambda: CLOCK)
        tenant = uuid.uuid4()
        entry = service.logEntry(tenant, "REQUEST_CREATED")
        entry.detail = {"tampered": True}
        with self.assertRaises(AIAuditTrailTampered):
            service.verifyChain(tenant)

    def testBrokenLinkIsDetected(self) -> None:
        tenant = uuid.uuid4()
        entry = AIAuditEntry(
            tenantId=tenant, action="REQUEST_CREATED", occurredAt=CLOCK, prevHash="BOGUS"
        )
        entry.hash = auditEntryHash(tenant, "BOGUS", entry)
        with self.assertRaises(AIAuditTrailTampered):
            verifyAuditChain([entry])

    def testForkIsDetected(self) -> None:
        service = AuditTrailService(now=lambda: CLOCK)
        tenant = uuid.uuid4()
        first = service.logEntry(tenant, "REQUEST_CREATED")
        service.logEntry(tenant, "REQUEST_STARTED")
        fork = AIAuditEntry(
            tenantId=tenant, action="REQUEST_COMPLETED", occurredAt=CLOCK, prevHash=first.hash
        )
        fork.hash = auditEntryHash(tenant, first.hash, fork)
        with self.assertRaises(AIAuditTrailTampered):
            verifyAuditChain([first, service.entriesForTenant(tenant)[1], fork])


class AuditTrailServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AuditTrailService(now=lambda: CLOCK)
        self.tenantId = uuid.uuid4()

    def testLogEntryChainsFromGenesis(self) -> None:
        first = self.service.logEntry(self.tenantId, "REQUEST_CREATED")
        second = self.service.logEntry(self.tenantId, "REQUEST_STARTED")
        self.assertEqual(first.prevHash, GENESIS_HASH)
        self.assertEqual(second.prevHash, first.hash)
        self.assertEqual(self.service.verifyChain(self.tenantId), 2)
        self.assertEqual(self.service.latestHash(self.tenantId), second.hash)

    def testLatestHashIsGenesisForEmptyTenant(self) -> None:
        self.assertEqual(self.service.latestHash(uuid.uuid4()), GENESIS_HASH)

    def testInvalidActionBecomesRecordInvalid(self) -> None:
        with self.assertRaises(AIAuditRecordInvalid):
            self.service.logEntry(self.tenantId, "NOPE")

    def testGetEntryIsTenantScoped(self) -> None:
        entry = self.service.logEntry(self.tenantId, "REQUEST_CREATED")
        with self.assertRaises(AIAuditRecordNotFound):
            self.service.getEntry(uuid.uuid4(), entry.id)
        with self.assertRaises(AIAuditRecordNotFound):
            self.service.getEntry(self.tenantId, uuid.uuid4())

    def testListEntriesFilters(self) -> None:
        actor = uuid.uuid4()
        requestId = uuid.uuid4()
        self.service.logEntry(
            self.tenantId, "REQUEST_CREATED", actorType="USER", actorId=actor, requestId=requestId
        )
        self.service.logEntry(
            self.tenantId, "USAGE_RECORDED", occurredAt=CLOCK + timedelta(hours=1)
        )
        self.service.logEntry(
            self.tenantId, "REQUEST_FAILED", outcome="FAILED", occurredAt=CLOCK + timedelta(hours=2)
        )
        self.assertEqual(len(self.service.listEntries(self.tenantId)), 3)
        self.assertEqual(
            len(self.service.listEntries(self.tenantId, AuditEntryFilter(action="USAGE_RECORDED"))),
            1,
        )
        self.assertEqual(
            len(self.service.listEntries(self.tenantId, AuditEntryFilter(actorId=actor))), 1
        )
        self.assertEqual(
            len(self.service.listEntries(self.tenantId, AuditEntryFilter(requestId=requestId))), 1
        )
        self.assertEqual(
            len(self.service.listEntries(self.tenantId, AuditEntryFilter(outcome="FAILED"))), 1
        )
        windowed = self.service.listEntries(
            self.tenantId,
            AuditEntryFilter(since=CLOCK + timedelta(hours=1), until=CLOCK + timedelta(hours=2)),
        )
        self.assertEqual([entry.action for entry in windowed], ["USAGE_RECORDED"])
        self.assertEqual(self.service.listEntries(uuid.uuid4()), ())

    def testDescribeEntryCarriesHashesNotContent(self) -> None:
        entry = self.service.logEntry(
            self.tenantId,
            "USAGE_RECORDED",
            correlationId="corr-o-1",
            contextSources=["projects:task:7"],
        )
        described = self.service.describeEntry(self.tenantId, entry.id)
        self.assertEqual(described.hash, entry.hash)
        self.assertEqual(described.prevHash, entry.prevHash)
        self.assertEqual(described.correlationId, "corr-o-1")
        self.assertEqual(described.contextSources, ("projects:task:7",))

    def testImportEntryIsIdempotent(self) -> None:
        entry = self.service.logEntry(self.tenantId, "REQUEST_CREATED")
        fresh = AuditTrailService(now=lambda: CLOCK)
        fresh.importEntry(entry)
        fresh.importEntry(entry)
        self.assertEqual(len(fresh.entriesForTenant(self.tenantId)), 1)

    def testRetentionCutoffArithmetic(self) -> None:
        cutoff = self.service.retentionCutoff(self.tenantId, 365, now=CLOCK)
        self.assertEqual(cutoff.cutoff, CLOCK - timedelta(days=365))
        self.assertEqual(cutoff.retentionDays, 365)
        for badDays in (0, -5, True, "365"):
            with self.assertRaises(AIAuditRecordInvalid, msg=str(badDays)):
                self.service.retentionCutoff(self.tenantId, badDays)  # type: ignore[arg-type]


class GovernancePolicyTests(unittest.TestCase):
    def testPolicyDefaultsToOpenWithUnlimitedBudget(self) -> None:
        policy = AIGovernancePolicy(tenantId=uuid.uuid4())
        self.assertEqual(policy.allowedProviders, ())
        self.assertEqual(policy.allowedModels, ())
        self.assertEqual(policy.disabledCapabilities, ())
        self.assertFalse(policy.allowRestrictedToExternal)
        self.assertEqual(policy.maxCostPerDay, Decimal("0"))
        self.assertTrue(policy.isActive)

    def testPolicyNormalizesCodeLists(self) -> None:
        policy = AIGovernancePolicy(
            tenantId=uuid.uuid4(),
            allowedProviders=["openai"],
            disabledCapabilities=("summarization",),
            maxCostPerDay="12.5",
        )
        self.assertEqual(policy.allowedProviders, ("OPENAI",))
        self.assertEqual(policy.disabledCapabilities, ("SUMMARIZATION",))
        self.assertEqual(policy.maxCostPerDay, Decimal("12.5"))

    def testPolicyRejectsBadShapes(self) -> None:
        tenant = uuid.uuid4()
        with self.assertRaises(ValueError):
            AIGovernancePolicy(tenantId=tenant, name="  ")
        with self.assertRaises(ValueError):
            AIGovernancePolicy(tenantId=tenant, allowedProviders="OPENAI")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            AIGovernancePolicy(tenantId=tenant, allowedProviders=["OPENAI", "openai"])
        with self.assertRaises(ValueError):
            AIGovernancePolicy(tenantId=tenant, maxCostPerDay=Decimal("-1"))
        with self.assertRaises(ValueError):
            AIGovernancePolicy(tenantId=tenant, currency="US")
        with self.assertRaises(ValueError):
            AIGovernancePolicy(tenantId=tenant, allowRestrictedToExternal="yes")  # type: ignore[arg-type]

    def testPolicyActivationFlipsState(self) -> None:
        policy = AIGovernancePolicy(tenantId=uuid.uuid4())
        policy.deactivate(now=CLOCK)
        self.assertFalse(policy.isActive)
        policy.activate(now=CLOCK)
        self.assertTrue(policy.isActive)


class GovernanceRequestTests(unittest.TestCase):
    def testRequestRejectsBadShapes(self) -> None:
        tenant = uuid.uuid4()
        with self.assertRaises((ValidationFailedError, ValueError)):
            GovernanceRequest(tenantId=tenant, classification="COSMIC")
        with self.assertRaises((ValidationFailedError, ValueError)):
            GovernanceRequest(tenantId=tenant, estimatedCost="expensive")  # type: ignore[arg-type]
        with self.assertRaises((ValidationFailedError, ValueError)):
            GovernanceRequest(tenantId=tenant, providerIsExternal="yes")  # type: ignore[arg-type]


class GovernanceEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = GovernanceService(now=lambda: CLOCK)
        self.tenantId = uuid.uuid4()

    def testOpenPolicyAllowsWithFivePassingReasons(self) -> None:
        policy = self.service.definePolicy(self.tenantId)
        evaluation = self.service.evaluate(makeRequest(self.tenantId), policy)
        self.assertTrue(evaluation.allowed)
        self.assertEqual(
            [reason.rule for reason in evaluation.reasons],
            ["CAPABILITY", "PROVIDER", "MODEL", "DATA_BOUNDARY", "COST_BUDGET"],
        )
        self.assertTrue(all(reason.allowed for reason in evaluation.reasons))
        decision = self.service.decide(makeRequest(self.tenantId), policy)
        self.assertTrue(decision.allowed)
        self.assertIsNone(raiseForDecision(decision))

    def testDisabledCapabilityDeniesFirst(self) -> None:
        policy = self.service.definePolicy(self.tenantId, disabledCapabilities=["SUMMARIZATION"])
        evaluation = self.service.evaluate(makeRequest(self.tenantId), policy)
        self.assertFalse(evaluation.allowed)
        denial = next(reason for reason in evaluation.reasons if not reason.allowed)
        self.assertEqual(denial.rule, "CAPABILITY")
        with self.assertRaises(AIGovernanceDenied) as raised:
            raiseForDecision(self.service.decide(makeRequest(self.tenantId), policy))
        self.assertEqual(raised.exception.httpStatus, 403)
        self.assertIn("SUMMARIZATION", str(raised.exception))

    def testProviderAllowlistDeniesUnknownProviders(self) -> None:
        policy = self.service.definePolicy(self.tenantId, allowedProviders=["OPENAI"])
        allowed = self.service.evaluate(makeRequest(self.tenantId), policy)
        self.assertTrue(allowed.allowed)
        denied = self.service.evaluate(makeRequest(self.tenantId, providerCode="ROGUE"), policy)
        self.assertFalse(denied.allowed)
        self.assertEqual(
            next(reason for reason in denied.reasons if not reason.allowed).rule, "PROVIDER"
        )

    def testModelAllowlistDeniesUnknownModels(self) -> None:
        policy = self.service.definePolicy(self.tenantId, allowedModels=["GPT-X"])
        denied = self.service.evaluate(makeRequest(self.tenantId, modelCode="OTHER"), policy)
        self.assertFalse(denied.allowed)
        self.assertEqual(
            next(reason for reason in denied.reasons if not reason.allowed).rule, "MODEL"
        )

    def testRestrictedToExternalNeedsExplicitOptIn(self) -> None:
        locked = self.service.definePolicy(self.tenantId)
        denied = self.service.evaluate(
            makeRequest(self.tenantId, classification="RESTRICTED", providerIsExternal=True),
            locked,
        )
        self.assertFalse(denied.allowed)
        opened = AIGovernancePolicy(tenantId=uuid.uuid4(), allowRestrictedToExternal=True)
        allowedExternal = self.service.evaluate(
            makeRequest(opened.tenantId, classification="RESTRICTED", providerIsExternal=True),
            opened,
        )
        self.assertTrue(allowedExternal.allowed)
        allowedInternal = self.service.evaluate(
            makeRequest(locked.tenantId, classification="RESTRICTED", providerIsExternal=False),
            locked,
        )
        self.assertTrue(allowedInternal.allowed)

    def testBudgetDeniesOverProjection(self) -> None:
        policy = self.service.definePolicy(self.tenantId, maxCostPerDay=Decimal("10"))
        denied = self.service.evaluate(
            makeRequest(
                self.tenantId,
                daySpend=Money(Decimal("9"), "USD"),
                estimatedCost=Money(Decimal("2"), "USD"),
            ),
            policy,
        )
        self.assertFalse(denied.allowed)
        self.assertEqual(
            next(reason for reason in denied.reasons if not reason.allowed).rule, "COST_BUDGET"
        )
        allowed = self.service.evaluate(
            makeRequest(
                self.tenantId,
                daySpend=Money(Decimal("7"), "USD"),
                estimatedCost=Money(Decimal("2"), "USD"),
            ),
            policy,
        )
        self.assertTrue(allowed.allowed)

    def testBudgetSkipsWithoutDaySpend(self) -> None:
        policy = self.service.definePolicy(self.tenantId, maxCostPerDay=Decimal("10"))
        evaluation = self.service.evaluate(
            makeRequest(self.tenantId, estimatedCost=Money(Decimal("999"), "USD")), policy
        )
        self.assertTrue(evaluation.allowed)
        budgetReason = next(reason for reason in evaluation.reasons if reason.rule == "COST_BUDGET")
        self.assertIn("skipped", budgetReason.message)

    def testBudgetCurrencyMismatchFailsClosed(self) -> None:
        policy = self.service.definePolicy(self.tenantId, maxCostPerDay=Decimal("10"))
        with self.assertRaises(AIConfigurationError):
            self.service.evaluate(
                makeRequest(
                    self.tenantId,
                    daySpend=Money(Decimal("1"), "EUR"),
                    estimatedCost=Money(Decimal("1"), "USD"),
                ),
                policy,
            )

    def testDecideBuildsAStableDecision(self) -> None:
        policy = self.service.definePolicy(self.tenantId)
        decision = self.service.decide(makeRequest(self.tenantId), policy)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.tenantId, self.tenantId)
        self.assertEqual(len(decision.reasons), 5)
        self.assertEqual(decision.evaluatedAt, CLOCK)

    def testEvaluationRejectsForeignPolicies(self) -> None:
        foreign = AIGovernancePolicy(tenantId=uuid.uuid4())
        with self.assertRaises(AIGovernancePolicyNotFound):
            self.service.evaluate(makeRequest(self.tenantId), foreign)

    def testEvaluationWithoutPolicyRaisesNotFound(self) -> None:
        with self.assertRaises(AIGovernancePolicyNotFound):
            self.service.evaluate(makeRequest(self.tenantId))


class GovernanceRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = GovernanceService(now=lambda: CLOCK)
        self.tenantId = uuid.uuid4()

    def testDefinePolicyIsUniquePerTenant(self) -> None:
        self.service.definePolicy(self.tenantId, name="first")
        with self.assertRaises(AIGovernancePolicyAlreadyRegistered):
            self.service.definePolicy(self.tenantId, name="second")

    def testDefinePolicyRejectsInvalidValues(self) -> None:
        with self.assertRaises(AIGovernancePolicyInvalid):
            self.service.definePolicy(self.tenantId, maxCostPerDay="fortune")

    def testGetPolicyIsTenantScoped(self) -> None:
        self.service.definePolicy(self.tenantId)
        with self.assertRaises(AIGovernancePolicyNotFound):
            self.service.getPolicy(uuid.uuid4())

    def testUpdatePolicyChangesOnlyGivenFields(self) -> None:
        policy = self.service.definePolicy(
            self.tenantId, allowedProviders=["OPENAI"], maxCostPerDay=Decimal("5")
        )
        updated = self.service.updatePolicy(
            self.tenantId, disabledCapabilities=["EMBEDDING"], now=CLOCK
        )
        self.assertEqual(updated.id, policy.id)
        self.assertEqual(updated.allowedProviders, ("OPENAI",))
        self.assertEqual(updated.disabledCapabilities, ("EMBEDDING",))
        self.assertEqual(updated.maxCostPerDay, Decimal("5"))
        self.assertEqual(updated.updatedAt, CLOCK)

    def testUpdatePolicyRejectsInvalidValues(self) -> None:
        self.service.definePolicy(self.tenantId)
        with self.assertRaises(AIGovernancePolicyInvalid):
            self.service.updatePolicy(self.tenantId, maxCostPerDay=Decimal("-2"))

    def testImportPolicyHydratesWithoutDuplicates(self) -> None:
        policy = AIGovernancePolicy(tenantId=self.tenantId, name="persisted")
        self.service.importPolicy(policy)
        self.service.importPolicy(policy)
        described = self.service.describePolicy(self.tenantId)
        self.assertEqual(described.policyId, policy.id)
        self.assertEqual(described.name, "persisted")
        other = AIGovernancePolicy(tenantId=self.tenantId, name="rival")
        with self.assertRaises(AIGovernancePolicyAlreadyRegistered):
            self.service.importPolicy(other)

    def testDescribePolicyExposesSafeReadModel(self) -> None:
        policy = self.service.definePolicy(self.tenantId, description="tenant rules")
        described = self.service.describePolicy(self.tenantId)
        self.assertEqual(described.tenantId, self.tenantId)
        self.assertEqual(described.policyId, policy.id)
        self.assertEqual(described.description, "tenant rules")
        self.assertTrue(described.isActive)


if __name__ == "__main__":
    unittest.main()
