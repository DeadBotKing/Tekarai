"""Phase 13-T unit tests — memory vocabularies, entities, engine. Offline.

Covers key normalization, canonical value identity and sizing, the scope
budget vocabulary that closes Open Question #8, the versioned entry with
its ownership/expiry/supersession rules and the Phase 13-B bridge, the
write planner (create, unchanged, versioned, forced), the retention
evaluator (expiry, both eviction strategies, the disabled strategy), and
the context selector (scope priority, latest-version-wins, ownership,
entry and token budgets).

No Django, database, network, provider, or clock dependency.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta

from apps.ai.domain.entities.aiRecords import AIMemory
from apps.ai.domain.entities.memoryRecords import (
    AIMemoryEntry,
    ensureValueChecksum,
)
from apps.ai.domain.exceptions import (
    AIMemoryBudgetExceeded,
    AIMemoryInvalid,
    AIMemoryPolicyInvalid,
    AIMemoryValueTooLarge,
)
from apps.ai.domain.services.memoryEngine import (
    MemorySelector,
    MemoryWriter,
    RetentionEvaluator,
    budgetFor,
)
from apps.ai.domain.valueObjects.memoryTypes import (
    EVICTION_STRATEGIES,
    MAX_ENTRIES_PER_SCOPE,
    MEMORY_KINDS,
    RETENTION_ACTIONS,
    MemoryBudget,
    MemoryKey,
    ScopeBudget,
    canonicalValue,
    ensureMemoryKind,
    ensureMemoryScope,
    normalizeKey,
    serializeValue,
    valueChecksum,
    valueSize,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
TENANT = uuid.UUID("55555555-5555-4555-8555-555555555555")
USER = uuid.UUID("66666666-6666-4666-8666-666666666666")
OTHER_USER = uuid.UUID("77777777-7777-4777-8777-777777777777")


def frozenClock() -> datetime:
    return CLOCK


def entry(
    key: str = "user.language",
    value: object = "fa",
    *,
    scope: str = "LONG_TERM",
    version: int = 1,
    userId: uuid.UUID | None = None,
    createdAt: datetime | None = None,
    classification: str = "INTERNAL",
    expiresAt: datetime | None = None,
    metadata: dict | None = None,
) -> AIMemoryEntry:
    return AIMemoryEntry(
        tenantId=TENANT,
        memoryKey=MemoryKey(scope=scope, key=key),
        value=value,
        version=version,
        userId=userId,
        classification=classification,
        expiresAt=expiresAt,
        metadata=metadata or {},
        createdAt=createdAt or CLOCK,
    )


class VocabularyTests(unittest.TestCase):
    def testClosedVocabulariesAreStable(self) -> None:
        self.assertIn("PREFERENCE", MEMORY_KINDS)
        self.assertIn("SUMMARY", MEMORY_KINDS)
        self.assertEqual(EVICTION_STRATEGIES, ("OLDEST_FIRST", "LOWEST_PRIORITY", "NONE"))
        self.assertEqual(RETENTION_ACTIONS, ("KEEP", "EXPIRE", "EVICT"))

    def testValuesAreNormalized(self) -> None:
        self.assertEqual(ensureMemoryKind(" preference "), "PREFERENCE")
        self.assertEqual(ensureMemoryScope("long_term"), "LONG_TERM")
        with self.assertRaises(ValidationFailedError):
            ensureMemoryKind("OPINION")
        with self.assertRaises(ValidationFailedError):
            ensureMemoryScope("ETERNAL")

    def testKeysAreAddressesNotProse(self) -> None:
        self.assertEqual(normalizeKey("  User.Language  "), "user.language")
        self.assertEqual(normalizeKey("project 42 summary"), "project_42_summary")
        for bad in ("", "   ", "!!", "a" * 200):
            with self.assertRaises(ValidationFailedError):
                normalizeKey(bad)

    def testMemoryKeyExposesQualifiedFormAndPriority(self) -> None:
        key = MemoryKey(scope="conversation", key="Last.Topic")
        self.assertEqual(key.qualified(), "CONVERSATION:last.topic")
        self.assertLess(MemoryKey(scope="TASK", key="a").priority, key.priority)


class ValueMathTests(unittest.TestCase):
    def testCanonicalFormIsOrderInsensitive(self) -> None:
        self.assertEqual(valueChecksum({"b": 1, "a": [1, 2]}), valueChecksum({"a": (1, 2), "b": 1}))

    def testDifferentValuesDiffer(self) -> None:
        self.assertNotEqual(valueChecksum("fa"), valueChecksum("en"))
        self.assertNotEqual(valueChecksum({"a": 1}), valueChecksum({"a": 2}))

    def testUnicodeIsNormalizedBeforeHashing(self) -> None:
        self.assertEqual(valueChecksum("e\u0301te"), valueChecksum("\u00e9te"))

    def testSizeReflectsTheSerializedValue(self) -> None:
        self.assertEqual(valueSize("fa"), len(serializeValue("fa").encode()))
        self.assertGreater(valueSize({"summary": "x" * 100}), valueSize("x"))

    def testNestedStructuresAreSupportedAndTuplesBecomeLists(self) -> None:
        self.assertEqual(canonicalValue({"k": (1, 2)}), {"k": [1, 2]})
        self.assertEqual(canonicalValue(None), None)

    def testUnserializableValuesAreRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            canonicalValue({"when": datetime.now(tz=UTC)})
        with self.assertRaises(ValidationFailedError):
            valueChecksum(object())

    def testChecksumHelperNormalizesInput(self) -> None:
        digest = valueChecksum("fa")
        self.assertEqual(ensureValueChecksum(digest.upper()), digest)
        with self.assertRaises(ValidationFailedError):
            ensureValueChecksum("nope")


class BudgetTests(unittest.TestCase):
    def testDefaultsAreBounded(self) -> None:
        budget = ScopeBudget()
        self.assertGreater(budget.maxEntries, 0)
        self.assertFalse(budget.expires)
        self.assertEqual(budget.eviction, "OLDEST_FIRST")

    def testRangesAreEnforced(self) -> None:
        with self.assertRaises(ValidationFailedError):
            ScopeBudget(maxEntries=0)
        with self.assertRaises(ValidationFailedError):
            ScopeBudget(maxEntries=MAX_ENTRIES_PER_SCOPE + 1)
        with self.assertRaises(ValidationFailedError):
            ScopeBudget(ttlSeconds=-1)
        with self.assertRaises(ValidationFailedError):
            ScopeBudget(maxValueBytes=0)
        with self.assertRaises(ValidationFailedError):
            ScopeBudget(maxEntries=True)

    def testPlatformDefaultsCoverEveryLiveScope(self) -> None:
        budget = MemoryBudget.platformDefault()
        shortTerm = budget.forScope("SHORT_TERM")
        longTerm = budget.forScope("LONG_TERM")
        self.assertTrue(shortTerm.expires)
        self.assertFalse(longTerm.expires)
        self.assertLess(shortTerm.maxEntries, longTerm.maxEntries)
        self.assertEqual(budget.forScope("AGENT").maxEntries, 200)

    def testUnknownScopeFallsBackToTheDefault(self) -> None:
        budget = MemoryBudget(default=ScopeBudget(maxEntries=7))
        self.assertEqual(budget.forScope("TASK").maxEntries, 7)
        self.assertEqual(budgetFor(budget, "TASK").maxEntries, 7)
        with self.assertRaises(AIMemoryPolicyInvalid):
            budgetFor("budget", "TASK")  # type: ignore[arg-type]

    def testBudgetRejectsForeignValues(self) -> None:
        with self.assertRaises(ValidationFailedError):
            MemoryBudget(scopes={"TASK": "budget"})  # type: ignore[dict-item]
        with self.assertRaises(ValidationFailedError):
            MemoryBudget(default="budget")  # type: ignore[arg-type]


class MemoryEntryTests(unittest.TestCase):
    def testEntryComputesChecksumAndSize(self) -> None:
        item = entry()
        self.assertEqual(item.checksum, valueChecksum("fa"))
        self.assertEqual(item.sizeBytes, valueSize("fa"))
        self.assertEqual(item.qualifiedKey, "LONG_TERM:user.language")
        self.assertTrue(item.isUsableAt(CLOCK))

    def testChecksumMismatchIsRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            AIMemoryEntry(
                tenantId=TENANT,
                memoryKey=MemoryKey(scope="LONG_TERM", key="k"),
                value="fa",
                checksum=valueChecksum("en"),
            )

    def testGuardsRejectBadInput(self) -> None:
        with self.assertRaises(ValidationFailedError):
            AIMemoryEntry(tenantId=TENANT, memoryKey="LONG_TERM:k", value="fa")  # type: ignore[arg-type]
        with self.assertRaises(ValidationFailedError):
            entry(version=0)
        with self.assertRaises(ValidationFailedError):
            entry(classification="SECRET")
        with self.assertRaises(ValidationFailedError):
            AIMemoryEntry(
                tenantId=TENANT,
                memoryKey=MemoryKey(scope="LONG_TERM", key="k"),
                value="fa",
                metadata=["nope"],  # type: ignore[arg-type]
            )

    def testOwnershipRules(self) -> None:
        tenantWide = entry()
        owned = entry(userId=USER)
        self.assertTrue(tenantWide.isOwnedBy(None))
        self.assertTrue(tenantWide.isOwnedBy(USER))
        self.assertTrue(owned.isOwnedBy(USER))
        self.assertFalse(owned.isOwnedBy(OTHER_USER))
        self.assertFalse(owned.isOwnedBy(None))

    def testExpiryAndSupersession(self) -> None:
        item = entry(expiresAt=CLOCK + timedelta(hours=1))
        self.assertFalse(item.isExpiredAt(CLOCK))
        self.assertTrue(item.isExpiredAt(CLOCK + timedelta(hours=2)))
        item.supersede(now=CLOCK)
        self.assertFalse(item.isActive)
        self.assertEqual(item.supersededAt, CLOCK)
        self.assertFalse(item.isUsableAt(CLOCK))

    def testSupersedeIsIdempotent(self) -> None:
        item = entry()
        item.supersede(now=CLOCK)
        item.supersede(now=CLOCK + timedelta(hours=1))
        self.assertEqual(item.supersededAt, CLOCK)

    def testTtlIsAppliedOnlyWhenTheCallerGaveNone(self) -> None:
        automatic = entry()
        automatic.withExpiry(ScopeBudget(ttlSeconds=3600), now=CLOCK)
        self.assertEqual(automatic.expiresAt, CLOCK + timedelta(seconds=3600))
        explicit = entry(expiresAt=CLOCK + timedelta(days=1))
        explicit.withExpiry(ScopeBudget(ttlSeconds=3600), now=CLOCK)
        self.assertEqual(explicit.expiresAt, CLOCK + timedelta(days=1))
        never = entry()
        never.withExpiry(ScopeBudget(ttlSeconds=0), now=CLOCK)
        self.assertIsNone(never.expiresAt)

    def testNextVersionInheritsIdentityWithoutMutatingTheOriginal(self) -> None:
        first = entry()
        second = first.nextVersion("en", now=CLOCK + timedelta(minutes=1))
        self.assertEqual(second.version, 2)
        self.assertEqual(second.memoryKey, first.memoryKey)
        self.assertEqual(first.value, "fa")
        self.assertEqual(second.value, "en")

    def testValueComparisonUsesTheChecksum(self) -> None:
        item = entry(value={"a": 1, "b": 2})
        self.assertTrue(item.hasSameValueAs({"b": 2, "a": 1}))
        self.assertFalse(item.hasSameValueAs({"a": 1}))

    def testContextProjectionCarriesNoRawIdentifiersBeyondTheKey(self) -> None:
        payload = entry(value={"language": "fa"}).toContextSource()
        self.assertEqual(payload["sourceDomain"], "MEMORY")
        self.assertEqual(payload["sourceEntityType"], "LONG_TERM")
        self.assertEqual(payload["sourceEntityId"], "user.language")
        self.assertIn("language", payload["content"])
        self.assertEqual(payload["classification"], "INTERNAL")

    def testRenderedValueKeepsStringsPlain(self) -> None:
        self.assertEqual(entry(value="fa").renderedValue(), "fa")
        self.assertIn("{", entry(value={"a": 1}).renderedValue())

    def testBridgeToPhase13BMemory(self) -> None:
        bridged = entry(userId=USER).toDomainMemory()
        self.assertIsInstance(bridged, AIMemory)
        self.assertEqual(bridged.scope, "LONG_TERM")
        self.assertEqual(bridged.userId, USER)


class MemoryWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.writer = MemoryWriter(now=frozenClock)
        self.key = MemoryKey(scope="LONG_TERM", key="user.language")

    def testFirstWriteCreatesVersionOne(self) -> None:
        plan = self.writer.plan(TENANT, self.key, "fa")
        self.assertEqual(plan.action, "CREATED")
        self.assertEqual(plan.entry.version, 1)
        self.assertIsNone(plan.superseded)
        self.assertFalse(plan.isNoop)

    def testIdenticalValueIsANoop(self) -> None:
        latest = entry()
        plan = self.writer.plan(TENANT, self.key, "fa", latest=latest)
        self.assertTrue(plan.isNoop)
        self.assertEqual(plan.entry.version, 1)

    def testChangedValueProducesTheNextVersion(self) -> None:
        latest = entry()
        plan = self.writer.plan(TENANT, self.key, "en", latest=latest)
        self.assertEqual(plan.action, "VERSIONED")
        self.assertEqual(plan.entry.version, 2)
        self.assertIs(plan.superseded, latest)
        self.assertEqual(plan.reason, "Value changed.")

    def testForceRewritesEvenAnIdenticalValue(self) -> None:
        plan = self.writer.plan(TENANT, self.key, "fa", latest=entry(), force=True)
        self.assertEqual(plan.action, "VERSIONED")
        self.assertEqual(plan.entry.version, 2)

    def testClassificationChangeAloneStillVersions(self) -> None:
        plan = self.writer.plan(
            TENANT, self.key, "fa", latest=entry(), classification="CONFIDENTIAL"
        )
        self.assertEqual(plan.action, "VERSIONED")
        self.assertEqual(plan.entry.classification, "CONFIDENTIAL")

    def testExpiredPredecessorStartsAFreshEntryAtTheNextVersion(self) -> None:
        stale = entry(expiresAt=CLOCK - timedelta(hours=1))
        plan = self.writer.plan(TENANT, self.key, "en", latest=stale)
        self.assertEqual(plan.action, "CREATED")
        self.assertEqual(plan.entry.version, 2)
        self.assertIn("expired", plan.reason.lower())

    def testScopeTtlIsAppliedToTheNewEntry(self) -> None:
        plan = self.writer.plan(TENANT, self.key, "fa", budget=ScopeBudget(ttlSeconds=60))
        self.assertEqual(plan.entry.expiresAt, CLOCK + timedelta(seconds=60))

    def testOversizedValueIsRefused(self) -> None:
        with self.assertRaises(AIMemoryValueTooLarge):
            self.writer.plan(TENANT, self.key, "x" * 5000, budget=ScopeBudget(maxValueBytes=1024))

    def testPlanRejectsForeignInput(self) -> None:
        with self.assertRaises(AIMemoryInvalid):
            self.writer.plan(TENANT, "LONG_TERM:key", "fa")  # type: ignore[arg-type]
        with self.assertRaises(AIMemoryPolicyInvalid):
            self.writer.plan(TENANT, self.key, "fa", budget="budget")  # type: ignore[arg-type]

    def testChecksumHelperMatchesTheEntry(self) -> None:
        self.assertEqual(MemoryWriter.checksumFor("fa"), entry().checksum)


class RetentionEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = RetentionEvaluator()

    def testEverythingFitsWhenTheScopeIsSmall(self) -> None:
        plan = self.evaluator.evaluate(
            "LONG_TERM", [entry("a"), entry("b")], ScopeBudget(maxEntries=5), now=CLOCK
        )
        self.assertEqual(len(plan.kept), 2)
        self.assertEqual(plan.removedCount, 0)

    def testExpiredEntriesAreReported(self) -> None:
        fresh = entry("fresh")
        stale = entry("stale", expiresAt=CLOCK - timedelta(minutes=1))
        plan = self.evaluator.evaluate(
            "LONG_TERM", [fresh, stale], ScopeBudget(maxEntries=5), now=CLOCK
        )
        self.assertEqual([item.key for item in plan.expired], ["stale"])
        self.assertEqual([item.key for item in plan.kept], ["fresh"])

    def testOldestEntriesAreEvictedFirst(self) -> None:
        entries = [
            entry("oldest", createdAt=CLOCK - timedelta(days=3)),
            entry("middle", createdAt=CLOCK - timedelta(days=2)),
            entry("newest", createdAt=CLOCK - timedelta(days=1)),
        ]
        plan = self.evaluator.evaluate("LONG_TERM", entries, ScopeBudget(maxEntries=2), now=CLOCK)
        self.assertEqual([item.key for item in plan.evicted], ["oldest"])
        self.assertEqual(len(plan.kept), 2)

    def testIncomingWriteCountsAgainstTheBudget(self) -> None:
        entries = [entry("a", createdAt=CLOCK - timedelta(days=2)), entry("b")]
        plan = self.evaluator.evaluate(
            "LONG_TERM", entries, ScopeBudget(maxEntries=2), now=CLOCK, incoming=1
        )
        self.assertEqual([item.key for item in plan.evicted], ["a"])

    def testLowestPriorityStrategyUsesMetadata(self) -> None:
        entries = [
            entry("important", createdAt=CLOCK - timedelta(days=5), metadata={"priority": 9}),
            entry("trivial", createdAt=CLOCK, metadata={"priority": 1}),
        ]
        plan = self.evaluator.evaluate(
            "LONG_TERM",
            entries,
            ScopeBudget(maxEntries=1, eviction="LOWEST_PRIORITY"),
            now=CLOCK,
        )
        self.assertEqual([item.key for item in plan.evicted], ["trivial"])

    def testDisabledEvictionRefusesInsteadOfDroppingData(self) -> None:
        with self.assertRaises(AIMemoryBudgetExceeded):
            self.evaluator.evaluate(
                "LONG_TERM",
                [entry("a"), entry("b")],
                ScopeBudget(maxEntries=1, eviction="NONE"),
                now=CLOCK,
            )

    def testEvaluationIsDeterministicForEqualTimestamps(self) -> None:
        entries = [entry(f"k{index}", createdAt=CLOCK) for index in range(4)]
        first = self.evaluator.evaluate("LONG_TERM", entries, ScopeBudget(maxEntries=2), now=CLOCK)
        second = self.evaluator.evaluate(
            "LONG_TERM", list(reversed(entries)), ScopeBudget(maxEntries=2), now=CLOCK
        )
        self.assertEqual([item.id for item in first.evicted], [item.id for item in second.evicted])

    def testForeignBudgetIsRejected(self) -> None:
        with self.assertRaises(AIMemoryPolicyInvalid):
            self.evaluator.evaluate("LONG_TERM", [], "budget", now=CLOCK)  # type: ignore[arg-type]


class MemorySelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.selector = MemorySelector()

    def testHigherPriorityScopesComeFirst(self) -> None:
        entries = [
            entry("summary", scope="LONG_TERM"),
            entry("topic", scope="CONVERSATION"),
            entry("goal", scope="TASK"),
        ]
        selection = self.selector.select(entries, now=CLOCK)
        self.assertEqual(
            [item.scope for item in selection.entries],
            ["TASK", "CONVERSATION", "LONG_TERM"],
        )

    def testOnlyTheLatestVersionOfAKeyCompetes(self) -> None:
        old = entry("user.language", value="fa", version=1)
        new = entry("user.language", value="en", version=2)
        selection = self.selector.select([old, new], now=CLOCK)
        self.assertEqual(len(selection.entries), 1)
        self.assertEqual(selection.entries[0].value, "en")

    def testExpiredAndInactiveEntriesAreSkipped(self) -> None:
        stale = entry("stale", expiresAt=CLOCK - timedelta(hours=1))
        retired = entry("retired")
        retired.forget(now=CLOCK)
        selection = self.selector.select([stale, retired, entry("live")], now=CLOCK)
        self.assertEqual([item.key for item in selection.entries], ["live"])

    def testAnotherUsersMemoryIsNeverSelected(self) -> None:
        selection = self.selector.select(
            [entry("mine", userId=USER), entry("theirs", userId=OTHER_USER), entry("shared")],
            now=CLOCK,
            userId=USER,
        )
        self.assertEqual({item.key for item in selection.entries}, {"mine", "shared"})

    def testScopeFilterNarrowsTheSelection(self) -> None:
        selection = self.selector.select(
            [entry("a", scope="TASK"), entry("b", scope="LONG_TERM")],
            scopes=("TASK",),
            now=CLOCK,
        )
        self.assertEqual([item.key for item in selection.entries], ["a"])

    def testEntryLimitIsHonoured(self) -> None:
        entries = [entry(f"k{index}") for index in range(5)]
        selection = self.selector.select(entries, maxEntries=2, now=CLOCK)
        self.assertEqual(len(selection.entries), 2)
        self.assertEqual(selection.droppedCount, 3)

    def testTokenBudgetStopsPackingButKeepsTheFirst(self) -> None:
        entries = [entry(f"k{index}", value="word " * 200) for index in range(3)]
        selection = self.selector.select(entries, maxTokens=50, now=CLOCK)
        self.assertEqual(len(selection.entries), 1)
        self.assertGreater(selection.tokenCount, 0)

    def testLimitsMustBePositive(self) -> None:
        with self.assertRaises(AIMemoryInvalid):
            self.selector.select([], maxEntries=0)
        with self.assertRaises(AIMemoryInvalid):
            self.selector.select([], maxTokens=0)

    def testEmptyInputProducesAnEmptySelection(self) -> None:
        selection = self.selector.select([], now=CLOCK)
        self.assertEqual(selection.entries, ())
        self.assertEqual(selection.consideredCount, 0)


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
