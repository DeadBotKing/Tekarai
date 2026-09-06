"""Phase 13-W integration tests — the observability stores over SQLite.

Covers the ``aiMetricSnapshots`` and ``aiAlertEvents`` persistence
contract: snapshot round trips with metric fidelity, the "latest window"
lookup that exposition and health depend on, time-filtered listings,
alert round trips and lifecycle updates, the active-alert query that
drives de-duplication, and the two retention sweeps — snapshots by window
end, alerts only once they are resolved.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from django.test import TestCase

from apps.ai.domain.entities.observabilityRecords import AIAlertEvent, AIMetricSnapshot
from apps.ai.domain.exceptions import AIAlertRuleInvalid
from apps.ai.infrastructure.models import AIAlertEventModel, AIMetricSnapshotModel
from apps.ai.infrastructure.repositories.observabilityRepositories import (
    DjangoAlertEventStore,
    DjangoMetricSnapshotStore,
    alertToEntity,
    snapshotToEntity,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


class DjangoMetricSnapshotStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.store = DjangoMetricSnapshotStore()

    def snapshot(self, **overrides: object) -> AIMetricSnapshot:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "windowStart": overrides.pop("windowStart", CLOCK - timedelta(hours=1)),
            "windowEnd": overrides.pop("windowEnd", CLOCK),
            "metrics": {
                "aiRequestsTotal": 42,
                "aiErrorRatio": 0.125,
                "aiCostTotal": 1.5,
            },
            "labels": {"tenant": "acme"},
            "sampleCount": 3,
            "metadata": {"contributors": ["USAGE"]},
        }
        params.update(overrides)
        return AIMetricSnapshot(**params)

    def testRoundTripPreservesMetricsAndLabels(self) -> None:
        stored = self.store.saveSnapshot(self.snapshot())
        loaded = self.store.getSnapshot(self.tenantId, stored.id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.valueFor("aiRequestsTotal"), 42.0)
        self.assertEqual(loaded.valueFor("aiErrorRatio"), 0.125)
        self.assertEqual(loaded.labels, {"tenant": "acme"})
        self.assertEqual(loaded.sampleCount, 3)
        self.assertEqual(loaded.metadata["contributors"], ["USAGE"])
        self.assertEqual(loaded.durationSeconds, 3600.0)

    def testUnknownSnapshotReadsAsNone(self) -> None:
        self.assertIsNone(self.store.getSnapshot(self.tenantId, uuid.uuid4()))

    def testReadsAreTenantScoped(self) -> None:
        stored = self.store.saveSnapshot(self.snapshot())
        self.assertIsNone(self.store.getSnapshot(self.otherTenantId, stored.id))
        self.assertIsNone(self.store.latestSnapshot(self.otherTenantId))

    def testLatestSnapshotIsTheNewestWindow(self) -> None:
        self.store.saveSnapshot(self.snapshot())
        newer = self.store.saveSnapshot(
            self.snapshot(windowStart=CLOCK, windowEnd=CLOCK + timedelta(hours=1))
        )
        latest = self.store.latestSnapshot(self.tenantId)
        assert latest is not None
        self.assertEqual(latest.id, newer.id)

    def testListingIsNewestFirstAndBounded(self) -> None:
        for offset in range(3):
            self.store.saveSnapshot(
                self.snapshot(
                    windowStart=CLOCK + timedelta(hours=offset),
                    windowEnd=CLOCK + timedelta(hours=offset + 1),
                )
            )
        rows = self.store.listSnapshots(self.tenantId)
        self.assertEqual(len(rows), 3)
        self.assertGreater(rows[0].windowEnd, rows[1].windowEnd)
        self.assertEqual(len(self.store.listSnapshots(self.tenantId, limit=1)), 1)

    def testListingFiltersByTimeWindow(self) -> None:
        self.store.saveSnapshot(
            self.snapshot(
                windowStart=CLOCK - timedelta(days=10), windowEnd=CLOCK - timedelta(days=9)
            )
        )
        self.store.saveSnapshot(self.snapshot())
        recent = self.store.listSnapshots(
            self.tenantId, since=CLOCK - timedelta(days=1), until=CLOCK + timedelta(minutes=1)
        )
        self.assertEqual(len(recent), 1)

    def testRetentionRemovesOldWindows(self) -> None:
        old = self.store.saveSnapshot(
            self.snapshot(
                windowStart=CLOCK - timedelta(days=200), windowEnd=CLOCK - timedelta(days=199)
            )
        )
        keep = self.store.saveSnapshot(self.snapshot())
        removed = self.store.deleteSnapshotsBefore(self.tenantId, CLOCK - timedelta(days=90))
        self.assertEqual(removed, 1)
        self.assertFalse(AIMetricSnapshotModel.objects.filter(id=old.id).exists())
        self.assertTrue(AIMetricSnapshotModel.objects.filter(id=keep.id).exists())

    def testRetentionCanRunAcrossAllTenants(self) -> None:
        for tenant in (self.tenantId, self.otherTenantId):
            self.store.saveSnapshot(
                self.snapshot(
                    tenantId=tenant,
                    windowStart=CLOCK - timedelta(days=200),
                    windowEnd=CLOCK - timedelta(days=199),
                )
            )
        self.assertEqual(self.store.deleteSnapshotsBefore(None, CLOCK - timedelta(days=90)), 2)

    def testMapperProducesAValidatedEntity(self) -> None:
        stored = self.store.saveSnapshot(self.snapshot())
        row = AIMetricSnapshotModel.objects.get(id=stored.id)
        entity = snapshotToEntity(row)
        self.assertIsInstance(entity, AIMetricSnapshot)
        self.assertEqual(len(entity.toSamples()), 3)


class DjangoAlertEventStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.store = DjangoAlertEventStore()

    def alert(self, **overrides: object) -> AIAlertEvent:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "ruleCode": overrides.pop("ruleCode", "AI_ERROR_RATIO_HIGH"),
            "metric": overrides.pop("metric", "aiErrorRatio"),
            "severity": overrides.pop("severity", "CRITICAL"),
            "observedValue": 0.42,
            "threshold": 0.1,
            "message": "error ratio too high",
            "firedAt": overrides.pop("firedAt", CLOCK),
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIAlertEvent(**params)

    def testRoundTripPreservesTheNumbers(self) -> None:
        stored = self.store.saveAlert(self.alert())
        loaded = self.store.getAlert(self.tenantId, stored.id)
        assert loaded is not None
        self.assertEqual(loaded.ruleCode, "AI_ERROR_RATIO_HIGH")
        self.assertEqual(loaded.observedValue, 0.42)
        self.assertEqual(loaded.threshold, 0.1)
        self.assertEqual(loaded.severity, "CRITICAL")
        self.assertEqual(loaded.state, "FIRING")
        self.assertTrue(loaded.isActive)

    def testReadsAreTenantScoped(self) -> None:
        stored = self.store.saveAlert(self.alert())
        self.assertIsNone(self.store.getAlert(self.otherTenantId, stored.id))
        self.assertEqual(self.store.listActiveAlerts(self.otherTenantId), ())

    def testUpdatePersistsResolution(self) -> None:
        stored = self.store.saveAlert(self.alert())
        stored.resolve(now=CLOCK + timedelta(minutes=5))
        updated = self.store.updateAlert(stored)
        self.assertEqual(updated.state, "RESOLVED")
        self.assertEqual(updated.resolvedAt, CLOCK + timedelta(minutes=5))
        self.assertEqual(updated.durationSeconds(), 300.0)

    def testUpdatePersistsAcknowledgement(self) -> None:
        stored = self.store.saveAlert(self.alert())
        actor = uuid.uuid4()
        stored.acknowledge(actorId=actor, now=CLOCK + timedelta(minutes=1))
        updated = self.store.updateAlert(stored)
        self.assertEqual(updated.state, "ACKNOWLEDGED")
        self.assertEqual(updated.acknowledgedBy, actor)

    def testUpdatingAnUnknownRowIsRefused(self) -> None:
        with self.assertRaises(AIAlertRuleInvalid):
            self.store.updateAlert(self.alert())

    def testActiveAlertsExcludeResolvedOnes(self) -> None:
        firing = self.store.saveAlert(self.alert())
        resolved = self.store.saveAlert(
            self.alert(ruleCode="AI_QUEUE_BACKLOG", metric="aiQueueDepth")
        )
        resolved.resolve(now=CLOCK)
        self.store.updateAlert(resolved)
        active = self.store.listActiveAlerts(self.tenantId)
        self.assertEqual([item.id for item in active], [firing.id])

    def testAcknowledgedAlertsStayActive(self) -> None:
        stored = self.store.saveAlert(self.alert())
        stored.acknowledge(now=CLOCK)
        self.store.updateAlert(stored)
        self.assertEqual(len(self.store.listActiveAlerts(self.tenantId)), 1)

    def testListingFiltersByStateSeverityAndRule(self) -> None:
        self.store.saveAlert(self.alert())
        self.store.saveAlert(
            self.alert(ruleCode="AI_QUEUE_BACKLOG", metric="aiQueueDepth", severity="WARNING")
        )
        self.assertEqual(len(self.store.listAlerts(self.tenantId)), 2)
        self.assertEqual(len(self.store.listAlerts(self.tenantId, severities=("WARNING",))), 1)
        self.assertEqual(len(self.store.listAlerts(self.tenantId, ruleCode="ai_queue_backlog")), 1)
        self.assertEqual(len(self.store.listAlerts(self.tenantId, states=("RESOLVED",))), 0)

    def testListingIsNewestFirstAndBounded(self) -> None:
        older = self.store.saveAlert(self.alert(firedAt=CLOCK - timedelta(hours=2)))
        newer = self.store.saveAlert(self.alert(firedAt=CLOCK))
        rows = self.store.listAlerts(self.tenantId)
        self.assertEqual([item.id for item in rows], [newer.id, older.id])
        self.assertEqual(len(self.store.listAlerts(self.tenantId, limit=1)), 1)

    def testTheSameRuleMayFireTwiceOverTime(self) -> None:
        first = self.store.saveAlert(self.alert(firedAt=CLOCK - timedelta(hours=3)))
        first.resolve(now=CLOCK - timedelta(hours=2))
        self.store.updateAlert(first)
        self.store.saveAlert(self.alert(firedAt=CLOCK))
        self.assertEqual(AIAlertEventModel.objects.count(), 2)
        self.assertEqual(len(self.store.listActiveAlerts(self.tenantId)), 1)

    def testRetentionRemovesResolvedAlertsOnly(self) -> None:
        firing = self.store.saveAlert(self.alert(firedAt=CLOCK - timedelta(days=400)))
        resolved = self.store.saveAlert(
            self.alert(
                ruleCode="AI_QUEUE_BACKLOG",
                metric="aiQueueDepth",
                firedAt=CLOCK - timedelta(days=400),
            )
        )
        resolved.resolve(now=CLOCK - timedelta(days=399))
        self.store.updateAlert(resolved)
        removed = self.store.deleteAlertsBefore(self.tenantId, CLOCK - timedelta(days=365))
        self.assertEqual(removed, 1)
        self.assertTrue(AIAlertEventModel.objects.filter(id=firing.id).exists())

    def testRetentionCanRunAcrossAllTenants(self) -> None:
        for tenant in (self.tenantId, self.otherTenantId):
            alert = self.store.saveAlert(
                self.alert(tenantId=tenant, firedAt=CLOCK - timedelta(days=400))
            )
            alert.resolve(now=CLOCK - timedelta(days=399))
            self.store.updateAlert(alert)
        self.assertEqual(self.store.deleteAlertsBefore(None, CLOCK - timedelta(days=365)), 2)

    def testMapperProducesAValidatedEntity(self) -> None:
        stored = self.store.saveAlert(self.alert())
        row = AIAlertEventModel.objects.get(id=stored.id)
        entity = alertToEntity(row)
        self.assertIsInstance(entity, AIAlertEvent)
        self.assertEqual(entity.metric, "aiErrorRatio")

    def testUnknownAlertReadsAsNone(self) -> None:
        self.assertIsNone(self.store.getAlert(self.tenantId, uuid.uuid4()))
