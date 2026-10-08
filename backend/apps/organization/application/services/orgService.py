"""Managing the organisation chart: units, positions, postings, the matrix.

The rules enforced here are the ones that keep the chart honest. Each is a
refusal, and each exists because of a specific way a permission system rots:

* **A unit cannot become its own ancestor.** A cycle in the chart makes
  "which department is this person in" unanswerable and hangs any walk up
  the tree.
* **A unit with people or children cannot be deleted**, only deactivated.
  Deleting it would orphan postings and silently strip access from whoever
  held them, with no record of why.
* **Codes are unique per tenant and immutable once in use.** The code is
  what a seed, an import and an integration refer to.
* **The matrix only accepts cells that exist.** A tick against a capability
  or verb the catalogue does not define grants nothing, so accepting it
  would write a permission that looks granted and is not.
* **Every structural change bumps the affected users' authorisation
  version.** A revoked posting has to stop working immediately, not when a
  cache entry happens to expire.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.organization.domain.services.accessMatrix import matrixView
from apps.organization.domain.valueObjects.orgStructure import (
    ACTION_LABELS_FA,
    ACTIONS,
    CAPABILITY_BY_KEY,
    DEPARTMENT_STATUS_ACTIVE,
    DEPARTMENT_STATUSES,
    SCOPES,
    actionCodesFor,
    defaultScopeFor,
    isScoped,
)

logger = logging.getLogger(__name__)


class OrganizationRuleViolation(Exception):
    """A change to the chart that the rules refuse."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Actor:
    id: uuid.UUID | None
    name: str = ""


def _repository():
    from apps.organization.infrastructure import orgRepository

    return orgRepository


def _invalidateUsers(userIds: list[str]) -> None:
    """Drop cached authorisation for these users, right now.

    Goes through identity's public application contract rather than its
    cache module: the organisation chart must not know how identity stores
    a decision. Guarded because a cache that is unavailable must not
    prevent a permission change from being *recorded* — the change is
    already committed, and a short window of stale access is logged rather
    than hidden.
    """
    if not userIds:
        return
    try:
        from apps.identity.application.services.authorizationInvalidation import (
            invalidateUsers,
        )

        invalidateUsers(userIds)
    except ImportError:  # pragma: no cover — identity is always installed
        logger.exception("Authorization invalidation contract unavailable")


def _audit(tenantId, entity, entityId, action, summary, actor: Actor, now) -> None:
    _repository().recordAudit(
        tenantId=tenantId,
        entity=entity,
        entityId=entityId,
        action=action,
        summary=summary,
        actorUserId=actor.id,
        actorName=actor.name,
        occurredAt=now,
    )


def _normalisedCode(raw: str) -> str:
    """Codes are upper-case and punctuation-free so two plants importing the
    same spreadsheet produce the same code."""
    return "".join(ch for ch in str(raw).strip().upper() if ch.isalnum() or ch in "-_")[:32]


# --- Departments -----------------------------------------------------------


def createDepartment(
    tenantId: uuid.UUID,
    *,
    name: str,
    code: str = "",
    actor: Actor,
    description: str = "",
    parentId=None,
    managerUserId=None,
    managerName: str = "",
    now: datetime | None = None,
):
    """Open a new unit — the «＋ افزودن واحد» path."""
    now = now or timezone.now()
    repository = _repository()
    name = name.strip()
    if not name:
        raise OrganizationRuleViolation("department.nameRequired", "نام واحد الزامی است.")

    code = _normalisedCode(code or name)
    if not code:
        raise OrganizationRuleViolation(
            "department.codeRequired",
            "کد واحد الزامی است (می‌توانید از حروف لاتین استفاده کنید).",
        )
    if repository.departmentCodeExists(tenantId, code):
        raise OrganizationRuleViolation(
            "department.codeTaken", f"واحدی با کد «{code}» از قبل وجود دارد."
        )
    if parentId:
        repository.getDepartment(tenantId, parentId)

    department = repository.createDepartment(
        tenantId=tenantId,
        now=now,
        code=code,
        name=name[:160],
        description=description[:500],
        parentId=parentId,
        managerUserId=managerUserId,
        managerName=managerName[:160],
    )
    _audit(tenantId, "department", department.id, "created", f"{code} — {name}", actor, now)
    return department


def updateDepartment(
    tenantId: uuid.UUID, departmentId, *, actor: Actor, now: datetime | None = None, **changes
):
    now = now or timezone.now()
    repository = _repository()
    department = repository.getDepartment(tenantId, departmentId)

    if "code" in changes and changes["code"]:
        newCode = _normalisedCode(changes["code"])
        if newCode != department.code:
            if repository.departmentCodeExists(tenantId, newCode, excludeId=department.id):
                raise OrganizationRuleViolation(
                    "department.codeTaken", f"واحدی با کد «{newCode}» از قبل وجود دارد."
                )
            department.code = newCode

    if "parentId" in changes:
        parentId = changes["parentId"]
        if parentId:
            if str(parentId) == str(department.id):
                raise OrganizationRuleViolation(
                    "department.selfParent", "یک واحد نمی‌تواند زیرمجموعه خودش باشد."
                )
            # A cycle makes "which unit is this person in" unanswerable.
            if str(department.id) in repository.ancestorIdsOf(tenantId, parentId):
                raise OrganizationRuleViolation(
                    "department.cycle",
                    "این انتخاب باعث ایجاد حلقه در ساختار سازمانی می‌شود.",
                )
            repository.getDepartment(tenantId, parentId)
        department.parentId = parentId

    if "status" in changes and changes["status"]:
        if changes["status"] not in DEPARTMENT_STATUSES:
            raise OrganizationRuleViolation("department.badStatus", "وضعیت واحد نامعتبر است.")
        department.status = changes["status"]

    for field in ("name", "description", "managerName"):
        if field in changes and changes[field] is not None:
            setattr(department, field, str(changes[field])[:500])
    if "managerUserId" in changes:
        department.managerUserId = changes["managerUserId"]

    repository.saveDepartment(department, now)
    _audit(tenantId, "department", department.id, "updated", department.name, actor, now)

    # Deactivating a unit removes access for everyone posted into it, so it
    # has to take effect on the next request, not when a cache expires.
    _invalidateUsers(repository.userIdsInDepartment(tenantId, department.id))
    return department


def deleteDepartment(tenantId: uuid.UUID, departmentId, *, actor: Actor, now=None) -> None:
    """Remove a unit entirely. Refused while anything still depends on it."""
    now = now or timezone.now()
    repository = _repository()
    department = repository.getDepartment(tenantId, departmentId)

    if department.isSystem:
        raise OrganizationRuleViolation(
            "department.systemProtected",
            "واحدهای پیش‌فرض حذف نمی‌شوند؛ در صورت نیاز آن‌ها را غیرفعال کنید.",
        )
    if repository.departmentHasChildren(tenantId, department.id):
        raise OrganizationRuleViolation(
            "department.hasChildren",
            "این واحد زیرمجموعه دارد؛ ابتدا زیرمجموعه‌ها را جابه‌جا یا حذف کنید.",
        )
    count = repository.departmentAssignmentCount(tenantId, department.id)
    if count:
        raise OrganizationRuleViolation(
            "department.hasMembers",
            f"{count} کاربر در این واحد هستند؛ ابتدا آن‌ها را منتقل کنید یا واحد را غیرفعال کنید.",
        )

    affected = repository.userIdsInDepartment(tenantId, department.id)
    repository.deleteDepartment(department)
    _audit(tenantId, "department", departmentId, "deleted", department.name, actor, now)
    _invalidateUsers(affected)


# --- Positions -------------------------------------------------------------


def createPosition(
    tenantId: uuid.UUID,
    *,
    name: str,
    code: str = "",
    actor: Actor,
    level: int = 0,
    description: str = "",
    now: datetime | None = None,
):
    """Define a new job title — the «＋ افزودن سمت» path."""
    now = now or timezone.now()
    repository = _repository()
    name = name.strip()
    if not name:
        raise OrganizationRuleViolation("position.nameRequired", "نام سمت الزامی است.")

    code = _normalisedCode(code or name)
    if not code:
        raise OrganizationRuleViolation("position.codeRequired", "کد سمت الزامی است.")
    if repository.positionCodeExists(tenantId, code):
        raise OrganizationRuleViolation(
            "position.codeTaken", f"سمتی با کد «{code}» از قبل وجود دارد."
        )

    position = repository.createPosition(
        tenantId=tenantId,
        now=now,
        code=code,
        name=name[:160],
        description=description[:500],
        level=int(level or 0),
    )
    _audit(tenantId, "position", position.id, "created", f"{code} — {name}", actor, now)
    # A brand-new position holds no permissions at all until the matrix is
    # filled in. Silence here is correct: inventing defaults for a title
    # nobody has described would be guessing about authority.
    return position


def updatePosition(
    tenantId: uuid.UUID, positionId, *, actor: Actor, now: datetime | None = None, **changes
):
    now = now or timezone.now()
    repository = _repository()
    position = repository.getPosition(tenantId, positionId)

    if "code" in changes and changes["code"]:
        newCode = _normalisedCode(changes["code"])
        if newCode != position.code:
            if repository.positionCodeExists(tenantId, newCode, excludeId=position.id):
                raise OrganizationRuleViolation(
                    "position.codeTaken", f"سمتی با کد «{newCode}» از قبل وجود دارد."
                )
            position.code = newCode

    for field in ("name", "description"):
        if field in changes and changes[field] is not None:
            setattr(position, field, str(changes[field])[:500])
    if "level" in changes and changes["level"] is not None:
        position.level = int(changes["level"])
    if "isActive" in changes and changes["isActive"] is not None:
        position.isActive = bool(changes["isActive"])

    repository.savePosition(position, now)
    _audit(tenantId, "position", position.id, "updated", position.name, actor, now)
    _invalidateUsers(repository.userIdsHoldingPosition(tenantId, position.id))
    return position


def deletePosition(tenantId: uuid.UUID, positionId, *, actor: Actor, now=None) -> None:
    now = now or timezone.now()
    repository = _repository()
    position = repository.getPosition(tenantId, positionId)

    if position.isSystem:
        raise OrganizationRuleViolation(
            "position.systemProtected",
            "سمت‌های پیش‌فرض حذف نمی‌شوند؛ در صورت نیاز آن‌ها را غیرفعال کنید.",
        )
    count = repository.positionAssignmentCount(tenantId, position.id)
    if count:
        raise OrganizationRuleViolation(
            "position.inUse",
            f"{count} کاربر این سمت را دارند؛ ابتدا سمت آن‌ها را تغییر دهید.",
        )

    affected = repository.userIdsHoldingPosition(tenantId, position.id)
    repository.deletePosition(position)
    _audit(tenantId, "position", positionId, "deleted", position.name, actor, now)
    _invalidateUsers(affected)


# --- Assignments -----------------------------------------------------------


def assignUser(
    tenantId: uuid.UUID,
    *,
    userId,
    departmentId,
    positionId,
    actor: Actor,
    userDisplayName: str = "",
    isPrimary: bool = True,
    reportsToUserId=None,
    now: datetime | None = None,
):
    """Post a person into a unit with a title — the access-granting act."""
    now = now or timezone.now()
    repository = _repository()

    department = repository.getDepartment(tenantId, departmentId)
    position = repository.getPosition(tenantId, positionId)

    if department.status != DEPARTMENT_STATUS_ACTIVE:
        raise OrganizationRuleViolation(
            "assignment.departmentInactive",
            "این واحد غیرفعال است؛ نمی‌توان کاربری را به آن منتسب کرد.",
        )
    if not position.isActive:
        raise OrganizationRuleViolation("assignment.positionInactive", "این سمت غیرفعال است.")
    if repository.assignmentExists(tenantId, userId, departmentId, positionId):
        raise OrganizationRuleViolation(
            "assignment.duplicate", "این کاربر با همین سمت در همین واحد ثبت شده است."
        )
    if reportsToUserId and str(reportsToUserId) == str(userId):
        raise OrganizationRuleViolation(
            "assignment.selfReporting", "کاربر نمی‌تواند به خودش گزارش دهد."
        )

    assignment = repository.createAssignment(
        tenantId=tenantId,
        now=now,
        userId=userId,
        userDisplayName=userDisplayName[:160],
        departmentId=departmentId,
        positionId=positionId,
        isPrimary=isPrimary,
        reportsToUserId=reportsToUserId,
        startedAt=now,
    )
    _audit(
        tenantId,
        "assignment",
        assignment.id,
        "created",
        f"{userDisplayName or userId} → {department.name} / {position.name}",
        actor,
        now,
    )
    _invalidateUsers([str(userId)])
    return assignment


def updateAssignment(
    tenantId: uuid.UUID, assignmentId, *, actor: Actor, now: datetime | None = None, **changes
):
    now = now or timezone.now()
    repository = _repository()
    assignment = repository.getAssignment(tenantId, assignmentId)

    if "positionId" in changes and changes["positionId"]:
        position = repository.getPosition(tenantId, changes["positionId"])
        if not position.isActive:
            raise OrganizationRuleViolation("assignment.positionInactive", "این سمت غیرفعال است.")
        assignment.positionId = position.id
    if "departmentId" in changes and changes["departmentId"]:
        department = repository.getDepartment(tenantId, changes["departmentId"])
        if department.status != DEPARTMENT_STATUS_ACTIVE:
            raise OrganizationRuleViolation(
                "assignment.departmentInactive", "این واحد غیرفعال است."
            )
        assignment.departmentId = department.id
    if "reportsToUserId" in changes:
        value = changes["reportsToUserId"]
        if value and str(value) == str(assignment.userId):
            raise OrganizationRuleViolation(
                "assignment.selfReporting", "کاربر نمی‌تواند به خودش گزارش دهد."
            )
        assignment.reportsToUserId = value
    if "isPrimary" in changes and changes["isPrimary"] is not None:
        assignment.isPrimary = bool(changes["isPrimary"])
    if "isActive" in changes and changes["isActive"] is not None:
        assignment.isActive = bool(changes["isActive"])
        assignment.endedAt = None if assignment.isActive else now

    repository.saveAssignment(assignment, now)
    _audit(tenantId, "assignment", assignment.id, "updated", str(assignment.userId), actor, now)
    _invalidateUsers([str(assignment.userId)])
    return assignment


def removeAssignment(tenantId: uuid.UUID, assignmentId, *, actor: Actor, now=None) -> None:
    now = now or timezone.now()
    repository = _repository()
    assignment = repository.getAssignment(tenantId, assignmentId)
    userId = str(assignment.userId)
    repository.deleteAssignment(assignment)
    _audit(tenantId, "assignment", assignmentId, "deleted", userId, actor, now)
    _invalidateUsers([userId])


# --- The matrix ------------------------------------------------------------


def setAccessCell(
    tenantId: uuid.UUID,
    *,
    positionId,
    capability: str,
    action: str,
    scope: str = "",
    departmentId=None,
    actor: Actor,
    now: datetime | None = None,
):
    """Grant one cell of the grid.

    ``departmentId`` of ``None`` writes the organisation-wide default for
    that position; a department id writes an override for that unit only.
    """
    now = now or timezone.now()
    repository = _repository()

    if capability not in CAPABILITY_BY_KEY:
        raise OrganizationRuleViolation(
            "rule.unknownCapability", f"قابلیت «{capability}» تعریف نشده است."
        )
    if action not in ACTIONS:
        raise OrganizationRuleViolation(
            "rule.unknownAction",
            f"عملیات «{ACTION_LABELS_FA.get(action, action)}» تعریف نشده است.",
        )
    if not actionCodesFor(capability, action):
        # The cell is not in the catalogue, so nothing would check it.
        # Accepting the tick would display a permission that does not exist.
        # Both names are shown in Persian: an administrator reading this
        # refusal should not have to know the internal keys.
        raise OrganizationRuleViolation(
            "rule.unsupportedCell",
            f"عملیات «{ACTION_LABELS_FA.get(action, action)}» برای قابلیت "
            f"«{CAPABILITY_BY_KEY[capability]['labelFa']}» تعریف نشده است.",
        )

    scope = scope or defaultScopeFor(capability)
    if scope not in SCOPES:
        raise OrganizationRuleViolation("rule.unknownScope", f"محدوده «{scope}» نامعتبر است.")
    if not isScoped(capability):
        # Storing a narrower scope on a plant-wide catalogue would be a
        # promise the evaluator does not keep; normalise instead of lying.
        scope = "all"

    position = repository.getPosition(tenantId, positionId)
    if departmentId:
        repository.getDepartment(tenantId, departmentId)

    row, created = repository.upsertRule(
        tenantId=tenantId,
        positionId=position.id,
        departmentId=departmentId,
        capability=capability,
        action=action,
        scope=scope,
        now=now,
        actorUserId=actor.id,
        actorName=actor.name,
    )
    _audit(
        tenantId,
        "accessRule",
        row.id,
        "granted" if created else "updated",
        f"{position.code} / {capability}.{action} = {scope}",
        actor,
        now,
    )
    _invalidateUsers(repository.userIdsHoldingPosition(tenantId, position.id))
    return row


def clearAccessCell(
    tenantId: uuid.UUID,
    *,
    positionId,
    capability: str,
    action: str,
    departmentId=None,
    actor: Actor,
    now: datetime | None = None,
) -> int:
    """Revoke one cell."""
    now = now or timezone.now()
    repository = _repository()
    position = repository.getPosition(tenantId, positionId)
    deleted = repository.revokeRule(
        tenantId=tenantId,
        positionId=position.id,
        departmentId=departmentId,
        capability=capability,
        action=action,
    )
    if deleted:
        _audit(
            tenantId,
            "accessRule",
            None,
            "revoked",
            f"{position.code} / {capability}.{action}",
            actor,
            now,
        )
        _invalidateUsers(repository.userIdsHoldingPosition(tenantId, position.id))
    return deleted


def accessMatrixFor(tenantId: uuid.UUID, departmentId=None) -> dict:
    """The grid in force for one unit, defaults folded in."""
    repository = _repository()
    rules = repository.ruleSnapshotsFor(tenantId)
    return matrixView(rules, departmentId=str(departmentId) if departmentId else "")


def seedDefaults(tenantId: uuid.UUID, *, now: datetime | None = None) -> dict:
    """Create the starting units, positions and matrix. Idempotent."""
    return _repository().seedOrganization(tenantId, now or timezone.now())
