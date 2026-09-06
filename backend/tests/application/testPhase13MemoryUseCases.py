"""Phase 13-T application tests — memory over a real SQLite database.

Covers the five §17 properties as behaviour rather than claims: tenant
isolation, user ownership, permission-aware context assembly through the
real Phase 13-K filter, immutable versioning with queryable history, and
audit entries in the real Phase 13-O ledger. Also covers the ceilings and
retention that close Open Question #8 (per-scope caps, time-to-live,
eviction, purge), forgetting (soft and hard), the fail-closed switch, and
the Phase 13-P maintenance job.

Persistence is the real ``DjangoMemoryEntryStore``; only the clock is
frozen.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from django.test import TestCase

from apps.ai.application.services.auditService import AuditApplicationService, AuditSettings
from apps.ai.application.services.memoryService import (
    AUDIT_MEMORY_EVICTED,
    AUDIT_MEMORY_FORGOTTEN,
    AUDIT_MEMORY_RECALLED,
    AUDIT_MEMORY_WRITTEN,
    MemoryApplicationService,
    MemoryMaintenanceJobHandler,
    MemorySettings,
    RememberCommand,
)
from apps.ai.application.services.queueService import (
    QueueApplicationService,
    QueueSettings,
    SubmitJobCommand,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIMemoryInvalid,
    AIMemoryNotFound,
    AIMemoryValueTooLarge,
)
from apps.ai.domain.services.authorizationService import (
    AuthorizationPrincipal,
    AuthorizationService,
    PermissionGrant,
)
from apps.ai.infrastructure.models import AIMemoryEntryModel
from apps.ai.infrastructure.repositories.auditRepositories import (
    DjangoAuditRecordStore,
    DjangoGovernancePolicyStore,
    DjangoRetentionPurger,
)
from apps.ai.infrastructure.repositories.memoryRepositories import DjangoMemoryEntryStore
from apps.ai.infrastructure.repositories.queueRepositories import DjangoJobStore
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


class MemoryTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.userId = uuid.uuid4()
        self.otherUserId = uuid.uuid4()
        self.clock = CLOCK
        self.store = DjangoMemoryEntryStore()
        self.audit = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=AuditSettings(enabled=True, retentionDays=365),
            now=lambda: CLOCK,
        )
        self.authorization = AuthorizationService(now=lambda: CLOCK)
        self.principal = AuthorizationPrincipal(
            tenantId=self.tenantId, subjectId=self.userId, roles=("ANALYST",)
        )
        self.service = self.buildService()

    def buildService(self, **overrides: Any) -> MemoryApplicationService:
        settings = MemorySettings(
            enabled=overrides.pop("enabled", True),
            maxEntriesPerScope=overrides.pop("maxEntriesPerScope", 200),
            defaultTtlSeconds=overrides.pop("defaultTtlSeconds", 0),
            maxValueBytes=overrides.pop("maxValueBytes", 32_768),
            eviction=overrides.pop("eviction", "OLDEST_FIRST"),
            contextMaxEntries=overrides.pop("contextMaxEntries", 10),
            contextMaxTokens=overrides.pop("contextMaxTokens", 1000),
            retentionDays=overrides.pop("retentionDays", 365),
            usePlatformScopeDefaults=overrides.pop("usePlatformScopeDefaults", True),
        )
        return MemoryApplicationService(
            self.store,
            permissionFilter=overrides.pop("permissionFilter", self.authorization),
            settings=settings,
            auditLogger=overrides.pop("auditLogger", self.audit),
            now=overrides.pop("now", lambda: self.clock),
        )

    def remember(self, key: str = "user.language", value: Any = "fa", **overrides: Any) -> Any:
        params: dict[str, Any] = {"scope": "LONG_TERM", "key": key, "value": value}
        params.update(overrides)
        return self.service.remember(self.tenantId, RememberCommand(**params))

    def grantMemory(self, *, scope: str = "", key: str = "") -> None:
        extra: dict[str, Any] = {}
        if scope and key:
            extra = {
                "sourceDomain": "MEMORY",
                "sourceEntityType": scope,
                "sourceEntityId": key,
            }
        self.authorization.registerGrant(
            PermissionGrant(
                tenantId=self.tenantId,
                subjectId=self.userId,
                permissionCode="AI_CONTEXT_SOURCE_READ",
                resourceType="CONTEXT_SOURCE",
                allowedClassifications=("PUBLIC", "INTERNAL"),
                **extra,
            )
        )

    def auditActions(self) -> list[str]:
        return [entry.action for entry in self.audit.listAuditEntries(self.tenantId)]


class WriteAndVersionTests(MemoryTestCase):
    def testFirstWriteCreatesOneActiveVersion(self) -> None:
        result = self.remember()
        self.assertEqual(result.action, "CREATED")
        self.assertEqual(result.memory.version, 1)
        self.assertTrue(result.memory.isActive)
        self.assertEqual(AIMemoryEntryModel.objects.count(), 1)
        self.assertIn(AUDIT_MEMORY_WRITTEN, self.auditActions())

    def testRewritingTheSameValueChangesNothing(self) -> None:
        self.remember()
        result = self.remember()
        self.assertTrue(result.isNoop)
        self.assertEqual(AIMemoryEntryModel.objects.count(), 1)

    def testChangedValueSupersedesInsteadOfEditing(self) -> None:
        self.remember(value="fa")
        result = self.remember(value="en")
        self.assertEqual(result.action, "VERSIONED")
        self.assertEqual(result.memory.version, 2)
        self.assertEqual(result.supersededVersion, 1)
        self.assertEqual(AIMemoryEntryModel.objects.count(), 2)
        previous = AIMemoryEntryModel.objects.get(version=1)
        self.assertFalse(previous.isActive)
        self.assertIsNotNone(previous.supersededAt)
        self.assertEqual(previous.value, "fa")

    def testHistoryKeepsEveryVersionInOrder(self) -> None:
        for value in ("fa", "en", "de"):
            self.remember(value=value)
        history = self.service.history(self.tenantId, "LONG_TERM", "user.language")
        self.assertEqual([item.version for item in history], [1, 2, 3])
        self.assertEqual(history[-1].isActive, True)
        self.assertEqual(history[0].isActive, False)

    def testRecallReturnsTheCurrentValue(self) -> None:
        self.remember(value="fa")
        self.remember(value="en")
        self.assertEqual(self.service.recall(self.tenantId, "LONG_TERM", "user.language"), "en")
        self.assertIn(AUDIT_MEMORY_RECALLED, self.auditActions())

    def testKeysAreNormalizedOnBothSides(self) -> None:
        self.remember(key="  User.Language ")
        self.assertEqual(self.service.recall(self.tenantId, "long_term", "USER.LANGUAGE"), "fa")

    def testStructuredValuesRoundTrip(self) -> None:
        payload = {"language": "fa", "channels": ["email", "sms"], "digest": True}
        self.remember(key="user.preferences", value=payload)
        self.assertEqual(
            self.service.recall(self.tenantId, "LONG_TERM", "user.preferences"), payload
        )

    def testUnknownKeyIsNotFound(self) -> None:
        with self.assertRaises(AIMemoryNotFound):
            self.service.recall(self.tenantId, "LONG_TERM", "missing.key")

    def testOversizedValueIsRefused(self) -> None:
        service = self.buildService(maxValueBytes=256)
        with self.assertRaises(AIMemoryValueTooLarge):
            service.remember(
                self.tenantId,
                RememberCommand(scope="LONG_TERM", key="big", value="x" * 5000),
            )

    def testInvalidCommandsAreRejected(self) -> None:
        with self.assertRaises(AIMemoryInvalid):
            self.service.remember(self.tenantId, "remember this")  # type: ignore[arg-type]
        with self.assertRaises(ValidationFailedError):
            self.remember(key="!!invalid!!")

    def testDisabledPlatformRefusesEverything(self) -> None:
        disabled = self.buildService(enabled=False)
        with self.assertRaises(AIConfigurationError):
            disabled.remember(self.tenantId, RememberCommand(scope="LONG_TERM", key="k", value="v"))
        with self.assertRaises(AIConfigurationError):
            disabled.listMemories(self.tenantId)


class OwnershipAndIsolationTests(MemoryTestCase):
    def testUserOwnedMemoryIsInvisibleToAnotherUser(self) -> None:
        self.remember(key="user.language", value="fa", userId=self.userId)
        self.assertEqual(
            self.service.recall(self.tenantId, "LONG_TERM", "user.language", userId=self.userId),
            "fa",
        )
        with self.assertRaises(AIMemoryNotFound):
            self.service.recall(
                self.tenantId, "LONG_TERM", "user.language", userId=self.otherUserId
            )

    def testTenantWideMemoryIsVisibleToEveryUser(self) -> None:
        self.remember(key="policy.tone", value="formal")
        self.assertEqual(
            self.service.recall(self.tenantId, "LONG_TERM", "policy.tone", userId=self.otherUserId),
            "formal",
        )

    def testTwoUsersKeepIndependentSlotsUnderTheSameKey(self) -> None:
        self.remember(key="user.language", value="fa", userId=self.userId)
        self.remember(key="user.language", value="en", userId=self.otherUserId)
        self.assertEqual(
            self.service.recall(self.tenantId, "LONG_TERM", "user.language", userId=self.userId),
            "fa",
        )
        self.assertEqual(
            self.service.recall(
                self.tenantId, "LONG_TERM", "user.language", userId=self.otherUserId
            ),
            "en",
        )

    def testMemoryNeverCrossesTenantBoundaries(self) -> None:
        self.remember()
        with self.assertRaises(AIMemoryNotFound):
            self.service.recall(self.otherTenantId, "LONG_TERM", "user.language")
        self.assertEqual(self.service.listMemories(self.otherTenantId), ())

    def testListingFiltersByScopeAndConversation(self) -> None:
        self.remember(key="a", scope="TASK")
        self.remember(key="b", scope="CONVERSATION", conversationId="conv-1")
        self.remember(key="c", scope="CONVERSATION", conversationId="conv-2")
        tasks = self.service.listMemories(self.tenantId, scopes=("TASK",))
        self.assertEqual([item.key for item in tasks], ["a"])
        conversation = self.service.listMemories(self.tenantId, conversationId="conv-1")
        self.assertEqual([item.key for item in conversation], ["b"])

    def testDescribeMemoryIsTenantScoped(self) -> None:
        created = self.remember()
        self.assertEqual(
            self.service.describeMemory(self.tenantId, created.memory.memoryId).key,
            "user.language",
        )
        with self.assertRaises(AIMemoryNotFound):
            self.service.describeMemory(self.otherTenantId, created.memory.memoryId)


class BudgetAndRetentionTests(MemoryTestCase):
    """Open Question #8: nothing about memory is unbounded."""

    def testScopeCeilingEvictsTheOldestEntry(self) -> None:
        service = self.buildService(maxEntriesPerScope=3, usePlatformScopeDefaults=False)
        for index in range(3):
            self.clock = CLOCK + timedelta(minutes=index)
            service.remember(
                self.tenantId,
                RememberCommand(scope="TASK", key=f"note.{index}", value=f"value {index}"),
            )
        self.clock = CLOCK + timedelta(minutes=10)
        result = service.remember(
            self.tenantId, RememberCommand(scope="TASK", key="note.new", value="fresh")
        )
        self.assertEqual(result.evictedCount, 1)
        active = {item.key for item in service.listMemories(self.tenantId, scopes=("TASK",))}
        self.assertNotIn("note.0", active)
        self.assertIn("note.new", active)
        self.assertIn(AUDIT_MEMORY_EVICTED, self.auditActions())

    def testEvictionKeepsTheRowForAudit(self) -> None:
        service = self.buildService(maxEntriesPerScope=1, usePlatformScopeDefaults=False)
        service.remember(self.tenantId, RememberCommand(scope="TASK", key="a", value="1"))
        self.clock = CLOCK + timedelta(minutes=1)
        service.remember(self.tenantId, RememberCommand(scope="TASK", key="b", value="2"))
        self.assertEqual(AIMemoryEntryModel.objects.count(), 2)
        self.assertEqual(AIMemoryEntryModel.objects.filter(isActive=True).count(), 1)

    def testScopeTimeToLiveExpiresAnEntry(self) -> None:
        service = self.buildService(defaultTtlSeconds=60, usePlatformScopeDefaults=False)
        service.remember(
            self.tenantId, RememberCommand(scope="SHORT_TERM", key="draft", value="text")
        )
        self.assertEqual(service.recall(self.tenantId, "SHORT_TERM", "draft"), "text")
        self.clock = CLOCK + timedelta(minutes=5)
        with self.assertRaises(AIMemoryNotFound):
            service.recall(self.tenantId, "SHORT_TERM", "draft")

    def testWritingAfterExpiryStartsANewVersionLine(self) -> None:
        service = self.buildService(defaultTtlSeconds=60, usePlatformScopeDefaults=False)
        service.remember(
            self.tenantId, RememberCommand(scope="SHORT_TERM", key="draft", value="first")
        )
        self.clock = CLOCK + timedelta(minutes=5)
        result = service.remember(
            self.tenantId, RememberCommand(scope="SHORT_TERM", key="draft", value="second")
        )
        self.assertEqual(result.action, "CREATED")
        self.assertEqual(result.memory.version, 2)
        self.assertEqual(service.recall(self.tenantId, "SHORT_TERM", "draft"), "second")

    def testPlatformScopeDefaultsGiveShortTermAnExpiry(self) -> None:
        self.remember(key="draft", scope="SHORT_TERM", value="text")
        stored = self.service.listMemories(self.tenantId, scopes=("SHORT_TERM",))[0]
        self.assertIsNotNone(stored.expiresAt)
        longTerm = self.remember(key="user.language", value="fa")
        self.assertIsNone(longTerm.memory.expiresAt)

    def testExplicitRetentionSweepExpiresAndEvicts(self) -> None:
        service = self.buildService(maxEntriesPerScope=2, usePlatformScopeDefaults=False)
        for index in range(2):
            self.clock = CLOCK + timedelta(minutes=index)
            service.remember(
                self.tenantId,
                RememberCommand(scope="TASK", key=f"k{index}", value=f"v{index}"),
            )
        plans = service.enforceRetention(self.tenantId, scopes=("TASK",))
        self.assertEqual(plans["TASK"].removedCount, 0)
        self.assertEqual(len(plans["TASK"].kept), 2)

    def testPurgeRemovesOnlyRetiredVersions(self) -> None:
        self.remember(value="fa")
        self.remember(value="en")
        self.assertEqual(self.service.purgeMemoryRetention(self.tenantId, retentionDays=1), 0)
        future = CLOCK + timedelta(days=800)
        self.assertEqual(self.service.purgeMemoryRetention(self.tenantId, now=future), 1)
        self.assertEqual(AIMemoryEntryModel.objects.count(), 1)
        self.assertEqual(self.service.recall(self.tenantId, "LONG_TERM", "user.language"), "en")

    def testPurgeRejectsAnImpossibleHorizon(self) -> None:
        with self.assertRaises(AIConfigurationError):
            self.service.purgeMemoryRetention(self.tenantId, retentionDays=0)

    def testConfigurationMayOnlyNarrowThePlatformDefaults(self) -> None:
        settings = MemorySettings(maxEntriesPerScope=10)
        budget = settings.budget()
        self.assertEqual(budget.forScope("LONG_TERM").maxEntries, 10)
        self.assertLessEqual(budget.forScope("SHORT_TERM").maxEntries, 10)
        self.assertTrue(budget.forScope("SHORT_TERM").expires)


class ForgettingTests(MemoryTestCase):
    def testSoftForgetRetiresEveryActiveVersion(self) -> None:
        self.remember(value="fa")
        self.remember(value="en")
        affected = self.service.forget(self.tenantId, "LONG_TERM", "user.language")
        self.assertEqual(affected, 1)
        with self.assertRaises(AIMemoryNotFound):
            self.service.recall(self.tenantId, "LONG_TERM", "user.language")
        self.assertEqual(AIMemoryEntryModel.objects.count(), 2)
        self.assertIn(AUDIT_MEMORY_FORGOTTEN, self.auditActions())

    def testHardForgetDeletesTheWholeHistory(self) -> None:
        self.remember(value="fa")
        self.remember(value="en")
        self.assertEqual(
            self.service.forget(self.tenantId, "LONG_TERM", "user.language", hard=True), 2
        )
        self.assertEqual(AIMemoryEntryModel.objects.count(), 0)

    def testForgettingAnUnknownKeyIsNotFound(self) -> None:
        with self.assertRaises(AIMemoryNotFound):
            self.service.forget(self.tenantId, "LONG_TERM", "missing.key")

    def testForgettingIsOwnerScoped(self) -> None:
        self.remember(key="user.language", value="fa", userId=self.userId)
        with self.assertRaises(AIMemoryNotFound):
            self.service.forget(
                self.tenantId, "LONG_TERM", "user.language", userId=self.otherUserId
            )
        self.assertEqual(
            self.service.recall(self.tenantId, "LONG_TERM", "user.language", userId=self.userId),
            "fa",
        )

    def testWritingAgainAfterForgettingStartsAFreshVersion(self) -> None:
        self.remember(value="fa")
        self.service.forget(self.tenantId, "LONG_TERM", "user.language")
        result = self.remember(value="en")
        self.assertEqual(result.action, "CREATED")
        self.assertEqual(result.memory.version, 2)


class PermissionAwareContextTests(MemoryTestCase):
    """§17 "permission-aware": memory joins a prompt through Phase 13-K."""

    def setUp(self) -> None:
        super().setUp()
        self.remember(key="user.language", value="fa")
        self.remember(key="project.goal", value="reduce downtime", scope="TASK")

    def testPrincipalWithoutAGrantGetsNoMemoryContext(self) -> None:
        result = self.service.buildContextSources(self.tenantId, self.principal)
        self.assertTrue(result.isEmpty)
        self.assertGreater(result.consideredCount, 0)
        self.assertEqual(result.authorizedCount, 0)

    def testGrantedPrincipalGetsAuthorizedSources(self) -> None:
        self.grantMemory()
        result = self.service.buildContextSources(self.tenantId, self.principal)
        self.assertFalse(result.isEmpty)
        self.assertEqual(result.authorizedCount, 2)
        self.assertEqual({source.sourceDomain for source in result.sources}, {"MEMORY"})
        self.assertGreater(result.tokenCount, 0)

    def testGrantScopedToOneSlotHidesTheRest(self) -> None:
        self.grantMemory(scope="TASK", key="project.goal")
        result = self.service.buildContextSources(self.tenantId, self.principal)
        self.assertEqual([item.key for item in result.entries], ["project.goal"])
        self.assertEqual(result.deniedCount, 1)

    def testRestrictedMemoryIsFilteredOut(self) -> None:
        self.remember(key="salary.band", value="confidential", classification="RESTRICTED")
        self.grantMemory()
        result = self.service.buildContextSources(self.tenantId, self.principal)
        self.assertNotIn("salary.band", {item.key for item in result.entries})

    def testAnotherUsersMemoryNeverEntersTheContext(self) -> None:
        self.remember(key="private.note", value="secret", userId=self.otherUserId)
        self.grantMemory()
        result = self.service.buildContextSources(self.tenantId, self.principal)
        self.assertNotIn("private.note", {item.key for item in result.entries})

    def testMissingFilterFailsClosed(self) -> None:
        service = self.buildService(permissionFilter=None)
        with self.assertRaises(AIConfigurationError):
            service.buildContextSources(self.tenantId, self.principal)

    def testScopeAndEntryLimitsApplyToTheContext(self) -> None:
        self.grantMemory()
        result = self.service.buildContextSources(
            self.tenantId, self.principal, scopes=("TASK",), maxEntries=1
        )
        self.assertEqual([item.scope for item in result.entries], ["TASK"])

    def testForeignPrincipalIsRefused(self) -> None:
        foreign = AuthorizationPrincipal(tenantId=self.otherTenantId, subjectId=uuid.uuid4())
        with self.assertRaises(AIMemoryInvalid):
            self.service.buildContextSources(self.tenantId, foreign)
        with self.assertRaises(AIMemoryInvalid):
            self.service.buildContextSources(self.tenantId, None)

    def testContextAssemblyIsAudited(self) -> None:
        self.grantMemory()
        self.service.buildContextSources(self.tenantId, self.principal)
        self.assertIn(AUDIT_MEMORY_RECALLED, self.auditActions())
        self.assertEqual(self.audit.verifyTenantChain(self.tenantId), len(self.auditActions()))


class MaintenanceJobTests(MemoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.service = self.buildService(maxEntriesPerScope=2, usePlatformScopeDefaults=False)
        self.queue = QueueApplicationService(
            DjangoJobStore(),
            auditService=self.audit,
            queueSettings=QueueSettings(enabled=True, defaultMaxAttempts=2, claimLimit=5),
            workerId="testWorker",
            now=lambda: CLOCK,
        )
        self.queue.registerHandler(MemoryMaintenanceJobHandler(self.service))

    def testMaintenanceRunsThroughTheQueue(self) -> None:
        for index in range(2):
            self.clock = CLOCK + timedelta(minutes=index)
            self.service.remember(
                self.tenantId,
                RememberCommand(scope="TASK", key=f"k{index}", value=f"v{index}"),
            )
        self.clock = CLOCK
        descriptor = self.queue.submitJob(
            SubmitJobCommand(
                tenantId=self.tenantId,
                kind="GENERIC",
                payload={"scopes": ["TASK"], "purge": True, "retentionDays": 365},
            )
        )
        report = self.queue.runOnce()
        self.assertEqual(report.succeeded, 1)
        settled = self.queue.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.status, "SUCCEEDED")
        self.assertEqual(settled.resultSummary["scopes"], ["TASK"])
        self.assertEqual(settled.resultSummary["purged"], 0)

    def testInvalidPayloadFailsTheJobNotTheWorker(self) -> None:
        descriptor = self.queue.submitJob(
            SubmitJobCommand(tenantId=self.tenantId, kind="GENERIC", payload={"scopes": "TASK"})
        )
        self.queue.runOnce()
        settled = self.queue.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.errorCode, "AI_MEMORY_POLICY_INVALID")

    def testHandlerAdvertisesItsKind(self) -> None:
        self.assertEqual(MemoryMaintenanceJobHandler(self.service).kind(), "GENERIC")
