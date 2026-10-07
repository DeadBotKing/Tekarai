"""The stock→purchase loop: turn low stock into actual purchase requests.

Everything either side of this module already existed. The warehouse knew
which parts were below minimum; ``SupplierPart`` knew who sells each one, at
what price, with what lead time and minimum order quantity; the requisition
→ order → receipt chain knew how to buy things. Nothing joined them, so a
low-stock alert ended as a notification somebody had to act on by hand,
re-keying numbers the system already held.

This scan closes the loop:

    موجودی زیر حداقل  →  پیشنهاد خرید  →  درخواست خرید پیش‌نویس
                                              ↓
                              (زنجیره‌ی موجود: تأیید → سفارش → رسید)

Two decisions shape the whole module.

**Drafts, not submitted requests.** The scan creates requisitions in
``draft``. A machine may notice the need; a person still decides to spend
the money, and the approval chain starts where it always did. It also means
the staleness clock — which starts at ``submittedAt`` — is not started by a
robot, so generated requests do not appear in the buyer's overdue list
before any human has seen them.

**One requisition per supplier, not per part.** Ten parts from one supplier
is one conversation and one purchase order, not ten. Parts with no supplier
on file are grouped into a single unassigned requisition so they stay
visible rather than being silently dropped.

Idempotency is arithmetic, not bookkeeping: see ``reorderPolicy``. Because a
freshly created draft counts as quantity on order, running the scan twice in
a row proposes nothing the second time, with no deduplication key to keep in
sync.

Layering: this module holds the decisions only. Stock comes from the
maintenance context's public inventory contract and all SQL lives in
``infrastructure/replenishmentRepository`` — the application layer may not
import the ORM (DependencyRules §3).
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from apps.maintenance.application.services.inventoryContract import (
    StockPosition,
    listStockPositions,
)
from apps.procurement.domain.services.reorderPolicy import ReorderVerdict, evaluateReorder
from apps.procurement.infrastructure.replenishmentRepository import (
    CreatedRequisition,
    RequisitionLineSpec,
    SupplierOffer,
    createDraftRequisition,
    quantitiesOnOrder,
    supplierOffersByPart,
)
from apps.sharedKernel.domain.events import DomainEvent
from apps.sharedKernel.infrastructure.wiring import defaultEventDispatcher

logger = logging.getLogger(__name__)

#: Event name routed in ``NOTIFICATION_EVENT_ROUTES``.
REPLENISHMENT_EVENT = "replenishmentRequisitionRaised"

#: Marks the requisitions this scan generated, so they can be told apart from
#: hand-raised ones in the list and in reporting.
GENERATED_JUSTIFICATION = "تولیدشده توسط تأمین خودکار انبار"

#: Worst first, so the buyer reading the list top-down meets the stockouts
#: before the routine top-ups.
URGENCY_RANK = {"critical": 0, "high": 1, "normal": 2}


@dataclass(frozen=True)
class ReplenishmentSuggestionDto:
    """One proposed purchase, with the evidence behind it."""

    partId: str
    partCode: str
    partName: str
    unit: str
    quantityOnHand: str
    minimumStock: str
    onOrderQuantity: str
    netAvailable: str
    suggestedQuantity: str
    estimatedUnitCost: str
    estimatedTotal: str
    urgency: str
    reason: str
    supplierId: str | None
    supplierName: str
    leadTimeDays: int


@dataclass(frozen=True)
class ReplenishmentScanDto:
    asOf: str
    suggestions: list[ReplenishmentSuggestionDto] = field(default_factory=list)
    #: Requisition numbers created by this run. Empty on a preview.
    createdRequisitions: list[str] = field(default_factory=list)
    createdRequisitionIds: list[str] = field(default_factory=list)
    #: Parts that are below minimum but were skipped, with the reason — a
    #: preview that silently omits them looks like the scan missed them.
    skipped: list[dict] = field(default_factory=list)

    @property
    def suggestedCount(self) -> int:
        return len(self.suggestions)

    @property
    def estimatedTotal(self) -> Decimal:
        return sum((Decimal(x.estimatedTotal) for x in self.suggestions), Decimal("0"))


def _bestOffer(offers: list[SupplierOffer]) -> SupplierOffer | None:
    """Who to buy this part from.

    The flagged preferred supplier wins. Failing that, the cheapest quote —
    a defensible automatic choice, and the buyer can always change it on the
    draft. Ties break on the shorter lead time, because when the price is
    the same the part that arrives sooner is strictly better.
    """
    if not offers:
        return None
    preferred = [x for x in offers if x.isPreferred]
    pool = preferred or offers
    return sorted(pool, key=lambda x: (x.unitPrice, x.leadTimeDays))[0]


def _suggestionFor(
    part: StockPosition, verdict: ReorderVerdict, offer: SupplierOffer | None
) -> ReplenishmentSuggestionDto:
    # The supplier's quote is the better price when there is one; the part's
    # own unitCost is the last price paid, which is the right fallback for a
    # part nobody has linked to a supplier yet.
    unitCost = offer.unitPrice if offer and offer.unitPrice > 0 else part.unitCost
    return ReplenishmentSuggestionDto(
        partId=str(part.partId),
        partCode=part.code,
        partName=part.name,
        unit=part.unit,
        quantityOnHand=str(part.quantityOnHand),
        minimumStock=str(part.minimumStock),
        onOrderQuantity=str(verdict.onOrderQuantity),
        netAvailable=str(verdict.netAvailable),
        suggestedQuantity=str(verdict.suggestedQuantity),
        estimatedUnitCost=str(unitCost),
        estimatedTotal=str((verdict.suggestedQuantity * unitCost).quantize(Decimal("0.01"))),
        urgency=verdict.urgency,
        reason=verdict.reason,
        supplierId=str(offer.supplierId) if offer else None,
        supplierName=offer.supplierName if offer else "",
        leadTimeDays=offer.leadTimeDays if offer else 0,
    )


def scanReplenishment(
    tenantId: uuid.UUID,
    *,
    now: datetime | None = None,
    apply: bool = False,
    actorId: uuid.UUID | None = None,
    actorName: str = "",
) -> ReplenishmentScanDto:
    """Work out what needs buying; optionally raise the draft requisitions.

    ``apply=False`` is the preview the UI loads and the dry run the cron job
    defaults to. ``apply=True`` is the only path that writes.
    """
    now = now or timezone.now()
    onOrder = quantitiesOnOrder(tenantId)
    offersByPart = supplierOffersByPart(tenantId)

    suggestions: list[ReplenishmentSuggestionDto] = []
    skipped: list[dict] = []

    for part in listStockPositions(tenantId):
        offer = _bestOffer(offersByPart.get(part.partId, []))
        verdict = evaluateReorder(
            quantityOnHand=part.quantityOnHand,
            minimumStock=part.minimumStock,
            reorderQuantity=part.reorderQuantity,
            onOrderQuantity=onOrder.get(part.partId, Decimal("0")),
            supplierMinimumOrderQty=offer.minimumOrderQty if offer else Decimal("0"),
            unit=part.unit,
            autoReorder=part.autoReorder,
        )

        if not verdict.shouldOrder:
            # Only report a skip for parts somebody would expect to see. A
            # part comfortably in stock is not a skip, it is just fine.
            if verdict.netAvailable <= verdict.reorderPoint:
                skipped.append(
                    {
                        "partId": str(part.partId),
                        "partCode": part.code,
                        "partName": part.name,
                        "reason": verdict.reason,
                    }
                )
            continue

        suggestions.append(_suggestionFor(part, verdict, offer))

    suggestions.sort(key=lambda x: (URGENCY_RANK.get(x.urgency, 3), x.partCode))

    result = ReplenishmentScanDto(
        asOf=now.date().isoformat(), suggestions=suggestions, skipped=skipped
    )
    if not apply or not suggestions:
        return result

    created = _raiseRequisitions(
        tenantId, suggestions, now=now, actorId=actorId, actorName=actorName
    )
    return ReplenishmentScanDto(
        asOf=result.asOf,
        suggestions=suggestions,
        skipped=skipped,
        createdRequisitions=[x.number for x in created],
        createdRequisitionIds=[str(x.requisitionId) for x in created],
    )


def _raiseRequisitions(
    tenantId: uuid.UUID,
    suggestions: list[ReplenishmentSuggestionDto],
    *,
    now: datetime,
    actorId: uuid.UUID | None,
    actorName: str,
) -> list[CreatedRequisition]:
    """One draft requisition per supplier, each carrying that supplier's lines."""
    bySupplier: dict[str | None, list[ReplenishmentSuggestionDto]] = defaultdict(list)
    for item in suggestions:
        bySupplier[item.supplierId].append(item)

    created: list[CreatedRequisition] = []
    for supplierId, items in bySupplier.items():
        # The requisition inherits the most urgent line's priority, which is
        # what decides its staleness threshold. Mixing a stockout into a
        # routine order must not slow the stockout down.
        priority = sorted(items, key=lambda x: URGENCY_RANK.get(x.urgency, 3))[0].urgency
        created.append(
            createDraftRequisition(
                tenantId,
                supplierId=uuid.UUID(supplierId) if supplierId else None,
                priority=priority,
                justification=GENERATED_JUSTIFICATION,
                requesterId=actorId,
                requesterName=actorName or "تأمین خودکار",
                now=now,
                lines=[
                    RequisitionLineSpec(
                        partId=uuid.UUID(item.partId),
                        partCode=item.partCode,
                        partName=item.partName,
                        unit=item.unit,
                        quantity=Decimal(item.suggestedQuantity),
                        estimatedUnitCost=Decimal(item.estimatedUnitCost),
                        # The reason travels with the line so the approver
                        # sees why this quantity, without opening the
                        # warehouse screen.
                        note=item.reason,
                    )
                    for item in items
                ],
            )
        )

    _announce(tenantId, created, now=now)
    return created


def _announce(
    tenantId: uuid.UUID, created: list[CreatedRequisition], *, now: datetime
) -> None:
    """Tell the buyers that drafts are waiting for them.

    Failure to notify must not undo requisitions that were correctly
    created — the purchase request is the valuable artefact and it is on the
    buyer's screen either way, so a broken dispatcher is logged, not raised.
    """
    if not created:
        return
    try:
        dispatcher = defaultEventDispatcher()
        for requisition in created:
            dispatcher.dispatch(
                DomainEvent(
                    name=REPLENISHMENT_EVENT,
                    occurredAt=now,
                    tenantId=tenantId,
                    payload={
                        "eventId": f"{REPLENISHMENT_EVENT}:{requisition.requisitionId}",
                        "sourceId": str(requisition.requisitionId),
                        "requisitionId": str(requisition.requisitionId),
                        "requisitionNumber": requisition.number,
                        "priority": requisition.priority,
                        "lineCount": requisition.lineCount,
                        "totalEstimated": str(requisition.totalEstimated),
                    },
                )
            )
    except Exception:  # noqa: BLE001 — notification is best-effort, see docstring
        logger.exception(
            "Replenishment requisitions were created but could not be announced",
            extra={"tenantId": str(tenantId), "count": len(created)},
        )
