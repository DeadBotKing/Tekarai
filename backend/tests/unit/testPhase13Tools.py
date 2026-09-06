"""Phase 13-X unit tests — tool vocabularies, entities, engine. Offline.

Covers the risk/effect/approval vocabularies, the ``ToolPolicy`` that maps
risk onto approval (Open Question #10), argument canonicalization,
fingerprinting and secret redaction, the three entities with their
lifecycles — including the dual-control rules that make "two people"
mean two people — the registry resolution, argument and output
validation, the fail-closed gatekeeper, execution budgets with loop
detection, and the structural guarantee that no ticket can be produced
from a blocked decision (§30).

No Django, database, network, provider, or clock dependency.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta

from apps.ai.domain.entities.aiRecords import AIToolExecution
from apps.ai.domain.entities.toolRecords import (
    AIToolApproval,
    AIToolDefinition,
    AIToolInvocation,
    approvalExpiry,
)
from apps.ai.domain.exceptions import (
    AIToolArgumentsInvalid,
    AIToolBudgetExceeded,
    AIToolInvalid,
    AIToolNotApproved,
    AIToolNotFound,
    AIToolOutputInvalid,
)
from apps.ai.domain.services.toolEngine import (
    ArgumentValidator,
    ExecutionBudget,
    ExecutionTicket,
    ToolGatekeeper,
    ToolProposal,
    ToolRegistry,
    prepareExecution,
)
from apps.ai.domain.valueObjects.toolTypes import (
    APPROVAL_MODES,
    TOOL_EFFECTS,
    TOOL_RISK_LEVELS,
    TOOL_STATUSES,
    ToolPolicy,
    argumentFingerprint,
    argumentSize,
    canonicalArguments,
    ensureApprovalMode,
    ensureRiskLevel,
    ensureToolCode,
    ensureToolEffect,
    ensureToolVersion,
    redactArguments,
    riskAtLeast,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
TENANT = uuid.UUID("a1a1a1a1-a1a1-4a1a-8a1a-a1a1a1a1a1a1")
ALICE = uuid.UUID("b2b2b2b2-b2b2-4b2b-8b2b-b2b2b2b2b2b2")
BOB = uuid.UUID("c3c3c3c3-c3c3-4c3c-8c3c-c3c3c3c3c3c3")

SCHEMA = {"type": "object", "required": ["projectId"]}


def definition(**overrides: object) -> AIToolDefinition:
    params: dict = {
        "tenantId": TENANT,
        "code": "SEARCH_PROJECT",
        "name": "Search project",
        "description": "Finds a project by identifier.",
        "inputSchema": SCHEMA,
        "requiredPermission": "AI_TOOL_EXECUTE",
        "createdAt": CLOCK,
        "updatedAt": CLOCK,
    }
    params.update(overrides)
    return AIToolDefinition(**params)


def approvedDefinition(**overrides: object) -> AIToolDefinition:
    item = definition(**overrides)
    item.submitForApproval(now=CLOCK)
    item.approve(approverId=ALICE, now=CLOCK)
    return item


class VocabularyTests(unittest.TestCase):
    def testClosedVocabulariesAreStable(self) -> None:
        self.assertEqual(TOOL_EFFECTS, ("READ_ONLY", "MUTATING", "EXTERNAL", "NOTIFYING"))
        self.assertEqual(TOOL_RISK_LEVELS, ("LOW", "MEDIUM", "HIGH", "CRITICAL"))
        self.assertEqual(
            APPROVAL_MODES, ("AUTOMATIC", "HUMAN_REQUIRED", "DUAL_CONTROL", "DISABLED")
        )
        self.assertIn("PENDING_APPROVAL", TOOL_STATUSES)

    def testValuesAreNormalized(self) -> None:
        self.assertEqual(ensureToolEffect(" mutating "), "MUTATING")
        self.assertEqual(ensureRiskLevel("critical"), "CRITICAL")
        self.assertEqual(ensureApprovalMode("dual_control"), "DUAL_CONTROL")
        self.assertEqual(ensureToolCode(" search_project "), "SEARCH_PROJECT")
        with self.assertRaises(ValidationFailedError):
            ensureToolEffect("DESTRUCTIVE")
        with self.assertRaises(ValidationFailedError):
            ensureRiskLevel("EXTREME")

    def testVersionsAreBounded(self) -> None:
        self.assertEqual(ensureToolVersion(3), 3)
        for bad in (0, -1, 1000, True):
            with self.assertRaises(ValidationFailedError):
                ensureToolVersion(bad)

    def testRiskComparison(self) -> None:
        self.assertTrue(riskAtLeast("CRITICAL", "HIGH"))
        self.assertTrue(riskAtLeast("HIGH", "HIGH"))
        self.assertFalse(riskAtLeast("LOW", "MEDIUM"))


class ArgumentTests(unittest.TestCase):
    def testCanonicalFormIsOrderInsensitive(self) -> None:
        self.assertEqual(
            argumentFingerprint("SEARCH_PROJECT", 1, {"b": 1, "a": [1, 2]}),
            argumentFingerprint("SEARCH_PROJECT", 1, {"a": (1, 2), "b": 1}),
        )

    def testFingerprintSeparatesToolAndVersion(self) -> None:
        base = argumentFingerprint("SEARCH_PROJECT", 1, {"a": 1})
        self.assertNotEqual(base, argumentFingerprint("SEARCH_PROJECT", 2, {"a": 1}))
        self.assertNotEqual(base, argumentFingerprint("GET_DOCUMENT", 1, {"a": 1}))
        self.assertEqual(len(base), 64)

    def testSecretsAreRedactedBeforeStorage(self) -> None:
        cleaned = redactArguments(
            {"projectId": "P-1", "apiKey": "sk-secret", "nested": {"password": "hunter2"}}
        )
        self.assertEqual(cleaned["projectId"], "P-1")
        self.assertEqual(cleaned["apiKey"], "[REDACTED]")
        self.assertEqual(cleaned["nested"]["password"], "[REDACTED]")

    def testRedactionHandlesListsAndEmptyInput(self) -> None:
        cleaned = redactArguments({"items": [{"accessToken": "abc", "id": 7}]})
        self.assertEqual(cleaned["items"][0]["accessToken"], "[REDACTED]")
        self.assertEqual(cleaned["items"][0]["id"], 7)
        self.assertEqual(redactArguments(None), {})

    def testRedactionUsesThePlatformDefinitionOfSecret(self) -> None:
        # camelCase is this codebase's convention, and the shared Phase 13-O
        # helper is what decides — X does not keep its own opinion.
        cleaned = redactArguments(
            {"accessToken": "a", "refreshToken": "b", "api_key": "c", "projectId": "P-1"}
        )
        self.assertEqual(cleaned["accessToken"], "[REDACTED]")
        self.assertEqual(cleaned["refreshToken"], "[REDACTED]")
        self.assertEqual(cleaned["api_key"], "[REDACTED]")
        self.assertEqual(cleaned["projectId"], "P-1")

    def testUnserializableArgumentsAreRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            canonicalArguments({"when": datetime.now(tz=UTC)})
        with self.assertRaises(ValidationFailedError):
            canonicalArguments(["not", "a", "mapping"])  # type: ignore[arg-type]

    def testSizeReflectsTheSerializedForm(self) -> None:
        self.assertGreater(argumentSize({"a": "x" * 100}), argumentSize({"a": "x"}))
        self.assertEqual(argumentSize(None), 2)


class ToolPolicyTests(unittest.TestCase):
    """Open Question #10: which risk needs a human, and which needs two."""

    def testDefaultsMapRiskOntoApproval(self) -> None:
        policy = ToolPolicy()
        self.assertEqual(policy.modeFor("LOW"), "AUTOMATIC")
        self.assertEqual(policy.modeFor("MEDIUM"), "AUTOMATIC")
        self.assertEqual(policy.modeFor("HIGH"), "HUMAN_REQUIRED")
        self.assertEqual(policy.modeFor("CRITICAL"), "DUAL_CONTROL")

    def testApprovalCountsFollowTheMode(self) -> None:
        policy = ToolPolicy()
        self.assertEqual(policy.approvalsNeeded("LOW"), 0)
        self.assertEqual(policy.approvalsNeeded("HIGH"), 1)
        self.assertEqual(policy.approvalsNeeded("CRITICAL"), 2)
        self.assertFalse(policy.requiresHuman("LOW"))
        self.assertTrue(policy.requiresHuman("CRITICAL"))

    def testAToolMayDeclareAStricterModeOnly(self) -> None:
        policy = ToolPolicy()
        self.assertEqual(policy.modeFor("LOW", "HUMAN_REQUIRED"), "HUMAN_REQUIRED")
        self.assertEqual(policy.modeFor("LOW", "DUAL_CONTROL"), "DUAL_CONTROL")
        # A looser declaration is ignored: the platform floor wins.
        self.assertEqual(policy.modeFor("CRITICAL", "AUTOMATIC"), "DUAL_CONTROL")
        self.assertEqual(policy.modeFor("HIGH", "AUTOMATIC"), "HUMAN_REQUIRED")

    def testDisabledAlwaysWins(self) -> None:
        self.assertEqual(ToolPolicy().modeFor("LOW", "DISABLED"), "DISABLED")

    def testThresholdsAreConfigurableAndValidated(self) -> None:
        strict = ToolPolicy(automaticBelowRisk="MEDIUM", dualControlAtRisk="HIGH")
        self.assertEqual(strict.modeFor("MEDIUM"), "HUMAN_REQUIRED")
        self.assertEqual(strict.modeFor("HIGH"), "DUAL_CONTROL")
        with self.assertRaises(ValidationFailedError):
            ToolPolicy(automaticBelowRisk="CRITICAL", dualControlAtRisk="LOW")
        with self.assertRaises(ValidationFailedError):
            ToolPolicy(maxCallsPerRequest=0)
        with self.assertRaises(ValidationFailedError):
            ToolPolicy(defaultTimeoutSeconds=100_000)


class DefinitionTests(unittest.TestCase):
    def testRegistryEntryStartsAsADraft(self) -> None:
        item = definition()
        self.assertEqual(item.status, "DRAFT")
        self.assertFalse(item.isRunnable)
        self.assertEqual(item.qualifiedCode, "SEARCH_PROJECT@1")
        self.assertFalse(item.mutatesState)

    def testEffectDeterminesWhetherItMutates(self) -> None:
        self.assertTrue(definition(effect="MUTATING").mutatesState)
        self.assertTrue(definition(effect="NOTIFYING").mutatesState)
        self.assertFalse(definition(effect="READ_ONLY").mutatesState)

    def testLifecycleFollowsItsMachine(self) -> None:
        item = definition()
        item.submitForApproval(now=CLOCK)
        self.assertEqual(item.status, "PENDING_APPROVAL")
        item.approve(approverId=ALICE, now=CLOCK)
        self.assertTrue(item.isRunnable)
        self.assertEqual(item.approvedBy, ALICE)
        item.suspend("incident", now=CLOCK)
        self.assertFalse(item.isRunnable)
        item.resume(now=CLOCK)
        self.assertTrue(item.isRunnable)
        item.retire(now=CLOCK)
        self.assertTrue(item.isTerminal)

    def testARetiredToolIsFrozen(self) -> None:
        item = approvedDefinition()
        item.retire(now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            item.resume(now=CLOCK)

    def testADraftCannotBeApprovedDirectly(self) -> None:
        with self.assertRaises(ValidationFailedError):
            definition().approve(approverId=ALICE, now=CLOCK)

    def testRejectionRequiresAReasonAndReturnsToDraft(self) -> None:
        item = definition()
        item.submitForApproval(now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            item.reject("  ", now=CLOCK)
        item.reject("schema is too loose", now=CLOCK)
        self.assertEqual(item.status, "DRAFT")
        self.assertEqual(item.rejectionReason, "schema is too loose")

    def testNewVersionClonesWithoutMutatingTheOriginal(self) -> None:
        original = approvedDefinition()
        successor = original.nextVersion(now=CLOCK, riskLevel="HIGH")
        self.assertEqual(successor.version, 2)
        self.assertEqual(successor.status, "DRAFT")
        self.assertEqual(successor.riskLevel, "HIGH")
        self.assertEqual(original.riskLevel, "LOW")
        self.assertTrue(original.isRunnable)

    def testGuardsRejectBadInput(self) -> None:
        with self.assertRaises(ValidationFailedError):
            definition(name="   ")
        with self.assertRaises(ValidationFailedError):
            definition(description="")
        with self.assertRaises(ValidationFailedError):
            definition(timeoutSeconds=0)
        with self.assertRaises(ValidationFailedError):
            definition(maxCallsPerRequest=999)
        with self.assertRaises(ValidationFailedError):
            definition(inputSchema=["nope"])


class ApprovalTests(unittest.TestCase):
    def approval(self, **overrides: object) -> AIToolApproval:
        params: dict = {
            "tenantId": TENANT,
            "toolCode": "DELETE_PROJECT",
            "toolVersion": 1,
            "argumentFingerprint": argumentFingerprint("DELETE_PROJECT", 1, {"id": 1}),
            "mode": "DUAL_CONTROL",
            "requiredApprovals": 2,
            "requestedBy": ALICE,
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIToolApproval(**params)

    def testDualControlNeedsTwoDistinctPeople(self) -> None:
        item = self.approval()
        item.grant(BOB, now=CLOCK)
        self.assertTrue(item.isPending)
        self.assertEqual(item.remainingApprovals, 1)
        item.grant(uuid.uuid4(), now=CLOCK)
        self.assertTrue(item.isGranted)

    def testTheSameApproverCannotCountTwice(self) -> None:
        item = self.approval()
        item.grant(BOB, now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            item.grant(BOB, now=CLOCK)

    def testTheRequesterCannotApproveTheirOwnCall(self) -> None:
        item = self.approval()
        with self.assertRaises(ValidationFailedError):
            item.grant(ALICE, now=CLOCK)

    def testSingleApprovalGrantsImmediately(self) -> None:
        item = self.approval(mode="HUMAN_REQUIRED", requiredApprovals=1)
        item.grant(BOB, now=CLOCK)
        self.assertTrue(item.isGranted)
        self.assertTrue(item.isUsableAt(CLOCK))

    def testDenialRequiresAReason(self) -> None:
        item = self.approval()
        with self.assertRaises(ValidationFailedError):
            item.deny("   ", now=CLOCK)
        item.deny("too risky", approverId=BOB, now=CLOCK)
        self.assertEqual(item.decision, "DENIED")
        self.assertEqual(item.reason, "too risky")

    def testADecidedApprovalIsFrozen(self) -> None:
        item = self.approval(mode="HUMAN_REQUIRED", requiredApprovals=1)
        item.grant(BOB, now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            item.grant(uuid.uuid4(), now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            item.deny("changed my mind", now=CLOCK)

    def testAnExpiredApprovalCannotBeGranted(self) -> None:
        item = self.approval(expiresAt=CLOCK - timedelta(minutes=1))
        with self.assertRaises(ValidationFailedError):
            item.grant(BOB, now=CLOCK)
        self.assertEqual(item.decision, "EXPIRED")

    def testAGrantedApprovalStopsBeingUsableAfterExpiry(self) -> None:
        item = self.approval(
            mode="HUMAN_REQUIRED", requiredApprovals=1, expiresAt=CLOCK + timedelta(minutes=5)
        )
        item.grant(BOB, now=CLOCK)
        self.assertTrue(item.isUsableAt(CLOCK))
        self.assertFalse(item.isUsableAt(CLOCK + timedelta(minutes=10)))

    def testExpiryHelperValidatesItsInput(self) -> None:
        self.assertEqual(approvalExpiry(CLOCK, 60), CLOCK + timedelta(seconds=60))
        with self.assertRaises(ValidationFailedError):
            approvalExpiry(CLOCK, 0)

    def testFingerprintIsRequired(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.approval(argumentFingerprint="short")


class InvocationTests(unittest.TestCase):
    def invocation(self, **overrides: object) -> AIToolInvocation:
        params: dict = {
            "tenantId": TENANT,
            "toolCode": "SEARCH_PROJECT",
            "toolVersion": 1,
            "arguments": {"projectId": "P-1", "apiKey": "secret"},
            "requestId": uuid.uuid4(),
            "toolId": uuid.uuid4(),
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIToolInvocation(**params)

    def testArgumentsAreRedactedOnConstruction(self) -> None:
        item = self.invocation()
        self.assertEqual(item.arguments["projectId"], "P-1")
        self.assertEqual(item.arguments["apiKey"], "[REDACTED]")
        self.assertEqual(len(item.fingerprint), 64)
        self.assertEqual(item.qualifiedCode, "SEARCH_PROJECT@1")

    def testSuccessRecordsResultAndLatency(self) -> None:
        item = self.invocation()
        item.transitionTo("RUNNING", now=CLOCK)
        item.succeed({"found": True}, now=CLOCK + timedelta(milliseconds=250))
        self.assertEqual(item.status, "SUCCEEDED")
        self.assertEqual(item.result, {"found": True})
        self.assertEqual(item.latencyMs, 250)
        self.assertTrue(item.isTerminal)

    def testFailureAndDenialRecordCodes(self) -> None:
        failing = self.invocation()
        failing.transitionTo("RUNNING", now=CLOCK)
        failing.fail("upstream_timeout", now=CLOCK)
        self.assertEqual(failing.status, "FAILED")
        self.assertEqual(failing.errorCode, "UPSTREAM_TIMEOUT")
        denied = self.invocation()
        denied.deny(now=CLOCK)
        self.assertEqual(denied.status, "DENIED")
        self.assertEqual(denied.errorCode, "AI_TOOL_DENIED")

    def testIllegalTransitionsAreRejected(self) -> None:
        item = self.invocation()
        with self.assertRaises(ValidationFailedError):
            item.succeed({}, now=CLOCK)
        item.deny(now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            item.transitionTo("RUNNING", now=CLOCK)

    def testBridgeToPhase13BExecution(self) -> None:
        bridged = self.invocation().toDomainExecution()
        self.assertIsInstance(bridged, AIToolExecution)
        self.assertEqual(bridged.status, "PENDING")

    def testBridgeRefusesWithoutProvenance(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.invocation(requestId=None).toDomainExecution()


class RegistryTests(unittest.TestCase):
    def testLatestApprovedVersionWins(self) -> None:
        registry = ToolRegistry(
            [
                approvedDefinition(version=1),
                approvedDefinition(version=2),
                definition(version=3),  # still a draft
            ]
        )
        resolved = registry.resolve("SEARCH_PROJECT")
        self.assertEqual(resolved.version, 2)

    def testAnExplicitVersionIsHonouredEvenAsADraft(self) -> None:
        registry = ToolRegistry([approvedDefinition(version=1), definition(version=2)])
        self.assertEqual(registry.resolve("SEARCH_PROJECT", 2).status, "DRAFT")

    def testUnknownToolAndVersion(self) -> None:
        registry = ToolRegistry([approvedDefinition()])
        with self.assertRaises(AIToolNotFound):
            registry.resolve("GET_DOCUMENT")
        with self.assertRaises(AIToolNotFound):
            registry.resolve("SEARCH_PROJECT", 9)

    def testATooWithoutAnApprovedVersionCannotBeResolved(self) -> None:
        registry = ToolRegistry([definition()])
        with self.assertRaises(AIToolNotApproved):
            registry.resolve("SEARCH_PROJECT")

    def testListRunnableExcludesDrafts(self) -> None:
        registry = ToolRegistry([approvedDefinition(version=1), definition(version=2)])
        self.assertEqual([item.version for item in registry.listRunnable()], [1])

    def testForeignEntriesAreRejected(self) -> None:
        with self.assertRaises(AIToolInvalid):
            ToolRegistry(["SEARCH_PROJECT"])  # type: ignore[list-item]


class ProposalAndValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ArgumentValidator()
        self.policy = ToolPolicy()

    def testProposalNormalizesItsInput(self) -> None:
        proposal = ToolProposal(toolCode=" search_project ", arguments={"projectId": "P-1"})
        self.assertEqual(proposal.toolCode, "SEARCH_PROJECT")
        self.assertEqual(len(proposal.fingerprintFor(1)), 64)

    def testValidArgumentsPassTheSchema(self) -> None:
        canonical = self.validator.validate(approvedDefinition(), {"projectId": "P-1"}, self.policy)
        self.assertEqual(canonical, {"projectId": "P-1"})

    def testMissingRequiredFieldIsRejected(self) -> None:
        with self.assertRaises(AIToolArgumentsInvalid):
            self.validator.validate(approvedDefinition(), {"other": 1}, self.policy)

    def testOversizedArgumentsAreRejected(self) -> None:
        policy = ToolPolicy(maxArgumentBytes=64)
        with self.assertRaises(AIToolArgumentsInvalid):
            self.validator.validate(approvedDefinition(), {"projectId": "x" * 500}, policy)

    def testOutputIsCheckedAgainstItsSchema(self) -> None:
        item = approvedDefinition(outputSchema={"type": "object", "required": ["found"]})
        self.assertEqual(self.validator.validateOutput(item, {"found": True}), {"found": True})
        with self.assertRaises(AIToolOutputInvalid):
            self.validator.validateOutput(item, {"other": 1})

    def testNoSchemaMeansNoCheck(self) -> None:
        item = approvedDefinition(inputSchema={}, outputSchema={})
        self.assertEqual(
            self.validator.validate(item, {"anything": 1}, self.policy), {"anything": 1}
        )
        self.assertEqual(self.validator.validateOutput(item, {"anything": 1}), {"anything": 1})

    def testForeignDefinitionIsRejected(self) -> None:
        with self.assertRaises(AIToolInvalid):
            self.validator.validate("tool", {}, self.policy)  # type: ignore[arg-type]


class GatekeeperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gatekeeper = ToolGatekeeper()
        self.policy = ToolPolicy()

    def testALowRiskApprovedToolRunsWithoutAHuman(self) -> None:
        decision = self.gatekeeper.decide(
            approvedDefinition(), self.policy, permitted=True, now=CLOCK
        )
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.requiresApproval)
        self.assertEqual(decision.approvalMode, "AUTOMATIC")

    def testADraftToolIsRefused(self) -> None:
        decision = self.gatekeeper.decide(definition(), self.policy, permitted=True, now=CLOCK)
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.errorCode, "AI_TOOL_NOT_APPROVED")
        self.assertIn("DRAFT", decision.reason)

    def testASuspendedToolIsRefused(self) -> None:
        item = approvedDefinition()
        item.suspend("incident", now=CLOCK)
        decision = self.gatekeeper.decide(item, self.policy, permitted=True, now=CLOCK)
        self.assertTrue(decision.blocked)

    def testAMissingPermissionIsRefused(self) -> None:
        decision = self.gatekeeper.decide(
            approvedDefinition(), self.policy, permitted=False, now=CLOCK
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.errorCode, "AI_TOOL_DENIED")

    def testAHighRiskToolNeedsAnApproval(self) -> None:
        decision = self.gatekeeper.decide(
            approvedDefinition(riskLevel="HIGH"), self.policy, permitted=True, now=CLOCK
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.errorCode, "AI_TOOL_APPROVAL_REQUIRED")
        self.assertEqual(decision.approvalsNeeded, 1)

    def testAGrantedApprovalUnblocksIt(self) -> None:
        approval = AIToolApproval(
            tenantId=TENANT,
            toolCode="SEARCH_PROJECT",
            toolVersion=1,
            argumentFingerprint=argumentFingerprint("SEARCH_PROJECT", 1, {"projectId": "P-1"}),
            mode="HUMAN_REQUIRED",
            requiredApprovals=1,
            requestedBy=ALICE,
            createdAt=CLOCK,
        )
        approval.grant(BOB, now=CLOCK)
        decision = self.gatekeeper.decide(
            approvedDefinition(riskLevel="HIGH"),
            self.policy,
            permitted=True,
            approval=approval,
            now=CLOCK,
        )
        self.assertTrue(decision.allowed)

    def testADeniedApprovalBlocksIt(self) -> None:
        approval = AIToolApproval(
            tenantId=TENANT,
            toolCode="SEARCH_PROJECT",
            toolVersion=1,
            argumentFingerprint=argumentFingerprint("SEARCH_PROJECT", 1, {}),
            mode="HUMAN_REQUIRED",
            requiredApprovals=1,
            createdAt=CLOCK,
        )
        approval.deny("no", now=CLOCK)
        decision = self.gatekeeper.decide(
            approvedDefinition(riskLevel="HIGH"),
            self.policy,
            permitted=True,
            approval=approval,
            now=CLOCK,
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.errorCode, "AI_TOOL_DENIED")

    def testADisabledToolNeverRuns(self) -> None:
        decision = self.gatekeeper.decide(
            approvedDefinition(declaredApprovalMode="DISABLED"),
            self.policy,
            permitted=True,
            now=CLOCK,
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.approvalMode, "DISABLED")

    def testForeignInputIsRejected(self) -> None:
        with self.assertRaises(AIToolInvalid):
            self.gatekeeper.decide("tool", self.policy, permitted=True)  # type: ignore[arg-type]
        with self.assertRaises(AIToolInvalid):
            self.gatekeeper.decide(approvedDefinition(), "policy", permitted=True)  # type: ignore[arg-type]


class BudgetTests(unittest.TestCase):
    def testCallsAreCapped(self) -> None:
        budget = ExecutionBudget(maxCalls=2)
        budget.check("a", [])
        budget.check("b", ["a"])
        with self.assertRaises(AIToolBudgetExceeded):
            budget.check("c", ["a", "b"])

    def testARepeatingCallIsTreatedAsALoop(self) -> None:
        budget = ExecutionBudget(maxCalls=10, maxRepeats=2)
        budget.check("a", ["a"])
        with self.assertRaises(AIToolBudgetExceeded):
            budget.check("a", ["a", "a"])

    def testRemainingIsReported(self) -> None:
        budget = ExecutionBudget(maxCalls=3)
        self.assertEqual(budget.remaining(["a"]), 2)
        self.assertEqual(budget.remaining(["a", "b", "c", "d"]), 0)

    def testBudgetsMustBePositive(self) -> None:
        with self.assertRaises(AIToolInvalid):
            ExecutionBudget(maxCalls=0)
        with self.assertRaises(AIToolInvalid):
            ExecutionBudget(maxCalls=1, maxRepeats=0)


class TicketTests(unittest.TestCase):
    """§30: there is no path from a raw proposal to a runnable ticket."""

    def setUp(self) -> None:
        self.gatekeeper = ToolGatekeeper()
        self.policy = ToolPolicy()

    def testAnAllowedDecisionProducesATicket(self) -> None:
        decision = self.gatekeeper.decide(
            approvedDefinition(), self.policy, permitted=True, now=CLOCK
        )
        ticket = prepareExecution(decision, {"projectId": "P-1"}, policy=self.policy)
        self.assertIsInstance(ticket, ExecutionTicket)
        self.assertEqual(ticket.qualifiedCode, "SEARCH_PROJECT@1")
        self.assertEqual(len(ticket.fingerprint), 64)
        self.assertLessEqual(ticket.timeoutSeconds, self.policy.defaultTimeoutSeconds)

    def testABlockedDecisionCannotProduceATicket(self) -> None:
        blocked = self.gatekeeper.decide(definition(), self.policy, permitted=True, now=CLOCK)
        with self.assertRaises(AIToolNotApproved):
            prepareExecution(blocked, {"projectId": "P-1"}, policy=self.policy)

    def testAMissingPermissionAlsoCannotProduceATicket(self) -> None:
        blocked = self.gatekeeper.decide(
            approvedDefinition(), self.policy, permitted=False, now=CLOCK
        )
        with self.assertRaises(AIToolNotApproved):
            prepareExecution(blocked, {}, policy=self.policy)

    def testATicketCannotBeForgedFromSomethingElse(self) -> None:
        with self.assertRaises(AIToolInvalid):
            prepareExecution("allowed", {}, policy=self.policy)  # type: ignore[arg-type]

    def testTheTicketTimeoutNeverExceedsThePolicy(self) -> None:
        policy = ToolPolicy(defaultTimeoutSeconds=5)
        decision = self.gatekeeper.decide(
            approvedDefinition(timeoutSeconds=120), policy, permitted=True, now=CLOCK
        )
        ticket = prepareExecution(decision, {"projectId": "P-1"}, policy=policy)
        self.assertEqual(ticket.timeoutSeconds, 5)


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
