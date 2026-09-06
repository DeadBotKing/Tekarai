"""Phase 13-T integration tests — ``DjangoMemoryEntryStore`` over SQLite.

Covers the ``aiMemoryEntries`` persistence contract: version round trips
with checksum and size fidelity, the "latest usable version" lookup that
every write starts from, owner-scoped visibility (tenant-wide rows are
shared, owned rows are not), scope/conversation filtered listings, the
lifecycle update that retires a version without editing its value, the
database-level uniqueness of one version per slot, targeted and key-wide
deletes, and the retention sweep that only touches retired rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.ai.domain.entities.memoryRecords import AIMemoryEntry
from apps.ai.domain.exceptions import AIMemoryInvalid
from apps.ai.domain.valueObjects.memoryTypes import MemoryKey, valueChecksum, valueSize
from apps.ai.infrastructure.models import AIMemoryEntryModel
from apps.ai.infrastructure.repositories.memoryRepositories import (
    DjangoMemoryEntryStore,
    memoryToEntity,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


class DjangoMemoryEntryStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.userId = uuid.uuid4()
        self.otherUserId = uuid.uuid4()
        self.store = DjangoMemoryEntryStore()

    def entry(
        self,
        key: str = "user.language",
        value: object = "fa",
        *,
        scope: str = "LONG_TERM",
        version: int = 1,
        userId: uuid.UUID | None = None,
        tenantId: uuid.UUID | None = None,
        conversationId: str = "",
        createdAt: datetime | None = None,
        classification: str = "INTERNAL",
        expiresAt: datetime | None = None,
    ) -> AIMemoryEntry:
        return AIMemoryEntry(
            tenantId=tenantId or self.tenantId,
            memoryKey=MemoryKey(scope=scope, key=key),
            value=value,
            version=version,
            userId=userId,
            conversationId=conversationId,
            classification=classification,
            expiresAt=expiresAt,
            metadata={"origin": "test"},
            createdAt=createdAt or CLOCK,
        )

    # -- round trip -----------------------------------------------------
    def testRoundTripPreservesValueChecksumAndSize(self) -> None:
        payload = {"language": "fa", "channels": ["email", "sms"]}
        stored = self.store.saveEntry(self.entry(value=payload))
        loaded = self.store.getEntry(self.tenantId, stored.id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.value, payload)
        self.assertEqual(loaded.checksum, valueChecksum(payload))
        self.assertEqual(loaded.sizeBytes, valueSize(payload))
        self.assertEqual(loaded.metadata, {"origin": "test"})
        self.assertEqual(loaded.qualifiedKey, "LONG_TERM:user.language")

    def testKeysAreStoredNormalized(self) -> None:
        self.store.saveEntry(self.entry(key="  User.Language "))
        row = AIMemoryEntryModel.objects.get(tenantId=self.tenantId)
        self.assertEqual(row.memoryKey, "user.language")

    def testUnknownEntryReadsAsNone(self) -> None:
        self.assertIsNone(self.store.getEntry(self.tenantId, uuid.uuid4()))

    def testReadsAreTenantScoped(self) -> None:
        stored = self.store.saveEntry(self.entry())
        self.assertIsNone(self.store.getEntry(self.otherTenantId, stored.id))
        self.assertIsNone(self.store.latestForKey(self.otherTenantId, "LONG_TERM", "user.language"))

    # -- latest / versions ----------------------------------------------
    def testLatestForKeyReturnsTheHighestVersion(self) -> None:
        self.store.saveEntry(self.entry(value="fa", version=1))
        self.store.saveEntry(self.entry(value="en", version=2))
        latest = self.store.latestForKey(self.tenantId, "LONG_TERM", "user.language")
        assert latest is not None
        self.assertEqual(latest.version, 2)
        self.assertEqual(latest.value, "en")

    def testLatestForKeyNormalizesItsArguments(self) -> None:
        self.store.saveEntry(self.entry())
        self.assertIsNotNone(
            self.store.latestForKey(self.tenantId, "long_term", "  USER.Language ")
        )

    def testListVersionsIsOrderedOldestFirst(self) -> None:
        for version, value in ((1, "fa"), (2, "en"), (3, "de")):
            self.store.saveEntry(self.entry(value=value, version=version))
        versions = self.store.listVersions(self.tenantId, "LONG_TERM", "user.language")
        self.assertEqual([item.version for item in versions], [1, 2, 3])

    def testOneVersionPerSlotIsEnforcedByTheDatabase(self) -> None:
        self.store.saveEntry(self.entry(version=1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.store.saveEntry(self.entry(value="other", version=1))

    def testTwoUsersMayHoldTheSameKeyAndVersion(self) -> None:
        self.store.saveEntry(self.entry(userId=self.userId))
        self.store.saveEntry(self.entry(value="en", userId=self.otherUserId))
        self.assertEqual(AIMemoryEntryModel.objects.count(), 2)

    # -- ownership ------------------------------------------------------
    def testOwnerlessLookupSeesOnlyTenantWideRows(self) -> None:
        self.store.saveEntry(self.entry(key="owned", userId=self.userId))
        self.store.saveEntry(self.entry(key="shared"))
        self.assertIsNone(self.store.latestForKey(self.tenantId, "LONG_TERM", "owned"))
        self.assertIsNotNone(self.store.latestForKey(self.tenantId, "LONG_TERM", "shared"))

    def testOwnerLookupSeesOwnedAndTenantWideRows(self) -> None:
        self.store.saveEntry(self.entry(key="owned", userId=self.userId))
        self.store.saveEntry(self.entry(key="shared"))
        self.assertIsNotNone(
            self.store.latestForKey(self.tenantId, "LONG_TERM", "owned", userId=self.userId)
        )
        self.assertIsNotNone(
            self.store.latestForKey(self.tenantId, "LONG_TERM", "shared", userId=self.userId)
        )
        self.assertIsNone(
            self.store.latestForKey(self.tenantId, "LONG_TERM", "owned", userId=self.otherUserId)
        )

    # -- listings -------------------------------------------------------
    def testListActiveFiltersByScope(self) -> None:
        self.store.saveEntry(self.entry(key="a", scope="TASK"))
        self.store.saveEntry(self.entry(key="b", scope="LONG_TERM"))
        rows = self.store.listActive(self.tenantId, scopes=("TASK",))
        self.assertEqual([item.key for item in rows], ["a"])

    def testListActiveFiltersByConversation(self) -> None:
        self.store.saveEntry(self.entry(key="a", scope="CONVERSATION", conversationId="c1"))
        self.store.saveEntry(self.entry(key="b", scope="CONVERSATION", conversationId="c2"))
        rows = self.store.listActive(self.tenantId, conversationId="c1")
        self.assertEqual([item.key for item in rows], ["a"])

    def testListActiveSkipsRetiredRows(self) -> None:
        stored = self.store.saveEntry(self.entry())
        stored.forget(now=CLOCK)
        self.store.updateEntry(stored)
        self.assertEqual(self.store.listActive(self.tenantId), ())

    def testListActiveRespectsTheLimit(self) -> None:
        for index in range(5):
            self.store.saveEntry(self.entry(key=f"k{index}"))
        self.assertEqual(len(self.store.listActive(self.tenantId, limit=2)), 2)

    def testCountActiveIsScopeAndTenantScoped(self) -> None:
        self.store.saveEntry(self.entry(key="a", scope="TASK"))
        self.store.saveEntry(self.entry(key="b", scope="TASK"))
        self.store.saveEntry(self.entry(key="c", scope="LONG_TERM"))
        self.assertEqual(self.store.countActive(self.tenantId, "TASK"), 2)
        self.assertEqual(self.store.countActive(self.otherTenantId, "TASK"), 0)

    # -- lifecycle updates ----------------------------------------------
    def testUpdateRetiresAVersionWithoutEditingItsValue(self) -> None:
        stored = self.store.saveEntry(self.entry(value="fa"))
        stored.supersede(now=CLOCK)
        updated = self.store.updateEntry(stored)
        self.assertFalse(updated.isActive)
        self.assertEqual(updated.supersededAt, CLOCK)
        self.assertEqual(AIMemoryEntryModel.objects.get(id=stored.id).value, "fa")

    def testUpdatingAnUnknownRowIsRefused(self) -> None:
        with self.assertRaises(AIMemoryInvalid):
            self.store.updateEntry(self.entry(key="ghost"))

    # -- deletes --------------------------------------------------------
    def testDeleteEntriesIsTargetedAndTenantScoped(self) -> None:
        first = self.store.saveEntry(self.entry(key="a"))
        self.store.saveEntry(self.entry(key="b"))
        self.assertEqual(self.store.deleteEntries(self.otherTenantId, (first.id,)), 0)
        self.assertEqual(self.store.deleteEntries(self.tenantId, (first.id,)), 1)
        self.assertEqual(self.store.deleteEntries(self.tenantId, ()), 0)
        self.assertEqual(AIMemoryEntryModel.objects.count(), 1)

    def testDeleteKeyRemovesEveryVersionOfThatSlot(self) -> None:
        self.store.saveEntry(self.entry(version=1))
        self.store.saveEntry(self.entry(value="en", version=2))
        self.store.saveEntry(self.entry(key="other"))
        self.assertEqual(self.store.deleteKey(self.tenantId, "LONG_TERM", "user.language"), 2)
        self.assertEqual(AIMemoryEntryModel.objects.count(), 1)

    def testDeleteKeyIsOwnerScoped(self) -> None:
        self.store.saveEntry(self.entry(userId=self.userId))
        self.assertEqual(
            self.store.deleteKey(
                self.tenantId, "LONG_TERM", "user.language", userId=self.otherUserId
            ),
            0,
        )
        self.assertEqual(
            self.store.deleteKey(self.tenantId, "LONG_TERM", "user.language", userId=self.userId),
            1,
        )

    def testRetentionSweepOnlyTouchesRetiredRows(self) -> None:
        live = self.store.saveEntry(self.entry(key="live"))
        retired = self.store.saveEntry(self.entry(key="retired"))
        retired.forget(now=CLOCK)
        self.store.updateEntry(retired)
        AIMemoryEntryModel.objects.filter(id__in=[live.id, retired.id]).update(
            createdAt=CLOCK - timedelta(days=800)
        )
        removed = self.store.deleteEntriesBefore(self.tenantId, CLOCK - timedelta(days=30))
        self.assertEqual(removed, 1)
        self.assertTrue(AIMemoryEntryModel.objects.filter(id=live.id).exists())

    def testRetentionSweepCanRunAcrossAllTenants(self) -> None:
        first = self.store.saveEntry(self.entry(key="a"))
        second = self.store.saveEntry(self.entry(key="b", tenantId=self.otherTenantId))
        for entry in (first, second):
            entry.forget(now=CLOCK)
            self.store.updateEntry(entry)
        AIMemoryEntryModel.objects.filter(id__in=[first.id, second.id]).update(
            createdAt=CLOCK - timedelta(days=800)
        )
        self.assertEqual(self.store.deleteEntriesBefore(None, CLOCK - timedelta(days=30)), 2)

    # -- mapping --------------------------------------------------------
    def testMapperProducesAValidatedEntity(self) -> None:
        stored = self.store.saveEntry(self.entry(expiresAt=CLOCK + timedelta(hours=1)))
        row = AIMemoryEntryModel.objects.get(id=stored.id)
        entity = memoryToEntity(row)
        self.assertIsInstance(entity, AIMemoryEntry)
        self.assertTrue(entity.isUsableAt(CLOCK))
        self.assertTrue(entity.isExpiredAt(CLOCK + timedelta(hours=2)))

    def testTenantWideSlotsCannotDuplicateAVersion(self) -> None:
        # A nullable owner column would let this pass (NULL != NULL in SQL);
        # the non-null ownerKey sentinel is what makes the constraint hold.
        self.store.saveEntry(self.entry(version=1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.store.saveEntry(self.entry(value="other", version=1))

    def testOwnerSentinelIsWrittenForBothCases(self) -> None:
        shared = self.store.saveEntry(self.entry(key="shared"))
        owned = self.store.saveEntry(self.entry(key="owned", userId=self.userId))
        self.assertEqual(AIMemoryEntryModel.objects.get(id=shared.id).ownerKey, "tenant")
        self.assertEqual(AIMemoryEntryModel.objects.get(id=owned.id).ownerKey, str(self.userId))
