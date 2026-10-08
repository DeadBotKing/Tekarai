"""Permit-to-work tables.

Four tables, and the split between them is deliberate.

``PermitToWorkModel`` is the document. ``PermitPrecautionModel`` is the
assessment it was issued against — rows, not a JSON blob, because an
investigator asks "who confirmed the gas test, and at what time", and a blob
cannot answer that. ``PermitIsolationPointModel`` is the lock-and-tag
register, with separate applied / verified / removed signatures because the
whole value of the register is that those are three distinct acts by
possibly three distinct people. ``PermitEventModel`` is the immutable log of
every transition: a permit's current status tells you where it is, the log
tells you how it got there, and after an incident only the second one
matters.

Nothing here is ever hard-deleted. A permit is a safety record.

Cross-context references (``deviceId``, ``workOrderId``, ``locationId``) are
plain UUID columns, not foreign keys, exactly like procurement's references
to spare parts: the architecture rules keep contexts from reaching into each
other's tables, and a database-level FK would be precisely that.
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.safety.domain.valueObjects.permitState import (
    ENERGY_TYPES,
    PERMIT_DRAFT,
    PERMIT_STATUSES,
    PERMIT_TYPES,
    RISK_LEVELS,
    RISK_MEDIUM,
)


class SafetyTenantStamped(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class PermitToWorkModel(SafetyTenantStamped):
    """One authorisation: this work, this equipment, these people, this window."""

    STATUS = [(x, x) for x in PERMIT_STATUSES]
    TYPE = [(x, x) for x in PERMIT_TYPES]
    RISK = [(x, x) for x in RISK_LEVELS]

    number = models.CharField(max_length=40)
    permitType = models.CharField(max_length=24, choices=TYPE, db_index=True)
    status = models.CharField(
        max_length=16, choices=STATUS, default=PERMIT_DRAFT, db_index=True
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    riskLevel = models.CharField(max_length=12, choices=RISK, default=RISK_MEDIUM)

    # What the work is on. Indexed because "is anything live on this
    # machine?" is the question asked before every job.
    deviceId = models.UUIDField(null=True, blank=True, db_index=True)
    workOrderId = models.UUIDField(null=True, blank=True, db_index=True)
    locationId = models.UUIDField(null=True, blank=True, db_index=True)
    locationName = models.CharField(max_length=240, blank=True, default="")

    # Who. Names are denormalised alongside the ids on purpose: a permit is
    # a legal record and must stay readable years later even if the user
    # account is renamed, transferred or deleted.
    requesterId = models.UUIDField(null=True, blank=True, db_index=True)
    requesterName = models.CharField(max_length=160, blank=True, default="")
    performerName = models.CharField(max_length=240, blank=True, default="")
    contractorName = models.CharField(max_length=240, blank=True, default="")
    personnelCount = models.PositiveIntegerField(default=1)

    approverId = models.UUIDField(null=True, blank=True)
    approverName = models.CharField(max_length=160, blank=True, default="")
    closedById = models.UUIDField(null=True, blank=True)
    closedByName = models.CharField(max_length=160, blank=True, default="")

    # The window the controls were assessed against. Indexed on validTo
    # because the expiry scan sorts on it.
    validFrom = models.DateTimeField(null=True, blank=True)
    validTo = models.DateTimeField(null=True, blank=True, db_index=True)

    submittedAt = models.DateTimeField(null=True, blank=True)
    approvedAt = models.DateTimeField(null=True, blank=True)
    activatedAt = models.DateTimeField(null=True, blank=True)
    suspendedAt = models.DateTimeField(null=True, blank=True)
    completedAt = models.DateTimeField(null=True, blank=True)
    closedAt = models.DateTimeField(null=True, blank=True)

    suspensionReason = models.CharField(max_length=500, blank=True, default="")
    rejectionReason = models.CharField(max_length=500, blank=True, default="")
    cancellationReason = models.CharField(max_length=500, blank=True, default="")
    closureNote = models.TextField(blank=True, default="")

    class Meta:
        db_table = "SafetyPermitToWork"
        ordering = ["-createdAt"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "number"], name="uq_safety_permit_number"
            ),
        ]
        indexes = [
            models.Index(fields=["tenantId", "status"], name="ix_safety_permit_status"),
        ]


class PermitPrecautionModel(SafetyTenantStamped):
    """One line of the checklist the permit is issued against.

    A row rather than a JSON field because ``confirmedById`` and
    ``confirmedAt`` are the evidence. "The checklist was completed" is not
    an answer; "the gas test was confirmed by X at 07:412" is.
    """

    permitId = models.UUIDField(db_index=True)
    code = models.CharField(max_length=60)
    text = models.CharField(max_length=500)
    isMandatory = models.BooleanField(default=True)
    confirmed = models.BooleanField(default=False)
    confirmedById = models.UUIDField(null=True, blank=True)
    confirmedByName = models.CharField(max_length=160, blank=True, default="")
    confirmedAt = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        db_table = "SafetyPermitPrecaution"
        ordering = ["createdAt"]


class PermitIsolationPointModel(SafetyTenantStamped):
    """One lock-and-tag point: what was isolated, by whom, checked by whom.

    Three independent signature pairs. Collapsing them into one "done"
    column would destroy the only thing the register is for — that applying
    an isolation and independently verifying it are different acts, and
    that every lock put on is accounted for when it comes back off.
    """

    ENERGY = [(x, x) for x in ENERGY_TYPES]

    permitId = models.UUIDField(db_index=True)
    pointCode = models.CharField(max_length=60)
    description = models.CharField(max_length=500)
    energyType = models.CharField(max_length=16, choices=ENERGY)
    isolationMethod = models.CharField(max_length=240, blank=True, default="")
    lockTag = models.CharField(max_length=60, blank=True, default="")

    appliedById = models.UUIDField(null=True, blank=True)
    appliedByName = models.CharField(max_length=160, blank=True, default="")
    appliedAt = models.DateTimeField(null=True, blank=True)

    verifiedById = models.UUIDField(null=True, blank=True)
    verifiedByName = models.CharField(max_length=160, blank=True, default="")
    verifiedAt = models.DateTimeField(null=True, blank=True)

    removedById = models.UUIDField(null=True, blank=True)
    removedByName = models.CharField(max_length=160, blank=True, default="")
    removedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "SafetyPermitIsolationPoint"
        ordering = ["pointCode"]


class PermitEventModel(SafetyTenantStamped):
    """Append-only trail of everything that happened to a permit.

    Written on every transition and every signature. Never updated, never
    deleted: the current status says where the permit is, this says how it
    got there, and after an incident the second question is the one that
    gets asked.
    """

    permitId = models.UUIDField(db_index=True)
    action = models.CharField(max_length=40, db_index=True)
    fromStatus = models.CharField(max_length=16, blank=True, default="")
    toStatus = models.CharField(max_length=16, blank=True, default="")
    actorId = models.UUIDField(null=True, blank=True)
    actorName = models.CharField(max_length=160, blank=True, default="")
    note = models.CharField(max_length=500, blank=True, default="")
    occurredAt = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "SafetyPermitEvent"
        ordering = ["occurredAt", "createdAt"]
