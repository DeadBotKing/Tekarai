"""Organisation chart tables: units, positions, postings and the matrix.

Four tables, and the split is the feature:

* ``OrganizationDepartmentModel`` and ``OrganizationPositionModel`` are
  **data**. A plant that opens an «آزمایشگاه» unit or invents a «سرپرست
  شیفت» title edits rows, never code.
* ``OrganizationAssignmentModel`` is the join that makes a person someone:
  user + department + position. It is a row rather than two columns on the
  user because people genuinely hold more than one posting — a رئیس
  تعمیرات who is also سرپرست برق during a shutdown.
* ``OrganizationAccessRuleModel`` is one cell of the permission grid:
  position × capability × action → scope, optionally narrowed to a single
  department. One row per cell rather than a JSON blob, because an auditor
  asks "who granted تأیید to سرپرست, and when" and a blob cannot answer.

Users are referenced by plain UUID, not a foreign key: ``identity`` is a
different bounded context and the architecture forbids reaching into its
tables. The same applies in reverse — identity reads this context through
its public application contract.
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.organization.domain.valueObjects.orgStructure import (
    ACTIONS,
    CAPABILITY_KEYS,
    DEPARTMENT_STATUS_ACTIVE,
    DEPARTMENT_STATUSES,
    SCOPE_DEPARTMENT,
    SCOPES,
)


class OrganizationStamped(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class OrganizationDepartmentModel(OrganizationStamped):
    """One unit: «فنی و مهندسی»، «QC»، «انبار» …"""

    STATUS = [(x, x) for x in DEPARTMENT_STATUSES]

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=12, choices=STATUS, default=DEPARTMENT_STATUS_ACTIVE)

    #: Units nest — «برق» under «فنی و مهندسی». Stored as a self-reference
    #: by id with no FK constraint so a re-parent can never be blocked by
    #: ordering; the cycle guard lives in the service.
    parentId = models.UUIDField(null=True, blank=True, db_index=True)

    #: The unit's head, denormalised for display. Authority still comes from
    #: the matrix — naming someone here grants nothing on its own, which is
    #: deliberate: one place to look when asking why access exists.
    managerUserId = models.UUIDField(null=True, blank=True)
    managerName = models.CharField(max_length=160, blank=True, default="")

    #: Rows the plant did not create. Protected from deletion so the default
    #: five cannot be removed by accident while assignments still point at
    #: them; they can always be deactivated instead.
    isSystem = models.BooleanField(default=False)

    class Meta:
        db_table = "OrganizationDepartment"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["tenantId", "code"], name="uq_org_department_code"),
        ]
        indexes = [
            models.Index(fields=["tenantId", "status"], name="ix_org_dept_status"),
        ]


class OrganizationPositionModel(OrganizationStamped):
    """One job title: «مدیر»، «سرپرست برق» …"""

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=500, blank=True, default="")

    #: Seniority, used for sorting the matrix and for recognising who is
    #: senior inside a unit. It grants nothing by itself: a higher number
    #: does not inherit a lower one's permissions, because "مدیر is above
    #: تکنسین therefore has every technician permission" is how systems
    #: quietly hand out access nobody approved.
    level = models.IntegerField(default=0, db_index=True)

    isActive = models.BooleanField(default=True)
    isSystem = models.BooleanField(default=False)

    class Meta:
        db_table = "OrganizationPosition"
        ordering = ["-level", "code"]
        constraints = [
            models.UniqueConstraint(fields=["tenantId", "code"], name="uq_org_position_code"),
        ]


class OrganizationAssignmentModel(OrganizationStamped):
    """«کاربر + واحد + سمت» — one posting."""

    userId = models.UUIDField(db_index=True)
    userDisplayName = models.CharField(max_length=160, blank=True, default="")
    departmentId = models.UUIDField(db_index=True)
    positionId = models.UUIDField(db_index=True)

    #: Which posting answers "which unit is this person in?" when they hold
    #: several. Work orders they raise are attributed here.
    isPrimary = models.BooleanField(default=True)
    isActive = models.BooleanField(default=True)

    #: Who they report to, for ``team`` scope. Nullable because the top of a
    #: unit reports to nobody inside it.
    reportsToUserId = models.UUIDField(null=True, blank=True, db_index=True)

    startedAt = models.DateTimeField(null=True, blank=True)
    endedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "OrganizationAssignment"
        ordering = ["-isPrimary", "-createdAt"]
        constraints = [
            # One posting per (user, department, position). Holding the same
            # title twice in one unit is a data error, not a promotion.
            models.UniqueConstraint(
                fields=["tenantId", "userId", "departmentId", "positionId"],
                name="uq_org_assignment_once",
            ),
        ]
        indexes = [
            models.Index(fields=["tenantId", "userId"], name="ix_org_assign_user"),
            models.Index(fields=["tenantId", "departmentId"], name="ix_org_assign_dept"),
        ]


class OrganizationAccessRuleModel(OrganizationStamped):
    """One cell of the permission grid.

    ``departmentId`` null means the rule applies in every unit — the
    organisation-wide default for that position. A row naming a department
    overrides it there, including when it is narrower.
    """

    CAPABILITY = [(x, x) for x in CAPABILITY_KEYS]
    ACTION = [(x, x) for x in ACTIONS]
    SCOPE = [(x, x) for x in SCOPES]

    positionId = models.UUIDField(db_index=True)
    departmentId = models.UUIDField(null=True, blank=True, db_index=True)
    capability = models.CharField(max_length=40, choices=CAPABILITY)
    action = models.CharField(max_length=16, choices=ACTION)
    scope = models.CharField(max_length=16, choices=SCOPE, default=SCOPE_DEPARTMENT)
    isActive = models.BooleanField(default=True)

    #: Who last changed this cell. A permission matrix without an author is
    #: an argument waiting to happen.
    updatedByUserId = models.UUIDField(null=True, blank=True)
    updatedByName = models.CharField(max_length=160, blank=True, default="")

    class Meta:
        db_table = "OrganizationAccessRule"
        ordering = ["capability", "action"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "positionId", "departmentId", "capability", "action"],
                name="uq_org_rule_cell",
            ),
        ]
        indexes = [
            models.Index(fields=["tenantId", "positionId"], name="ix_org_rule_position"),
        ]


class OrganizationAuditModel(OrganizationStamped):
    """Append-only log of structural and permission changes.

    Separate from the rows it describes so that deleting a department does
    not delete the evidence that it existed and who could act in it.
    """

    entity = models.CharField(max_length=32, db_index=True)
    entityId = models.UUIDField(null=True, blank=True, db_index=True)
    action = models.CharField(max_length=40)
    summary = models.CharField(max_length=500, blank=True, default="")
    actorUserId = models.UUIDField(null=True, blank=True)
    actorName = models.CharField(max_length=160, blank=True, default="")
    occurredAt = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "OrganizationAudit"
        ordering = ["-occurredAt"]
