"""Persistence for performance reviews — Phase 29.

Django lives here and nowhere above. Everything handed upwards is either a
plain dict (for the API) or one of the pure value objects from
``performanceReviewRules``, so the scoring arithmetic never sees an ORM row.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta

from django.utils.timezone import make_aware

from apps.maintenance.domain.services.performanceReviewRules import (
    RaterScore,
    SystemMetrics,
)
from apps.maintenance.domain.valueObjects.performanceState import (
    CYCLE_DRAFT,
    DEFAULT_SYSTEM_WEIGHT_PERCENT,
)
from apps.maintenance.infrastructure.models import (
    MaintenancePersonnelModel,
    PerformanceRaterScoreModel,
    PerformanceResultModel,
    PerformanceReviewCycleModel,
)


def _loadJson(raw: str) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


class PerformanceReviewRepositoryDjango:
    """Cycles, the marks submitted into them, and the computed results."""

    # -- cycles ------------------------------------------------------------
    def listCycles(self, tenantId: uuid.UUID) -> list[dict]:
        rows = PerformanceReviewCycleModel.objects.filter(
            tenantId=tenantId, deletedAt__isnull=True
        )
        counts = self._scoreCounts(tenantId, [row.id for row in rows])
        return [self._cycleDict(row, counts.get(row.id, 0)) for row in rows]

    def getCycle(self, tenantId: uuid.UUID, cycleId: uuid.UUID) -> dict | None:
        row = PerformanceReviewCycleModel.objects.filter(
            tenantId=tenantId, id=cycleId, deletedAt__isnull=True
        ).first()
        if row is None:
            return None
        return self._cycleDict(row, self._scoreCounts(tenantId, [row.id]).get(row.id, 0))

    def saveCycle(self, tenantId: uuid.UUID, values: dict, now: datetime) -> dict:
        cycleId = values.get("id")
        defaults = {
            "code": values.get("code", ""),
            "name": values.get("name", ""),
            "fromDate": values["fromDate"],
            "toDate": values["toDate"],
            "status": values.get("status") or CYCLE_DRAFT,
            "systemWeightPercent": int(
                values.get("systemWeightPercent", DEFAULT_SYSTEM_WEIGHT_PERCENT)
            ),
            "roleWeights": json.dumps(values.get("roleWeights") or {}, ensure_ascii=False)
            if values.get("roleWeights")
            else "",
            "note": values.get("note", ""),
            "updatedAt": now,
        }
        if cycleId:
            PerformanceReviewCycleModel.objects.filter(
                tenantId=tenantId, id=cycleId
            ).update(**defaults)
            row = PerformanceReviewCycleModel.objects.get(tenantId=tenantId, id=cycleId)
        else:
            row = PerformanceReviewCycleModel.objects.create(
                tenantId=tenantId, createdAt=now, **defaults
            )
        return self._cycleDict(row, 0)

    def deleteCycle(self, tenantId: uuid.UUID, cycleId: uuid.UUID, now: datetime) -> bool:
        updated = PerformanceReviewCycleModel.objects.filter(
            tenantId=tenantId, id=cycleId, deletedAt__isnull=True
        ).update(deletedAt=now)
        if updated:
            # Scores and results go with their cycle; orphans would otherwise
            # be counted into a future cycle that happens to reuse the id.
            PerformanceRaterScoreModel.objects.filter(
                tenantId=tenantId, cycleId=cycleId, deletedAt__isnull=True
            ).update(deletedAt=now)
            PerformanceResultModel.objects.filter(
                tenantId=tenantId, cycleId=cycleId, deletedAt__isnull=True
            ).update(deletedAt=now)
        return bool(updated)

    # -- scores ------------------------------------------------------------
    def listScores(
        self,
        tenantId: uuid.UUID,
        cycleId: uuid.UUID,
        personnelId: uuid.UUID | None = None,
    ) -> list[dict]:
        rows = PerformanceRaterScoreModel.objects.filter(
            tenantId=tenantId, cycleId=cycleId, deletedAt__isnull=True
        )
        if personnelId is not None:
            rows = rows.filter(personnelId=personnelId)
        names = self._personnelNames(tenantId)
        return [self._scoreDict(row, names) for row in rows.order_by("raterRole")]

    def saveScore(self, tenantId: uuid.UUID, values: dict, now: datetime) -> dict:
        """Upsert on (cycle, person, role).

        Deliberately an upsert rather than an insert: a manager revising their
        own mark is normal, a manager voting twice is not, and the unique
        constraint makes the second impossible anyway.
        """
        existing = PerformanceRaterScoreModel.objects.filter(
            tenantId=tenantId,
            cycleId=values["cycleId"],
            personnelId=values["personnelId"],
            raterRole=values["raterRole"],
            deletedAt__isnull=True,
        ).first()
        payload = {
            "score": values.get("score", 0),
            "note": values.get("note", ""),
            "raterName": values.get("raterName", ""),
            "raterUserId": values.get("raterUserId") or None,
            "updatedAt": now,
        }
        if existing is not None:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.save(update_fields=list(payload.keys()))
            row = existing
        else:
            row = PerformanceRaterScoreModel.objects.create(
                tenantId=tenantId,
                cycleId=values["cycleId"],
                personnelId=values["personnelId"],
                raterRole=values["raterRole"],
                submittedAt=now,
                **payload,
            )
        return self._scoreDict(row, self._personnelNames(tenantId))

    def deleteScore(self, tenantId: uuid.UUID, scoreId: uuid.UUID, now: datetime) -> bool:
        return bool(
            PerformanceRaterScoreModel.objects.filter(
                tenantId=tenantId, id=scoreId, deletedAt__isnull=True
            ).update(deletedAt=now)
        )

    def loadRaterScores(
        self, tenantId: uuid.UUID, cycleId: uuid.UUID
    ) -> dict[uuid.UUID, list[RaterScore]]:
        """Every mark in a cycle, grouped by the person it is about.

        Each rater arrives carrying their own history, because reliability is
        learned across cycles and the domain layer cannot read a database.
        """
        history = self.raterHistory(tenantId, cycleId)
        grouped: dict[uuid.UUID, list[RaterScore]] = {}
        rows = PerformanceRaterScoreModel.objects.filter(
            tenantId=tenantId, cycleId=cycleId, deletedAt__isnull=True
        )
        for row in rows:
            deviation, cycles = history.get(row.raterRole, (None, 0))
            grouped.setdefault(row.personnelId, []).append(
                RaterScore(
                    raterRole=row.raterRole,
                    score=float(row.score),
                    raterName=row.raterName,
                    note=row.note,
                    historicalDeviation=deviation,
                    historicalCycles=cycles,
                )
            )
        return grouped

    def raterHistory(
        self, tenantId: uuid.UUID, excludeCycleId: uuid.UUID | None = None
    ) -> dict[str, tuple[float, int]]:
        """Mean absolute z-distance from consensus per role, over past cycles.

        This is the part that learns. It is read out of the stored breakdowns
        of *previous* results rather than recomputed, so a rater's standing
        reflects the cycles as they were actually judged. The current cycle is
        excluded so a rater is never penalised twice for the same mark — once
        through damping and again through their own history.
        """
        rows = PerformanceResultModel.objects.filter(
            tenantId=tenantId, deletedAt__isnull=True
        )
        if excludeCycleId is not None:
            rows = rows.exclude(cycleId=excludeCycleId)

        totals: dict[str, list[float]] = {}
        cyclesSeen: dict[str, set] = {}
        for row in rows.only("cycleId", "breakdown"):
            payload = _loadJson(row.breakdown)
            for entry in payload.get("raters", []):
                role = entry.get("raterRole")
                if not role:
                    continue
                try:
                    deviation = abs(float(entry.get("deviation", 0)))
                except (TypeError, ValueError):
                    continue
                totals.setdefault(role, []).append(deviation)
                cyclesSeen.setdefault(role, set()).add(row.cycleId)

        return {
            role: (sum(values) / len(values), len(cyclesSeen.get(role, set())))
            for role, values in totals.items()
            if values
        }

    # -- results -----------------------------------------------------------
    def saveResults(
        self, tenantId: uuid.UUID, cycleId: uuid.UUID, outcomes: list, now: datetime
    ) -> int:
        """Replace a cycle's results with a freshly computed set."""
        PerformanceResultModel.objects.filter(
            tenantId=tenantId, cycleId=cycleId, deletedAt__isnull=True
        ).update(deletedAt=now)
        created = 0
        for outcome in outcomes:
            PerformanceResultModel.objects.create(
                tenantId=tenantId,
                cycleId=cycleId,
                personnelId=outcome.personnelId,
                finalScore=outcome.finalScore,
                humanScore=outcome.humanScore,
                systemScore=outcome.systemScoreValue,
                consensus=outcome.consensus,
                spread=outcome.spread,
                raterCount=outcome.raterCount,
                dampedCount=outcome.dampedCount,
                systemWeightPercent=outcome.systemWeightPercent,
                breakdown=json.dumps(
                    {
                        "raters": [
                            {
                                "raterRole": rater.raterRole,
                                "raterName": rater.raterName,
                                "rawScore": rater.rawScore,
                                "baseWeight": rater.baseWeight,
                                "deviation": rater.deviation,
                                "damping": rater.damping,
                                "reliability": rater.reliability,
                                "contribution": rater.contribution,
                                "damped": rater.damped,
                                "reason": rater.reason,
                            }
                            for rater in outcome.raters
                        ],
                        "systemMetrics": outcome.systemMetrics,
                        "notes": outcome.notes,
                    },
                    ensure_ascii=False,
                ),
                computedAt=now,
            )
            created += 1
        return created

    def listResults(self, tenantId: uuid.UUID, cycleId: uuid.UUID) -> list[dict]:
        rows = PerformanceResultModel.objects.filter(
            tenantId=tenantId, cycleId=cycleId, deletedAt__isnull=True
        ).order_by("-finalScore")
        names = self._personnelNames(tenantId)
        return [self._resultDict(row, names) for row in rows]

    # -- the measured half -------------------------------------------------
    def loadSystemMetrics(
        self, tenantId: uuid.UUID, start: date, end: date
    ) -> dict[uuid.UUID, SystemMetrics]:
        """What the work record says about each person over the window.

        A caveat worth stating plainly, because it limits how far this can be
        trusted: work orders and PM executions identify who did the work by
        **name string** (``assignedToName``, ``performedByName``), not by a
        foreign key to personnel. So the join below is on the person's name.
        Two technicians with the same name would be merged, and a typo or a
        later rename silently detaches the history. Fixing that properly means
        adding real personnel references to those tables, which is a change to
        two established contexts and is not in this slice.

        Every metric is ``None`` when there is nothing to measure, never zero:
        a technician who was never assigned preventive work must not be marked
        down for preventive compliance they were never given a chance to earn.
        ``onTimeCompletion`` is always ``None`` here because work orders carry
        no due date at all — rather than invent one, the weight it would have
        taken is renormalised across the metrics that do exist.
        """
        from apps.maintenance.domain.valueObjects.maintenanceState import WO_COMPLETED
        from apps.maintenance.infrastructure.models import (
            PmExecutionModel,
            WorkOrderModel,
        )

        # Work order timestamps are timezone-aware; comparing them against a
        # naive datetime warns now and silently shifts the window later.
        startAt = make_aware(datetime.combine(start, datetime.min.time()))
        endAt = make_aware(datetime.combine(end + timedelta(days=1), datetime.min.time()))

        byName: dict[str, uuid.UUID] = {}
        for row in MaintenancePersonnelModel.objects.filter(
            tenantId=tenantId, deletedAt__isnull=True
        ).values("id", "fullName"):
            name = (row["fullName"] or "").strip()
            if name:
                byName[name] = row["id"]

        orders: dict[uuid.UUID, dict[str, int]] = {}
        orderRows = WorkOrderModel.objects.filter(
            tenantId=tenantId,
            deletedAt__isnull=True,
            createdAt__gte=startAt,
            createdAt__lt=endAt,
        ).values("assignedToName", "status", "repeatFailure")
        for row in orderRows:
            personnelId = byName.get((row.get("assignedToName") or "").strip())
            if personnelId is None:
                continue
            bucket = orders.setdefault(
                personnelId, {"total": 0, "completed": 0, "repeat": 0}
            )
            bucket["total"] += 1
            if row.get("status") == WO_COMPLETED:
                bucket["completed"] += 1
            if row.get("repeatFailure"):
                bucket["repeat"] += 1

        pm: dict[uuid.UUID, dict[str, int]] = {}
        # PmExecution has no soft-delete column — an execution is a historical
        # fact, so there is nothing to filter here.
        pmRows = PmExecutionModel.objects.filter(
            tenantId=tenantId,
            performedOn__gte=start,
            performedOn__lte=end,
        ).values("performedByName", "onTime")
        for row in pmRows:
            personnelId = byName.get((row.get("performedByName") or "").strip())
            if personnelId is None:
                continue
            bucket = pm.setdefault(personnelId, {"total": 0, "onTime": 0})
            bucket["total"] += 1
            if row.get("onTime"):
                bucket["onTime"] += 1

        metrics: dict[uuid.UUID, SystemMetrics] = {}
        for personnelId in set(orders) | set(pm):
            orderStat = orders.get(personnelId)
            pmStat = pm.get(personnelId)
            completionRate = None
            rework = None
            if orderStat and orderStat["total"]:
                completionRate = orderStat["completed"] / orderStat["total"] * 100.0
                # A penalty expressed as a score: no repeat failures is 100.
                rework = (1 - orderStat["repeat"] / orderStat["total"]) * 100.0
            compliance = None
            if pmStat and pmStat["total"]:
                compliance = pmStat["onTime"] / pmStat["total"] * 100.0
            metrics[personnelId] = SystemMetrics(
                pmCompliance=compliance,
                onTimeCompletion=None,
                completionRate=completionRate,
                reworkPenalty=rework,
            )
        return metrics

    def listPersonnel(self, tenantId: uuid.UUID) -> list[dict]:
        rows = MaintenancePersonnelModel.objects.filter(
            tenantId=tenantId, deletedAt__isnull=True, active=True
        ).order_by("fullName")
        return [
            {
                "id": str(row.id),
                "personnelCode": row.personnelCode,
                "fullName": row.fullName,
                "specialty": row.specialty,
                "unit": row.unit,
            }
            for row in rows
        ]

    # -- helpers -----------------------------------------------------------
    def _scoreCounts(self, tenantId: uuid.UUID, cycleIds: list) -> dict:
        if not cycleIds:
            return {}
        counts: dict = {}
        rows = PerformanceRaterScoreModel.objects.filter(
            tenantId=tenantId, cycleId__in=cycleIds, deletedAt__isnull=True
        ).values_list("cycleId", flat=True)
        for cycleId in rows:
            counts[cycleId] = counts.get(cycleId, 0) + 1
        return counts

    def _personnelNames(self, tenantId: uuid.UUID) -> dict:
        return dict(
            MaintenancePersonnelModel.objects.filter(
                tenantId=tenantId, deletedAt__isnull=True
            ).values_list("id", "fullName")
        )

    def _cycleDict(self, row: PerformanceReviewCycleModel, scoreCount: int) -> dict:
        return {
            "id": str(row.id),
            "code": row.code,
            "name": row.name,
            "fromDate": row.fromDate.isoformat(),
            "toDate": row.toDate.isoformat(),
            "status": row.status,
            "systemWeightPercent": row.systemWeightPercent,
            "roleWeights": _loadJson(row.roleWeights),
            "note": row.note,
            "scoreCount": scoreCount,
        }

    def _scoreDict(self, row: PerformanceRaterScoreModel, names: dict) -> dict:
        return {
            "id": str(row.id),
            "cycleId": str(row.cycleId),
            "personnelId": str(row.personnelId),
            "personnelName": names.get(row.personnelId, ""),
            "raterRole": row.raterRole,
            "raterName": row.raterName,
            "score": float(row.score),
            "note": row.note,
        }

    def _resultDict(self, row: PerformanceResultModel, names: dict) -> dict:
        payload = _loadJson(row.breakdown)
        return {
            "id": str(row.id),
            "cycleId": str(row.cycleId),
            "personnelId": str(row.personnelId),
            "personnelName": names.get(row.personnelId, ""),
            "finalScore": float(row.finalScore),
            "humanScore": float(row.humanScore),
            "systemScore": float(row.systemScore) if row.systemScore is not None else None,
            "consensus": float(row.consensus),
            "spread": float(row.spread),
            "raterCount": row.raterCount,
            "dampedCount": row.dampedCount,
            "systemWeightPercent": row.systemWeightPercent,
            "raters": payload.get("raters", []),
            "systemMetrics": payload.get("systemMetrics", {}),
            "notes": payload.get("notes", []),
        }
