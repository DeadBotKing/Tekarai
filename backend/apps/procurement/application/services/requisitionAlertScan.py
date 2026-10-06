"""Scheduled scan for purchase requisitions nobody has bought.

Emits ``purchaseRequisitionStale`` domain events for every open requisition
that has waited longer than its priority allows. The notification engine
routes them (§30) to the buyers.

Weekly-idempotent in the same way as the maintenance alert scan: the payload
``eventId`` is scoped to the ISO week, so running the scan daily — which you
want, so a request that goes stale on Tuesday is not announced the following
Monday — produces at most one notification per requisition per week instead
of nagging every morning.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone

from apps.procurement.domain.services.requisitionAging import evaluateRequisitionAging
from apps.procurement.domain.valueObjects.requisitionState import OPEN_REQUISITION_STATUSES
from apps.procurement.infrastructure.models import PurchaseRequisitionModel
from apps.sharedKernel.domain.events import DomainEvent
from apps.sharedKernel.infrastructure.wiring import defaultEventDispatcher

logger = logging.getLogger(__name__)

#: Event name routed in ``NOTIFICATION_EVENT_ROUTES``.
STALE_REQUISITION_EVENT = "purchaseRequisitionStale"

#: Who is expected to act on a stalled purchase request.
BUYER_ROLES = ["maintenanceManager"]

#: Used when nobody holds a buyer role. Without this the alert resolves to an
#: empty recipient list and is silently dropped — which is exactly what
#: happened on a fresh install, where the only user is the tenant admin.
FALLBACK_ROLES = ["tenantAdmin", "platformAdmin"]


def resolveAlertRecipients(tenantId: uuid.UUID, requesterId: uuid.UUID | None) -> list[str]:
    """Everyone who should hear that a purchase request has stalled.

    Recipients are resolved here rather than left to a ``ROLE`` spec in the
    route table because the requester has to be included by id: they are the
    person actually waiting for the part, and the user's ask was literally
    "tell me". Role holders are added so the people who can *do* something
    about it hear too.
    """
    from apps.identity.application.services import profileDirectory

    recipients: list[str] = []
    if requesterId:
        recipients.append(str(requesterId))

    buyers = [str(x) for x in profileDirectory.userIdsOfRole(tenantId, BUYER_ROLES)]
    if not buyers:
        buyers = [str(x) for x in profileDirectory.userIdsOfRole(tenantId, FALLBACK_ROLES)]
    recipients.extend(buyers)

    # Ordered de-duplication: the requester may also be the buyer.
    return list(dict.fromkeys(recipients))


@dataclass(frozen=True)
class StaleRequisitionDto:
    requisitionId: str
    number: str
    priority: str
    daysWaiting: int
    thresholdDays: int
    requesterName: str


@dataclass(frozen=True)
class RequisitionAlertScanDto:
    asOf: str
    isoWeek: str
    staleRequisitions: int = 0
    items: list[StaleRequisitionDto] = field(default_factory=list)


def scanStaleRequisitions(
    tenantId: uuid.UUID,
    *,
    now: datetime | None = None,
    dispatch: bool = True,
) -> RequisitionAlertScanDto:
    """Age every open requisition of one tenant and announce the late ones.

    ``dispatch=False`` lets callers (and the API) ask the same question
    without producing notifications.
    """
    now = now or timezone.now()
    isoYear, isoWeek, _ = now.isocalendar()
    weekKey = f"{isoYear}-W{isoWeek:02d}"
    dispatcher = defaultEventDispatcher() if dispatch else None

    items: list[StaleRequisitionDto] = []
    rows = PurchaseRequisitionModel.objects.filter(
        tenantId=tenantId, status__in=OPEN_REQUISITION_STATUSES
    )
    for requisition in rows:
        aging = evaluateRequisitionAging(
            status=requisition.status,
            priority=requisition.priority,
            submittedAt=requisition.submittedAt,
            now=now,
        )
        if not aging.isStale:
            continue
        items.append(
            StaleRequisitionDto(
                requisitionId=str(requisition.id),
                number=requisition.number,
                priority=requisition.priority,
                daysWaiting=aging.daysWaiting,
                thresholdDays=aging.thresholdDays,
                requesterName=requisition.requesterName,
            )
        )
        if dispatcher is None:
            continue
        recipients = resolveAlertRecipients(tenantId, requisition.requesterId)
        if not recipients:
            # Nothing to deliver to. Say so loudly rather than reporting a
            # successful scan that notified nobody.
            logger.warning(
                "Stale purchase requisition has no alert recipients",
                extra={"requisitionId": str(requisition.id), "tenantId": str(tenantId)},
            )
            continue
        dispatcher.dispatch(
            DomainEvent(
                name=STALE_REQUISITION_EVENT,
                occurredAt=now,
                tenantId=tenantId,
                payload={
                    "eventId": f"{STALE_REQUISITION_EVENT}:{requisition.id}:{weekKey}",
                    "sourceId": str(requisition.id),
                    "recipientIds": recipients,
                    "requisitionId": str(requisition.id),
                    "requisitionNumber": requisition.number,
                    "priority": requisition.priority,
                    "status": requisition.status,
                    "daysWaiting": aging.daysWaiting,
                    "thresholdDays": aging.thresholdDays,
                    "requesterName": requisition.requesterName,
                },
            )
        )

    return RequisitionAlertScanDto(
        asOf=now.date().isoformat(),
        isoWeek=weekKey,
        staleRequisitions=len(items),
        items=items,
    )
