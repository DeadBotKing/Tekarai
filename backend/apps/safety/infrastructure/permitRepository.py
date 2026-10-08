"""Database access for permits.

Exists because the application layer may not touch the ORM (DependencyRules
§3, enforced by ``tests/architecture/testArchitecturalRules.py``).
``permitService`` decides; this module reads and writes.

Every query here is tenant-scoped at the first filter, with no code path
that takes a permit id alone. In a multi-tenant safety system, a missing
tenant filter is not a privacy bug — it is one plant closing another
plant's permit.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db import transaction

from apps.safety.domain.valueObjects.permitState import (
    EXPIRY_REVIEW_STATUSES,
    LIVE_PERMIT_STATUSES,
)
from apps.safety.infrastructure.models import (
    PermitEventModel,
    PermitIsolationPointModel,
    PermitPrecautionModel,
    PermitToWorkModel,
)


class PermitNotFound(Exception):
    """Asked for a permit that does not exist in this tenant."""


def nextPermitNumber(tenantId: uuid.UUID, now: datetime) -> str:
    """Human-quotable id, e.g. ``PTW-20261007-014``.

    Date-prefixed and sequential within the day because permits are read
    aloud over a radio and written on a board at the job face. A raw UUID
    cannot be.
    """
    stamp = now.strftime("%Y%m%d")
    prefix = f"PTW-{stamp}-"
    used = (
        PermitToWorkModel.objects.filter(tenantId=tenantId, number__startswith=prefix)
        .order_by()
        .values_list("number", flat=True)
    )
    highest = 0
    for number in used:
        tail = number.rsplit("-", 1)[-1]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"{prefix}{highest + 1:03d}"


@transaction.atomic
def createPermitRow(
    *,
    tenantId: uuid.UUID,
    permitType: str,
    title: str,
    description: str,
    riskLevel: str,
    deviceId,
    workOrderId,
    locationId,
    locationName: str,
    requesterId,
    requesterName: str,
    performerName: str,
    contractorName: str,
    personnelCount: int,
    validFrom,
    validTo,
    precautions: list[dict],
    now: datetime,
) -> PermitToWorkModel:
    """Write the permit and its checklist as one unit.

    Atomic because a permit with a half-written checklist is worse than no
    permit: it looks complete and is not.
    """
    permit = PermitToWorkModel.objects.create(
        tenantId=tenantId,
        number=nextPermitNumber(tenantId, now),
        permitType=permitType,
        title=title[:300],
        description=description,
        riskLevel=riskLevel,
        deviceId=deviceId,
        workOrderId=workOrderId,
        locationId=locationId,
        locationName=locationName[:240],
        requesterId=requesterId,
        requesterName=requesterName[:160],
        performerName=performerName[:240],
        contractorName=contractorName[:240],
        personnelCount=max(1, int(personnelCount or 1)),
        validFrom=validFrom,
        validTo=validTo,
        updatedAt=now,
    )
    PermitPrecautionModel.objects.bulk_create(
        [
            PermitPrecautionModel(
                tenantId=tenantId,
                permitId=permit.id,
                code=item["code"],
                text=item["text"],
                isMandatory=item["isMandatory"],
            )
            for item in precautions
        ]
    )
    return permit


def loadPermit(tenantId: uuid.UUID, permitId: uuid.UUID) -> PermitToWorkModel:
    try:
        return PermitToWorkModel.objects.get(tenantId=tenantId, id=permitId)
    except PermitToWorkModel.DoesNotExist as error:
        raise PermitNotFound(str(permitId)) from error


def savePermit(permit: PermitToWorkModel) -> None:
    permit.save()


def precautionRows(tenantId: uuid.UUID, permitId: uuid.UUID) -> list[PermitPrecautionModel]:
    return list(
        PermitPrecautionModel.objects.filter(tenantId=tenantId, permitId=permitId).order_by(
            "-isMandatory", "createdAt"
        )
    )


def isolationRows(
    tenantId: uuid.UUID, permitId: uuid.UUID
) -> list[PermitIsolationPointModel]:
    return list(
        PermitIsolationPointModel.objects.filter(
            tenantId=tenantId, permitId=permitId
        ).order_by("pointCode")
    )


def createIsolationRow(
    *,
    tenantId: uuid.UUID,
    permitId: uuid.UUID,
    pointCode: str,
    description: str,
    energyType: str,
    isolationMethod: str = "",
    lockTag: str = "",
    now: datetime | None = None,
) -> PermitIsolationPointModel:
    return PermitIsolationPointModel.objects.create(
        tenantId=tenantId,
        permitId=permitId,
        pointCode=pointCode[:60],
        description=description[:500],
        energyType=energyType,
        isolationMethod=isolationMethod[:240],
        lockTag=lockTag[:60],
        updatedAt=now,
    )


def appendEvent(
    *,
    tenantId: uuid.UUID,
    permitId: uuid.UUID,
    action: str,
    fromStatus: str,
    toStatus: str,
    actorId,
    actorName: str,
    note: str,
    occurredAt: datetime,
) -> None:
    """Append to the trail. Never updates, never deletes."""
    PermitEventModel.objects.create(
        tenantId=tenantId,
        permitId=permitId,
        action=action,
        fromStatus=fromStatus,
        toStatus=toStatus,
        actorId=actorId,
        actorName=actorName[:160],
        note=note[:500],
        occurredAt=occurredAt,
    )


def eventRows(tenantId: uuid.UUID, permitId: uuid.UUID) -> list[PermitEventModel]:
    return list(
        PermitEventModel.objects.filter(tenantId=tenantId, permitId=permitId).order_by(
            "occurredAt", "createdAt"
        )
    )


def listPermits(
    tenantId: uuid.UUID,
    *,
    status: str = "",
    permitType: str = "",
    deviceId=None,
    liveOnly: bool = False,
    limit: int = 200,
) -> list[PermitToWorkModel]:
    queryset = PermitToWorkModel.objects.filter(tenantId=tenantId)
    if status:
        queryset = queryset.filter(status=status)
    if permitType:
        queryset = queryset.filter(permitType=permitType)
    if deviceId:
        queryset = queryset.filter(deviceId=deviceId)
    if liveOnly:
        queryset = queryset.filter(status__in=LIVE_PERMIT_STATUSES)
    return list(queryset.order_by("-createdAt")[: max(1, min(limit, 500))])


def permitsForDevice(tenantId: uuid.UUID, deviceId: uuid.UUID) -> list[PermitToWorkModel]:
    return list(
        PermitToWorkModel.objects.filter(tenantId=tenantId, deviceId=deviceId).order_by(
            "-createdAt"
        )
    )


def conflictingLivePermits(
    tenantId: uuid.UUID, permit: PermitToWorkModel
) -> list[PermitToWorkModel]:
    """Other live permits on the same asset.

    Overlapping permits on one machine are legitimate but must be a
    conscious decision, so they are surfaced at approval rather than
    blocked. Returns nothing when the permit is not tied to a device —
    a permit on "the whole yard" cannot be matched this way.
    """
    if not permit.deviceId:
        return []
    return list(
        PermitToWorkModel.objects.filter(
            tenantId=tenantId,
            deviceId=permit.deviceId,
            status__in=LIVE_PERMIT_STATUSES,
        )
        .exclude(id=permit.id)
        .order_by("number")
    )


def permitsNeedingExpiryReview(tenantId: uuid.UUID) -> list[PermitToWorkModel]:
    """Permits whose clock matters: issued or running, with an end time."""
    return list(
        PermitToWorkModel.objects.filter(
            tenantId=tenantId, status__in=EXPIRY_REVIEW_STATUSES, validTo__isnull=False
        ).order_by("validTo")
    )


def tenantIdsWithLivePermits() -> list[uuid.UUID]:
    """Tenants the expiry scan has any reason to visit."""
    return list(
        PermitToWorkModel.objects.filter(status__in=EXPIRY_REVIEW_STATUSES)
        .order_by()
        .values_list("tenantId", flat=True)
        .distinct()
    )
