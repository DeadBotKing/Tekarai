"""Database access for the stock→purchase loop.

Everything in this module exists because the application layer may not touch
the ORM (DependencyRules §3, enforced by
``tests/architecture/testArchitecturalRules.py``). ``replenishmentScan``
decides *what* to buy; this module answers the two questions that need a
database to answer — "how much is already coming?" and "write these
requisitions" — and nothing else.

Queries return plain values, never querysets or model instances, so laziness
cannot leak a second round of SQL into the caller.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum

from apps.procurement.domain.valueObjects.requisitionState import OPEN_REQUISITION_STATUSES
from apps.procurement.infrastructure.models import (
    PurchaseOrderLineModel,
    PurchaseOrderModel,
    PurchaseRequisitionLineModel,
    PurchaseRequisitionModel,
    SupplierModel,
    SupplierPartModel,
)

#: Purchase-order statuses whose undelivered balance still counts as incoming
#: stock. A cancelled order brings nothing; a fully received one has already
#: landed on the shelf and is counted in ``quantityOnHand``.
INBOUND_ORDER_STATUSES = ("draft", "submitted", "approved", "partiallyReceived")

#: Requisition statuses that represent a live intention to buy. ``draft`` is
#: included deliberately — including the drafts this very scan created, which
#: is what makes a repeat run propose nothing.
PENDING_REQUISITION_STATUSES = ("draft", *OPEN_REQUISITION_STATUSES)


@dataclass(frozen=True)
class SupplierOffer:
    """One supplier's terms for one part."""

    supplierId: uuid.UUID
    supplierName: str
    unitPrice: Decimal
    minimumOrderQty: Decimal
    leadTimeDays: int
    isPreferred: bool


@dataclass(frozen=True)
class RequisitionLineSpec:
    """A line to write, as decided by the application layer."""

    partId: uuid.UUID
    partCode: str
    partName: str
    unit: str
    quantity: Decimal
    estimatedUnitCost: Decimal
    note: str


@dataclass(frozen=True)
class CreatedRequisition:
    requisitionId: uuid.UUID
    number: str
    lineCount: int
    priority: str
    totalEstimated: Decimal


def quantitiesOnOrder(tenantId: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    """How much of each part is already inbound.

    Two sources, deliberately both:

    * **Pending requisition lines** — asked for but not yet turned into an
      order. Omitting these is what makes a nightly scan pile up duplicate
      requests for the same part.
    * **Undelivered purchase-order balance** (``ordered − received``) —
      bought and on its way. Counting the full ordered quantity instead of
      the balance would keep a part that was only half delivered out of the
      reorder list forever.
    """
    totals: dict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal("0"))

    pendingRequisitionIds = list(
        PurchaseRequisitionModel.objects.filter(
            tenantId=tenantId, status__in=PENDING_REQUISITION_STATUSES
        ).values_list("id", flat=True)
    )
    requisitionRows = (
        PurchaseRequisitionLineModel.objects.filter(
            tenantId=tenantId, requisitionId__in=pendingRequisitionIds
        )
        .values("partId")
        .annotate(total=Sum("quantity"))
    )
    for row in requisitionRows:
        totals[row["partId"]] += Decimal(row["total"] or 0)

    inboundOrderIds = list(
        PurchaseOrderModel.objects.filter(
            tenantId=tenantId, status__in=INBOUND_ORDER_STATUSES
        ).values_list("id", flat=True)
    )
    orderRows = (
        PurchaseOrderLineModel.objects.filter(
            tenantId=tenantId, purchaseOrderId__in=inboundOrderIds
        )
        .values("partId")
        .annotate(total=Sum(F("orderedQuantity") - F("receivedQuantity")))
    )
    for row in orderRows:
        # An over-delivery makes the balance negative. That is surplus, not
        # a debt against some other part's availability, so it is floored.
        totals[row["partId"]] += max(Decimal("0"), Decimal(row["total"] or 0))

    return dict(totals)


def supplierOffersByPart(tenantId: uuid.UUID) -> dict[uuid.UUID, list[SupplierOffer]]:
    """The supplier catalogue, indexed by part, in one pass."""
    names = dict(SupplierModel.objects.filter(tenantId=tenantId).values_list("id", "name"))
    offers: dict[uuid.UUID, list[SupplierOffer]] = defaultdict(list)
    for link in SupplierPartModel.objects.filter(tenantId=tenantId):
        offers[link.partId].append(
            SupplierOffer(
                supplierId=link.supplierId,
                supplierName=names.get(link.supplierId, ""),
                unitPrice=Decimal(link.unitPrice),
                minimumOrderQty=Decimal(link.minimumOrderQty),
                leadTimeDays=int(link.leadTimeDays),
                isPreferred=bool(link.isPreferred),
            )
        )
    return dict(offers)


@transaction.atomic
def createDraftRequisition(
    tenantId: uuid.UUID,
    *,
    supplierId: uuid.UUID | None,
    priority: str,
    justification: str,
    lines: list[RequisitionLineSpec],
    requesterId: uuid.UUID | None,
    requesterName: str,
    now: datetime,
) -> CreatedRequisition:
    """Write one draft requisition and its lines, atomically.

    Atomic so a failure partway cannot leave a requisition header with no
    lines — an empty purchase request is worse than none, because somebody
    has to work out what it was meant to say.
    """
    total = sum(
        (line.quantity * line.estimatedUnitCost for line in lines), Decimal("0")
    ).quantize(Decimal("0.01"))

    requisition = PurchaseRequisitionModel.objects.create(
        tenantId=tenantId,
        number=f"PR-{uuid.uuid4().hex[:8].upper()}",
        status="draft",
        requesterId=requesterId,
        requesterName=requesterName,
        priority=priority,
        justification=justification,
        totalEstimated=total,
    )
    PurchaseRequisitionLineModel.objects.bulk_create(
        [
            PurchaseRequisitionLineModel(
                tenantId=tenantId,
                requisitionId=requisition.id,
                partId=line.partId,
                partCode=line.partCode,
                partName=line.partName,
                unit=line.unit,
                quantity=line.quantity,
                estimatedUnitCost=line.estimatedUnitCost,
                preferredSupplierId=supplierId,
                note=line.note[:500],
            )
            for line in lines
        ]
    )
    return CreatedRequisition(
        requisitionId=requisition.id,
        number=requisition.number,
        lineCount=len(lines),
        priority=priority,
        totalEstimated=total,
    )
