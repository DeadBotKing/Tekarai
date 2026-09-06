"""Phase 13-Y integration tests — the agent stores over real SQLite.

Covers the ``aiAgentDefinitions``, ``aiAgentApprovals``, ``aiAgentRuns``
and ``aiAgentSteps`` persistence contract: version round trips and the
database-level uniqueness of one version per code, lifecycle updates,
the approval lookups that drive de-duplication and the anti-spam rule
(pending, usable, latest — including a findable denial), run and step
round trips, redaction surviving the round trip, the step ordering that
is the run's trace, and the retention sweep that spares runs still
awaiting a human. Also covers the capability resolver over the
Phase 13-F table.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.ai.domain.entities.agentRecords import (
    AIAgentApproval,
    AIAgentDefinition,
    AIAgentRun,
    AIAgentStep,
)
from apps.ai.domain.exceptions import AIAgentInvalid
from apps.ai.domain.valueObjects.agentTypes import inputFingerprint
from apps.ai.infrastructure.agentAdapters import DjangoAgentCapabilityResolver
from apps.ai.infrastructure.models import (
    AIAgentApprovalModel,
    AIAgentDefinitionModel,
    AIAgentRunModel,
    AIAgentStepModel,
    AICapabilityModel,
)
from apps.ai.infrastructure.repositories.agentRepositories import (
    DjangoAgentApprovalStore,
    DjangoAgentDefinitionStore,
    DjangoAgentExecutionStore,
    approvalToEntity,
    definitionToEntity,
    runToEntity,
    stepToEntity,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 6, 9, 0, 0, tzinfo=UTC)
FINGERPRINT = inputFingerprint("ANALYST", 1, {"task": "a"})


class DjangoAgentDefinitionStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.approver = uuid.uuid4()
        self.store = DjangoAgentDefinitionStore()

    def definition(self, **overrides: object) -> AIAgentDefinition:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "code": overrides.pop("code", "ANALYST"),
            "name": "Project analyst",
            "description": "Analyzes a project.",
            "instructions": "Analyze the project and report risks.",
            "version": overrides.pop("version", 1),
            "accessLevel": "READ_ONLY",
            "riskLevel": "LOW",
            "capabilityCodes": ("SUMMARIZATION",),
            "toolCodes": ("SEARCH_PROJECT",),
            "outputSchema": {"type": "object", "required": ["summary"]},
            "contextPolicy": {"maxContextTokens": 8000},
            "executionPolicy": {"maxSteps": 4},
            "metadata": {"owner": "platform"},
            "createdAt": CLOCK,
            "updatedAt": CLOCK,
        }
        params.update(overrides)
        return AIAgentDefinition(**params)

    def testRoundTripPreservesPoliciesAndAccessLevel(self) -> None:
        stored = self.store.saveDefinition(self.definition())
        loaded = self.store.getDefinition(self.tenantId, stored.id)
        assert loaded is not None
        self.assertEqual(loaded.qualifiedCode, "ANALYST@1")
        self.assertEqual(loaded.accessLevel, "READ_ONLY")
        self.assertEqual(loaded.outputSchema["required"], ["summary"])
        self.assertEqual(loaded.contextPolicy, {"maxContextTokens": 8000})
        self.assertEqual(loaded.executionPolicy, {"maxSteps": 4})
        self.assertEqual(loaded.capabilityCodes, ("SUMMARIZATION",))
        self.assertEqual(loaded.toolCodes, ("SEARCH_PROJECT",))
        self.assertEqual(loaded.metadata, {"owner": "platform"})
        self.assertEqual(loaded.status, "DRAFT")

    def testOneVersionPerCodeIsEnforcedByTheDatabase(self) -> None:
        self.store.saveDefinition(self.definition())
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.store.saveDefinition(self.definition())

    def testTwoVersionsCoexist(self) -> None:
        self.store.saveDefinition(self.definition(version=1))
        self.store.saveDefinition(self.definition(version=2, accessLevel="MUTATING"))
        versions = self.store.listVersions(self.tenantId, "ANALYST")
        self.assertEqual([item.version for item in versions], [1, 2])
        self.assertEqual(versions[1].accessLevel, "MUTATING")

    def testTheSameCodeMayExistInTwoTenants(self) -> None:
        self.store.saveDefinition(self.definition())
        self.store.saveDefinition(self.definition(tenantId=self.otherTenantId))
        self.assertEqual(AIAgentDefinitionModel.objects.count(), 2)
        self.assertEqual(len(self.store.listVersions(self.tenantId, "ANALYST")), 1)

    def testUpdatePersistsTheLifecycle(self) -> None:
        stored = self.store.saveDefinition(self.definition())
        stored.submitForApproval(now=CLOCK)
        stored.approve(approverId=self.approver, now=CLOCK)
        updated = self.store.updateDefinition(stored)
        reloaded = self.store.getDefinition(self.tenantId, updated.id)
        assert reloaded is not None
        self.assertEqual(reloaded.status, "APPROVED")
        self.assertEqual(reloaded.approvedBy, self.approver)
        self.assertEqual(reloaded.approvedAt, CLOCK)

    def testInstructionsAreVersionedPerRow(self) -> None:
        self.store.saveDefinition(self.definition(version=1))
        self.store.saveDefinition(self.definition(version=2, instructions="Tighter scope."))
        first = self.store.findVersion(self.tenantId, "ANALYST", 1)
        assert first is not None
        self.assertEqual(first.instructions, "Analyze the project and report risks.")

    def testStatusFilteringAndTenantIsolation(self) -> None:
        self.store.saveDefinition(self.definition())
        approved = self.definition(version=2)
        approved.submitForApproval(now=CLOCK)
        approved.approve(approverId=self.approver, now=CLOCK)
        self.store.saveDefinition(approved)
        self.store.saveDefinition(self.definition(tenantId=self.otherTenantId, code="SCOUT"))
        approvedOnly = self.store.listDefinitions(self.tenantId, statuses=("APPROVED",))
        self.assertEqual([item.version for item in approvedOnly], [2])
        otherRows = self.store.listDefinitions(self.otherTenantId)
        self.assertEqual([item.code for item in otherRows], ["SCOUT"])

    def testUnknownTenantAndCodeReturnNone(self) -> None:
        self.store.saveDefinition(self.definition())
        self.assertIsNone(self.store.findVersion(self.otherTenantId, "ANALYST", 1))
        self.assertIsNone(self.store.findVersion(self.tenantId, "SCOUT", 1))
        self.assertIsNone(self.store.getDefinition(self.tenantId, uuid.uuid4()))


class DjangoAgentApprovalStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.requester = uuid.uuid4()
        self.approver = uuid.uuid4()
        self.store = DjangoAgentApprovalStore()

    def approval(self, **overrides: object) -> AIAgentApproval:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "agentCode": "ANALYST",
            "agentVersion": 1,
            "inputFingerprint": overrides.pop("inputFingerprint", FINGERPRINT),
            "mode": "HUMAN_REQUIRED",
            "requiredApprovals": 1,
            "requestedBy": self.requester,
            "expiresAt": CLOCK + timedelta(hours=1),
            "createdAt": overrides.pop("createdAt", CLOCK),
        }
        params.update(overrides)
        return AIAgentApproval(**params)

    def testRoundTripPreservesTheApprovalState(self) -> None:
        stored = self.store.saveApproval(self.approval())
        loaded = self.store.getApproval(self.tenantId, stored.id)
        assert loaded is not None
        self.assertEqual(loaded.decision, "PENDING")
        self.assertEqual(loaded.mode, "HUMAN_REQUIRED")
        self.assertEqual(loaded.inputFingerprint, FINGERPRINT)
        self.assertEqual(loaded.requestedBy, self.requester)

    def testFindPendingReturnsOnlyPending(self) -> None:
        pending = self.store.saveApproval(self.approval())
        granted = self.approval()
        granted.grant(self.approver, now=CLOCK)
        self.store.saveApproval(granted)
        found = self.store.findPending(self.tenantId, "ANALYST", FINGERPRINT)
        assert found is not None
        self.assertEqual(found.id, pending.id)
        self.assertIsNone(self.store.findPending(self.tenantId, "ANALYST", "f" * 64))

    def testFindUsableRespectsGrantAndExpiry(self) -> None:
        granted = self.approval()
        granted.grant(self.approver, now=CLOCK)
        self.store.saveApproval(granted)
        usable = self.store.findUsable(self.tenantId, "ANALYST", FINGERPRINT, now=CLOCK)
        assert usable is not None
        self.assertEqual(usable.id, granted.id)
        # Expired in the future? No — after the expiry it is not usable.
        self.assertIsNone(
            self.store.findUsable(
                self.tenantId, "ANALYST", FINGERPRINT, now=CLOCK + timedelta(hours=2)
            )
        )

    def testFindLatestReturnsADenialSoItSticks(self) -> None:
        denied = self.approval()
        denied.deny("No", approverId=self.approver, now=CLOCK)
        self.store.saveApproval(denied)
        latest = self.store.findLatest(self.tenantId, "ANALYST", FINGERPRINT)
        assert latest is not None
        self.assertEqual(latest.decision, "DENIED")
        self.assertEqual(latest.reason, "No")

    def testApprovalIsBoundToTenantCodeAndFingerprint(self) -> None:
        self.store.saveApproval(self.approval())
        self.assertIsNone(self.store.findPending(self.otherTenantId, "ANALYST", FINGERPRINT))
        self.assertIsNone(self.store.findPending(self.tenantId, "SCOUT", FINGERPRINT))

    def testDecidedApprovalsLeaveThePendingLookup(self) -> None:
        stored = self.store.saveApproval(self.approval())
        stored.grant(self.approver, now=CLOCK)
        self.store.updateApproval(stored)
        self.assertIsNone(self.store.findPending(self.tenantId, "ANALYST", FINGERPRINT))
        self.assertIsNotNone(
            self.store.findUsable(self.tenantId, "ANALYST", FINGERPRINT, now=CLOCK)
        )

    def testUpdateRequiresAnExistingRow(self) -> None:
        stored = self.store.saveApproval(self.approval())
        stored.tenantId = self.otherTenantId  # wrong tenant
        with self.assertRaises(AIAgentInvalid):
            self.store.updateApproval(stored)


class DjangoAgentExecutionStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.actor = uuid.uuid4()
        self.store = DjangoAgentExecutionStore()
        self.definition = AIAgentDefinition(
            tenantId=self.tenantId,
            code="ANALYST",
            name="Project analyst",
            instructions="Analyze the project.",
            createdAt=CLOCK,
            updatedAt=CLOCK,
        )

    def makeRun(self, **overrides: object) -> AIAgentRun:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "agentId": self.definition.id,
            "agentCode": "ANALYST",
            "agentVersion": 1,
            "requestedBy": self.actor,
            "input": {"task": "a", "apiKey": "raw-secret"},
            "createdAt": overrides.pop("createdAt", CLOCK),
        }
        params.update(overrides)
        return AIAgentRun(**params)

    def step(self, run: AIAgentRun, ordinal: int = 1, **overrides: object) -> AIAgentStep:
        params: dict = {
            "tenantId": self.tenantId,
            "runId": run.id,
            "ordinal": ordinal,
            "kind": "TOOL",
            "status": "SUCCEEDED",
            "toolCode": "SEARCH_PROJECT",
            "toolVersion": 1,
            "arguments": {"projectId": "P-1"},
            "result": {"found": True},
        }
        params.update(overrides)
        return AIAgentStep(**params)

    def testRunRoundTripRedactsAndPreservesCounters(self) -> None:
        stored = self.store.saveRun(self.makeRun())
        stored.transitionTo("RUNNING", now=CLOCK)
        stored.complete("answer", {"summary": "ok"}, now=CLOCK + timedelta(milliseconds=5))
        stored.modelCallCount = 1
        stored.toolCallCount = 1
        stored.inputTokens = 10
        stored.outputTokens = 3
        self.store.updateRun(stored)
        loaded = self.store.getRun(self.tenantId, stored.id)
        assert loaded is not None
        self.assertEqual(loaded.status, "COMPLETED")
        self.assertEqual(loaded.input["apiKey"], "[REDACTED]")
        self.assertEqual(loaded.input["task"], "a")
        self.assertEqual(loaded.answer, "answer")
        self.assertEqual(loaded.output, {"summary": "ok"})
        self.assertEqual(loaded.modelCallCount, 1)
        self.assertEqual(loaded.toolCallCount, 1)
        self.assertEqual(loaded.inputTokens, 10)
        self.assertEqual(loaded.latencyMs, 5)
        self.assertEqual(len(loaded.inputFingerprint), 64)

    def testRunIsTenantScoped(self) -> None:
        stored = self.store.saveRun(self.makeRun())
        self.assertIsNone(self.store.getRun(self.otherTenantId, stored.id))
        self.assertEqual(self.store.listRuns(self.otherTenantId), ())

    def testListRunsFiltersByCodeAndStatus(self) -> None:
        settled = self.store.saveRun(self.makeRun())
        settled.deny("AI_AGENT_DENIED", now=CLOCK)
        self.store.updateRun(settled)
        pending = self.store.saveRun(self.makeRun(createdAt=CLOCK + timedelta(seconds=1)))
        scout = self.store.saveRun(
            self.makeRun(agentCode="SCOUT", createdAt=CLOCK + timedelta(seconds=2))
        )
        scout.deny("AI_AGENT_DENIED", now=CLOCK)
        self.store.updateRun(scout)
        byStatus = self.store.listRuns(self.tenantId, statuses=("PENDING",))
        self.assertEqual([item.id for item in byStatus], [pending.id])
        byCode = self.store.listRuns(self.tenantId, agentCode="SCOUT")
        self.assertEqual(len(byCode), 1)
        self.assertEqual(byCode[0].agentCode, "SCOUT")

    def testStepRoundTripAndOrdinalOrdering(self) -> None:
        run = self.store.saveRun(self.makeRun())
        self.store.saveStep(self.step(run, ordinal=2, kind="MODEL", toolCode=""))
        self.store.saveStep(self.step(run, ordinal=1, toolCode="SEARCH_PROJECT"))
        self.store.saveStep(
            self.step(
                run,
                ordinal=3,
                status="DENIED",
                toolCode="CREATE_TASK",
                arguments={"title": "T"},
                reason="Beyond the access level.",
                errorCode="AI_AGENT_ACCESS_LEVEL_EXCEEDED",
            )
        )
        steps = self.store.listSteps(self.tenantId, run.id)
        self.assertEqual([step.ordinal for step in steps], [1, 2, 3])
        self.assertEqual(steps[2].status, "DENIED")
        self.assertEqual(steps[2].errorCode, "AI_AGENT_ACCESS_LEVEL_EXCEEDED")
        self.assertEqual(steps[0].result, {"found": True})
        self.assertEqual(steps[0].arguments, {"projectId": "P-1"})

    def testStepOrdinalIsUniquePerRun(self) -> None:
        run = self.store.saveRun(self.makeRun())
        self.store.saveStep(self.step(run, ordinal=1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.store.saveStep(self.step(run, ordinal=1))

    def testStepsAreTenantScoped(self) -> None:
        run = self.store.saveRun(self.makeRun())
        self.store.saveStep(self.step(run))
        self.assertEqual(self.store.listSteps(self.otherTenantId, run.id), ())

    def testRetentionPurgesSettledRunsAndTheirStepsOnly(self) -> None:
        settled = self.store.saveRun(self.makeRun())
        settled.transitionTo("RUNNING", now=CLOCK - timedelta(days=399))
        settled.complete("done", now=CLOCK - timedelta(days=399))
        self.store.updateRun(settled)
        self.store.saveStep(self.step(settled))
        # auto_now_add owns createdAt on insert; backdate via update.
        AIAgentRunModel.objects.filter(id=settled.id).update(createdAt=CLOCK - timedelta(days=400))
        AIAgentStepModel.objects.filter(runId=settled.id).update(
            createdAt=CLOCK - timedelta(days=399)
        )
        recent = self.store.saveRun(self.makeRun())
        recent.transitionTo("RUNNING", now=CLOCK)
        recent.complete("done", now=CLOCK)
        self.store.updateRun(recent)
        awaiting = self.store.saveRun(self.makeRun())
        # still PENDING — a human has not decided yet — aged past the horizon
        AIAgentRunModel.objects.filter(id=awaiting.id).update(createdAt=CLOCK - timedelta(days=400))
        removedRuns, removedSteps = self.store.deleteSettledBefore(
            self.tenantId, CLOCK - timedelta(days=365)
        )
        self.assertEqual(removedRuns, 1)
        self.assertEqual(removedSteps, 1)
        self.assertIsNone(self.store.getRun(self.tenantId, settled.id))
        self.assertIsNotNone(self.store.getRun(self.tenantId, recent.id))
        self.assertIsNotNone(self.store.getRun(self.tenantId, awaiting.id))
        # The spared run's steps survive.
        self.assertEqual(len(self.store.listSteps(self.tenantId, awaiting.id)), 0)

    def testGlobalSweepAcrossTenants(self) -> None:
        first = self.store.saveRun(self.makeRun())
        first.deny("AI_AGENT_DENIED", now=CLOCK)
        self.store.updateRun(first)
        second = self.store.saveRun(self.makeRun(tenantId=self.otherTenantId))
        second.deny("AI_AGENT_DENIED", now=CLOCK)
        self.store.updateRun(second)
        AIAgentRunModel.objects.filter(id__in=[first.id, second.id]).update(
            createdAt=CLOCK - timedelta(days=400)
        )
        removed, _ = self.store.deleteSettledBefore(None, CLOCK - timedelta(days=365))
        self.assertEqual(removed, 2)

    def testRehydrationRejectsCorruptStatuses(self) -> None:
        row = AIAgentRunModel.objects.create(
            tenantId=self.tenantId,
            agentId=self.definition.id,
            agentCode="ANALYST",
            agentVersion=1,
            status="BOGUS",
        )
        with self.assertRaises(ValidationFailedError):
            runToEntity(row)
        badStep = AIAgentStepModel.objects.create(
            tenantId=self.tenantId,
            runId=uuid.uuid4(),
            ordinal=1,
            kind="HTTP",
            status="SUCCEEDED",
        )
        with self.assertRaises(ValidationFailedError):
            stepToEntity(badStep)


class MappedEntityTests(TestCase):
    """The toEntity mappers stay in lock-step with the models."""

    def testDefinitionMapperIsInvertible(self) -> None:
        tenant = uuid.uuid4()
        definition = AIAgentDefinition(
            tenantId=tenant,
            code="ANALYST",
            name="Project analyst",
            instructions="Analyze the project.",
            accessLevel="MUTATING",
            riskLevel="HIGH",
            declaredApprovalMode="DUAL_CONTROL",
            permissionPolicy={"requiredPermission": "AI_AGENT_ANALYZE"},
            createdAt=CLOCK,
            updatedAt=CLOCK,
        )
        row = AIAgentDefinitionModel.objects.create(
            id=definition.id,
            tenantId=tenant,
            code=definition.code,
            version=definition.version,
            name=definition.name,
            description=definition.description,
            instructions=definition.instructions,
            accessLevel=definition.accessLevel,
            riskLevel=definition.riskLevel,
            capabilityCodes=list(definition.capabilityCodes),
            toolCodes=list(definition.toolCodes),
            outputSchema=dict(definition.outputSchema),
            contextPolicy=dict(definition.contextPolicy),
            modelPolicy=dict(definition.modelPolicy),
            permissionPolicy=dict(definition.permissionPolicy),
            executionPolicy=dict(definition.executionPolicy),
            declaredApprovalMode=definition.declaredApprovalMode,
            status=definition.status,
            rejectionReason=definition.rejectionReason,
            metadata=dict(definition.metadata),
        )
        loaded = definitionToEntity(row)
        self.assertEqual(loaded.id, definition.id)
        self.assertEqual(loaded.accessLevel, "MUTATING")
        self.assertEqual(loaded.declaredApprovalMode, "DUAL_CONTROL")
        self.assertEqual(loaded.requiredPermission, "AI_AGENT_ANALYZE")

    def testApprovalMapperRoundTripsApproverList(self) -> None:
        tenant = uuid.uuid4()
        approval = AIAgentApproval(
            tenantId=tenant,
            agentCode="ANALYST",
            agentVersion=1,
            inputFingerprint=FINGERPRINT,
            mode="DUAL_CONTROL",
            requiredApprovals=2,
            createdAt=CLOCK,
        )
        row = AIAgentApprovalModel.objects.create(
            id=approval.id,
            tenantId=tenant,
            agentCode=approval.agentCode,
            agentVersion=approval.agentVersion,
            inputFingerprint=approval.inputFingerprint,
            mode=approval.mode,
            decision=approval.decision,
            requiredApprovals=approval.requiredApprovals,
            approvals=[str(uuid.uuid4()), str(uuid.uuid4())],
        )
        loaded = approvalToEntity(row)
        self.assertEqual(len(loaded.approvals), 2)
        self.assertEqual(loaded.remainingApprovals, 0)


class CapabilityResolverTests(TestCase):
    def testAvailableCodesAreTheActiveOnesForTheTenant(self) -> None:
        tenant = uuid.uuid4()
        other = uuid.uuid4()
        AICapabilityModel.objects.create(
            tenantId=tenant, code="SUMMARIZATION", name="Summarization", isActive=True
        )
        AICapabilityModel.objects.create(
            tenantId=tenant, code="LEGACY", name="Legacy", isActive=False
        )
        AICapabilityModel.objects.create(
            tenantId=other, code="OTHER_TENANT_ONLY", name="Other", isActive=True
        )
        resolver = DjangoAgentCapabilityResolver()
        self.assertEqual(resolver.availableCodes(tenant), frozenset({"SUMMARIZATION"}))
