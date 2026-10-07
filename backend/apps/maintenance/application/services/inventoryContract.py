"""Public inventory contract for other bounded contexts (Phase 06 RULE E/F).

Procurement has to move spare-part stock when a goods receipt is posted or a
purchase return is sent back to the supplier. It used to do that by importing
``apps.maintenance.infrastructure.models`` directly and mutating
``SparePartModel`` rows by hand — a cross-context reach into another context's
infrastructure, which the architecture tests forbid (only ``.application`` is
public).

Besides the layering violation, the hand-rolled version had a real defect:

    part = SparePartModel.objects.get(...)
    part.quantityOnHand += accepted
    part.save(...)

That is a read-modify-write with no row lock. Two receipts posted for the same
part at the same moment both read the old balance and the second ``save``
silently discards the first one's quantity. The maintenance repository already
does this correctly — ``recordTransaction`` runs inside ``transaction.atomic``
with ``select_for_update`` — so routing through it fixes the race as well as
the dependency direction.

Quantities here are **signed**, matching the ledger: stock coming in is
positive, stock going back out to a supplier is negative.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from apps.maintenance.domain.entities.sparePart import (
    PART_TRANSACTION_RECEIPT,
    PART_TRANSACTION_RETURN,
)


def _repository():  # noqa: ANN202 - returns the context's SparePartRepository
    """Resolve this context's own composition root.

    Imported inside the function, exactly like the notification application
    services do, so the application layer keeps no import-time dependency on
    its own infrastructure.
    """
    from apps.maintenance.infrastructure.container import sparePartRepository

    return sparePartRepository()


def recordGoodsReceipt(
    *,
    tenantId: uuid.UUID,
    partId: uuid.UUID,
    quantity: Decimal,
    unitCost: Decimal | None,
    reference: str,
    note: str = "",
    actorId: uuid.UUID | None = None,
    at=None,
) -> None:
    """Add received stock to a part and append a RECEIPT row to the ledger.

    ``unitCost`` refreshes the part's carrying cost when supplied; passing
    ``None`` keeps the existing cost (a receipt without a priced line).
    """
    repository = _repository()
    moment = at or _now()
    repository.recordTransaction(
        tenantId,
        partId,
        PART_TRANSACTION_RECEIPT,
        abs(Decimal(quantity)),
        note,
        reference,
        actorId,
        moment,
    )
    if unitCost is not None:
        part = repository.getById(tenantId, partId)
        repository.update(
            tenantId,
            partId,
            part.name,
            part.unit,
            part.quantityOnHand,
            part.minimumStock,
            Decimal(unitCost),
        )


def recordSupplierReturn(
    *,
    tenantId: uuid.UUID,
    partId: uuid.UUID,
    quantity: Decimal,
    reference: str,
    note: str = "",
    actorId: uuid.UUID | None = None,
    at=None,
) -> None:
    """Remove returned stock from a part and append a RETURN row.

    Raises the repository's own insufficient-stock error when the balance
    cannot cover the return, so the caller no longer has to pre-check and
    then race against a concurrent issue.
    """
    repository = _repository()
    moment = at or _now()
    repository.recordTransaction(
        tenantId,
        partId,
        PART_TRANSACTION_RETURN,
        -abs(Decimal(quantity)),
        note,
        reference,
        actorId,
        moment,
    )


def _now():  # noqa: ANN202 - datetime, imported lazily to keep the module thin
    from datetime import UTC, datetime

    return datetime.now(UTC)


# --- Stock positions, for the procurement replenishment loop ---------------
#
# Procurement needs to know what is on the shelf and what each part's reorder
# policy says, so it can turn a shortage into a purchase request. It must not
# read ``SparePartModel`` to find out: that is this context's infrastructure,
# and the architecture rules make only ``.application`` public. The snapshot
# below is a plain value object — no ORM rows escape, and the shape procurement
# depends on is one this context controls.


@dataclass(frozen=True)
class StockPosition:
    """One spare part's stock level and its reorder policy."""

    partId: uuid.UUID
    code: str
    name: str
    unit: str
    quantityOnHand: Decimal
    minimumStock: Decimal
    reorderQuantity: Decimal
    autoReorder: bool
    #: Last price paid. The fallback estimate for a part with no supplier.
    unitCost: Decimal


def listStockPositions(tenantId: uuid.UUID) -> list[StockPosition]:
    """Every live spare part of one tenant, with its reorder settings.

    Soft-deleted parts are excluded by the repository, so a retired part is
    never proposed for purchase.
    """
    return [
        StockPosition(
            partId=part.id,
            code=part.code,
            name=part.name,
            unit=part.unit,
            quantityOnHand=Decimal(part.quantityOnHand),
            minimumStock=Decimal(part.minimumStock),
            reorderQuantity=Decimal(part.reorderQuantity),
            autoReorder=bool(part.autoReorder),
            unitCost=Decimal(part.unitCost),
        )
        for part in _repository().list(tenantId)
    ]


def tenantIdsWithStock() -> list[uuid.UUID]:
    """Every tenant holding at least one live spare part.

    Exposed here rather than queried by procurement because the spare-part
    table belongs to this context. ``order_by()`` is load-bearing: the
    model's ``Meta.ordering`` columns join a DISTINCT select, which would
    return one row per part instead of one per tenant — so a scheduled scan
    would run 50 times over a 50-part warehouse.
    """
    from apps.maintenance.infrastructure.models import SparePartModel

    return list(
        SparePartModel.objects.filter(deletedAt__isnull=True)
        .order_by()
        .values_list("tenantId", flat=True)
        .distinct()
    )
