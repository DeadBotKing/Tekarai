"""Database access for the organisation chart.

Exists because the application layer may not touch the ORM (DependencyRules
§3). Queries return plain values or domain snapshots, never querysets, so a
lazy evaluation cannot leak a second round of SQL into a caller that is
making an authorisation decision.

Every query is tenant-scoped at the first filter. In a permission system a
missing tenant filter is not a privacy bug, it is one plant granting access
inside another.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db import transaction

from apps.organization.domain.services.accessMatrix import AssignmentSnapshot, RuleSnapshot
from apps.organization.domain.valueObjects.orgStructure import (
    DEFAULT_ACCESS_MATRIX,
    DEFAULT_DEPARTMENTS,
    DEFAULT_POSITIONS,
    DEPARTMENT_STATUS_ACTIVE,
)
from apps.organization.infrastructure.models import (
    OrganizationAccessRuleModel,
    OrganizationAssignmentModel,
    OrganizationAuditModel,
    OrganizationDepartmentModel,
    OrganizationPositionModel,
)


class OrganizationNotFound(Exception):
    """Asked for a department, position or assignment that is not here."""


# --- Reads used by the authorisation path ---------------------------------
#
# These two are on the hot path: every permission check for every request
# can reach them, so they are deliberately narrow (two indexed queries, no
# joins, no model instances returned).


def assignmentSnapshotsFor(tenantId: uuid.UUID, userId: uuid.UUID) -> list[AssignmentSnapshot]:
    rows = OrganizationAssignmentModel.objects.filter(
        tenantId=tenantId, userId=userId, isActive=True
    ).values("userId", "departmentId", "positionId")
    if not rows:
        return []

    positionIds = {row["positionId"] for row in rows}
    positions = {
        x["id"]: x
        for x in OrganizationPositionModel.objects.filter(
            tenantId=tenantId, id__in=positionIds, isActive=True
        ).values("id", "code", "level")
    }
    departmentIds = {row["departmentId"] for row in rows}
    activeDepartments = set(
        OrganizationDepartmentModel.objects.filter(
            tenantId=tenantId, id__in=departmentIds, status=DEPARTMENT_STATUS_ACTIVE
        )
        .order_by()
        .values_list("id", flat=True)
    )

    snapshots: list[AssignmentSnapshot] = []
    for row in rows:
        position = positions.get(row["positionId"])
        # A posting into a deactivated unit, or holding a retired title,
        # grants nothing. «غیرفعال» has to mean the access is gone.
        if position is None or row["departmentId"] not in activeDepartments:
            continue
        snapshots.append(
            AssignmentSnapshot(
                userId=str(row["userId"]),
                departmentId=str(row["departmentId"]),
                positionId=str(row["positionId"]),
                positionCode=position["code"],
                positionLevel=position["level"],
                isActive=True,
            )
        )
    return snapshots


def ruleSnapshotsFor(
    tenantId: uuid.UUID, positionIds: list[str] | None = None
) -> list[RuleSnapshot]:
    queryset = OrganizationAccessRuleModel.objects.filter(tenantId=tenantId, isActive=True)
    if positionIds:
        queryset = queryset.filter(positionId__in=positionIds)
    return [
        RuleSnapshot(
            positionId=str(row["positionId"]),
            capability=row["capability"],
            action=row["action"],
            scope=row["scope"],
            departmentId=str(row["departmentId"]) if row["departmentId"] else "",
            isActive=True,
        )
        for row in queryset.values("positionId", "departmentId", "capability", "action", "scope")
    ]


def teamMemberIdsFor(tenantId: uuid.UUID, userId: uuid.UUID) -> list[str]:
    """Who reports to this user — the roster behind ``team`` scope.

    Direct reports only, deliberately: a transitive walk would make a
    supervisor's «تیم خودش» quietly mean «کل واحد» in a deep chart, which
    is a different permission that an administrator did not grant.
    """
    return [
        str(x)
        for x in OrganizationAssignmentModel.objects.filter(
            tenantId=tenantId, reportsToUserId=userId, isActive=True
        )
        .order_by()
        .values_list("userId", flat=True)
        .distinct()
    ]


def departmentIdsForUser(tenantId: uuid.UUID, userId: uuid.UUID) -> list[str]:
    return [
        str(x)
        for x in OrganizationAssignmentModel.objects.filter(
            tenantId=tenantId, userId=userId, isActive=True
        )
        .order_by()
        .values_list("departmentId", flat=True)
        .distinct()
    ]


def primaryDepartmentFor(tenantId: uuid.UUID, userId: uuid.UUID) -> str:
    row = (
        OrganizationAssignmentModel.objects.filter(tenantId=tenantId, userId=userId, isActive=True)
        .order_by("-isPrimary", "createdAt")
        .values_list("departmentId", flat=True)
        .first()
    )
    return str(row) if row else ""


def userIdsInDepartments(tenantId: uuid.UUID, departmentIds: list[str]) -> list[str]:
    if not departmentIds:
        return []
    return [
        str(x)
        for x in OrganizationAssignmentModel.objects.filter(
            tenantId=tenantId, departmentId__in=departmentIds, isActive=True
        )
        .order_by()
        .values_list("userId", flat=True)
        .distinct()
    ]


# --- Departments -----------------------------------------------------------


def listDepartments(tenantId: uuid.UUID, *, includeInactive: bool = True) -> list:
    queryset = OrganizationDepartmentModel.objects.filter(tenantId=tenantId)
    if not includeInactive:
        queryset = queryset.filter(status=DEPARTMENT_STATUS_ACTIVE)
    return list(queryset.order_by("code"))


def getDepartment(tenantId: uuid.UUID, departmentId) -> OrganizationDepartmentModel:
    try:
        return OrganizationDepartmentModel.objects.get(tenantId=tenantId, id=departmentId)
    except OrganizationDepartmentModel.DoesNotExist as error:
        raise OrganizationNotFound(f"department {departmentId}") from error


def departmentCodeExists(tenantId: uuid.UUID, code: str, *, excludeId=None) -> bool:
    queryset = OrganizationDepartmentModel.objects.filter(tenantId=tenantId, code=code)
    if excludeId:
        queryset = queryset.exclude(id=excludeId)
    return queryset.exists()


def createDepartment(
    *, tenantId: uuid.UUID, now: datetime, **fields
) -> OrganizationDepartmentModel:
    return OrganizationDepartmentModel.objects.create(tenantId=tenantId, updatedAt=now, **fields)


def saveDepartment(department, now: datetime) -> None:
    department.updatedAt = now
    department.save()


def departmentHasChildren(tenantId: uuid.UUID, departmentId) -> bool:
    return OrganizationDepartmentModel.objects.filter(
        tenantId=tenantId, parentId=departmentId
    ).exists()


def departmentAssignmentCount(tenantId: uuid.UUID, departmentId) -> int:
    return OrganizationAssignmentModel.objects.filter(
        tenantId=tenantId, departmentId=departmentId, isActive=True
    ).count()


def deleteDepartment(department) -> None:
    OrganizationAccessRuleModel.objects.filter(
        tenantId=department.tenantId, departmentId=department.id
    ).delete()
    department.delete()


def ancestorIdsOf(tenantId: uuid.UUID, departmentId) -> list[str]:
    """Walk up the chart. Used to refuse a re-parent that makes a cycle."""
    seen: list[str] = []
    current = departmentId
    while current:
        if str(current) in seen:
            break
        seen.append(str(current))
        parent = (
            OrganizationDepartmentModel.objects.filter(tenantId=tenantId, id=current)
            .values_list("parentId", flat=True)
            .first()
        )
        current = parent
    return seen


# --- Positions -------------------------------------------------------------


def listPositions(tenantId: uuid.UUID, *, includeInactive: bool = True) -> list:
    queryset = OrganizationPositionModel.objects.filter(tenantId=tenantId)
    if not includeInactive:
        queryset = queryset.filter(isActive=True)
    return list(queryset.order_by("-level", "code"))


def getPosition(tenantId: uuid.UUID, positionId) -> OrganizationPositionModel:
    try:
        return OrganizationPositionModel.objects.get(tenantId=tenantId, id=positionId)
    except OrganizationPositionModel.DoesNotExist as error:
        raise OrganizationNotFound(f"position {positionId}") from error


def positionCodeExists(tenantId: uuid.UUID, code: str, *, excludeId=None) -> bool:
    queryset = OrganizationPositionModel.objects.filter(tenantId=tenantId, code=code)
    if excludeId:
        queryset = queryset.exclude(id=excludeId)
    return queryset.exists()


def createPosition(*, tenantId: uuid.UUID, now: datetime, **fields) -> OrganizationPositionModel:
    return OrganizationPositionModel.objects.create(tenantId=tenantId, updatedAt=now, **fields)


def savePosition(position, now: datetime) -> None:
    position.updatedAt = now
    position.save()


def positionAssignmentCount(tenantId: uuid.UUID, positionId) -> int:
    return OrganizationAssignmentModel.objects.filter(
        tenantId=tenantId, positionId=positionId, isActive=True
    ).count()


def deletePosition(position) -> None:
    OrganizationAccessRuleModel.objects.filter(
        tenantId=position.tenantId, positionId=position.id
    ).delete()
    position.delete()


# --- Assignments -----------------------------------------------------------


def listAssignments(
    tenantId: uuid.UUID, *, departmentId=None, userId=None, includeInactive: bool = False
) -> list:
    queryset = OrganizationAssignmentModel.objects.filter(tenantId=tenantId)
    if departmentId:
        queryset = queryset.filter(departmentId=departmentId)
    if userId:
        queryset = queryset.filter(userId=userId)
    if not includeInactive:
        queryset = queryset.filter(isActive=True)
    return list(queryset.order_by("-isPrimary", "-createdAt"))


def getAssignment(tenantId: uuid.UUID, assignmentId) -> OrganizationAssignmentModel:
    try:
        return OrganizationAssignmentModel.objects.get(tenantId=tenantId, id=assignmentId)
    except OrganizationAssignmentModel.DoesNotExist as error:
        raise OrganizationNotFound(f"assignment {assignmentId}") from error


def assignmentExists(tenantId: uuid.UUID, userId, departmentId, positionId) -> bool:
    return OrganizationAssignmentModel.objects.filter(
        tenantId=tenantId, userId=userId, departmentId=departmentId, positionId=positionId
    ).exists()


@transaction.atomic
def createAssignment(*, tenantId: uuid.UUID, now: datetime, **fields):
    assignment = OrganizationAssignmentModel.objects.create(
        tenantId=tenantId, updatedAt=now, **fields
    )
    if assignment.isPrimary:
        _demoteOtherPrimaries(assignment)
    return assignment


@transaction.atomic
def saveAssignment(assignment, now: datetime) -> None:
    assignment.updatedAt = now
    assignment.save()
    if assignment.isPrimary:
        _demoteOtherPrimaries(assignment)


def _demoteOtherPrimaries(assignment) -> None:
    """Exactly one primary posting per user — the one work is attributed to."""
    OrganizationAssignmentModel.objects.filter(
        tenantId=assignment.tenantId, userId=assignment.userId
    ).exclude(id=assignment.id).update(isPrimary=False)


def deleteAssignment(assignment) -> None:
    assignment.delete()


def userIdsWithAssignments(tenantId: uuid.UUID) -> list[str]:
    return [
        str(x)
        for x in OrganizationAssignmentModel.objects.filter(tenantId=tenantId)
        .order_by()
        .values_list("userId", flat=True)
        .distinct()
    ]


def userIdsHoldingPosition(tenantId: uuid.UUID, positionId) -> list[str]:
    return [
        str(x)
        for x in OrganizationAssignmentModel.objects.filter(
            tenantId=tenantId, positionId=positionId
        )
        .order_by()
        .values_list("userId", flat=True)
        .distinct()
    ]


def userIdsInDepartment(tenantId: uuid.UUID, departmentId) -> list[str]:
    return [
        str(x)
        for x in OrganizationAssignmentModel.objects.filter(
            tenantId=tenantId, departmentId=departmentId
        )
        .order_by()
        .values_list("userId", flat=True)
        .distinct()
    ]


# --- Access rules ----------------------------------------------------------


def listRules(tenantId: uuid.UUID, *, departmentId=None, positionId=None) -> list:
    queryset = OrganizationAccessRuleModel.objects.filter(tenantId=tenantId)
    if positionId:
        queryset = queryset.filter(positionId=positionId)
    if departmentId == "":
        queryset = queryset.filter(departmentId__isnull=True)
    elif departmentId is not None:
        queryset = queryset.filter(departmentId=departmentId)
    return list(queryset.order_by("capability", "action"))


def upsertRule(
    *,
    tenantId: uuid.UUID,
    positionId,
    departmentId,
    capability: str,
    action: str,
    scope: str,
    now: datetime,
    actorUserId=None,
    actorName: str = "",
):
    """Write one cell. Returns ``(row, created)``."""
    row, created = OrganizationAccessRuleModel.objects.update_or_create(
        tenantId=tenantId,
        positionId=positionId,
        departmentId=departmentId,
        capability=capability,
        action=action,
        defaults={
            "scope": scope,
            "isActive": True,
            "updatedAt": now,
            "updatedByUserId": actorUserId,
            "updatedByName": actorName[:160],
        },
    )
    return row, created


def revokeRule(
    *, tenantId: uuid.UUID, positionId, departmentId, capability: str, action: str
) -> int:
    """Clear one cell.

    A hard delete, not a soft one. A revoked permission that lingers as an
    inactive row invites somebody to "reactivate" it later without the
    review that granting it the first time required.
    """
    deleted, _ = OrganizationAccessRuleModel.objects.filter(
        tenantId=tenantId,
        positionId=positionId,
        departmentId=departmentId,
        capability=capability,
        action=action,
    ).delete()
    return deleted


def tenantIdsWithOrganization() -> list[uuid.UUID]:
    return list(
        OrganizationDepartmentModel.objects.order_by().values_list("tenantId", flat=True).distinct()
    )


# --- Audit -----------------------------------------------------------------


def recordAudit(
    *,
    tenantId: uuid.UUID,
    entity: str,
    entityId,
    action: str,
    summary: str,
    actorUserId,
    actorName: str,
    occurredAt: datetime,
) -> None:
    OrganizationAuditModel.objects.create(
        tenantId=tenantId,
        entity=entity,
        entityId=entityId,
        action=action,
        summary=summary[:500],
        actorUserId=actorUserId,
        actorName=actorName[:160],
        occurredAt=occurredAt,
    )


def listAudit(tenantId: uuid.UUID, *, limit: int = 100) -> list:
    return list(
        OrganizationAuditModel.objects.filter(tenantId=tenantId).order_by("-occurredAt")[
            : max(1, min(limit, 500))
        ]
    )


# --- Seeding ---------------------------------------------------------------


@transaction.atomic
def seedOrganization(tenantId: uuid.UUID, now: datetime) -> dict:
    """Create the starting units, positions and matrix. Idempotent.

    Everything written here is ordinary data the plant may rename, retire or
    delete. The seed exists so a fresh install is usable on day one, not to
    define a schema.
    """
    created = {"departments": 0, "positions": 0, "rules": 0}

    for code, name in DEFAULT_DEPARTMENTS:
        _, isNew = OrganizationDepartmentModel.objects.get_or_create(
            tenantId=tenantId,
            code=code,
            defaults={"name": name, "isSystem": True, "updatedAt": now},
        )
        created["departments"] += int(isNew)

    for code, name, level in DEFAULT_POSITIONS:
        _, isNew = OrganizationPositionModel.objects.get_or_create(
            tenantId=tenantId,
            code=code,
            defaults={"name": name, "level": level, "isSystem": True, "updatedAt": now},
        )
        created["positions"] += int(isNew)

    positions = {x.code: x.id for x in OrganizationPositionModel.objects.filter(tenantId=tenantId)}
    for positionCode, capabilities in DEFAULT_ACCESS_MATRIX.items():
        positionId = positions.get(positionCode)
        if positionId is None:
            continue
        for capability, actions in capabilities.items():
            for action, scope in actions.items():
                # Organisation-wide defaults (departmentId null): a new unit
                # inherits a sane matrix instead of starting blank, which is
                # what makes «+ افزودن واحد» safe to use.
                _, isNew = OrganizationAccessRuleModel.objects.get_or_create(
                    tenantId=tenantId,
                    positionId=positionId,
                    departmentId=None,
                    capability=capability,
                    action=action,
                    defaults={"scope": scope, "updatedAt": now},
                )
                created["rules"] += int(isNew)

    return created
