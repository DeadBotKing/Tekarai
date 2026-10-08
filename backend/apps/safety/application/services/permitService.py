"""Permit-to-work operations: create, authorise, run, close.

The decisions live in ``domain/services/permitRules``; this module applies
them to stored rows, writes the audit trail and raises the alarms.
It is deliberately thin — every refusal comes from the domain, so the rules
can be read, reviewed and tested in one file without a database.

Two things are enforced here rather than in the domain because they need
persisted state:

* **Signatures are captured at the moment of the act**, not reconstructed
  later. ``confirmPrecaution``, ``applyIsolation`` and ``verifyIsolation``
  stamp who and when immediately, because that is the evidence.
* **Every transition writes a ``PermitEvent``.** The status column says
  where a permit is; the event log says how it got there, and after an
  incident that is the question.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.safety.domain.services.permitRules import (
    IsolationSnapshot,
    PermitRuleViolation,
    PrecautionSnapshot,
    evaluateIssueReadiness,
    evaluatePermitValidity,
    guardActivation,
    guardApproval,
    guardClosure,
    guardIsolationRemoval,
    guardIsolationVerifier,
    guardResume,
    guardTransition,
)
from apps.safety.domain.valueObjects.permitState import (
    LIVE_PERMIT_STATUSES,
    PERMIT_ACTIVE,
    PERMIT_APPROVED,
    PERMIT_CANCELLED,
    PERMIT_CLOSED,
    PERMIT_COMPLETED,
    PERMIT_EXPIRED,
    PERMIT_REJECTED,
    PERMIT_SUBMITTED,
    PERMIT_SUSPENDED,
    WORK_IN_PROGRESS_STATUSES,
    standardPrecautionsFor,
)
from apps.safety.infrastructure.permitRepository import (
    appendEvent,
    conflictingLivePermits,
    createPermitRow,
    isolationRows,
    loadPermit,
    precautionRows,
    savePermit,
)

logger = logging.getLogger(__name__)

PERMIT_APPROVED_EVENT = "permitApproved"
PERMIT_EXPIRING_EVENT = "permitExpiringSoon"
PERMIT_OVERDUE_EVENT = "permitOverdue"


@dataclass(frozen=True)
class Actor:
    """Who is performing the action. Both halves are recorded.

    The name is stored alongside the id because a permit is read years
    later, by people who do not have access to the user table and after the
    account may have been renamed or removed.
    """

    id: uuid.UUID | None
    name: str = ""


def _snapshots(tenantId: uuid.UUID, permitId: uuid.UUID):
    precautions = [
        PrecautionSnapshot(
            code=row.code,
            text=row.text,
            isMandatory=row.isMandatory,
            confirmed=row.confirmed,
        )
        for row in precautionRows(tenantId, permitId)
    ]
    isolations = [
        IsolationSnapshot(
            pointCode=row.pointCode,
            description=row.description,
            appliedById=str(row.appliedById or ""),
            verifiedById=str(row.verifiedById or ""),
            removedById=str(row.removedById or ""),
        )
        for row in isolationRows(tenantId, permitId)
    ]
    return precautions, isolations


def _transition(
    permit,
    *,
    target: str,
    actor: Actor,
    action: str,
    now: datetime,
    note: str = "",
    fields: dict | None = None,
) -> None:
    """Apply a status change and log it. The guard has already run."""
    previous = permit.status
    permit.status = target
    for key, value in (fields or {}).items():
        setattr(permit, key, value)
    permit.updatedAt = now
    savePermit(permit)
    appendEvent(
        tenantId=permit.tenantId,
        permitId=permit.id,
        action=action,
        fromStatus=previous,
        toStatus=target,
        actorId=actor.id,
        actorName=actor.name,
        note=note,
        occurredAt=now,
    )


# --- Creation --------------------------------------------------------------


def createPermit(
    tenantId: uuid.UUID,
    *,
    permitType: str,
    title: str,
    actor: Actor,
    description: str = "",
    riskLevel: str = "medium",
    deviceId: uuid.UUID | None = None,
    workOrderId: uuid.UUID | None = None,
    locationId: uuid.UUID | None = None,
    locationName: str = "",
    performerName: str = "",
    contractorName: str = "",
    personnelCount: int = 1,
    validFrom: datetime | None = None,
    validTo: datetime | None = None,
    extraPrecautions: list[dict] | None = None,
    now: datetime | None = None,
):
    """Open a draft permit, pre-loaded with the checklist for its type.

    Seeding the standard precautions is the point of having permit types at
    all. A blank checklist gets ticked; a list that names *this* job's
    hazards gets read. The requester may add more, never fewer — the
    standard mandatory items cannot be removed from the form.
    """
    now = now or timezone.now()
    permit = createPermitRow(
        tenantId=tenantId,
        permitType=permitType,
        title=title,
        description=description,
        riskLevel=riskLevel,
        deviceId=deviceId,
        workOrderId=workOrderId,
        locationId=locationId,
        locationName=locationName,
        requesterId=actor.id,
        requesterName=actor.name,
        performerName=performerName,
        contractorName=contractorName,
        personnelCount=personnelCount,
        validFrom=validFrom,
        validTo=validTo,
        precautions=[
            {"code": code, "text": text, "isMandatory": mandatory}
            for code, text, mandatory in standardPrecautionsFor(permitType)
        ]
        + [
            {
                "code": str(item.get("code", "custom"))[:60],
                "text": str(item.get("text", ""))[:500],
                "isMandatory": bool(item.get("isMandatory", False)),
            }
            for item in (extraPrecautions or [])
            if str(item.get("text", "")).strip()
        ],
        now=now,
    )
    appendEvent(
        tenantId=tenantId,
        permitId=permit.id,
        action="created",
        fromStatus="",
        toStatus=permit.status,
        actorId=actor.id,
        actorName=actor.name,
        note="",
        occurredAt=now,
    )
    return permit


# --- Lifecycle -------------------------------------------------------------


def submitPermit(tenantId: uuid.UUID, permitId: uuid.UUID, *, actor: Actor, now=None):
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    guardTransition(permit.status, PERMIT_SUBMITTED)
    _transition(
        permit,
        target=PERMIT_SUBMITTED,
        actor=actor,
        action="submitted",
        now=now,
        fields={"submittedAt": now},
    )
    return permit


def approvePermit(
    tenantId: uuid.UUID, permitId: uuid.UUID, *, actor: Actor, note: str = "", now=None
):
    """Authorise the permit. Every safety guard runs here.

    This is the one call in the system that converts an intention into
    permission to put hands on equipment, so it is also the one that
    refuses the most.
    """
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    precautions, isolations = _snapshots(tenantId, permitId)

    guardApproval(
        currentStatus=permit.status,
        permitType=permit.permitType,
        riskLevel=permit.riskLevel,
        requesterId=str(permit.requesterId or ""),
        approverId=str(actor.id or ""),
        validFrom=permit.validFrom,
        validTo=permit.validTo,
        precautions=precautions,
        isolations=isolations,
        now=now,
    )

    # A second live permit on the same asset means two crews can be working
    # on one machine without either knowing. The conflict is surfaced
    # rather than blocked: simultaneous permits are legitimate (two trades,
    # one shutdown) but must be a conscious decision, so it is recorded on
    # the permit and announced instead of silently allowed.
    conflicts = conflictingLivePermits(tenantId, permit)
    conflictNote = ""
    if conflicts:
        conflictNote = "مجوزهای فعال هم‌زمان روی همین تجهیز: " + "، ".join(
            x.number for x in conflicts
        )

    _transition(
        permit,
        target=PERMIT_APPROVED,
        actor=actor,
        action="approved",
        now=now,
        note="؛ ".join(x for x in (note, conflictNote) if x),
        fields={"approvedAt": now, "approverId": actor.id, "approverName": actor.name},
    )
    _announce(permit, PERMIT_APPROVED_EVENT, now=now, extra={"conflicts": conflictNote})
    return permit


def rejectPermit(
    tenantId: uuid.UUID, permitId: uuid.UUID, *, actor: Actor, reason: str, now=None
):
    """Refuse the permit. A reason is required.

    "Rejected" with no reason teaches the requester nothing and guarantees
    the same permit comes back unchanged.
    """
    if not reason.strip():
        raise PermitRuleViolation("permit.reject.reasonRequired", "دلیل رد مجوز الزامی است.")
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    guardTransition(permit.status, PERMIT_REJECTED)
    _transition(
        permit,
        target=PERMIT_REJECTED,
        actor=actor,
        action="rejected",
        now=now,
        note=reason,
        fields={"rejectionReason": reason[:500]},
    )
    return permit


def activatePermit(tenantId: uuid.UUID, permitId: uuid.UUID, *, actor: Actor, now=None):
    """The performer accepts the permit and work begins."""
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    guardActivation(
        currentStatus=permit.status,
        validFrom=permit.validFrom,
        validTo=permit.validTo,
        now=now,
    )
    _transition(
        permit,
        target=PERMIT_ACTIVE,
        actor=actor,
        action="activated",
        now=now,
        fields={"activatedAt": permit.activatedAt or now},
    )
    return permit


def suspendPermit(
    tenantId: uuid.UUID, permitId: uuid.UUID, *, actor: Actor, reason: str, now=None
):
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    guardTransition(permit.status, PERMIT_SUSPENDED)
    _transition(
        permit,
        target=PERMIT_SUSPENDED,
        actor=actor,
        action="suspended",
        now=now,
        note=reason,
        fields={"suspendedAt": now, "suspensionReason": reason[:500]},
    )
    return permit


def resumePermit(tenantId: uuid.UUID, permitId: uuid.UUID, *, actor: Actor, now=None):
    """Restart suspended work — re-checked against the clock, not waved through."""
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    guardResume(
        currentStatus=permit.status,
        validFrom=permit.validFrom,
        validTo=permit.validTo,
        now=now,
    )
    _transition(
        permit,
        target=PERMIT_ACTIVE,
        actor=actor,
        action="resumed",
        now=now,
        fields={"suspendedAt": None, "suspensionReason": ""},
    )
    return permit


def completePermit(
    tenantId: uuid.UUID, permitId: uuid.UUID, *, actor: Actor, note: str = "", now=None
):
    """Tools down. The equipment is *not* handed back yet — that is closure."""
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    guardTransition(permit.status, PERMIT_COMPLETED)
    _transition(
        permit,
        target=PERMIT_COMPLETED,
        actor=actor,
        action="completed",
        now=now,
        note=note,
        fields={"completedAt": now},
    )
    return permit


def closePermit(
    tenantId: uuid.UUID, permitId: uuid.UUID, *, actor: Actor, note: str = "", now=None
):
    """Hand the equipment back. Refused while any lock is still on."""
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    _, isolations = _snapshots(tenantId, permitId)
    guardClosure(currentStatus=permit.status, isolations=isolations)
    _transition(
        permit,
        target=PERMIT_CLOSED,
        actor=actor,
        action="closed",
        now=now,
        note=note,
        fields={
            "closedAt": now,
            "closedById": actor.id,
            "closedByName": actor.name,
            "closureNote": note,
        },
    )
    return permit


def cancelPermit(
    tenantId: uuid.UUID, permitId: uuid.UUID, *, actor: Actor, reason: str, now=None
):
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    guardTransition(permit.status, PERMIT_CANCELLED)
    _transition(
        permit,
        target=PERMIT_CANCELLED,
        actor=actor,
        action="cancelled",
        now=now,
        note=reason,
        fields={"cancellationReason": reason[:500]},
    )
    return permit


# --- Checklist and isolation register --------------------------------------


def confirmPrecaution(
    tenantId: uuid.UUID,
    permitId: uuid.UUID,
    precautionId: uuid.UUID,
    *,
    actor: Actor,
    note: str = "",
    now=None,
):
    """Sign off one checklist line.

    Refused once the permit is authorised: the checklist *is* the
    assessment the authorisation was granted against, and letting it change
    afterwards would mean the signed permit no longer describes what was
    approved.
    """
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    if permit.status not in ("draft", PERMIT_SUBMITTED):
        raise PermitRuleViolation(
            "permit.precaution.locked",
            "پس از صدور مجوز، چک‌لیست قابل تغییر نیست؛ "
            "برای تغییر شرایط، مجوز جدید صادر کنید.",
        )
    row = next(
        (x for x in precautionRows(tenantId, permitId) if x.id == precautionId), None
    )
    if row is None:
        raise PermitRuleViolation("permit.precaution.notFound", "این مورد چک‌لیست یافت نشد.")
    row.confirmed = True
    row.confirmedById = actor.id
    row.confirmedByName = actor.name
    row.confirmedAt = now
    row.note = note[:500]
    row.updatedAt = now
    row.save()
    appendEvent(
        tenantId=tenantId,
        permitId=permitId,
        action="precautionConfirmed",
        fromStatus=permit.status,
        toStatus=permit.status,
        actorId=actor.id,
        actorName=actor.name,
        note=f"{row.code}: {row.text}"[:500],
        occurredAt=now,
    )
    return row


def applyIsolation(
    tenantId: uuid.UUID,
    permitId: uuid.UUID,
    isolationId: uuid.UUID,
    *,
    actor: Actor,
    now=None,
):
    """Record that a lock and tag went on, and who put it there."""
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    row = next((x for x in isolationRows(tenantId, permitId) if x.id == isolationId), None)
    if row is None:
        raise PermitRuleViolation("permit.isolation.notFound", "این نقطه جداسازی یافت نشد.")
    if row.removedById:
        raise PermitRuleViolation(
            "permit.isolation.alreadyRemoved",
            "این قفل برداشته شده است؛ برای جداسازی مجدد، نقطه جدیدی ثبت کنید.",
        )
    row.appliedById = actor.id
    row.appliedByName = actor.name
    row.appliedAt = now
    # Applying again invalidates any previous verification: the thing that
    # was checked is not necessarily the thing that is now in place.
    row.verifiedById = None
    row.verifiedByName = ""
    row.verifiedAt = None
    row.updatedAt = now
    row.save()
    appendEvent(
        tenantId=tenantId,
        permitId=permitId,
        action="isolationApplied",
        fromStatus=permit.status,
        toStatus=permit.status,
        actorId=actor.id,
        actorName=actor.name,
        note=f"{row.pointCode}: {row.description}"[:500],
        occurredAt=now,
    )
    return row


def verifyIsolation(
    tenantId: uuid.UUID,
    permitId: uuid.UUID,
    isolationId: uuid.UUID,
    *,
    actor: Actor,
    now=None,
):
    """Independently confirm an isolation is actually in place.

    Above high risk the verifier may not be the person who applied it —
    one competent person cannot check their own work.
    """
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    row = next((x for x in isolationRows(tenantId, permitId) if x.id == isolationId), None)
    if row is None:
        raise PermitRuleViolation("permit.isolation.notFound", "این نقطه جداسازی یافت نشد.")
    if not row.appliedById:
        raise PermitRuleViolation(
            "permit.isolation.notApplied",
            "ابتدا باید اجرای قفل‌گذاری ثبت شود، سپس تأیید.",
        )
    guardIsolationVerifier(
        appliedById=str(row.appliedById or ""),
        verifiedById=str(actor.id or ""),
        riskLevel=permit.riskLevel,
    )
    row.verifiedById = actor.id
    row.verifiedByName = actor.name
    row.verifiedAt = now
    row.updatedAt = now
    row.save()
    appendEvent(
        tenantId=tenantId,
        permitId=permitId,
        action="isolationVerified",
        fromStatus=permit.status,
        toStatus=permit.status,
        actorId=actor.id,
        actorName=actor.name,
        note=f"{row.pointCode}"[:500],
        occurredAt=now,
    )
    return row


def removeIsolation(
    tenantId: uuid.UUID,
    permitId: uuid.UUID,
    isolationId: uuid.UUID,
    *,
    actor: Actor,
    now=None,
):
    """Take the lock off. Refused while work is still running."""
    now = now or timezone.now()
    permit = loadPermit(tenantId, permitId)
    guardIsolationRemoval(permitStatus=permit.status)
    row = next((x for x in isolationRows(tenantId, permitId) if x.id == isolationId), None)
    if row is None:
        raise PermitRuleViolation("permit.isolation.notFound", "این نقطه جداسازی یافت نشد.")
    row.removedById = actor.id
    row.removedByName = actor.name
    row.removedAt = now
    row.updatedAt = now
    row.save()
    appendEvent(
        tenantId=tenantId,
        permitId=permitId,
        action="isolationRemoved",
        fromStatus=permit.status,
        toStatus=permit.status,
        actorId=actor.id,
        actorName=actor.name,
        note=f"{row.pointCode}"[:500],
        occurredAt=now,
    )
    return row


# --- Read model ------------------------------------------------------------


def permitReadiness(tenantId: uuid.UUID, permit) -> dict:
    """What still stands between this permit and authorisation."""
    precautions, isolations = _snapshots(tenantId, permit.id)
    report = evaluateIssueReadiness(
        permitType=permit.permitType, precautions=precautions, isolations=isolations
    )
    return {"isReadyToIssue": report.isSatisfied, "blockers": report.blockers}


def permitValidityView(permit, now: datetime | None = None) -> dict:
    """Where the permit sits against its own clock.

    Computed per response, never stored: a persisted ``isExpired`` would be
    wrong every moment between the scan that set it and the next one.
    """
    validity = evaluatePermitValidity(
        validFrom=permit.validFrom, validTo=permit.validTo, now=now or timezone.now()
    )
    return {
        "hasStarted": validity.hasStarted,
        "isExpired": validity.isExpired,
        "isWithinWindow": validity.isWithinWindow,
        "minutesUntilStart": validity.minutesUntilStart,
        "minutesRemaining": validity.minutesRemaining,
        "isExpiringSoon": validity.isExpiringSoon,
        # A permit whose window has closed while work was still in progress
        # is the emergency case: people may still be on the job under an
        # authorisation that no longer exists.
        "isOverdueWithWorkInProgress": validity.isExpired
        and permit.status in WORK_IN_PROGRESS_STATUSES,
    }


def livePermitsForDevice(tenantId: uuid.UUID, deviceId: uuid.UUID) -> list:
    """Permits currently constraining one asset — the pre-job check."""
    from apps.safety.infrastructure.permitRepository import permitsForDevice

    return [x for x in permitsForDevice(tenantId, deviceId) if x.status in LIVE_PERMIT_STATUSES]


# --- Alarms ----------------------------------------------------------------


def _announce(permit, eventName: str, *, now: datetime, extra: dict | None = None) -> None:
    """Best-effort broadcast of a permit event.

    A failure to announce must never undo a safety decision that was
    correctly recorded, so this is logged rather than raised.
    """
    from apps.sharedKernel.domain.events import DomainEvent
    from apps.sharedKernel.infrastructure.wiring import defaultEventDispatcher

    try:
        defaultEventDispatcher().dispatch(
            DomainEvent(
                name=eventName,
                occurredAt=now,
                tenantId=permit.tenantId,
                payload={
                    "eventId": f"{eventName}:{permit.id}:{int(now.timestamp()) // 3600}",
                    "sourceId": str(permit.id),
                    "permitId": str(permit.id),
                    "permitNumber": permit.number,
                    "permitType": permit.permitType,
                    "status": permit.status,
                    "title": permit.title,
                    "riskLevel": permit.riskLevel,
                    **(extra or {}),
                },
            )
        )
    except Exception:  # noqa: BLE001 — see docstring
        logger.exception(
            "Permit event could not be announced",
            extra={"permitId": str(permit.id), "event": eventName},
        )


def scanPermitExpiry(tenantId: uuid.UUID, *, now=None, apply: bool = False) -> dict:
    """Find permits running out of time, and expire the ones that are safe to.

    The asymmetry is the point:

    * An **approved but never started** permit past its window is expired
      automatically. Nobody is on the job, and leaving a dead authorisation
      sitting in the approved list is how someone picks it up tomorrow.
    * An **active or suspended** permit past its window is **never**
      auto-expired. People may still be inside the vessel. Silently
      cancelling their authorisation does not get them out — it just
      removes the record that they are there. It raises an alarm instead,
      and a human closes it.
    """
    from apps.safety.infrastructure.permitRepository import permitsNeedingExpiryReview

    now = now or timezone.now()
    expired: list[str] = []
    overdue: list[str] = []
    expiringSoon: list[str] = []

    for permit in permitsNeedingExpiryReview(tenantId):
        validity = evaluatePermitValidity(
            validFrom=permit.validFrom, validTo=permit.validTo, now=now
        )
        if validity.isExpired and permit.status == PERMIT_APPROVED:
            expired.append(permit.number)
            if apply:
                _transition(
                    permit,
                    target=PERMIT_EXPIRED,
                    actor=Actor(id=None, name="سامانه"),
                    action="expired",
                    now=now,
                    note="بازه اعتبار بدون شروع کار به پایان رسید.",
                )
        elif validity.isExpired and permit.status in WORK_IN_PROGRESS_STATUSES:
            overdue.append(permit.number)
            if apply:
                _announce(permit, PERMIT_OVERDUE_EVENT, now=now)
        elif validity.isExpiringSoon:
            expiringSoon.append(permit.number)
            if apply:
                _announce(permit, PERMIT_EXPIRING_EVENT, now=now)

    return {
        "asOf": now.isoformat(),
        "expired": expired,
        "overdueWithWorkInProgress": overdue,
        "expiringSoon": expiringSoon,
        "applied": apply,
    }
