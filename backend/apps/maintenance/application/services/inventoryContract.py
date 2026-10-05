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
