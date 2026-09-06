"""Phase 13-X integration tests — the tool stores over real SQLite.

Covers the ``aiToolDefinitions``, ``aiToolApprovals`` and
``aiToolInvocations`` persistence contract: version round trips and the
database-level uniqueness of one version per code, lifecycle updates, the
approval lookups that drive de-duplication (pending, usable, latest), the
per-request fingerprint history that powers loop detection, redaction
surviving the round trip, and the retention sweep that spares calls still
awaiting a human.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.ai.domain.entities.toolRecords import (
    AIToolApproval,
    AIToolDefinition,
    AIToolInvocation,
)
from apps.ai.domain.exceptions import AIToolInvalid
from apps.ai.domain.valueObjects.toolTypes import argumentFingerprint
from apps.ai.infrastructure.models import (
    AIToolApprovalModel,
    AIToolDefinitionModel,
    AIToolInvocationModel,
)
from apps.ai.infrastructure.repositories.toolRepositories import (
    DjangoToolApprovalStore,
    DjangoToolDefinitionStore,
    DjangoToolInvocationStore,
    approvalToEntity,
    definitionToEntity,
    invocationToEntity,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
FINGERPRINT = argumentFingerprint("SEARCH_PROJECT", 1, {"projectId": "P-1"})


class DjangoToolDefinitionStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.approver = uuid.uuid4()
        self.store = DjangoToolDefinitionStore()

    def definition(self, **overrides: object) -> AIToolDefinition:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "code": overrides.pop("code", "SEARCH_PROJECT"),
            "name": "Search project",
            "description": "Finds a project.",
            "version": overrides.pop("version", 1),
            "effect": "READ_ONLY",
            "riskLevel": "LOW",
            "inputSchema": {"type": "object", "required": ["projectId"]},
            "outputSchema": {"type": "object"},
            "requiredPermission": "AI_TOOL_EXECUTE",
            "metadata": {"owner": "platform"},
            "createdAt": CLOCK,
            "updatedAt": CLOCK,
        }
        params.update(overrides)
        return AIToolDefinition(**params)

    def testRoundTripPreservesSchemasAndPolicy(self) -> None:
        stored = self.store.saveDefinition(self.definition())
        loaded = self.store.getDefinition(self.tenantId, stored.id)
        assert loaded is not None
        self.assertEqual(loaded.qualifiedCode, "SEARCH_PROJECT@1")
        self.assertEqual(loaded.inputSchema["required"], ["projectId"])
        self.assertEqual(loaded.requiredPermission, "AI_TOOL_EXECUTE")
        self.assertEqual(loaded.metadata, {"owner": "platform"})
        self.assertEqual(loaded.status, "DRAFT")

    def testOneVersionPerCodeIsEnforcedByTheDatabase(self) -> None:
        self.store.saveDefinition(self.definition())
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.store.saveDefinition(self.definition())

    def testTwoVersionsCoexist(self) -> None:
        self.store.saveDefinition(self.definition(version=1))
        self.store.saveDefinition(self.definition(version=2))
        versions = self.store.listVersions(self.tenantId, "SEARCH_PROJECT")
        self.assertEqual([item.version for item in versions], [1, 2])

    def testTheSameCodeMayExistInTwoTenants(self) -> None:
        self.store.saveDefinition(self.definition())
        self.store.saveDefinition(self.definition(tenantId=self.otherTenantId))
        self.assertEqual(AIToolDefinitionModel.objects.count(), 2)

    def testUpdatePersistsTheLifecycle(self) -> None:
        stored = self.store.saveDefinition(self.definition())
        stored.submitForApproval(now=CLOCK)
        stored.approve(approverId=self.approver, now=CLOCK)
        updated = self.store.updateDefinition(stored)
        self.assertEqual(updated.status, "APPROVED")
        self.assertEqual(updated.approvedBy, self.approver)
        self.assertEqual(updated.approvedAt, CLOCK)

    def testUpdatingAnUnknownRowIsRefused(self) -> None:
        with self.assertRaises(AIToolInvalid):
            self.store.updateDefinition(self.definition(code="GHOST_TOOL"))

    def testLookupsAreNormalizedAndTenantScoped(self) -> None:
        self.store.saveDefinition(self.definition())
        self.assertIsNotNone(self.store.findVersion(self.tenantId, "search_project", 1))
        self.assertIsNone(self.store.findVersion(self.otherTenantId, "SEARCH_PROJECT", 1))
        self.assertIsNone(self.store.findVersion(self.tenantId, "SEARCH_PROJECT", 9))

    def testListingFiltersByStatusAndIsOrdered(self) -> None:
        self.store.saveDefinition(self.definition(code="ZULU_TOOL"))
        approved = self.store.saveDefinition(self.definition(code="ALPHA_TOOL"))
        approved.submitForApproval(now=CLOCK)
        approved.approve(approverId=self.approver, now=CLOCK)
        self.store.updateDefinition(approved)
        allRows = self.store.listDefinitions(self.tenantId)
        self.assertEqual([item.code for item in allRows], ["ALPHA_TOOL", "ZULU_TOOL"])
        self.assertEqual(len(self.store.listDefinitions(self.tenantId, statuses=("APPROVED",))), 1)

    def testMapperProducesAValidatedEntity(self) -> None:
        self.store.saveDefinition(self.definition())
        row = AIToolDefinitionModel.objects.get()
        entity = definitionToEntity(row)
        self.assertIsInstance(entity, AIToolDefinition)
        self.assertFalse(entity.mutatesState)


class DjangoToolApprovalStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.alice = uuid.uuid4()
        self.bob = uuid.uuid4()
        self.store = DjangoToolApprovalStore()

    def approval(self, **overrides: object) -> AIToolApproval:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "toolCode": "SEARCH_PROJECT",
            "toolVersion": 1,
            "argumentFingerprint": overrides.pop("argumentFingerprint", FINGERPRINT),
            "mode": "HUMAN_REQUIRED",
            "requiredApprovals": 1,
            "requestedBy": self.alice,
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIToolApproval(**params)

    def testRoundTripPreservesTheRequest(self) -> None:
        stored = self.store.saveApproval(self.approval())
        loaded = self.store.getApproval(self.tenantId, stored.id)
        assert loaded is not None
        self.assertEqual(loaded.toolCode, "SEARCH_PROJECT")
        self.assertEqual(loaded.argumentFingerprint, FINGERPRINT)
        self.assertTrue(loaded.isPending)
        self.assertEqual(loaded.requestedBy, self.alice)

    def testApproverListSurvivesTheRoundTrip(self) -> None:
        stored = self.store.saveApproval(self.approval(mode="DUAL_CONTROL", requiredApprovals=2))
        stored.grant(self.bob, now=CLOCK)
        updated = self.store.updateApproval(stored)
        self.assertEqual(updated.approvals, (self.bob,))
        self.assertEqual(updated.remainingApprovals, 1)

    def testGrantAndDenialArePersisted(self) -> None:
        granted = self.store.saveApproval(self.approval())
        granted.grant(self.bob, now=CLOCK)
        self.assertTrue(self.store.updateApproval(granted).isGranted)
        denied = self.store.saveApproval(
            self.approval(argumentFingerprint=argumentFingerprint("SEARCH_PROJECT", 1, {}))
        )
        denied.deny("no", approverId=self.bob, now=CLOCK)
        self.assertEqual(self.store.updateApproval(denied).decision, "DENIED")

    def testUpdatingAnUnknownRowIsRefused(self) -> None:
        with self.assertRaises(AIToolInvalid):
            self.store.updateApproval(self.approval())

    def testPendingLookupFindsOnlyPendingRequests(self) -> None:
        stored = self.store.saveApproval(self.approval())
        self.assertIsNotNone(self.store.findPending(self.tenantId, "SEARCH_PROJECT", FINGERPRINT))
        stored.grant(self.bob, now=CLOCK)
        self.store.updateApproval(stored)
        self.assertIsNone(self.store.findPending(self.tenantId, "SEARCH_PROJECT", FINGERPRINT))

    def testUsableLookupRespectsExpiry(self) -> None:
        stored = self.store.saveApproval(self.approval(expiresAt=CLOCK + timedelta(hours=1)))
        stored.grant(self.bob, now=CLOCK)
        self.store.updateApproval(stored)
        self.assertIsNotNone(
            self.store.findUsable(self.tenantId, "SEARCH_PROJECT", FINGERPRINT, now=CLOCK)
        )
        self.assertIsNone(
            self.store.findUsable(
                self.tenantId,
                "SEARCH_PROJECT",
                FINGERPRINT,
                now=CLOCK + timedelta(hours=2),
            )
        )

    def testLatestLookupSeesADenial(self) -> None:
        stored = self.store.saveApproval(self.approval())
        stored.deny("no", approverId=self.bob, now=CLOCK)
        self.store.updateApproval(stored)
        latest = self.store.findLatest(self.tenantId, "SEARCH_PROJECT", FINGERPRINT)
        assert latest is not None
        self.assertEqual(latest.decision, "DENIED")

    def testLookupsAreTenantScoped(self) -> None:
        self.store.saveApproval(self.approval())
        self.assertIsNone(self.store.findPending(self.otherTenantId, "SEARCH_PROJECT", FINGERPRINT))
        self.assertIsNone(self.store.findLatest(self.otherTenantId, "SEARCH_PROJECT", FINGERPRINT))

    def testListingFiltersByDecision(self) -> None:
        self.store.saveApproval(self.approval())
        denied = self.store.saveApproval(
            self.approval(argumentFingerprint=argumentFingerprint("SEARCH_PROJECT", 1, {}))
        )
        denied.deny("no", now=CLOCK)
        self.store.updateApproval(denied)
        self.assertEqual(len(self.store.listApprovals(self.tenantId)), 2)
        self.assertEqual(len(self.store.listApprovals(self.tenantId, decisions=("PENDING",))), 1)

    def testMapperProducesAValidatedEntity(self) -> None:
        self.store.saveApproval(self.approval())
        row = AIToolApprovalModel.objects.get()
        entity = approvalToEntity(row)
        self.assertIsInstance(entity, AIToolApproval)
        self.assertEqual(entity.mode, "HUMAN_REQUIRED")


class DjangoToolInvocationStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.requestId = uuid.uuid4()
        self.store = DjangoToolInvocationStore()

    def invocation(self, **overrides: object) -> AIToolInvocation:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "toolCode": "SEARCH_PROJECT",
            "toolVersion": 1,
            "arguments": {"projectId": "P-1", "apiKey": "sk-live"},
            "requestId": overrides.pop("requestId", self.requestId),
            "toolId": uuid.uuid4(),
            "actorId": uuid.uuid4(),
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIToolInvocation(**params)

    def testRedactionSurvivesTheRoundTrip(self) -> None:
        stored = self.store.saveInvocation(self.invocation())
        loaded = self.store.getInvocation(self.tenantId, stored.id)
        assert loaded is not None
        self.assertEqual(loaded.arguments["projectId"], "P-1")
        self.assertEqual(loaded.arguments["apiKey"], "[REDACTED]")
        row = AIToolInvocationModel.objects.get(id=stored.id)
        self.assertEqual(row.arguments["apiKey"], "[REDACTED]")

    def testLifecycleUpdatesArePersisted(self) -> None:
        stored = self.store.saveInvocation(self.invocation())
        stored.transitionTo("RUNNING", now=CLOCK)
        stored.succeed({"found": True}, now=CLOCK + timedelta(milliseconds=120))
        updated = self.store.updateInvocation(stored)
        self.assertEqual(updated.status, "SUCCEEDED")
        self.assertEqual(updated.result, {"found": True})
        self.assertEqual(updated.latencyMs, 120)

    def testUpdatingAnUnknownRowIsRefused(self) -> None:
        with self.assertRaises(AIToolInvalid):
            self.store.updateInvocation(self.invocation())

    def testFingerprintHistoryIsPerRequestAndOrdered(self) -> None:
        self.store.saveInvocation(self.invocation())
        self.store.saveInvocation(self.invocation(arguments={"projectId": "P-2"}))
        self.store.saveInvocation(self.invocation(requestId=uuid.uuid4()))
        history = self.store.fingerprintsForRequest(self.tenantId, self.requestId)
        self.assertEqual(len(history), 2)
        self.assertEqual(len(set(history)), 2)

    def testHistoryIsTenantScoped(self) -> None:
        self.store.saveInvocation(self.invocation())
        self.assertEqual(self.store.fingerprintsForRequest(self.otherTenantId, self.requestId), ())

    def testListingFiltersByToolStatusAndRequest(self) -> None:
        first = self.store.saveInvocation(self.invocation())
        first.deny(now=CLOCK)
        self.store.updateInvocation(first)
        self.store.saveInvocation(self.invocation(toolCode="DELETE_PROJECT", arguments={}))
        self.assertEqual(len(self.store.listInvocations(self.tenantId)), 2)
        self.assertEqual(
            len(self.store.listInvocations(self.tenantId, toolCode="DELETE_PROJECT")), 1
        )
        self.assertEqual(len(self.store.listInvocations(self.tenantId, statuses=("DENIED",))), 1)
        self.assertEqual(
            len(self.store.listInvocations(self.tenantId, requestId=self.requestId)), 2
        )

    def testRetentionSparesCallsAwaitingAHuman(self) -> None:
        pending = self.store.saveInvocation(self.invocation())
        settled = self.store.saveInvocation(self.invocation(arguments={"projectId": "P-9"}))
        settled.deny(now=CLOCK)
        self.store.updateInvocation(settled)
        AIToolInvocationModel.objects.filter(id__in=[pending.id, settled.id]).update(
            createdAt=CLOCK - timedelta(days=500)
        )
        removed = self.store.deleteInvocationsBefore(self.tenantId, CLOCK - timedelta(days=365))
        self.assertEqual(removed, 1)
        self.assertTrue(AIToolInvocationModel.objects.filter(id=pending.id).exists())

    def testRetentionCanRunAcrossAllTenants(self) -> None:
        for tenant in (self.tenantId, self.otherTenantId):
            item = self.store.saveInvocation(self.invocation(tenantId=tenant))
            item.deny(now=CLOCK)
            self.store.updateInvocation(item)
        AIToolInvocationModel.objects.all().update(createdAt=CLOCK - timedelta(days=500))
        self.assertEqual(self.store.deleteInvocationsBefore(None, CLOCK - timedelta(days=365)), 2)

    def testMapperProducesAValidatedEntity(self) -> None:
        stored = self.store.saveInvocation(self.invocation())
        row = AIToolInvocationModel.objects.get(id=stored.id)
        entity = invocationToEntity(row)
        self.assertIsInstance(entity, AIToolInvocation)
        self.assertEqual(entity.qualifiedCode, "SEARCH_PROJECT@1")

    def testUnknownInvocationReadsAsNone(self) -> None:
        self.assertIsNone(self.store.getInvocation(self.tenantId, uuid.uuid4()))
