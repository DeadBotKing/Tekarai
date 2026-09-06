"""Phase 13-Y application tests — the §31 chain over a real SQLite DB.

Covers the registry lifecycle and versioning, execution through the
**real** Phase 13-K authorization service and the **real** Phase 13-X
tool chain (one executor, two consumers), the two axes of Open
Question #11 — the structural access level and the risk-driven
approval with dual control — fingerprint binding, TTL, denial
stickiness, the plan-act loop with its step history, memory and
knowledge wiring, secret redaction in run rows, tenant isolation,
retention, the fail-closed switch, and the Phase 13-O audit trail.

The central assertion of the suite is §31's rule: an agent is not a
prompt. Its proposals reach tools only through the registry, the
access level, the budget, and — when risk demands it — a human.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from django.test import TestCase

from apps.ai.application.services.agentService import (
    AUDIT_AGENT_APPROVED,
    AUDIT_AGENT_DENIED,
    AUDIT_AGENT_INVOKED,
    AUDIT_AGENT_REGISTERED,
    AgentApplicationService,
    AgentSettings,
    RegisterAgentCommand,
    RunAgentCommand,
    ScriptedAgentModelCaller,
    ToolExecutorAdapter,
)
from apps.ai.application.services.auditService import AuditApplicationService, AuditSettings
from apps.ai.application.services.toolService import (
    CallableToolRunner,
    ToolApplicationService,
    ToolSettings,
)
from apps.ai.domain.exceptions import (
    AIAgentAlreadyRegistered,
    AIAgentApprovalNotFound,
    AIAgentInvalid,
    AIAgentNotApproved,
    AIAgentNotFound,
    AIConfigurationError,
)
from apps.ai.domain.services.agentEngine import (
    AgentKnowledgeContext,
    AgentMemoryContext,
    AgentModelReply,
)
from apps.ai.domain.services.authorizationService import (
    AuthorizationPrincipal,
    AuthorizationService,
    PermissionGrant,
)
from apps.ai.domain.services.toolEngine import ToolProposal
from apps.ai.infrastructure.models import (
    AIAgentApprovalModel,
    AIAgentRunModel,
    AIToolInvocationModel,
)
from apps.ai.infrastructure.repositories.agentRepositories import (
    DjangoAgentApprovalStore,
    DjangoAgentDefinitionStore,
    DjangoAgentExecutionStore,
)
from apps.ai.infrastructure.repositories.auditRepositories import (
    DjangoAuditRecordStore,
    DjangoGovernancePolicyStore,
    DjangoRetentionPurger,
)
from apps.ai.infrastructure.repositories.toolRepositories import (
    DjangoToolApprovalStore,
    DjangoToolDefinitionStore,
    DjangoToolInvocationStore,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 6, 9, 0, 0, tzinfo=UTC)
AGENT_INPUT_SCHEMA: dict[str, Any] = {"type": "object", "required": ["task"]}


class StubCapabilityResolver:
    def __init__(self, codes: frozenset[str]) -> None:
        self._codes = codes

    def availableCodes(self, tenantId: Any) -> frozenset[str]:
        return self._codes


class StubMemoryProvider:
    def __init__(self, context: AgentMemoryContext | None = None, fail: bool = False) -> None:
        self._context = context or AgentMemoryContext()
        self._fail = fail
        self.calls: list[Any] = []

    def contextFor(self, tenantId: Any, principal: Any, definition: Any) -> AgentMemoryContext:
        self.calls.append((tenantId, principal, definition))
        if self._fail:
            raise RuntimeError("memory store down")
        return self._context


class StubKnowledgeProvider:
    def __init__(self, context: AgentKnowledgeContext | None = None, fail: bool = False) -> None:
        self._context = context or AgentKnowledgeContext()
        self._fail = fail
        self.calls: list[Any] = []

    def searchFor(
        self, tenantId: Any, principal: Any, definition: Any, query: str
    ) -> AgentKnowledgeContext:
        self.calls.append((tenantId, principal, definition, query))
        if self._fail:
            raise RuntimeError("retrieval down")
        return self._context


class AgentTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.alice = uuid.uuid4()  # the human who runs agents
        self.bob = uuid.uuid4()  # approver one
        self.carol = uuid.uuid4()  # approver two
        self.definitionStore = DjangoAgentDefinitionStore()
        self.approvalStore = DjangoAgentApprovalStore()
        self.executionStore = DjangoAgentExecutionStore()
        self.audit = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=AuditSettings(enabled=True, retentionDays=365),
            now=lambda: CLOCK,
        )
        self.authorization = AuthorizationService(now=lambda: CLOCK)
        self.principal = AuthorizationPrincipal(
            tenantId=self.tenantId, subjectId=self.alice, roles=("OPERATOR",)
        )
        self.toolCalls: list[dict[str, Any]] = []
        self.toolRunner = CallableToolRunner(
            {
                "SEARCH_PROJECT": self.searchProject,
                "CREATE_TASK": self.createTask,
                "SEND_EMAIL": self.sendEmail,
                "DELETE_PROJECT": self.deleteProject,
            }
        )
        self.toolService = ToolApplicationService(
            DjangoToolDefinitionStore(),
            DjangoToolInvocationStore(),
            DjangoToolApprovalStore(),
            runners=[self.toolRunner],
            permissionChecker=self.authorization,
            settings=ToolSettings(enabled=True),
            now=lambda: CLOCK,
        )
        self.caller = ScriptedAgentModelCaller()
        self.memoryProvider = StubMemoryProvider()
        self.knowledgeProvider = StubKnowledgeProvider()
        self.service = self.buildService()

    # -- doubles --------------------------------------------------------
    def searchProject(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.toolCalls.append(arguments)
        return {"found": True, "projectId": arguments.get("projectId")}

    def createTask(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.toolCalls.append(arguments)
        return {"created": arguments.get("title")}

    def sendEmail(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.toolCalls.append(arguments)
        return {"sent": True, "to": arguments.get("to")}

    def deleteProject(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.toolCalls.append(arguments)
        return {"deleted": arguments.get("projectId")}

    # -- helpers --------------------------------------------------------
    def buildService(self, **overrides: Any) -> AgentApplicationService:
        settings = AgentSettings(
            enabled=overrides.pop("enabled", True),
            automaticBelowRisk=overrides.pop("automaticBelowRisk", "HIGH"),
            dualControlAtRisk=overrides.pop("dualControlAtRisk", "CRITICAL"),
            maxStepsPerRun=overrides.pop("maxStepsPerRun", 10),
            maxToolCallsPerRun=overrides.pop("maxToolCallsPerRun", 20),
            maxRepeatsPerRun=overrides.pop("maxRepeatsPerRun", 2),
            maxDurationSeconds=overrides.pop("maxDurationSeconds", 120),
            maxContextTokens=overrides.pop("maxContextTokens", 16_000),
            approvalTtlSeconds=overrides.pop("approvalTtlSeconds", 3600),
            retentionDays=overrides.pop("retentionDays", 365),
        )
        return AgentApplicationService(
            self.definitionStore,
            self.approvalStore,
            self.executionStore,
            permissionChecker=overrides.pop("permissionChecker", self.authorization),
            capabilityResolver=overrides.pop(
                "capabilityResolver", StubCapabilityResolver(frozenset({"SUMMARIZATION"}))
            ),
            memoryProvider=overrides.pop("memoryProvider", self.memoryProvider),
            knowledgeProvider=overrides.pop("knowledgeProvider", self.knowledgeProvider),
            toolExecutor=overrides.pop("toolExecutor", ToolExecutorAdapter(self.toolService)),
            modelCaller=overrides.pop("modelCaller", self.caller),
            settings=settings,
            auditLogger=overrides.pop("auditLogger", self.audit),
            now=lambda: CLOCK,
        )

    def registerTool(self, **overrides: Any) -> Any:
        from apps.ai.application.services.toolService import RegisterToolCommand

        params: dict[str, Any] = {
            "code": "SEARCH_PROJECT",
            "name": "Search project",
            "description": "Finds a project.",
            "inputSchema": {"type": "object", "required": ["projectId"]},
            "riskLevel": "LOW",
        }
        params.update(overrides)
        return self.toolService.registerTool(self.tenantId, RegisterToolCommand(**params))

    def approveTool(self, code: str = "SEARCH_PROJECT", version: int = 1) -> None:
        self.toolService.submitForApproval(self.tenantId, code, version)
        self.toolService.approveTool(self.tenantId, code, version, approverId=self.bob)

    def setupToolPlatform(self) -> None:
        self.registerTool()
        self.approveTool()

    def registerAgent(self, **overrides: Any) -> Any:
        params: dict[str, Any] = {
            "code": "ANALYST",
            "name": "Project analyst",
            "instructions": "Analyze the project and report risks.",
            "accessLevel": "READ_ONLY",
            "riskLevel": "LOW",
            "toolCodes": ("SEARCH_PROJECT",),
        }
        params.update(overrides)
        return self.service.registerAgent(self.tenantId, RegisterAgentCommand(**params))

    def approveAgent(self, code: str = "ANALYST", version: int = 1) -> Any:
        self.service.submitForApproval(self.tenantId, code, version)
        return self.service.approveAgent(self.tenantId, code, version, approverId=self.bob)

    def setupAgentPlatform(self, **agentOverrides: Any) -> Any:
        self.setupToolPlatform()
        self.grantAgentPermission()
        self.grantToolPermission()
        self.registerAgent(**agentOverrides)
        return self.approveAgent(
            code=agentOverrides.get("code", "ANALYST"),
            version=agentOverrides.get("version", 1),
        )

    def grantAgentPermission(self, *, principal: Any | None = None) -> None:
        self.authorization.registerGrant(
            PermissionGrant(
                tenantId=self.tenantId,
                subjectId=self.alice if principal is None else principal.subjectId,
                permissionCode="AI_AGENT_RUN",
                resourceType="AI_AGENT",
            )
        )

    def grantToolPermission(self) -> None:
        self.authorization.registerGrant(
            PermissionGrant(
                tenantId=self.tenantId,
                subjectId=self.alice,
                permissionCode="AI_TOOL_EXECUTE",
                resourceType="AI_TOOL",
            )
        )

    def runAgent(self, **overrides: Any) -> Any:
        params: dict[str, Any] = {
            "agentCode": "ANALYST",
            "input": {"task": "status report"},
            "principal": self.principal,
            "actorId": self.alice,
        }
        params.update(overrides)
        return self.service.runAgent(self.tenantId, RunAgentCommand(**params))

    def auditActions(self) -> list[str]:
        return [entry.action for entry in self.audit.listAuditEntries(self.tenantId)]


class RegistryTests(AgentTestCase):
    def testRegisteringStartsInDraftAndIsAudited(self) -> None:
        descriptor = self.registerAgent()
        self.assertEqual(descriptor.status, "DRAFT")
        self.assertEqual(descriptor.version, 1)
        self.assertEqual(descriptor.approvalMode, "AUTOMATIC")
        self.assertEqual(descriptor.requiredPermission, "AI_AGENT_RUN")
        self.assertIn(AUDIT_AGENT_REGISTERED, self.auditActions())

    def testDuplicateVersionIsRejected(self) -> None:
        self.registerAgent()
        with self.assertRaises(AIAgentAlreadyRegistered):
            self.registerAgent(version=1)

    def testUnknownCapabilityIsRejectedAtRegistration(self) -> None:
        with self.assertRaises(AIAgentInvalid):
            self.registerAgent(capabilityCodes=("FLYING",))

    def testKnownCapabilityIsAccepted(self) -> None:
        descriptor = self.registerAgent(capabilityCodes=("summarization",))
        self.assertEqual(descriptor.capabilityCodes, ("SUMMARIZATION",))

    def testApprovalGateMovesEntryToApprovedAndAudits(self) -> None:
        self.registerAgent()
        approved = self.approveAgent()
        self.assertEqual(approved.status, "APPROVED")
        self.assertEqual(approved.approvedBy, self.bob)
        self.assertIn(AUDIT_AGENT_APPROVED, self.auditActions())

    def testRejectionReturnsToDraftWithAReason(self) -> None:
        self.registerAgent()
        self.service.submitForApproval(self.tenantId, "ANALYST", 1)
        rejected = self.service.rejectAgent(self.tenantId, "ANALYST", 1, "Too broad")
        self.assertEqual(rejected.status, "DRAFT")
        self.assertEqual(rejected.rejectionReason, "Too broad")

    def testPublishNewVersionClonesIntoDraft(self) -> None:
        self.registerAgent()
        successor = self.service.publishNewVersion(
            self.tenantId, "ANALYST", instructions="Tighter scope."
        )
        self.assertEqual(successor.version, 2)
        self.assertEqual(successor.status, "DRAFT")
        self.assertEqual(successor.name, "Project analyst")
        versions = self.definitionStore.listVersions(self.tenantId, "ANALYST")
        self.assertEqual([item.version for item in versions], [1, 2])

    def testRiskDrivesTheApprovalMode(self) -> None:
        self.assertEqual(self.registerAgent(riskLevel="LOW").approvalMode, "AUTOMATIC")
        self.assertEqual(
            self.registerAgent(code="MODIFIER", riskLevel="HIGH").approvalMode,
            "HUMAN_REQUIRED",
        )
        self.assertEqual(
            self.registerAgent(code="AUTONOMOUS_AGENT", riskLevel="CRITICAL").approvalMode,
            "DUAL_CONTROL",
        )

    def testAccessLevelIsVersionedAndImmutable(self) -> None:
        self.registerAgent(accessLevel="READ_ONLY")
        successor = self.service.publishNewVersion(self.tenantId, "ANALYST", accessLevel="MUTATING")
        self.assertEqual(successor.accessLevel, "MUTATING")
        first = self.definitionStore.findVersion(self.tenantId, "ANALYST", 1)
        assert first is not None
        self.assertEqual(first.accessLevel, "READ_ONLY")  # v1 unchanged

    def testTenantIsolationInTheRegistry(self) -> None:
        self.registerAgent()
        self.assertEqual(self.service.listAgents(self.otherTenantId), ())
        with self.assertRaises(AIAgentNotFound):
            self.service.describeAgent(self.otherTenantId, "ANALYST", 1)


class ExecutionGateTests(AgentTestCase):
    def testRunningWithoutPermissionDeniesAndRecordsTheRow(self) -> None:
        self.setupAgentPlatform()
        # No AI_AGENT_RUN grant for this principal:
        other = uuid.uuid4()
        stranger = AuthorizationPrincipal(
            tenantId=self.tenantId, subjectId=other, roles=("OPERATOR",)
        )
        result = self.runAgent(principal=stranger, actorId=other)
        self.assertTrue(result.denied)
        self.assertEqual(result.run.status, "DENIED")
        self.assertEqual(result.run.errorCode, "AI_AGENT_DENIED")
        self.assertFalse(result.executed)
        self.assertEqual(len(self.caller.requests), 0)  # the model never saw it
        # The row exists even though the answer was "no".
        self.assertEqual(AIAgentRunModel.objects.count(), 1)
        self.assertIn(AUDIT_AGENT_DENIED, self.auditActions())

    def testRunningWithPermissionCompletes(self) -> None:
        self.setupAgentPlatform()
        self.caller.addReply(
            AgentModelReply(answer="All risks logged.", inputTokens=10, outputTokens=5)
        )
        result = self.runAgent()
        self.assertTrue(result.completed)
        self.assertEqual(result.run.answer, "All risks logged.")
        self.assertEqual(result.run.modelCallCount, 1)
        self.assertEqual(result.run.toolCallCount, 0)
        self.assertEqual(result.run.inputTokens, 10)
        self.assertEqual(result.run.outputTokens, 5)
        self.assertIn(AUDIT_AGENT_INVOKED, self.auditActions())

    def testDraftAgentIsNotRunnable(self) -> None:
        self.setupToolPlatform()
        self.grantAgentPermission()
        self.registerAgent()  # stays DRAFT
        with self.assertRaises(AIAgentNotApproved):
            self.runAgent()

    def testSuspendedAgentIsNotRunnable(self) -> None:
        self.setupAgentPlatform()
        self.service.suspendAgent(self.tenantId, "ANALYST", 1, "Incident")
        # With no version pinned, only approved versions resolve; a
        # suspended-only registry answers "no approved version", not a run.
        with self.assertRaises(AIAgentNotApproved):
            self.runAgent()

    def testMissingPermissionCheckerRefusesToRun(self) -> None:
        self.setupAgentPlatform()
        bare = self.buildService(permissionChecker=None)
        with self.assertRaises(AIConfigurationError):
            bare.runAgent(self.tenantId, RunAgentCommand(agentCode="ANALYST"))

    def testDisabledPlatformRefuses(self) -> None:
        self.setupAgentPlatform()
        off = self.buildService(enabled=False)
        with self.assertRaises(AIConfigurationError):
            off.runAgent(self.tenantId, RunAgentCommand(agentCode="ANALYST"))

    def testOtherTenantCannotRunTheAgent(self) -> None:
        self.setupAgentPlatform()
        self.caller.addReply(AgentModelReply(answer="x"))
        with self.assertRaises(AIAgentNotFound):
            self.service.runAgent(
                self.otherTenantId,
                RunAgentCommand(agentCode="ANALYST", principal=self.principal),
            )

    def testVersionPinningUsesTheResolvedVersion(self) -> None:
        self.setupAgentPlatform()
        self.service.publishNewVersion(self.tenantId, "ANALYST", instructions="v2 instructions")
        self.approveAgent(version=2)
        self.caller.addReply(AgentModelReply(answer="from v1"))
        result = self.runAgent(version=1)
        self.assertEqual(result.run.agentVersion, 1)
        # The model saw v1's instructions, not v2's.
        self.assertIn("Analyze the project and report risks.", self.caller.requests[0].contextText)

    def testLatestApprovedVersionIsResolvedByDefault(self) -> None:
        self.setupAgentPlatform()
        self.service.publishNewVersion(self.tenantId, "ANALYST", instructions="v2 instructions")
        self.approveAgent(version=2)
        self.caller.addReply(AgentModelReply(answer="from v2"))
        result = self.runAgent()
        self.assertEqual(result.run.agentVersion, 2)
        self.assertIn("v2 instructions", self.caller.requests[0].contextText)

    def testInputSecretsAreRedactedInTheRunRow(self) -> None:
        self.setupAgentPlatform()
        self.caller.addReply(AgentModelReply(answer="ok"))
        self.runAgent(input={"task": "t", "apiKey": "raw-secret"})
        row = AIAgentRunModel.objects.get()
        self.assertEqual(row.input["apiKey"], "[REDACTED]")
        self.assertEqual(row.input["task"], "t")

    def testRunInputWithoutQuerySkipsKnowledge(self) -> None:
        self.setupAgentPlatform()
        self.caller.addReply(AgentModelReply(answer="ok"))
        self.runAgent()
        self.assertEqual(self.knowledgeProvider.calls, [])  # no "query" key


class ApprovalWorkflowTests(AgentTestCase):
    def testHighRiskOpensApprovalAndMakesNoModelCall(self) -> None:
        self.setupAgentPlatform(riskLevel="HIGH")
        result = self.runAgent()
        self.assertTrue(result.awaitingApproval)
        self.assertEqual(result.run.status, "PENDING")
        assert result.approval is not None
        self.assertEqual(result.approval.decision, "PENDING")
        self.assertEqual(result.approval.mode, "HUMAN_REQUIRED")
        self.assertEqual(result.approval.remaining, 1)
        self.assertEqual(len(self.caller.requests), 0)  # nothing ran
        self.assertEqual(AIAgentApprovalModel.objects.count(), 1)

    def testGrantedApprovalThenTheRunStarts(self) -> None:
        self.setupAgentPlatform(riskLevel="HIGH")
        first = self.runAgent()
        assert first.approval is not None
        granted = self.service.grantApproval(
            self.tenantId, first.approval.approvalId, approverId=self.bob
        )
        self.assertEqual(granted.decision, "GRANTED")
        self.caller.addReply(AgentModelReply(answer="cleared"))
        second = self.runAgent()
        self.assertTrue(second.completed)
        self.assertEqual(second.run.answer, "cleared")

    def testDualControlNeedsTwoDistinctApprovers(self) -> None:
        self.setupAgentPlatform(riskLevel="CRITICAL")
        first = self.runAgent()
        assert first.approval is not None
        approvalId = first.approval.approvalId
        afterFirst = self.service.grantApproval(self.tenantId, approvalId, approverId=self.bob)
        self.assertEqual(afterFirst.decision, "PENDING")  # one of two
        self.assertEqual(afterFirst.remaining, 1)
        with self.assertRaises(ValidationFailedError):
            self.service.grantApproval(self.tenantId, approvalId, approverId=self.bob)
        self.caller.addReply(AgentModelReply(answer="dual-cleared"))
        result = self.runAgent()
        self.assertTrue(result.awaitingApproval)  # still one approval short
        self.service.grantApproval(self.tenantId, approvalId, approverId=self.carol)
        second = self.runAgent()
        self.assertTrue(second.completed)

    def testRequesterCannotApproveTheirOwnRun(self) -> None:
        self.setupAgentPlatform(riskLevel="HIGH")
        first = self.runAgent()
        assert first.approval is not None
        with self.assertRaises(ValidationFailedError):
            self.service.grantApproval(
                self.tenantId, first.approval.approvalId, approverId=self.alice
            )

    def testDenialSticksForTheWindow(self) -> None:
        self.setupAgentPlatform(riskLevel="HIGH")
        first = self.runAgent()
        assert first.approval is not None
        self.service.denyApproval(
            self.tenantId, first.approval.approvalId, "Out of scope", approverId=self.bob
        )
        retry = self.runAgent()
        self.assertTrue(retry.denied)
        self.assertEqual(retry.run.errorCode, "AI_AGENT_DENIED")
        # No new approval row was opened — that is the anti-spam rule.
        self.assertEqual(AIAgentApprovalModel.objects.count(), 1)

    def testApprovalIsBoundToTheExactInput(self) -> None:
        self.setupAgentPlatform(riskLevel="HIGH")
        first = self.runAgent(input={"task": "analyze A"})
        assert first.approval is not None
        self.service.grantApproval(self.tenantId, first.approval.approvalId, approverId=self.bob)
        self.caller.addReply(AgentModelReply(answer="x"))
        other = self.runAgent(input={"task": "analyze B"})
        # The approval for input A does not authorize input B.
        self.assertTrue(other.awaitingApproval)
        assert other.approval is not None
        self.assertNotEqual(other.approval.approvalId, first.approval.approvalId)

    def testExpiredApprovalIsNotUsable(self) -> None:
        self.setupAgentPlatform(riskLevel="HIGH")
        first = self.runAgent()
        assert first.approval is not None
        self.service.grantApproval(self.tenantId, first.approval.approvalId, approverId=self.bob)
        # Rewind the approval expiry into the past.
        AIAgentApprovalModel.objects.filter(id=first.approval.approvalId).update(
            expiresAt=CLOCK - timedelta(seconds=1), decidedAt=CLOCK - timedelta(seconds=1)
        )
        retry = self.runAgent()
        self.assertTrue(retry.awaitingApproval)  # asked again, not executed

    def testExplicitForeignApprovalIdIsNotFound(self) -> None:
        self.setupAgentPlatform(riskLevel="HIGH")
        with self.assertRaises(AIAgentApprovalNotFound):
            self.runAgent(approvalId=uuid.uuid4())

    def testDenyingAnApprovalDeniesThePendingRun(self) -> None:
        self.setupAgentPlatform(riskLevel="HIGH")
        first = self.runAgent()
        assert first.approval is not None
        self.service.denyApproval(
            self.tenantId, first.approval.approvalId, "No", approverId=self.bob
        )
        row = AIAgentRunModel.objects.get(id=first.run.runId)
        self.assertEqual(row.status, "DENIED")


class PlanActIntegrationTests(AgentTestCase):
    def testToolProposalRunsThroughTheXChain(self) -> None:
        self.setupAgentPlatform()
        self.caller.addReply(
            AgentModelReply(
                proposals=(ToolProposal(toolCode="SEARCH_PROJECT", arguments={"projectId": "P-7"}),)
            )
        )
        self.caller.addReply(AgentModelReply(answer="found P-7"))
        result = self.runAgent()
        self.assertTrue(result.completed)
        # The X chain ran exactly once, with the run's arguments.
        self.assertEqual(self.toolCalls, [{"projectId": "P-7"}])
        invocation = AIToolInvocationModel.objects.get()
        self.assertEqual(invocation.status, "SUCCEEDED")
        self.assertEqual(invocation.actorId, self.alice)  # Y-D12: the human's identity
        steps = self.service.listSteps(self.tenantId, result.run.runId)
        self.assertEqual([step.kind for step in steps], ["TOOL", "MODEL"])
        self.assertEqual(steps[0].status, "SUCCEEDED")
        self.assertEqual(steps[0].result, {"found": True, "projectId": "P-7"})

    def testAccessLevelBlocksMutatingToolStructurally(self) -> None:
        self.setupToolPlatform()
        self.registerTool(
            code="CREATE_TASK",
            name="Create task",
            description="Creates a task.",
            effect="MUTATING",
            inputSchema={"type": "object", "required": ["title"]},
            riskLevel="MEDIUM",
        )
        self.approveTool(code="CREATE_TASK")
        self.grantAgentPermission()
        self.grantToolPermission()
        self.registerAgent(toolCodes=("SEARCH_PROJECT", "CREATE_TASK"))
        self.approveAgent()
        # The READ_ONLY analyst proposes the MUTATING tool:
        self.caller.addReply(
            AgentModelReply(
                proposals=(ToolProposal(toolCode="CREATE_TASK", arguments={"title": "T-1"}),)
            )
        )
        self.caller.addReply(AgentModelReply(answer="cannot, and will not"))
        result = self.service.runAgent(
            self.tenantId,
            RunAgentCommand(
                agentCode="ANALYST",
                input={"task": "t"},
                principal=self.principal,
                actorId=self.alice,
            ),
        )
        self.assertTrue(result.completed)
        self.assertEqual(self.toolCalls, [])  # the tool never ran
        steps = self.service.listSteps(self.tenantId, result.run.runId)
        self.assertEqual(steps[0].status, "DENIED")
        self.assertEqual(steps[0].errorCode, "AI_AGENT_ACCESS_LEVEL_EXCEEDED")

    def testAutonomousAgentMayProposeExternalTools(self) -> None:
        self.setupAgentPlatform()
        self.registerTool(
            code="SEND_EMAIL",
            name="Send email",
            description="Sends an email.",
            effect="EXTERNAL",
            inputSchema={"type": "object", "required": ["to"]},
            riskLevel="LOW",
        )
        self.approveTool(code="SEND_EMAIL")
        self.authorization.registerGrant(
            PermissionGrant(
                tenantId=self.tenantId,
                subjectId=self.alice,
                permissionCode="AI_TOOL_EXECUTE",
                resourceType="AI_TOOL",
                resourceId="SEND_EMAIL",
            )
        )
        self.registerAgent(code="DISPATCHER", accessLevel="AUTONOMOUS", toolCodes=("SEND_EMAIL",))
        self.approveAgent(code="DISPATCHER")
        self.caller.addReply(
            AgentModelReply(
                proposals=(ToolProposal(toolCode="SEND_EMAIL", arguments={"to": "a@b.c"}),)
            )
        )
        self.caller.addReply(AgentModelReply(answer="sent"))
        result = self.service.runAgent(
            self.tenantId,
            RunAgentCommand(
                agentCode="DISPATCHER",
                input={"task": "notify"},
                principal=self.principal,
                actorId=self.alice,
            ),
        )
        self.assertTrue(result.completed)
        self.assertEqual(self.toolCalls, [{"to": "a@b.c"}])

    def testUndeclaredToolIsDeniedWithAStepRow(self) -> None:
        self.setupAgentPlatform()
        self.caller.addReply(
            AgentModelReply(
                proposals=(ToolProposal(toolCode="WIPE_DATABASE", version=1, arguments={}),)
            )
        )
        self.caller.addReply(AgentModelReply(answer="no such tool"))
        result = self.runAgent()
        steps = self.service.listSteps(self.tenantId, result.run.runId)
        self.assertEqual(steps[0].status, "DENIED")
        self.assertEqual(steps[0].errorCode, "AI_AGENT_TOOL_NOT_DECLARED")

    def testAwaitingApprovalToolDoesNotPauseTheRun(self) -> None:
        # Y-D11: a HIGH-risk tool asked for mid-run is not executed; the
        # model is told so and the run continues.
        self.setupAgentPlatform()
        self.registerTool(
            code="DELETE_PROJECT",
            name="Delete project",
            description="Deletes a project.",
            effect="MUTATING",
            inputSchema={"type": "object", "required": ["projectId"]},
            riskLevel="HIGH",
        )
        self.approveTool(code="DELETE_PROJECT")
        self.registerAgent(code="CLEANER", accessLevel="MUTATING", toolCodes=("DELETE_PROJECT",))
        self.approveAgent(code="CLEANER")
        self.caller.addReply(
            AgentModelReply(
                proposals=(ToolProposal(toolCode="DELETE_PROJECT", arguments={"projectId": "P-9"}),)
            )
        )
        self.caller.addReply(AgentModelReply(answer="skipped the deletion"))
        result = self.service.runAgent(
            self.tenantId,
            RunAgentCommand(
                agentCode="CLEANER",
                input={"task": "clean"},
                principal=self.principal,
                actorId=self.alice,
            ),
        )
        self.assertTrue(result.completed)
        steps = self.service.listSteps(self.tenantId, result.run.runId)
        self.assertEqual(steps[0].status, "DENIED")
        self.assertEqual(steps[0].errorCode, "AI_AGENT_TOOL_APPROVAL_REQUIRED")
        # X opened its own approval and parked the call as PENDING — it
        # never executed.
        invocation = AIToolInvocationModel.objects.get()
        self.assertEqual(invocation.status, "PENDING")
        self.assertEqual(self.toolCalls, [])

    def testBudgetExhaustionFailsTheRunWithAStableCode(self) -> None:
        self.service = self.buildService(maxStepsPerRun=2)
        self.setupAgentPlatform()
        for _ in range(4):
            self.caller.addReply(
                AgentModelReply(
                    proposals=(
                        ToolProposal(toolCode="SEARCH_PROJECT", arguments={"projectId": "P-1"}),
                    )
                )
            )
        result = self.runAgent()
        self.assertEqual(result.run.status, "FAILED")
        self.assertEqual(result.run.errorCode, "AI_AGENT_BUDGET_EXCEEDED")
        self.assertIn(AUDIT_AGENT_INVOKED, self.auditActions())

    def testRepeatingTheSameCallIsALoopEvenAcrossSteps(self) -> None:
        self.setupAgentPlatform()
        for _ in range(3):
            self.caller.addReply(
                AgentModelReply(
                    proposals=(
                        ToolProposal(toolCode="SEARCH_PROJECT", arguments={"projectId": "P-1"}),
                    )
                )
            )
        result = self.runAgent()
        self.assertEqual(result.run.status, "FAILED")
        self.assertEqual(result.run.errorCode, "AI_AGENT_BUDGET_EXCEEDED")
        # Two calls executed, the third refused; all three model steps
        # plus the two tool steps are visible in the history.
        steps = self.service.listSteps(self.tenantId, result.run.runId)
        toolSteps = [step for step in steps if step.kind == "TOOL"]
        self.assertEqual(len(toolSteps), 2)

    def testScriptedCallerRunningOutFailsTheRun(self) -> None:
        self.setupAgentPlatform()
        # No replies at all: the first model call fails.
        result = self.runAgent()
        self.assertEqual(result.run.status, "FAILED")
        self.assertEqual(result.run.errorCode, "AI_AGENT_EXECUTION_FAILED")

    def testMemoryAndKnowledgeReachTheContext(self) -> None:
        self.memoryProvider = StubMemoryProvider(
            AgentMemoryContext(
                text="prefers concise answers",
                sources=("memory:AGENT:style",),
                tokenCount=4,
                entryCount=1,
            )
        )
        self.knowledgeProvider = StubKnowledgeProvider(
            AgentKnowledgeContext(
                text="Q3 targets are documented in P-900",
                sources=("knowledge:P-900",),
                tokenCount=5,
                chunkCount=1,
            )
        )
        self.service = self.buildService()
        self.setupAgentPlatform()
        self.caller.addReply(AgentModelReply(answer="with context"))
        self.runAgent(input={"task": "summarize", "query": "Q3 targets"})
        contextText = self.caller.requests[0].contextText
        self.assertIn("prefers concise answers", contextText)
        self.assertIn("Q3 targets are documented in P-900", contextText)
        # The knowledge provider got the query from the run input.
        self.assertEqual(self.knowledgeProvider.calls[0][3], "Q3 targets")

    def testFailingProvidersMeanEmptyContextNotANOpenOne(self) -> None:
        self.memoryProvider = StubMemoryProvider(fail=True)
        self.knowledgeProvider = StubKnowledgeProvider(fail=True)
        self.service = self.buildService()
        self.setupAgentPlatform()
        self.caller.addReply(AgentModelReply(answer="bare"))
        result = self.runAgent(input={"task": "summarize", "query": "anything"})
        self.assertTrue(result.completed)
        self.assertNotIn("remembered", self.caller.requests[0].contextText)

    def testPrincipalPropagatesToEveryToolCall(self) -> None:
        self.setupAgentPlatform()
        self.caller.addReply(
            AgentModelReply(
                proposals=(ToolProposal(toolCode="SEARCH_PROJECT", arguments={"projectId": "P-1"}),)
            )
        )
        self.caller.addReply(AgentModelReply(answer="ok"))
        self.runAgent()
        # The X invocation row carries the human who started the run.
        self.assertEqual(AIToolInvocationModel.objects.get().actorId, self.alice)


class RetentionTests(AgentTestCase):
    def testRetentionPurgesSettledRunsAndSparesPendingOnes(self) -> None:
        self.setupAgentPlatform()
        self.caller.addReply(AgentModelReply(answer="done"))
        settled = self.runAgent()
        # A second, HIGH-risk agent whose run waits on a human:
        self.registerAgent(code="ARCHIVIST", riskLevel="HIGH")
        self.approveAgent(code="ARCHIVIST")
        pending = self.service.runAgent(
            self.tenantId,
            RunAgentCommand(
                agentCode="ARCHIVIST",
                input={"task": "archive"},
                principal=self.principal,
                actorId=self.alice,
            ),
        )
        self.assertTrue(pending.awaitingApproval)
        # Age both rows past the retention horizon.
        AIAgentRunModel.objects.filter(id__in=[settled.run.runId, pending.run.runId]).update(
            createdAt=CLOCK - timedelta(days=400)
        )
        removedRuns, removedSteps = self.service.purgeAgentRetention(
            self.tenantId, retentionDays=365
        )
        self.assertEqual(removedRuns, 1)
        self.assertGreaterEqual(removedSteps, 1)
        self.assertIsNone(self.executionStore.getRun(self.tenantId, settled.run.runId))
        self.assertIsNotNone(self.executionStore.getRun(self.tenantId, pending.run.runId))

    def testRetentionWithoutTenantIsAGlobalSweep(self) -> None:
        self.setupAgentPlatform()
        self.caller.addReply(AgentModelReply(answer="done"))
        settled = self.runAgent()
        AIAgentRunModel.objects.filter(id=settled.run.runId).update(
            createdAt=CLOCK - timedelta(days=400)
        )
        removed, _ = self.service.purgeAgentRetention(retentionDays=365)
        self.assertEqual(removed, 1)


class AuditTests(AgentTestCase):
    def testTheFullLifecycleLeavesAnAuditTrail(self) -> None:
        self.setupAgentPlatform(riskLevel="HIGH")
        self.runAgent()  # awaiting approval
        self.service.denyApproval(
            self.tenantId,
            AIAgentApprovalModel.objects.get().id,
            "No",
            approverId=self.bob,
        )
        actions = self.auditActions()
        self.assertIn(AUDIT_AGENT_REGISTERED, actions)
        self.assertIn(AUDIT_AGENT_APPROVED, actions)  # registry approval + grant
        self.assertIn(AUDIT_AGENT_DENIED, actions)

    def testSuccessfulRunIsAuditedWithItsSources(self) -> None:
        self.setupAgentPlatform()
        self.memoryProvider = StubMemoryProvider(
            AgentMemoryContext(
                text="fact", sources=("memory:AGENT:fact",), tokenCount=1, entryCount=1
            )
        )
        self.service = self.buildService()
        self.caller.addReply(AgentModelReply(answer="ok"))
        self.runAgent()
        entries = [
            entry
            for entry in self.audit.listAuditEntries(self.tenantId)
            if entry.action == AUDIT_AGENT_INVOKED
        ]
        self.assertTrue(entries)
        self.assertTrue(any(entry.outcome == "SUCCEEDED" for entry in entries))
        self.assertIn("memory:AGENT:fact", entries[-1].contextSources)
