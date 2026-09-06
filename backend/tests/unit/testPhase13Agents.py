"""Phase 13-Y unit tests — agent vocabularies, entities, engine. Offline.

Covers the access-level vocabularies and their effect allowlists (the
"what" half of Open Question #11), the ``AgentPolicy`` that maps risk
onto approval (the "who says yes" half), input fingerprinting and secret
redaction, the four entities with their lifecycles — including the
dual-control rules and the Phase 13-B status machine — the fail-closed
gatekeeper, the shared run budget with cross-step loop detection, the
context builder, and the plan-act loop with its structural guarantees:
a proposal beyond the agent's access level never reaches the tool
executor, and every step — denied ones included — becomes a row.

No Django, database, network, provider, or clock dependency.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from apps.ai.domain.entities.agentRecords import (
    AIAgentApproval,
    AIAgentDefinition,
    AIAgentRun,
    AIAgentStep,
)
from apps.ai.domain.entities.aiRecords import AIAgent, AIAgentExecution
from apps.ai.domain.exceptions import (
    AIAgentBudgetExceeded,
    AIAgentInvalid,
    AIAgentNotApproved,
    AIAgentOutputInvalid,
    AIContextTooLarge,
)
from apps.ai.domain.services.agentEngine import (
    STEP_TOOL_ACCESS_DENIED,
    STEP_TOOL_APPROVAL_REQUIRED,
    STEP_TOOL_NOT_DECLARED,
    AgentContext,
    AgentContextBuilder,
    AgentGatekeeper,
    AgentKnowledgeContext,
    AgentMemoryContext,
    AgentModelReply,
    AgentPlanner,
    AgentRunBudget,
    AgentToolDeclaration,
    AgentToolOutcome,
)
from apps.ai.domain.services.toolEngine import ToolProposal
from apps.ai.domain.valueObjects.agentTypes import (
    ACCESS_EFFECT_ALLOWLIST,
    AGENT_ACCESS_LEVELS,
    AGENT_STATUSES,
    AGENT_STEP_KINDS,
    AGENT_STEP_STATUSES,
    AgentPolicy,
    accessEffectAllowlist,
    allowsEffect,
    ensureAgentAccessLevel,
    ensureAgentCode,
    ensureAgentStatus,
    ensureAgentVersion,
    ensureStepKind,
    ensureStepStatus,
    inputFingerprint,
    inputSize,
    redactInput,
)
from apps.ai.domain.valueObjects.auditTypes import REDACTED
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 6, 9, 0, 0, tzinfo=UTC)
TENANT = uuid.UUID("a1a1a1a1-a1a1-4a1a-8a1a-a1a1a1a1a1a1")
ALICE = uuid.UUID("b2b2b2b2-b2b2-4b2b-8b2b-b2b2b2b2b2b2")
BOB = uuid.UUID("c3c3c3c3-c3c3-4c3c-8c3c-c3c3c3c3c3c3")
CAROL = uuid.UUID("d4d4d4d4-d4d4-4d4d-8d4d-d4d4d4d4d4d4")


def definition(**overrides: object) -> AIAgentDefinition:
    params: dict = {
        "tenantId": TENANT,
        "code": "ANALYST",
        "name": "Project analyst",
        "instructions": "Analyze the project and report risks.",
        "createdAt": CLOCK,
        "updatedAt": CLOCK,
    }
    params.update(overrides)
    return AIAgentDefinition(**params)


def approvedDefinition(**overrides: object) -> AIAgentDefinition:
    item = definition(**overrides)
    item.submitForApproval(now=CLOCK)
    item.approve(approverId=BOB, now=CLOCK)
    return item


def runFor(definition: AIAgentDefinition, **overrides: object) -> AIAgentRun:
    params: dict = {
        "tenantId": TENANT,
        "agentId": definition.id,
        "agentCode": definition.code,
        "agentVersion": definition.version,
        "input": {"task": "status report"},
        "createdAt": CLOCK,
    }
    params.update(overrides)
    return AIAgentRun(**params)


class ScriptedCaller:
    """Replays canned replies; records the requests it saw."""

    def __init__(self, replies: list[Any]) -> None:
        self._replies = list(replies)
        self.requests: list[Any] = []

    def call(self, tenantId: Any, request: Any) -> Any:
        self.requests.append(request)
        if not self._replies:
            from apps.ai.domain.exceptions import AIAgentExecutionFailed

            raise AIAgentExecutionFailed("The scripted model caller ran out of replies.")
        return self._replies.pop(0)


class RecordingExecutor:
    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.calls: list[Any] = []

    def execute(self, tenantId: Any, proposal: Any, *, principal: Any = None) -> Any:
        self.calls.append((proposal, principal))
        return (
            self.outcomes.pop(0)
            if self.outcomes
            else AgentToolOutcome(status="SUCCEEDED", result={"ok": True})
        )


class VocabularyTests(unittest.TestCase):
    def testClosedVocabulariesAreStable(self) -> None:
        self.assertEqual(AGENT_ACCESS_LEVELS, ("ADVISORY", "READ_ONLY", "MUTATING", "AUTONOMOUS"))
        self.assertEqual(ACCESS_EFFECT_ALLOWLIST["ADVISORY"], ())
        self.assertEqual(ACCESS_EFFECT_ALLOWLIST["READ_ONLY"], ("READ_ONLY",))
        self.assertEqual(
            ACCESS_EFFECT_ALLOWLIST["MUTATING"], ("READ_ONLY", "MUTATING", "NOTIFYING")
        )
        self.assertEqual(
            ACCESS_EFFECT_ALLOWLIST["AUTONOMOUS"],
            ("READ_ONLY", "MUTATING", "EXTERNAL", "NOTIFYING"),
        )
        self.assertIn("PENDING_APPROVAL", AGENT_STATUSES)
        self.assertEqual(AGENT_STEP_KINDS, ("MODEL", "TOOL"))
        self.assertEqual(AGENT_STEP_STATUSES, ("SUCCEEDED", "FAILED", "DENIED"))

    def testValuesAreNormalized(self) -> None:
        self.assertEqual(ensureAgentAccessLevel(" read_only "), "READ_ONLY")
        self.assertEqual(ensureAgentStatus("pending_approval"), "PENDING_APPROVAL")
        self.assertEqual(ensureStepKind("tool"), "TOOL")
        self.assertEqual(ensureStepStatus("denied"), "DENIED")
        self.assertEqual(ensureAgentCode(" analyst "), "ANALYST")
        with self.assertRaises(ValidationFailedError):
            ensureAgentAccessLevel("OMNIPOTENT")
        with self.assertRaises(ValidationFailedError):
            ensureAgentStatus("ARCHIVED")
        with self.assertRaises(ValidationFailedError):
            ensureStepKind("HTTP")
        with self.assertRaises(ValidationFailedError):
            ensureStepStatus("PENDING")

    def testVersionsAreBounded(self) -> None:
        self.assertEqual(ensureAgentVersion(3), 3)
        for bad in (0, -1, 1000, True):
            with self.assertRaises(ValidationFailedError):
                ensureAgentVersion(bad)

    def testAllowlistIsMonotonic(self) -> None:
        levels = list(AGENT_ACCESS_LEVELS)
        for lower, higher in zip(levels, levels[1:], strict=False):
            self.assertTrue(set(accessEffectAllowlist(lower)) <= set(accessEffectAllowlist(higher)))

    def testAllowsEffectIsStructural(self) -> None:
        self.assertFalse(allowsEffect("ADVISORY", "READ_ONLY"))
        self.assertTrue(allowsEffect("READ_ONLY", "READ_ONLY"))
        self.assertFalse(allowsEffect("READ_ONLY", "MUTATING"))
        self.assertTrue(allowsEffect("MUTATING", "NOTIFYING"))
        self.assertFalse(allowsEffect("MUTATING", "EXTERNAL"))
        self.assertTrue(allowsEffect("AUTONOMOUS", "EXTERNAL"))
        self.assertFalse(allowsEffect("AUTONOMOUS", "DESTRUCTIVE"))


class AgentPolicyTests(unittest.TestCase):
    def testDefaultRiskMapping(self) -> None:
        policy = AgentPolicy()
        self.assertEqual(policy.modeFor("LOW"), "AUTOMATIC")
        self.assertEqual(policy.modeFor("MEDIUM"), "AUTOMATIC")
        self.assertEqual(policy.modeFor("HIGH"), "HUMAN_REQUIRED")
        self.assertEqual(policy.modeFor("CRITICAL"), "DUAL_CONTROL")

    def testThresholdsAreConfigurationDriven(self) -> None:
        policy = AgentPolicy(automaticBelowRisk="MEDIUM")
        self.assertEqual(policy.modeFor("MEDIUM"), "HUMAN_REQUIRED")
        self.assertEqual(policy.modeFor("LOW"), "AUTOMATIC")
        dual = AgentPolicy(automaticBelowRisk="LOW", dualControlAtRisk="HIGH")
        self.assertEqual(dual.modeFor("HIGH"), "DUAL_CONTROL")
        self.assertEqual(dual.modeFor("CRITICAL"), "DUAL_CONTROL")

    def testStricterDeclarationIsHonouredLooserIsIgnored(self) -> None:
        policy = AgentPolicy()
        # LOW risk → AUTOMATIC by default; a declaration of HUMAN_REQUIRED
        # is stricter and must win.
        self.assertEqual(policy.modeFor("LOW", "HUMAN_REQUIRED"), "HUMAN_REQUIRED")
        # CRITICAL → DUAL_CONTROL; a looser declaration must be ignored.
        self.assertEqual(policy.modeFor("CRITICAL", "AUTOMATIC"), "DUAL_CONTROL")
        self.assertEqual(policy.modeFor("HIGH", "DUAL_CONTROL"), "DUAL_CONTROL")

    def testDisabledDeclarationIsRefusedForAgents(self) -> None:
        policy = AgentPolicy()
        with self.assertRaises(ValidationFailedError):
            policy.modeFor("LOW", "DISABLED")

    def testApprovalsNeededFollowsMode(self) -> None:
        policy = AgentPolicy()
        self.assertEqual(policy.approvalsNeeded("LOW"), 0)
        self.assertEqual(policy.approvalsNeeded("HIGH"), 1)
        self.assertEqual(policy.approvalsNeeded("CRITICAL"), 2)
        self.assertTrue(policy.requiresHuman("CRITICAL"))
        self.assertFalse(policy.requiresHuman("LOW"))

    def testImpossiblePoliciesAreRefused(self) -> None:
        with self.assertRaises(ValidationFailedError):
            AgentPolicy(automaticBelowRisk="CRITICAL", dualControlAtRisk="LOW")
        for bad in (0, -1, True):
            with self.assertRaises(ValidationFailedError):
                AgentPolicy(maxSteps=bad)
        with self.assertRaises(ValidationFailedError):
            AgentPolicy(maxSteps=51)
        with self.assertRaises(ValidationFailedError):
            AgentPolicy(maxRepeats=6)


class FingerprintAndRedactionTests(unittest.TestCase):
    def testInputFingerprintIsDeterministicAndDistinguishing(self) -> None:
        first = inputFingerprint("ANALYST", 1, {"task": "a"})
        second = inputFingerprint("ANALYST", 1, {"task": "a"})
        other = inputFingerprint("ANALYST", 1, {"task": "b"})
        otherVersion = inputFingerprint("ANALYST", 2, {"task": "a"})
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertNotEqual(first, otherVersion)
        self.assertEqual(len(first), 64)

    def testRedactionUsesTheSharedPlatformDefinition(self) -> None:
        payload = {
            "apiKey": "secret-value",
            "totalTokens": 42,
            "nested": {"password": "hunter2", "projectId": "P-1"},
        }
        redacted = redactInput(payload)
        self.assertEqual(redacted["apiKey"], REDACTED)
        self.assertEqual(redacted["nested"]["password"], REDACTED)
        # totalTokens must survive: the Phase 13-O definition deliberately
        # keeps metering counters (one definition, one place to fix).
        self.assertEqual(redacted["totalTokens"], 42)
        self.assertEqual(redacted["nested"]["projectId"], "P-1")

    def testInputSizeIsCanonicalBytes(self) -> None:
        self.assertGreater(inputSize({"task": "hello"}), 0)
        self.assertEqual(inputSize({"b": 1, "a": 2}), inputSize({"a": 2, "b": 1}))


class DefinitionTests(unittest.TestCase):
    def testNameAndInstructionsAreRequired(self) -> None:
        with self.assertRaises(ValidationFailedError):
            definition(name="  ")
        with self.assertRaises(ValidationFailedError):
            definition(instructions="   ")

    def testPolicyFieldsMustBeMappings(self) -> None:
        for field in (
            "outputSchema",
            "contextPolicy",
            "modelPolicy",
            "permissionPolicy",
            "executionPolicy",
        ):
            with self.assertRaises(ValidationFailedError):
                definition(**{field: "nope"})

    def testExecutionPolicyCeilingsAreEnforced(self) -> None:
        with self.assertRaises(ValidationFailedError):
            definition(executionPolicy={"maxSteps": 0})
        with self.assertRaises(ValidationFailedError):
            definition(executionPolicy={"maxSteps": 51})
        with self.assertRaises(ValidationFailedError):
            definition(executionPolicy={"maxToolCalls": 101})
        with self.assertRaises(ValidationFailedError):
            definition(executionPolicy={"maxDurationSeconds": 1801})
        with self.assertRaises(ValidationFailedError):
            definition(contextPolicy={"maxContextTokens": 0})

    def testLifecycleTransitionsAreEnforced(self) -> None:
        item = definition()
        with self.assertRaises(ValidationFailedError):
            item.approve(approverId=ALICE, now=CLOCK)  # DRAFT → APPROVED is not a step
        with self.assertRaises(ValidationFailedError):
            item.suspend(now=CLOCK)  # DRAFT → SUSPENDED is not a step
        item.submitForApproval(now=CLOCK)
        item.approve(approverId=ALICE, now=CLOCK)
        self.assertEqual(item.status, "APPROVED")
        item.suspend(now=CLOCK)
        item.resume(now=CLOCK)
        self.assertEqual(item.status, "APPROVED")
        item.retire(now=CLOCK)
        self.assertEqual(item.status, "RETIRED")
        with self.assertRaises(ValidationFailedError):
            item.resume(now=CLOCK)  # RETIRED is terminal

    def testRejectRequiresAReason(self) -> None:
        item = definition()
        item.submitForApproval(now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            item.reject("  ", now=CLOCK)
        item.reject("Not ready", now=CLOCK)
        self.assertEqual(item.status, "DRAFT")
        self.assertEqual(item.rejectionReason, "Not ready")

    def testNextVersionLeavesTheOriginalUntouched(self) -> None:
        item = definition()
        successor = item.nextVersion(now=CLOCK, instructions="New instructions")
        self.assertEqual(item.instructions, "Analyze the project and report risks.")
        self.assertEqual(successor.version, item.version + 1)
        self.assertEqual(successor.instructions, "New instructions")
        self.assertEqual(successor.code, item.code)
        self.assertEqual(successor.accessLevel, item.accessLevel)
        self.assertEqual(successor.status, "DRAFT")

    def testAllowsEffectFollowsTheLevel(self) -> None:
        self.assertTrue(approvedDefinition(accessLevel="READ_ONLY").allowsEffect("READ_ONLY"))
        self.assertFalse(approvedDefinition(accessLevel="READ_ONLY").allowsEffect("MUTATING"))
        self.assertFalse(approvedDefinition(accessLevel="ADVISORY").allowsEffect("READ_ONLY"))
        self.assertTrue(approvedDefinition(accessLevel="AUTONOMOUS").allowsEffect("EXTERNAL"))

    def testRequiredPermissionHasASensibleDefault(self) -> None:
        self.assertEqual(approvedDefinition().requiredPermission, "AI_AGENT_RUN")
        overridden = approvedDefinition(permissionPolicy={"requiredPermission": "ai_agent_analyze"})
        self.assertEqual(overridden.requiredPermission, "AI_AGENT_ANALYZE")

    def testIsRunnableOnlyWhenApproved(self) -> None:
        item = definition()
        self.assertFalse(item.isRunnable)
        item.submitForApproval(now=CLOCK)
        self.assertFalse(item.isRunnable)
        item.approve(approverId=ALICE, now=CLOCK)
        self.assertTrue(item.isRunnable)
        self.assertTrue(item.isActive)

    def testToBaseAgentBridgesToPhaseB(self) -> None:
        item = approvedDefinition(
            capabilityCodes=("SUMMARIZATION",),
            toolCodes=("SEARCH_PROJECT",),
            executionPolicy={"maxSteps": 3},
        )
        base: AIAgent = item.toBaseAgent()
        self.assertEqual(base.code, item.code)
        self.assertEqual(base.name, item.name)
        self.assertEqual(base.instructions, item.instructions)
        self.assertEqual(base.capabilityCodes, ("SUMMARIZATION",))
        self.assertEqual(base.toolCodes, ("SEARCH_PROJECT",))
        self.assertEqual(base.id, item.id)
        self.assertTrue(base.isActive)


class ApprovalTests(unittest.TestCase):
    def approval(self, **overrides: object) -> AIAgentApproval:
        params: dict = {
            "tenantId": TENANT,
            "agentCode": "ANALYST",
            "agentVersion": 1,
            "inputFingerprint": inputFingerprint("ANALYST", 1, {"task": "a"}),
            "requestedBy": ALICE,
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIAgentApproval(**params)

    def testFingerprintIsRequired(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.approval(inputFingerprint="short")

    def testSingleGrantGrants(self) -> None:
        item = self.approval(requiredApprovals=1)
        item.grant(BOB, now=CLOCK)
        self.assertTrue(item.isGranted)
        self.assertEqual(item.decidedAt, CLOCK)

    def testDualControlNeedsTwoDistinctPeople(self) -> None:
        item = self.approval(mode="DUAL_CONTROL", requiredApprovals=2)
        item.grant(BOB, now=CLOCK)
        self.assertFalse(item.isGranted)
        self.assertEqual(item.remainingApprovals, 1)
        with self.assertRaises(ValidationFailedError):
            item.grant(BOB, now=CLOCK)  # the same person twice
        item.grant(CAROL, now=CLOCK)
        self.assertTrue(item.isGranted)
        self.assertEqual(item.remainingApprovals, 0)

    def testRequesterCannotApproveTheirOwnRun(self) -> None:
        item = self.approval(requestedBy=ALICE)
        with self.assertRaises(ValidationFailedError):
            item.grant(ALICE, now=CLOCK)

    def testDenyRequiresAReasonAndIsTerminal(self) -> None:
        item = self.approval()
        with self.assertRaises(ValidationFailedError):
            item.deny("  ")
        item.deny("Out of scope", approverId=BOB, now=CLOCK)
        self.assertEqual(item.decision, "DENIED")
        with self.assertRaises(ValidationFailedError):
            item.grant(BOB, now=CLOCK)  # already decided

    def testExpiredApprovalCannotBeGranted(self) -> None:
        item = self.approval(expiresAt=CLOCK)
        with self.assertRaises(ValidationFailedError):
            item.grant(BOB, now=CLOCK + timedelta(seconds=1))
        self.assertEqual(item.decision, "EXPIRED")

    def testUsabilityCombinesGrantAndExpiry(self) -> None:
        item = self.approval(expiresAt=CLOCK + timedelta(hours=1))
        self.assertFalse(item.isUsableAt(CLOCK))  # pending
        item.grant(BOB, now=CLOCK)
        self.assertTrue(item.isUsableAt(CLOCK))
        self.assertFalse(item.isUsableAt(CLOCK + timedelta(hours=2)))


class RunTests(unittest.TestCase):
    def testStatusVocabularyIsThePhaseBMachine(self) -> None:
        item = runFor(approvedDefinition())
        with self.assertRaises(ValidationFailedError):
            runFor(approvedDefinition(), status="ARCHIVED")
        with self.assertRaises(ValidationFailedError):
            runFor(approvedDefinition(), status="AWAITING_APPROVAL")  # not a B status
        self.assertEqual(item.status, "PENDING")

    def testTransitionsMirrorPhaseBExactly(self) -> None:
        item = runFor(approvedDefinition())
        with self.assertRaises(ValidationFailedError):
            item.transitionTo("COMPLETED", now=CLOCK)  # PENDING cannot complete
        item.transitionTo("RUNNING", now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            item.transitionTo("DENIED", now=CLOCK)  # RUNNING cannot be denied
        item.complete("done", now=CLOCK + timedelta(milliseconds=10))
        self.assertEqual(item.status, "COMPLETED")
        self.assertEqual(item.answer, "done")
        self.assertEqual(item.latencyMs, 10)

    def testInputIsRedactedAndFingerprintedOnConstruction(self) -> None:
        item = runFor(
            approvedDefinition(),
            input={"task": "a", "apiKey": "raw-secret"},
        )
        self.assertEqual(item.input["apiKey"], REDACTED)
        self.assertEqual(len(item.inputFingerprint), 64)

    def testFailAndDenyRecordStableCodes(self) -> None:
        item = runFor(approvedDefinition())
        item.deny("AI_AGENT_DENIED", now=CLOCK)
        self.assertEqual(item.status, "DENIED")
        self.assertEqual(item.errorCode, "AI_AGENT_DENIED")
        self.assertTrue(item.isTerminal)
        other = runFor(approvedDefinition())
        other.transitionTo("RUNNING", now=CLOCK)
        other.fail("AI_AGENT_BUDGET_EXCEEDED", now=CLOCK)
        self.assertEqual(other.status, "FAILED")

    def testToDomainExecutionBridgesToPhaseB(self) -> None:
        item = runFor(approvedDefinition(), requestedBy=ALICE)
        base: AIAgentExecution = item.toDomainExecution()
        self.assertEqual(base.id, item.id)
        self.assertEqual(base.agentId, item.agentId)
        self.assertEqual(base.requestedBy, ALICE)
        self.assertEqual(base.status, item.status)


class StepTests(unittest.TestCase):
    def testToolStepsRequireAToolCode(self) -> None:
        run = runFor(approvedDefinition())
        with self.assertRaises(ValidationFailedError):
            AIAgentStep(tenantId=TENANT, runId=run.id, ordinal=1, kind="TOOL")

    def testArgumentsAreRedacted(self) -> None:
        run = runFor(approvedDefinition())
        step = AIAgentStep(
            tenantId=TENANT,
            runId=run.id,
            ordinal=1,
            kind="TOOL",
            status="SUCCEEDED",
            toolCode="SEARCH_PROJECT",
            toolVersion=1,
            arguments={"apiKey": "raw", "projectId": "P-1"},
        )
        self.assertEqual(step.arguments["apiKey"], REDACTED)
        self.assertEqual(step.arguments["projectId"], "P-1")

    def testKindsAndStatusesAreClosed(self) -> None:
        run = runFor(approvedDefinition())
        for badKind in ("HTTP", "QUEUE"):
            with self.assertRaises(ValidationFailedError):
                AIAgentStep(tenantId=TENANT, runId=run.id, ordinal=1, kind=badKind)
        for badStatus in ("PENDING", "RUNNING"):
            with self.assertRaises(ValidationFailedError):
                AIAgentStep(
                    tenantId=TENANT, runId=run.id, ordinal=1, kind="MODEL", status=badStatus
                )
        self.assertTrue(
            AIAgentStep(tenantId=TENANT, runId=run.id, ordinal=1, kind="MODEL").isModelCall
        )


class GatekeeperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gatekeeper = AgentGatekeeper()
        self.policy = AgentPolicy()
        self.approval = AIAgentApproval(
            tenantId=TENANT,
            agentCode="ANALYST",
            agentVersion=1,
            inputFingerprint=inputFingerprint("ANALYST", 1, {"task": "a"}),
            requiredApprovals=1,
            requestedBy=ALICE,
            createdAt=CLOCK,
            expiresAt=CLOCK + timedelta(hours=1),
        )
        self.approval.grant(BOB, now=CLOCK)

    def decide(
        self,
        *,
        definition: AIAgentDefinition,
        permitted: bool = True,
        capabilitiesAvailable: bool = True,
        approval: AIAgentApproval | None = None,
    ) -> Any:
        return self.gatekeeper.decide(
            definition,
            self.policy,
            permitted=permitted,
            capabilitiesAvailable=capabilitiesAvailable,
            approval=approval,
            now=CLOCK,
        )

    def testDraftAndSuspendedAgentsAreBlocked(self) -> None:
        decision = self.decide(definition=definition())
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.errorCode, "AI_AGENT_NOT_APPROVED")
        suspended = approvedDefinition()
        suspended.suspend(now=CLOCK)
        blocked = self.decide(definition=suspended)
        self.assertTrue(blocked.blocked)
        self.assertEqual(blocked.errorCode, "AI_AGENT_NOT_APPROVED")

    def testMissingPermissionDenies(self) -> None:
        decision = self.decide(definition=approvedDefinition(), permitted=False)
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.errorCode, "AI_AGENT_DENIED")

    def testUnavailableCapabilitiesBlock(self) -> None:
        decision = self.decide(definition=approvedDefinition(), capabilitiesAvailable=False)
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.errorCode, "AI_AGENT_POLICY_INVALID")

    def testHighRiskWithoutApprovalAsksForIt(self) -> None:
        decision = self.decide(definition=approvedDefinition(riskLevel="HIGH"))
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.errorCode, "AI_AGENT_APPROVAL_REQUIRED")
        self.assertTrue(decision.requiresApproval)
        self.assertEqual(decision.approvalsNeeded, 1)

    def testDeniedApprovalDenies(self) -> None:
        denied = AIAgentApproval(
            tenantId=TENANT,
            agentCode="ANALYST",
            agentVersion=1,
            inputFingerprint=inputFingerprint("ANALYST", 1, {"task": "a"}),
            requiredApprovals=1,
            requestedBy=ALICE,
            createdAt=CLOCK,
            expiresAt=CLOCK + timedelta(hours=1),
        )
        denied.deny("No", approverId=BOB, now=CLOCK)
        decision = self.decide(definition=approvedDefinition(riskLevel="HIGH"), approval=denied)
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.errorCode, "AI_AGENT_DENIED")

    def testPendingApprovalStillAsks(self) -> None:
        pending = AIAgentApproval(
            tenantId=TENANT,
            agentCode="ANALYST",
            agentVersion=1,
            inputFingerprint=inputFingerprint("ANALYST", 1, {"task": "a"}),
            requiredApprovals=2,
            requestedBy=ALICE,
            createdAt=CLOCK,
            expiresAt=CLOCK + timedelta(hours=1),
        )
        pending.grant(BOB, now=CLOCK)  # one of two
        decision = self.decide(
            definition=approvedDefinition(riskLevel="CRITICAL"), approval=pending
        )
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.errorCode, "AI_AGENT_APPROVAL_REQUIRED")

    def testUsableApprovalAllows(self) -> None:
        decision = self.decide(
            definition=approvedDefinition(riskLevel="HIGH"), approval=self.approval
        )
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requiresApproval)  # the mode needs it
        self.assertEqual(decision.approvalsNeeded, 1)  # and it is satisfied

    def testAutomaticRiskNeedsNoApproval(self) -> None:
        decision = self.decide(definition=approvedDefinition(riskLevel="LOW"))
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.approvalMode, "AUTOMATIC")


class BudgetTests(unittest.TestCase):
    def testStepCeilingIsEnforced(self) -> None:
        budget = AgentRunBudget(
            maxSteps=2, maxToolCalls=5, maxRepeats=2, maxDurationSeconds=60, startedAt=CLOCK
        )
        budget.checkModelCall(CLOCK)
        budget.checkModelCall(CLOCK)
        with self.assertRaises(AIAgentBudgetExceeded):
            budget.checkModelCall(CLOCK)

    def testToolCallCeilingCountsDeniedAttempts(self) -> None:
        budget = AgentRunBudget(
            maxSteps=10, maxToolCalls=2, maxRepeats=5, maxDurationSeconds=60, startedAt=CLOCK
        )
        budget.checkToolCall("fp-1", CLOCK)
        budget.checkToolCall("fp-2", CLOCK)
        with self.assertRaises(AIAgentBudgetExceeded):
            budget.checkToolCall("fp-3", CLOCK)

    def testRepeatDetectionAccumulatesAcrossSteps(self) -> None:
        budget = AgentRunBudget(
            maxSteps=10, maxToolCalls=10, maxRepeats=2, maxDurationSeconds=60, startedAt=CLOCK
        )
        # The same fingerprint in three different "steps" is a loop.
        budget.checkToolCall("same", CLOCK)
        budget.checkToolCall("same", CLOCK)
        with self.assertRaises(AIAgentBudgetExceeded):
            budget.checkToolCall("same", CLOCK)

    def testDurationCeilingUsesTheInjectedClock(self) -> None:
        ticks = [CLOCK]

        def clock() -> datetime:
            ticks[0] = ticks[0] + timedelta(seconds=31)
            return ticks[0]

        budget = AgentRunBudget(
            maxSteps=10,
            maxToolCalls=10,
            maxRepeats=5,
            maxDurationSeconds=60,
            startedAt=CLOCK,
            clock=clock,
        )
        budget.checkModelCall()  # t+31, still inside
        with self.assertRaises(AIAgentBudgetExceeded):
            budget.checkModelCall()  # t+62 → over the 60s ceiling

    def testForRunTakesTheMinimumOfPolicyAndDefinition(self) -> None:
        policy = AgentPolicy(maxSteps=10, maxToolCalls=20, maxDurationSeconds=120)
        strict = approvedDefinition(
            executionPolicy={"maxSteps": 3, "maxToolCalls": 5, "maxDurationSeconds": 30}
        )
        budget = AgentRunBudget.forRun(policy, strict, now=CLOCK)
        self.assertEqual(budget.maxSteps, 3)
        self.assertEqual(budget.maxToolCalls, 5)
        self.assertEqual(budget.maxDurationSeconds, 30)
        relaxed = approvedDefinition()
        default = AgentRunBudget.forRun(policy, relaxed, now=CLOCK)
        self.assertEqual(default.maxSteps, 10)
        self.assertEqual(default.maxToolCalls, 20)

    def testTokenAccountingAccumulates(self) -> None:
        budget = AgentRunBudget(
            maxSteps=10, maxToolCalls=10, maxRepeats=5, maxDurationSeconds=60, startedAt=CLOCK
        )
        budget.checkModelCall(CLOCK)
        budget.recordModel(100, 40)
        budget.checkModelCall(CLOCK)
        budget.recordModel(50, 10)
        self.assertEqual(budget.inputTokens, 150)
        self.assertEqual(budget.outputTokens, 50)
        self.assertEqual(budget.totalTokens, 200)
        self.assertEqual(budget.modelCalls, 2)


class ContextBuilderTests(unittest.TestCase):
    def build(self, **overrides: object) -> Any:
        params: dict = {"maxContextTokens": 100_000}
        params.update(overrides)
        definition = approvedDefinition()
        run = runFor(definition)
        return AgentContextBuilder().build(definition, run, **params)

    def testAssemblesAllSections(self) -> None:
        memory = AgentMemoryContext(
            text="remembered fact", sources=("memory:AGENT:pref",), tokenCount=3, entryCount=1
        )
        knowledge = AgentKnowledgeContext(
            text="policy text", sources=("knowledge:doc-1",), tokenCount=2, chunkCount=1
        )
        context: AgentContext = self.build(memory=memory, knowledge=knowledge)
        rendered = context.render()
        self.assertIn("Analyze the project and report risks.", rendered)
        self.assertIn("remembered fact", rendered)
        self.assertIn("policy text", rendered)
        self.assertIn('"task": "status report"', rendered)
        self.assertEqual(context.sources, ("memory:AGENT:pref", "knowledge:doc-1"))
        self.assertGreater(context.totalTokens, 0)

    def testTokenCeilingIsFailClosed(self) -> None:
        definition = approvedDefinition(
            instructions="x" * 4000  # well beyond a tiny ceiling
        )
        run = runFor(definition)
        with self.assertRaises(AIContextTooLarge):
            AgentContextBuilder().build(definition, run, maxContextTokens=50)

    def testMissingProvidersMeanEmptySections(self) -> None:
        context = self.build()
        self.assertEqual(context.memorySources, ())
        self.assertEqual(context.knowledgeSources, ())
        self.assertNotIn("remembered", context.render())


class PlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.definition = approvedDefinition(
            accessLevel="READ_ONLY",
            toolCodes=("SEARCH_PROJECT",),
        )
        self.runRecord = runFor(self.definition)
        self.runRecord.transitionTo("RUNNING", now=CLOCK)
        self.context = AgentContextBuilder().build(
            self.definition, self.runRecord, maxContextTokens=100_000
        )
        self.budget = AgentRunBudget(
            maxSteps=10, maxToolCalls=10, maxRepeats=2, maxDurationSeconds=3600, startedAt=CLOCK
        )
        self.declarations = (
            AgentToolDeclaration(
                code="SEARCH_PROJECT",
                version=1,
                name="Search project",
                description="Finds a project.",
                effect="READ_ONLY",
            ),
        )
        self.steps: list[Any] = []
        self.executor = RecordingExecutor()
        self.caller = ScriptedCaller([])
        self.planner = AgentPlanner(self.caller, self.executor, clock=lambda: CLOCK)

    def makeCaller(self, replies: list[Any]) -> ScriptedCaller:
        self.caller = ScriptedCaller(replies)
        self.planner = AgentPlanner(self.caller, self.executor, clock=lambda: CLOCK)
        return self.caller

    def runLoop(self) -> Any:
        return self.planner.run(
            TENANT,
            self.definition,
            self.runRecord,
            self.context,
            self.budget,
            principal=ALICE,
            declarations=self.declarations,
            on_step=self.steps.append,
        )

    def testAnswerOnFirstCallCompletes(self) -> None:
        self.makeCaller([AgentModelReply(answer="all good", inputTokens=10, outputTokens=5)])
        outcome = self.runLoop()
        self.assertEqual(outcome.status, "COMPLETED")
        self.assertEqual(outcome.answer, "all good")
        self.assertEqual(len(outcome.steps), 1)
        self.assertEqual(outcome.steps[0].kind, "MODEL")
        self.assertEqual(len(self.steps), 1)  # persisted through the callback
        self.assertEqual(self.executor.calls, [])

    def testProposalThenAnswerIsTheHappyPath(self) -> None:
        self.executor = RecordingExecutor(
            [AgentToolOutcome(status="SUCCEEDED", result={"found": 3, "projectId": "P-1"})]
        )
        self.makeCaller(
            [
                AgentModelReply(
                    proposals=(
                        ToolProposal(toolCode="SEARCH_PROJECT", arguments={"projectId": "P-1"}),
                    )
                ),
                AgentModelReply(answer="found it", inputTokens=9, outputTokens=4),
            ]
        )
        outcome = self.runLoop()
        self.assertEqual(outcome.status, "COMPLETED")
        self.assertEqual([step.kind for step in outcome.steps], ["TOOL", "MODEL"])
        self.assertEqual(outcome.steps[0].status, "SUCCEEDED")
        self.assertEqual(self.executor.calls[0][0].toolCode, "SEARCH_PROJECT")
        # Y-D12: the run's principal — not the agent — executes the tool.
        self.assertEqual(self.executor.calls[0][1], ALICE)
        # The second request carries the first step's result in its history.
        self.assertEqual(len(self.caller.requests[1].history), 1)
        self.assertIn("P-1", self.caller.requests[1].contextText)

    def testProposalBeyondTheAccessLevelNeverReachesTheExecutor(self) -> None:
        mutating = (
            AgentToolDeclaration(
                code="CREATE_TASK",
                version=1,
                name="Create task",
                description="Creates a task.",
                effect="MUTATING",
            ),
            *self.declarations,
        )
        self.makeCaller(
            [
                AgentModelReply(proposals=(ToolProposal(toolCode="CREATE_TASK", arguments={}),)),
                AgentModelReply(answer="gave up"),
            ]
        )
        self.planner = AgentPlanner(self.caller, self.executor, clock=lambda: CLOCK)
        outcome = self.planner.run(
            TENANT,
            self.definition,
            self.runRecord,
            self.context,
            self.budget,
            principal=ALICE,
            declarations=mutating,
            on_step=self.steps.append,
        )
        self.assertEqual(outcome.status, "COMPLETED")
        toolStep = outcome.steps[0]
        self.assertEqual(toolStep.status, "DENIED")
        self.assertEqual(toolStep.errorCode, STEP_TOOL_ACCESS_DENIED)
        self.assertEqual(self.executor.calls, [])  # structural guarantee

    def testUndeclaredToolIsDenied(self) -> None:
        self.makeCaller(
            [
                AgentModelReply(proposals=(ToolProposal(toolCode="SEND_EMAIL", arguments={}),)),
                AgentModelReply(answer="done"),
            ]
        )
        outcome = self.runLoop()
        self.assertEqual(outcome.steps[0].status, "DENIED")
        self.assertEqual(outcome.steps[0].errorCode, STEP_TOOL_NOT_DECLARED)
        self.assertEqual(self.executor.calls, [])

    def testAdvisoryAgentCannotProposeAnyTool(self) -> None:
        advisory = approvedDefinition(accessLevel="ADVISORY", toolCodes=("SEARCH_PROJECT",))
        advisoryRun = runFor(advisory)
        advisoryRun.transitionTo("RUNNING", now=CLOCK)
        advisoryContext = AgentContextBuilder().build(
            advisory, advisoryRun, maxContextTokens=100_000
        )
        self.makeCaller(
            [
                AgentModelReply(proposals=(ToolProposal(toolCode="SEARCH_PROJECT", arguments={}),)),
                AgentModelReply(answer="text only"),
            ]
        )
        self.planner = AgentPlanner(self.caller, self.executor, clock=lambda: CLOCK)
        outcome = self.planner.run(
            TENANT,
            advisory,
            advisoryRun,
            advisoryContext,
            self.budget,
            declarations=self.declarations,
            on_step=self.steps.append,
        )
        self.assertEqual(outcome.steps[0].errorCode, STEP_TOOL_ACCESS_DENIED)
        self.assertEqual(self.executor.calls, [])

    def testAwaitingApprovalToolIsDeniedNotPaused(self) -> None:
        self.executor = RecordingExecutor(
            [AgentToolOutcome(status="AWAITING_APPROVAL", reason="A human must approve this call.")]
        )
        self.planner = AgentPlanner(self.caller, self.executor, clock=lambda: CLOCK)
        self.makeCaller(
            [
                AgentModelReply(
                    proposals=(
                        ToolProposal(toolCode="SEARCH_PROJECT", arguments={"projectId": "P-9"}),
                    )
                ),
                AgentModelReply(answer="without the data"),
            ]
        )
        outcome = self.runLoop()
        self.assertEqual(outcome.steps[0].status, "DENIED")
        self.assertEqual(outcome.steps[0].errorCode, STEP_TOOL_APPROVAL_REQUIRED)
        self.assertEqual(outcome.status, "COMPLETED")

    def testToolFailureIsRecordedAndTheModelDecides(self) -> None:
        self.executor = RecordingExecutor(
            [AgentToolOutcome(status="FAILED", errorCode="AI_TOOL_EXECUTION_FAILED", reason="boom")]
        )
        self.planner = AgentPlanner(self.caller, self.executor, clock=lambda: CLOCK)
        self.makeCaller(
            [
                AgentModelReply(
                    proposals=(
                        ToolProposal(toolCode="SEARCH_PROJECT", arguments={"projectId": "P-1"}),
                    )
                ),
                AgentModelReply(answer="tool failed, here is what I know"),
            ]
        )
        outcome = self.runLoop()
        self.assertEqual(outcome.steps[0].status, "FAILED")
        self.assertEqual(outcome.status, "COMPLETED")

    def testRepeatAcrossStepsIsALoop(self) -> None:
        proposal = AgentModelReply(
            proposals=(ToolProposal(toolCode="SEARCH_PROJECT", arguments={"projectId": "P-1"}),)
        )
        self.makeCaller([proposal, proposal, proposal])
        with self.assertRaises(AIAgentBudgetExceeded):
            self.runLoop()
        # Two attempts executed and were recorded; the third was refused
        # by the budget *before* it could become a row (Phase 13-X
        # semantics: the check happens before the record).
        self.assertEqual(len(self.steps), 2)

    def testStepBudgetExhaustionFailsTheRun(self) -> None:
        self.budget = AgentRunBudget(
            maxSteps=2, maxToolCalls=10, maxRepeats=5, maxDurationSeconds=3600, startedAt=CLOCK
        )
        self.makeCaller(
            [
                AgentModelReply(
                    proposals=(
                        ToolProposal(toolCode="SEARCH_PROJECT", arguments={"projectId": f"P-{i}"}),
                    )
                )
                for i in range(4)
            ]
        )
        with self.assertRaises(AIAgentBudgetExceeded):
            self.runLoop()

    def testDurationExhaustionFailsTheRun(self) -> None:
        ticks = [CLOCK]

        def clock() -> datetime:
            ticks[0] = ticks[0] + timedelta(seconds=10)
            return ticks[0]

        self.budget = AgentRunBudget(
            maxSteps=10,
            maxToolCalls=10,
            maxRepeats=5,
            maxDurationSeconds=25,
            startedAt=CLOCK,
            clock=clock,
        )
        self.makeCaller(
            [
                AgentModelReply(
                    proposals=(
                        ToolProposal(toolCode="SEARCH_PROJECT", arguments={"projectId": f"P-{i}"}),
                    )
                )
                for i in range(6)
            ]
        )
        self.planner = AgentPlanner(self.caller, self.executor, clock=clock)
        with self.assertRaises(AIAgentBudgetExceeded):
            self.runLoop()

    def testInvalidReplyShapesAreRefused(self) -> None:
        with self.assertRaises(AIAgentInvalid):
            AgentModelReply(answer="x", proposals=(ToolProposal(toolCode="SEARCH_PROJECT"),))
        with self.assertRaises(AIAgentInvalid):
            AgentModelReply()  # neither an answer nor a proposal
        # A caller that returns something that is not a reply is refused
        # by the planner, not interpreted.
        self.caller = ScriptedCaller([{"answer": "not a reply"}])
        self.planner = AgentPlanner(self.caller, self.executor, clock=lambda: CLOCK)
        with self.assertRaises(AIAgentInvalid):
            self.runLoop()

    def testStructuredOutputIsValidatedAgainstTheSchema(self) -> None:
        definition = approvedDefinition(
            outputSchema={"type": "object", "required": ["summary"]},
        )
        run = runFor(definition)
        run.transitionTo("RUNNING", now=CLOCK)
        context = AgentContextBuilder().build(definition, run, maxContextTokens=100_000)
        self.makeCaller([AgentModelReply(answer="x", structured={"wrong": True})])
        self.planner = AgentPlanner(self.caller, self.executor, clock=lambda: CLOCK)
        with self.assertRaises(AIAgentOutputInvalid):
            self.planner.run(
                TENANT,
                definition,
                run,
                context,
                self.budget,
                declarations=self.declarations,
                on_step=self.steps.append,
            )
        # A conforming payload passes.
        run2 = runFor(definition)
        run2.transitionTo("RUNNING", now=CLOCK)
        self.makeCaller([AgentModelReply(answer="x", structured={"summary": "ok"})])
        outcome = self.planner.run(
            TENANT,
            definition,
            run2,
            context,
            self.budget,
            declarations=self.declarations,
            on_step=self.steps.append,
        )
        self.assertEqual(outcome.output, {"summary": "ok"})

    def testPlannerRefusesNonApprovedDefinitions(self) -> None:
        draft = definition()
        with self.assertRaises(AIAgentNotApproved):
            self.planner.run(
                TENANT,
                draft,
                self.runRecord,
                self.context,
                self.budget,
                declarations=self.declarations,
                on_step=self.steps.append,
            )

    def testDeniedAttemptsCountTowardTheRepeatBudget(self) -> None:
        # An out-of-level proposal that repeats is a loop even though it
        # never executes (Phase 13-X semantics: denied attempts count).
        mutating = (
            AgentToolDeclaration(
                code="CREATE_TASK",
                version=1,
                name="Create task",
                description="Creates a task.",
                effect="MUTATING",
            ),
            *self.declarations,
        )
        self.planner = AgentPlanner(self.caller, self.executor, clock=lambda: CLOCK)
        proposal = AgentModelReply(proposals=(ToolProposal(toolCode="CREATE_TASK", arguments={}),))
        self.makeCaller([proposal, proposal, proposal])
        with self.assertRaises(AIAgentBudgetExceeded):
            self.planner.run(
                TENANT,
                self.definition,
                self.runRecord,
                self.context,
                self.budget,
                declarations=mutating,
                on_step=self.steps.append,
            )
        self.assertEqual(self.executor.calls, [])


if __name__ == "__main__":
    unittest.main()
