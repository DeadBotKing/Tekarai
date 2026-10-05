"""Personnel performance review use cases — Phase 29.

The slice answers one question defensibly: *what mark did this person earn
this period, and why that mark?*

Three things combine. Managers submit opinions. The work record contributes a
measured score of its own. A weighting then merges them — and, crucially,
down-weights opinions that sit far from where every other rater sits, so one
manager playing favourites or settling a grudge cannot move the result much.

The arithmetic itself lives in ``domain/services/performanceReviewRules.py``
as pure functions; this layer only fetches, authorises, validates and stores.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace

from apps.maintenance.application.services.tenantResolver import (
    parseDateOrNone,
    resolveTenantId,
)
from apps.maintenance.application.useCases.registryUseCases import (
    PERMISSION_REGISTRY_MANAGE,
    PERMISSION_REGISTRY_VIEW,
)
from apps.maintenance.domain.services.performanceReviewRules import (
    rankOutcomes,
    scoreReview,
)
from apps.maintenance.domain.valueObjects.performanceState import (
    CYCLE_CLOSED,
    CYCLE_STATUSES,
    DEFAULT_ROLE_WEIGHTS,
    MAX_CYCLE_DAYS,
    MIN_CYCLE_GREGORIAN_YEAR,
    RATER_ROLES,
    SCORE_MAX,
    SCORE_MIN,
)
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_DELETE, UseCase
from apps.sharedKernel.domain.errors import DomainError, EntityNotFoundError


class PerformanceReviewError(DomainError):
    """A review was set up or scored in a way that cannot be defended."""


# =====================================================================================
# Commands / queries
# =====================================================================================
@dataclass(frozen=True)
class CycleQuery:
    cycleId: str = ""


@dataclass(frozen=True)
class SaveCycleCommand:
    id: str = ""
    code: str = ""
    name: str = ""
    fromDate: str = ""
    toDate: str = ""
    status: str = "draft"
    systemWeightPercent: int = 30
    roleWeights: dict = field(default_factory=dict)
    note: str = ""


@dataclass(frozen=True)
class SaveRaterScoreCommand:
    cycleId: str = ""
    personnelId: str = ""
    raterRole: str = ""
    score: float = 0.0
    raterName: str = ""
    note: str = ""


@dataclass(frozen=True)
class DeleteScoreCommand:
    scoreId: str = ""


@dataclass(frozen=True)
class ComputeCycleCommand:
    cycleId: str = ""


# =====================================================================================
# Base
# =====================================================================================
class PerformanceReviewUseCaseBase(UseCase):
    """Shared wiring. Mirrors the other maintenance use cases."""

    def __init__(
        self,
        *,
        reviewRepository,  # noqa: ANN001 — protocol, injected by the container
        unitOfWork,  # noqa: ANN001
        auditRecorder,  # noqa: ANN001
        eventDispatcher,  # noqa: ANN001
        permissionGate,  # noqa: ANN001
        clock,  # noqa: ANN001
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.reviewRepository = reviewRepository

    def requireCycle(self, tenantId: uuid.UUID, rawId: str) -> dict:
        if not rawId:
            raise PerformanceReviewError("A review cycle must be chosen.")
        try:
            cycleId = uuid.UUID(str(rawId))
        except (TypeError, ValueError) as exc:
            raise PerformanceReviewError("That review cycle id is not valid.") from exc
        cycle = self.reviewRepository.getCycle(tenantId, cycleId)
        if cycle is None:
            raise EntityNotFoundError("That review cycle no longer exists.")
        return cycle


# =====================================================================================
# Cycles
# =====================================================================================
class ListReviewCyclesUseCase(PerformanceReviewUseCaseBase):
    """Every appraisal round, newest period first."""

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: CycleQuery) -> dict:
        tenantId = resolveTenantId("")
        return {
            "cycles": self.reviewRepository.listCycles(tenantId),
            "raterRoles": list(RATER_ROLES),
            "defaultRoleWeights": dict(DEFAULT_ROLE_WEIGHTS),
        }


class SaveReviewCycleUseCase(PerformanceReviewUseCaseBase):
    """Open or amend an appraisal round."""

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: SaveCycleCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        if not command.code.strip() or not command.name.strip():
            raise PerformanceReviewError("A review cycle needs a code and a name.")
        if command.status not in CYCLE_STATUSES:
            raise PerformanceReviewError(f"Unknown cycle status «{command.status}».")

        fromDate = parseDateOrNone(command.fromDate)
        toDate = parseDateOrNone(command.toDate)
        if fromDate is None or toDate is None:
            raise PerformanceReviewError("A review cycle needs a start and an end date.")
        if toDate < fromDate:
            raise PerformanceReviewError("A review cycle cannot end before it starts.")
        # A Jalali year typed into a Gregorian field is the likeliest mistake
        # here: «1405-01-01» is a perfectly valid Gregorian date, so nothing
        # downstream complains — it simply renders back as «۱۱ دی ۷۸۳» once
        # converted. Refusing the medieval range turns a confusing display
        # into a clear error at the point of entry.
        if fromDate.year < MIN_CYCLE_GREGORIAN_YEAR:
            raise PerformanceReviewError(
                f"«{fromDate.isoformat()}» looks like a Jalali year written into a "
                "Gregorian date field. Dates are stored as Gregorian — 1405 در "
                "تقویم جلالی برابر 2026 میلادی است."
            )
        if (toDate - fromDate).days > MAX_CYCLE_DAYS:
            raise PerformanceReviewError(
                f"A review cycle cannot be longer than {MAX_CYCLE_DAYS} days."
            )

        weight = int(command.systemWeightPercent)
        if not 0 <= weight <= 100:
            raise PerformanceReviewError(
                "The system's share of the mark must be between 0 and 100 percent."
            )

        roleWeights = {}
        for role, value in (command.roleWeights or {}).items():
            if role not in RATER_ROLES:
                raise PerformanceReviewError(f"Unknown rater role «{role}».")
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise PerformanceReviewError(f"The weight for «{role}» must be a number.") from exc
            if numeric < 0:
                raise PerformanceReviewError("A rater weight cannot be negative.")
            roleWeights[role] = numeric

        values = {
            "id": command.id or None,
            "code": command.code.strip(),
            "name": command.name.strip(),
            "fromDate": fromDate,
            "toDate": toDate,
            "status": command.status,
            "systemWeightPercent": weight,
            "roleWeights": roleWeights,
            "note": command.note,
        }
        saved = self.reviewRepository.saveCycle(tenantId, values, now)
        self.audit(
            AUDIT_CREATE,
            resourceType="PerformanceCycle",
            resourceId=saved["id"],
            tenantId=tenantId,
        )
        return saved


class DeleteReviewCycleUseCase(PerformanceReviewUseCaseBase):
    """Retire a round along with its marks and results.

    A closed cycle cannot be deleted. By the time a cycle is closed its marks
    have been shown to the people they describe, and erasing the round would
    take every score and every stored justification with it — leaving an
    appraisal that was acted on but can no longer be explained. The same
    reasoning already stops a closed cycle accepting new marks; deletion is
    the larger version of the same mistake. Reopen it first if it really was
    closed in error.
    """

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, query: CycleQuery) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        cycle = self.requireCycle(tenantId, query.cycleId)
        if cycle["status"] == CYCLE_CLOSED:
            raise PerformanceReviewError(
                "A closed cycle cannot be deleted; its results have already "
                "been published. Reopen it first if it was closed in error."
            )
        removed = self.reviewRepository.deleteCycle(tenantId, uuid.UUID(cycle["id"]), now)
        if not removed:
            raise EntityNotFoundError("That review cycle no longer exists.")
        self.audit(
            AUDIT_DELETE,
            resourceType="PerformanceCycle",
            resourceId=cycle["id"],
            tenantId=tenantId,
        )
        return {"deleted": True, "id": cycle["id"]}


# =====================================================================================
# Marks
# =====================================================================================
class ListRaterScoresUseCase(PerformanceReviewUseCaseBase):
    """The marks submitted into one cycle, plus who can still be scored."""

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: CycleQuery) -> dict:
        tenantId = resolveTenantId("")
        cycle = self.requireCycle(tenantId, query.cycleId)
        return {
            "cycle": cycle,
            "scores": self.reviewRepository.listScores(tenantId, uuid.UUID(cycle["id"])),
            "personnel": self.reviewRepository.listPersonnel(tenantId),
            "raterRoles": list(RATER_ROLES),
        }


class SaveRaterScoreUseCase(PerformanceReviewUseCaseBase):
    """Submit or revise one manager's mark for one person."""

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: SaveRaterScoreCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        cycle = self.requireCycle(tenantId, command.cycleId)

        # A closed cycle is a published document. Letting a mark change after
        # the person has been shown their score would make the stored result
        # a lie about how it was reached.
        if cycle["status"] == CYCLE_CLOSED:
            raise PerformanceReviewError(
                "This cycle is closed; its marks can no longer be changed."
            )
        if command.raterRole not in RATER_ROLES:
            raise PerformanceReviewError(f"Unknown rater role «{command.raterRole}».")
        try:
            score = float(command.score)
        except (TypeError, ValueError) as exc:
            raise PerformanceReviewError("A mark must be a number.") from exc
        if not SCORE_MIN <= score <= SCORE_MAX:
            raise PerformanceReviewError(f"A mark must be between {SCORE_MIN} and {SCORE_MAX}.")
        try:
            personnelId = uuid.UUID(str(command.personnelId))
        except (TypeError, ValueError) as exc:
            raise PerformanceReviewError("That employee id is not valid.") from exc

        values = {
            "cycleId": uuid.UUID(cycle["id"]),
            "personnelId": personnelId,
            "raterRole": command.raterRole,
            "score": score,
            "raterName": command.raterName.strip(),
            "note": command.note,
        }
        saved = self.reviewRepository.saveScore(tenantId, values, now)
        self.audit(
            AUDIT_CREATE,
            resourceType="PerformanceScore",
            resourceId=saved["id"],
            tenantId=tenantId,
        )
        return saved


class DeleteRaterScoreUseCase(PerformanceReviewUseCaseBase):
    """Withdraw a mark."""

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: DeleteScoreCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        try:
            scoreId = uuid.UUID(str(command.scoreId))
        except (TypeError, ValueError) as exc:
            raise PerformanceReviewError("That mark id is not valid.") from exc
        if not self.reviewRepository.deleteScore(tenantId, scoreId, now):
            raise EntityNotFoundError("That mark no longer exists.")
        self.audit(
            AUDIT_DELETE,
            resourceType="PerformanceScore",
            resourceId=str(scoreId),
            tenantId=tenantId,
        )
        return {"deleted": True, "id": str(scoreId)}


# =====================================================================================
# The computation
# =====================================================================================
class ComputeReviewCycleUseCase(PerformanceReviewUseCaseBase):
    """Combine opinion and record into one final mark per person.

    Writes the results down rather than returning them only, so the number a
    person was shown stays recoverable even after the underlying work orders
    move on.
    """

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: ComputeCycleCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        cycle = self.requireCycle(tenantId, command.cycleId)
        cycleId = uuid.UUID(cycle["id"])

        grouped = self.reviewRepository.loadRaterScores(tenantId, cycleId)
        metrics = self.reviewRepository.loadSystemMetrics(
            tenantId,
            date.fromisoformat(cycle["fromDate"]),
            date.fromisoformat(cycle["toDate"]),
        )
        names = {
            person["id"]: person["fullName"]
            for person in self.reviewRepository.listPersonnel(tenantId)
        }

        roleWeights = cycle.get("roleWeights") or None
        outcomes = []
        # Anyone with an opinion *or* a work record gets a result. Scoring only
        # the people someone bothered to rate would quietly exclude the staff
        # no manager got round to.
        for personnelId in set(grouped) | set(metrics):
            outcomes.append(
                scoreReview(
                    personnelId=str(personnelId),
                    raters=grouped.get(personnelId, []),
                    metrics=metrics.get(personnelId),
                    personnelName=names.get(str(personnelId), ""),
                    systemWeightPercent=cycle["systemWeightPercent"],
                    roleWeights=roleWeights,
                )
            )

        stored = self.reviewRepository.saveResults(tenantId, cycleId, outcomes, now)
        self.audit(
            AUDIT_CREATE,
            resourceType="PerformanceResult",
            resourceId=cycle["id"],
            tenantId=tenantId,
        )
        return {
            "cycle": cycle,
            "computed": stored,
            "results": self.reviewRepository.listResults(tenantId, cycleId),
        }


class GetReviewResultsUseCase(PerformanceReviewUseCaseBase):
    """The comparison read model: ranked people, ready to chart.

    Only people an actual manager scored are ranked against each other.

    This matters more than it looks. The measured half alone will happily give
    a technician who closed two work orders a perfect 100, and ranking that
    against someone six managers scrutinised would put the unexamined person
    on top — rewarding *not being reviewed*. People with no marks yet are
    still returned, with their measured score and ``rank`` 0, so the gap is
    visible and chaseable rather than hidden; they are simply kept out of the
    ranking and the averages until somebody rates them.
    """

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: CycleQuery) -> dict:
        tenantId = resolveTenantId("")
        cycle = self.requireCycle(tenantId, query.cycleId)
        results = self.reviewRepository.listResults(tenantId, uuid.UUID(cycle["id"]))

        rated = [row for row in results if row["raterCount"] > 0]
        unrated = sorted(
            (row for row in results if row["raterCount"] == 0),
            key=lambda row: row["personnelName"],
        )

        # rankOutcomes only reads finalScore/personnelName/personnelId, so the
        # stored rows can be ranked by the same tested function the engine uses.
        ranked = rankOutcomes(
            [
                SimpleNamespace(
                    personnelId=row["personnelId"],
                    finalScore=row["finalScore"],
                    personnelName=row["personnelName"],
                )
                for row in rated
            ]
        )
        rankById = {row.personnelId: rank for rank, row in ranked}
        ordered = sorted(rated, key=lambda row: -row["finalScore"])
        for row in ordered:
            row["rank"] = rankById.get(row["personnelId"], 0)
            row["comparable"] = True
        for row in unrated:
            row["rank"] = 0
            row["comparable"] = False

        scores = [row["finalScore"] for row in ordered]
        return {
            "cycle": cycle,
            "results": ordered,
            "unrated": unrated,
            "summary": {
                "count": len(ordered),
                "unratedCount": len(unrated),
                "averageScore": round(sum(scores) / len(scores), 2) if scores else 0.0,
                "highestScore": max(scores) if scores else 0.0,
                "lowestScore": min(scores) if scores else 0.0,
                "dampedTotal": sum(row["dampedCount"] for row in ordered),
            },
        }
