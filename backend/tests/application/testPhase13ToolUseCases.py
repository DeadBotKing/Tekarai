"""Phase 13-X application tests — the §30 chain over a real SQLite DB.

Covers registry administration and versioning, the permission check
through the **real** Phase 13-K authorization service, risk-driven
approval including dual control, execution through a runner, argument and
output validation, per-request budgets and loop detection, failure
recording, tenant isolation, retention, the fail-closed switch, and the
Phase 13-O audit trail.

The central assertion of the suite is §30's rule: a model proposal never
reaches a runner unless the registry, the permission check, and (when
risk demands it) a human all said yes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from django.test import TestCase

from apps.ai.application.services.auditService import AuditApplicationService, AuditSettings
from apps.ai.application.services.toolService import (
    AUDIT_TOOL_APPROVED,
    AUDIT_TOOL_DENIED,
    AUDIT_TOOL_INVOKED,
    AUDIT_TOOL_REGISTERED,
    CallableToolRunner,
    InvokeToolCommand,
    RegisterToolCommand,
    ToolApplicationService,
    ToolSettings,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIToolAlreadyRegistered,
    AIToolApprovalNotFound,
    AIToolArgumentsInvalid,
    AIToolBudgetExceeded,
    AIToolDenied,
    AIToolExecutionFailed,
    AIToolInvalid,
    AIToolNotApproved,
    AIToolNotFound,
    AIToolOutputInvalid,
)
from apps.ai.domain.services.authorizationService import (
    AuthorizationPrincipal,
    AuthorizationService,
    PermissionGrant,
)
from apps.ai.infrastructure.models import (
    AIToolApprovalModel,
    AIToolInvocationModel,
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

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
PROJECT_SCHEMA = {"type": "object", "required": ["projectId"]}


class ToolTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.alice = uuid.uuid4()
        self.bob = uuid.uuid4()
        self.clock = CLOCK
        self.definitionStore = DjangoToolDefinitionStore()
        self.invocationStore = DjangoToolInvocationStore()
        self.approvalStore = DjangoToolApprovalStore()
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
        self.calls: list[dict[str, Any]] = []
        self.runner = CallableToolRunner({"SEARCH_PROJECT": self.searchProject})
        self.service = self.buildService()

    # -- doubles --------------------------------------------------------
    def searchProject(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(arguments)
        return {"found": True, "projectId": arguments.get("projectId")}

    # -- helpers --------------------------------------------------------
    def buildService(self, **overrides: Any) -> ToolApplicationService:
        settings = ToolSettings(
            enabled=overrides.pop("enabled", True),
            automaticBelowRisk=overrides.pop("automaticBelowRisk", "HIGH"),
            dualControlAtRisk=overrides.pop("dualControlAtRisk", "CRITICAL"),
            maxCallsPerRequest=overrides.pop("maxCallsPerRequest", 10),
            maxRepeatsPerRequest=overrides.pop("maxRepeatsPerRequest", 2),
            defaultTimeoutSeconds=overrides.pop("defaultTimeoutSeconds", 30),
            maxArgumentBytes=overrides.pop("maxArgumentBytes", 16_384),
            approvalTtlSeconds=overrides.pop("approvalTtlSeconds", 3600),
            retentionDays=overrides.pop("retentionDays", 365),
        )
        return ToolApplicationService(
            self.definitionStore,
            self.invocationStore,
            self.approvalStore,
            runners=overrides.pop("runners", [self.runner]),
            permissionChecker=overrides.pop("permissionChecker", self.authorization),
            settings=settings,
            auditLogger=overrides.pop("auditLogger", self.audit),
            now=lambda: self.clock,
        )

    def register(self, **overrides: Any) -> Any:
        params: dict[str, Any] = {
            "code": "SEARCH_PROJECT",
            "name": "Search project",
            "description": "Finds a project by identifier.",
            "inputSchema": PROJECT_SCHEMA,
            "riskLevel": "LOW",
        }
        params.update(overrides)
        return self.service.registerTool(self.tenantId, RegisterToolCommand(**params))

    def approveVersion(self, code: str = "SEARCH_PROJECT", version: int = 1) -> Any:
        self.service.submitForApproval(self.tenantId, code, version)
        return self.service.approveTool(self.tenantId, code, version, approverId=self.bob)

    def grantPermission(self, *, resourceId: str = "") -> None:
        extra: dict[str, Any] = {}
        if resourceId:
            extra = {"resourceId": resourceId}
        self.authorization.registerGrant(
            PermissionGrant(
                tenantId=self.tenantId,
                subjectId=self.alice,
                permissionCode="AI_TOOL_EXECUTE",
                resourceType="AI_TOOL",
                **extra,
            )
        )

    def invoke(self, **overrides: Any) -> Any:
        params: dict[str, Any] = {
            "toolCode": "SEARCH_PROJECT",
            "arguments": {"projectId": "P-1"},
            "principal": self.principal,
            "actorId": self.alice,
        }
        params.update(overrides)
        return self.service.invokeTool(self.tenantId, InvokeToolCommand(**params))

    def auditActions(self) -> list[str]:
        return [entry.action for entry in self.audit.listAuditEntries(self.tenantId)]


class RegistryTests(ToolTestCase):
    def testRegisteringStartsInDraftAndIsAudited(self) -> None:
        descriptor = self.register()
        self.assertEqual(descriptor.status, "DRAFT")
        self.assertEqual(descriptor.version, 1)
        self.assertEqual(descriptor.approvalMode, "AUTOMATIC")
        self.assertEqual(descriptor.requiredPermission, "AI_TOOL_EXECUTE")
        self.assertIn(AUDIT_TOOL_REGISTERED, self.auditActions())

    def testRiskDrivesTheApprovalModeShownInTheRegistry(self) -> None:
        self.assertEqual(self.register(riskLevel="LOW").approvalMode, "AUTOMATIC")
        self.assertEqual(
            self.register(code="DELETE_PROJECT", riskLevel="HIGH").approvalMode,
            "HUMAN_REQUIRED",
        )
        self.assertEqual(
            self.register(code="WIPE_TENANT", riskLevel="CRITICAL").approvalMode,
            "DUAL_CONTROL",
        )

    def testTheApprovalGateMovesTheEntryToApproved(self) -> None:
        self.register()
        approved = self.approveVersion()
        self.assertEqual(approved.status, "APPROVED")
        self.assertEqual(approved.approvedBy, self.bob)
        self.assertIn(AUDIT_TOOL_APPROVED, self.auditActions())

    def testRejectionReturnsToDraftWithAReason(self) -> None:
        self.register()
        self.service.submitForApproval(self.tenantId, "SEARCH_PROJECT", 1)
        rejected = self.service.rejectTool(
            self.tenantId, "SEARCH_PROJECT", 1, "schema is too loose"
        )
        self.assertEqual(rejected.status, "DRAFT")
        self.assertEqual(rejected.rejectionReason, "schema is too loose")
        self.assertIn(AUDIT_TOOL_DENIED, self.auditActions())

    def testSuspendAndResume(self) -> None:
        self.register()
        self.approveVersion()
        self.assertEqual(
            self.service.suspendTool(self.tenantId, "SEARCH_PROJECT", 1, "incident").status,
            "SUSPENDED",
        )
        self.assertEqual(
            self.service.resumeTool(self.tenantId, "SEARCH_PROJECT", 1).status, "APPROVED"
        )

    def testANewVersionStartsAsADraftBesideTheApprovedOne(self) -> None:
        self.register()
        self.approveVersion()
        successor = self.service.publishNewVersion(
            self.tenantId, "SEARCH_PROJECT", riskLevel="HIGH"
        )
        self.assertEqual(successor.version, 2)
        self.assertEqual(successor.status, "DRAFT")
        self.assertEqual(
            self.service.describeTool(self.tenantId, "SEARCH_PROJECT", 1).status, "APPROVED"
        )

    def testDuplicateVersionsAreRefused(self) -> None:
        self.register()
        with self.assertRaises(AIToolAlreadyRegistered):
            self.register(version=1)

    def testListingFiltersByStatus(self) -> None:
        self.register()
        self.register(code="DELETE_PROJECT")
        self.approveVersion()
        self.assertEqual(len(self.service.listTools(self.tenantId)), 2)
        self.assertEqual(len(self.service.listTools(self.tenantId, statuses=("APPROVED",))), 1)

    def testUnknownToolIsNotFound(self) -> None:
        with self.assertRaises(AIToolNotFound):
            self.service.describeTool(self.tenantId, "MISSING_TOOL", 1)
        with self.assertRaises(AIToolNotFound):
            self.service.publishNewVersion(self.tenantId, "MISSING_TOOL")

    def testToolsAreTenantScoped(self) -> None:
        self.register()
        self.assertEqual(self.service.listTools(self.otherTenantId), ())
        with self.assertRaises(AIToolNotFound):
            self.service.describeTool(self.otherTenantId, "SEARCH_PROJECT", 1)

    def testInvalidCommandsAreRejected(self) -> None:
        with self.assertRaises(AIToolInvalid):
            self.service.registerTool(self.tenantId, "tool")  # type: ignore[arg-type]
        with self.assertRaises(ValidationFailedError):
            self.register(name="   ")

    def testDisabledPlatformRefusesEverything(self) -> None:
        disabled = self.buildService(enabled=False)
        with self.assertRaises(AIConfigurationError):
            disabled.listTools(self.tenantId)
        with self.assertRaises(AIConfigurationError):
            disabled.invokeTool(self.tenantId, InvokeToolCommand(toolCode="SEARCH_PROJECT"))


class ExecutionChainTests(ToolTestCase):
    """§30: registry → permission → execution, in that order, always."""

    def setUp(self) -> None:
        super().setUp()
        self.register()
        self.approveVersion()

    def testAnApprovedToolWithPermissionRuns(self) -> None:
        self.grantPermission()
        result = self.invoke()
        self.assertTrue(result.succeeded)
        self.assertEqual(result.invocation.result["found"], True)
        self.assertEqual(self.calls, [{"projectId": "P-1"}])
        self.assertIn(AUDIT_TOOL_INVOKED, self.auditActions())

    def testADraftToolNeverRuns(self) -> None:
        self.register(code="DRAFT_TOOL", inputSchema={})
        self.grantPermission()
        with self.assertRaises(AIToolNotApproved):
            self.invoke(toolCode="DRAFT_TOOL", arguments={})
        self.assertEqual(self.calls, [])

    def testASuspendedToolStopsRunning(self) -> None:
        self.grantPermission()
        self.invoke()
        self.service.suspendTool(self.tenantId, "SEARCH_PROJECT", 1, "incident")
        with self.assertRaises(AIToolNotApproved):
            self.invoke()
        self.assertEqual(len(self.calls), 1)

    def testWithoutPermissionNothingRuns(self) -> None:
        with self.assertRaises(AIToolDenied):
            self.invoke()
        self.assertEqual(self.calls, [])
        self.assertIn(AUDIT_TOOL_DENIED, self.auditActions())

    def testADeniedCallIsStillRecorded(self) -> None:
        with self.assertRaises(AIToolDenied):
            self.invoke()
        stored = AIToolInvocationModel.objects.get()
        self.assertEqual(stored.status, "DENIED")
        self.assertEqual(stored.errorCode, "AI_TOOL_DENIED")

    def testAToolScopedGrantOnlyOpensThatTool(self) -> None:
        self.register(code="DELETE_PROJECT", inputSchema={})
        self.approveVersion("DELETE_PROJECT", 1)
        self.runner.register("DELETE_PROJECT", lambda arguments: {"deleted": True})
        self.grantPermission(resourceId="SEARCH_PROJECT")
        self.assertTrue(self.invoke().succeeded)
        with self.assertRaises(AIToolDenied):
            self.invoke(toolCode="DELETE_PROJECT", arguments={})

    def testMissingPermissionCheckerFailsClosed(self) -> None:
        service = self.buildService(permissionChecker=None)
        with self.assertRaises(AIConfigurationError):
            service.invokeTool(
                self.tenantId,
                InvokeToolCommand(
                    toolCode="SEARCH_PROJECT",
                    arguments={"projectId": "P-1"},
                    principal=self.principal,
                ),
            )

    def testAMissingPrincipalIsDenied(self) -> None:
        self.grantPermission()
        with self.assertRaises(AIToolDenied):
            self.invoke(principal=None)

    def testArgumentsAreValidatedBeforeAnythingRuns(self) -> None:
        self.grantPermission()
        with self.assertRaises(AIToolArgumentsInvalid):
            self.invoke(arguments={"wrong": 1})
        self.assertEqual(self.calls, [])
        self.assertEqual(AIToolInvocationModel.objects.count(), 0)

    def testOutputIsValidatedAgainstItsSchema(self) -> None:
        self.register(
            code="STRICT_TOOL",
            inputSchema={},
            outputSchema={"type": "object", "required": ["found"]},
        )
        self.approveVersion("STRICT_TOOL", 1)
        self.runner.register("STRICT_TOOL", lambda arguments: {"other": 1})
        self.grantPermission()
        with self.assertRaises(AIToolOutputInvalid):
            self.invoke(toolCode="STRICT_TOOL", arguments={})

    def testAFailingToolIsRecordedNotSwallowed(self) -> None:
        def explode(arguments: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("upstream is down")

        self.register(code="FLAKY_TOOL", inputSchema={})
        self.approveVersion("FLAKY_TOOL", 1)
        self.runner.register("FLAKY_TOOL", explode)
        self.grantPermission()
        with self.assertRaises(AIToolExecutionFailed):
            self.invoke(toolCode="FLAKY_TOOL", arguments={})
        stored = AIToolInvocationModel.objects.get(toolCode="FLAKY_TOOL")
        self.assertEqual(stored.status, "FAILED")
        self.assertTrue(stored.errorCode)

    def testAMissingRunnerIsAConfigurationError(self) -> None:
        self.register(code="NO_RUNNER", inputSchema={})
        self.approveVersion("NO_RUNNER", 1)
        self.grantPermission()
        with self.assertRaises(AIConfigurationError):
            self.invoke(toolCode="NO_RUNNER", arguments={})

    def testSecretsNeverReachTheStore(self) -> None:
        self.register(code="AUTH_TOOL", inputSchema={})
        self.approveVersion("AUTH_TOOL", 1)
        self.runner.register("AUTH_TOOL", lambda arguments: {"ok": True})
        self.grantPermission()
        self.invoke(toolCode="AUTH_TOOL", arguments={"apiKey": "sk-live", "id": 7})
        stored = AIToolInvocationModel.objects.get(toolCode="AUTH_TOOL")
        self.assertEqual(stored.arguments["apiKey"], "[REDACTED]")
        self.assertEqual(stored.arguments["id"], 7)

    def testTheRunnerSeesOnlyValidatedArguments(self) -> None:
        self.grantPermission()
        self.invoke(arguments={"projectId": "P-9"})
        self.assertEqual(self.calls[-1], {"projectId": "P-9"})


class ApprovalWorkflowTests(ToolTestCase):
    """Open Question #10: the approval workflow, end to end."""

    def setUp(self) -> None:
        super().setUp()
        self.register(code="DELETE_PROJECT", riskLevel="HIGH", inputSchema={})
        self.approveVersion("DELETE_PROJECT", 1)
        self.runner.register("DELETE_PROJECT", lambda arguments: {"deleted": True})
        self.register(code="WIPE_TENANT", riskLevel="CRITICAL", inputSchema={})
        self.approveVersion("WIPE_TENANT", 1)
        self.runner.register("WIPE_TENANT", lambda arguments: {"wiped": True})
        self.grantPermission()

    def testAHighRiskCallStopsAndOpensAnApproval(self) -> None:
        result = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        self.assertTrue(result.awaitingApproval)
        self.assertEqual(result.invocation.status, "PENDING")
        assert result.approval is not None
        self.assertEqual(result.approval.mode, "HUMAN_REQUIRED")
        self.assertEqual(result.approval.requiredApprovals, 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(AIToolApprovalModel.objects.count(), 1)

    def testTheSameProposalReusesItsPendingApproval(self) -> None:
        first = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        second = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        assert first.approval is not None and second.approval is not None
        self.assertEqual(first.approval.approvalId, second.approval.approvalId)
        self.assertEqual(AIToolApprovalModel.objects.count(), 1)

    def testGrantingLetsTheNextAttemptRun(self) -> None:
        pending = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        assert pending.approval is not None
        self.service.grantApproval(self.tenantId, pending.approval.approvalId, approverId=self.bob)
        result = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        self.assertTrue(result.succeeded)
        self.assertEqual(result.invocation.result, {"deleted": True})

    def testTheRequesterCannotApproveTheirOwnCall(self) -> None:
        pending = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        assert pending.approval is not None
        with self.assertRaises(ValidationFailedError):
            self.service.grantApproval(
                self.tenantId, pending.approval.approvalId, approverId=self.alice
            )

    def testCriticalRiskNeedsTwoDistinctApprovers(self) -> None:
        pending = self.invoke(toolCode="WIPE_TENANT", arguments={})
        assert pending.approval is not None
        approvalId = pending.approval.approvalId
        first = self.service.grantApproval(self.tenantId, approvalId, approverId=self.bob)
        self.assertEqual(first.decision, "PENDING")
        self.assertEqual(first.remaining, 1)
        # still blocked with only one approval
        stillPending = self.invoke(toolCode="WIPE_TENANT", arguments={})
        self.assertTrue(stillPending.awaitingApproval)
        second = self.service.grantApproval(self.tenantId, approvalId, approverId=uuid.uuid4())
        self.assertEqual(second.decision, "GRANTED")
        self.assertTrue(self.invoke(toolCode="WIPE_TENANT", arguments={}).succeeded)

    def testTheSameApproverCannotSatisfyDualControlTwice(self) -> None:
        pending = self.invoke(toolCode="WIPE_TENANT", arguments={})
        assert pending.approval is not None
        self.service.grantApproval(self.tenantId, pending.approval.approvalId, approverId=self.bob)
        with self.assertRaises(ValidationFailedError):
            self.service.grantApproval(
                self.tenantId, pending.approval.approvalId, approverId=self.bob
            )

    def testDenyingBlocksTheCallAndTheInvocation(self) -> None:
        pending = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        assert pending.approval is not None
        denied = self.service.denyApproval(
            self.tenantId, pending.approval.approvalId, "not this quarter", approverId=self.bob
        )
        self.assertEqual(denied.decision, "DENIED")
        stored = AIToolInvocationModel.objects.get(id=pending.invocation.invocationId)
        self.assertEqual(stored.status, "DENIED")
        with self.assertRaises(AIToolDenied):
            self.invoke(toolCode="DELETE_PROJECT", arguments={})

    def testADenialStopsTheAgentFromReAskingForever(self) -> None:
        pending = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        assert pending.approval is not None
        self.service.denyApproval(
            self.tenantId, pending.approval.approvalId, "no", approverId=self.bob
        )
        for _ in range(3):
            with self.assertRaises(AIToolDenied):
                self.invoke(toolCode="DELETE_PROJECT", arguments={})
        # exactly one approval request exists: the denial was not re-opened
        self.assertEqual(AIToolApprovalModel.objects.count(), 1)

    def testTheDenialExpiresWithItsWindow(self) -> None:
        pending = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        assert pending.approval is not None
        self.service.denyApproval(
            self.tenantId, pending.approval.approvalId, "not now", approverId=self.bob
        )
        self.clock = CLOCK + timedelta(hours=2)
        again = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        self.assertTrue(again.awaitingApproval)

    def testAnExpiredApprovalStopsWorking(self) -> None:
        pending = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        assert pending.approval is not None
        self.service.grantApproval(self.tenantId, pending.approval.approvalId, approverId=self.bob)
        self.clock = CLOCK + timedelta(hours=2)
        result = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        self.assertTrue(result.awaitingApproval)
        self.assertEqual(self.calls, [])

    def testApprovalIsBoundToTheExactArguments(self) -> None:
        pending = self.invoke(toolCode="DELETE_PROJECT", arguments={"projectId": "P-1"})
        assert pending.approval is not None
        self.service.grantApproval(self.tenantId, pending.approval.approvalId, approverId=self.bob)
        self.assertTrue(
            self.invoke(toolCode="DELETE_PROJECT", arguments={"projectId": "P-1"}).succeeded
        )
        other = self.invoke(toolCode="DELETE_PROJECT", arguments={"projectId": "P-2"})
        self.assertTrue(other.awaitingApproval)

    def testApprovalsAreListedAndDescribed(self) -> None:
        pending = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        assert pending.approval is not None
        self.assertEqual(len(self.service.listApprovals(self.tenantId)), 1)
        self.assertEqual(len(self.service.listApprovals(self.tenantId, decisions=("PENDING",))), 1)
        described = self.service.describeApproval(self.tenantId, pending.approval.approvalId)
        self.assertEqual(described.toolCode, "DELETE_PROJECT")

    def testUnknownApprovalIsNotFound(self) -> None:
        with self.assertRaises(AIToolApprovalNotFound):
            self.service.describeApproval(self.tenantId, uuid.uuid4())
        with self.assertRaises(AIToolApprovalNotFound):
            self.service.grantApproval(self.tenantId, uuid.uuid4(), approverId=self.bob)

    def testAToolMayDemandMoreThanItsRiskRequires(self) -> None:
        self.register(
            code="CAREFUL_TOOL",
            riskLevel="LOW",
            inputSchema={},
            declaredApprovalMode="HUMAN_REQUIRED",
        )
        self.approveVersion("CAREFUL_TOOL", 1)
        self.runner.register("CAREFUL_TOOL", lambda arguments: {"ok": True})
        result = self.invoke(toolCode="CAREFUL_TOOL", arguments={})
        self.assertTrue(result.awaitingApproval)

    def testALooserDeclarationCannotEscapeReview(self) -> None:
        self.register(
            code="SNEAKY_TOOL",
            riskLevel="CRITICAL",
            inputSchema={},
            declaredApprovalMode="AUTOMATIC",
        )
        self.approveVersion("SNEAKY_TOOL", 1)
        self.runner.register("SNEAKY_TOOL", lambda arguments: {"ok": True})
        result = self.invoke(toolCode="SNEAKY_TOOL", arguments={})
        self.assertTrue(result.awaitingApproval)
        assert result.approval is not None
        self.assertEqual(result.approval.mode, "DUAL_CONTROL")


class BudgetTests(ToolTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.register()
        self.approveVersion()
        self.grantPermission()
        self.requestId = uuid.uuid4()

    def testCallsWithinOneRequestAreCapped(self) -> None:
        service = self.buildService(maxCallsPerRequest=2, maxRepeatsPerRequest=9)
        for index in range(2):
            service.invokeTool(
                self.tenantId,
                InvokeToolCommand(
                    toolCode="SEARCH_PROJECT",
                    arguments={"projectId": f"P-{index}"},
                    principal=self.principal,
                    actorId=self.alice,
                    requestId=self.requestId,
                ),
            )
        with self.assertRaises(AIToolBudgetExceeded):
            service.invokeTool(
                self.tenantId,
                InvokeToolCommand(
                    toolCode="SEARCH_PROJECT",
                    arguments={"projectId": "P-3"},
                    principal=self.principal,
                    actorId=self.alice,
                    requestId=self.requestId,
                ),
            )

    def testARepeatingCallIsTreatedAsALoop(self) -> None:
        for _ in range(2):
            self.invoke(requestId=self.requestId)
        with self.assertRaises(AIToolBudgetExceeded):
            self.invoke(requestId=self.requestId)

    def testABudgetIsPerRequestNotGlobal(self) -> None:
        service = self.buildService(maxCallsPerRequest=1)
        service.invokeTool(
            self.tenantId,
            InvokeToolCommand(
                toolCode="SEARCH_PROJECT",
                arguments={"projectId": "P-1"},
                principal=self.principal,
                requestId=self.requestId,
            ),
        )
        # a different request starts with a fresh budget
        service.invokeTool(
            self.tenantId,
            InvokeToolCommand(
                toolCode="SEARCH_PROJECT",
                arguments={"projectId": "P-1"},
                principal=self.principal,
                requestId=uuid.uuid4(),
            ),
        )
        self.assertEqual(len(self.calls), 2)

    def testTheToolsOwnCeilingIsHonouredToo(self) -> None:
        self.register(code="ONE_SHOT", inputSchema={}, maxCallsPerRequest=1)
        self.approveVersion("ONE_SHOT", 1)
        self.runner.register("ONE_SHOT", lambda arguments: {"ok": True})
        self.invoke(toolCode="ONE_SHOT", arguments={}, requestId=self.requestId)
        with self.assertRaises(AIToolBudgetExceeded):
            self.invoke(toolCode="ONE_SHOT", arguments={}, requestId=self.requestId)


class ReadAndRetentionTests(ToolTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.register()
        self.approveVersion()
        self.grantPermission()
        self.result = self.invoke(requestId=uuid.uuid4())

    def testInvocationsAreReadableAndFiltered(self) -> None:
        described = self.service.describeInvocation(
            self.tenantId, self.result.invocation.invocationId
        )
        self.assertEqual(described.status, "SUCCEEDED")
        self.assertEqual(len(self.service.listInvocations(self.tenantId)), 1)
        self.assertEqual(
            len(self.service.listInvocations(self.tenantId, toolCode="SEARCH_PROJECT")), 1
        )
        self.assertEqual(len(self.service.listInvocations(self.tenantId, statuses=("DENIED",))), 0)

    def testInvocationsAreTenantScoped(self) -> None:
        self.assertEqual(self.service.listInvocations(self.otherTenantId), ())
        with self.assertRaises(AIToolNotFound):
            self.service.describeInvocation(self.otherTenantId, self.result.invocation.invocationId)

    def testRetentionRemovesSettledCallsOnly(self) -> None:
        self.register(code="DELETE_PROJECT", riskLevel="HIGH", inputSchema={})
        self.approveVersion("DELETE_PROJECT", 1)
        self.runner.register("DELETE_PROJECT", lambda arguments: {"deleted": True})
        pendingCall = self.invoke(toolCode="DELETE_PROJECT", arguments={})
        future = CLOCK + timedelta(days=500)
        removed = self.service.purgeToolRetention(self.tenantId, now=future)
        self.assertEqual(removed, 1)
        self.assertTrue(
            AIToolInvocationModel.objects.filter(id=pendingCall.invocation.invocationId).exists()
        )

    def testRetentionRejectsAnImpossibleHorizon(self) -> None:
        with self.assertRaises(AIConfigurationError):
            self.service.purgeToolRetention(self.tenantId, retentionDays=0)

    def testAuditChainStaysVerifiable(self) -> None:
        actions = self.auditActions()
        self.assertIn(AUDIT_TOOL_REGISTERED, actions)
        self.assertIn(AUDIT_TOOL_APPROVED, actions)
        self.assertIn(AUDIT_TOOL_INVOKED, actions)
        self.assertEqual(self.audit.verifyTenantChain(self.tenantId), len(actions))

    def testTheRegistryViewOnlyResolvesApprovedVersions(self) -> None:
        self.service.publishNewVersion(self.tenantId, "SEARCH_PROJECT")
        registry = self.service.registry(self.tenantId)
        self.assertEqual(registry.resolve("SEARCH_PROJECT").version, 1)
        self.assertEqual(len(registry.listRunnable()), 1)


class RunnerTests(ToolTestCase):
    def testTheRunnerRefusesAnythingButATicket(self) -> None:
        with self.assertRaises(AIToolInvalid):
            self.runner.run(self.tenantId, {"toolCode": "SEARCH_PROJECT"})

    def testHandlersMustBeCallable(self) -> None:
        with self.assertRaises(AIToolInvalid):
            CallableToolRunner({"SEARCH_PROJECT": "not callable"})

    def testSupportsIsCaseInsensitive(self) -> None:
        self.assertTrue(self.runner.supports(" search_project "))
        self.assertFalse(self.runner.supports("UNKNOWN_TOOL"))
