"""When a spare part needs buying, and how much of it to buy.

Pure domain rules: no ORM, no clock, no settings. Everything the decision
needs is passed in, so the preview endpoint, the scheduled scan and the
tests all reach the same verdict from the same numbers.

The warehouse already knew a part was below its minimum — ``SparePart.lowStock``
and the ``sparePartLowStock`` alert have said so for a long time. What was
missing was the other half of the sentence: *therefore order this much from
this supplier*. That is what lives here.

Three rules carry all the weight:

1. **Count what is already coming.** The trigger is net available stock —
   what is on the shelf *plus* what is already on an open requisition or an
   unreceived purchase order — never the shelf alone. A scan that ignores
   goods in transit raises a fresh request every single night for the same
   part until it arrives, which is the classic way this feature becomes a
   spam generator and gets switched off. Because the requisition this scan
   creates immediately counts as incoming, re-running the scan a minute
   later proposes nothing: the loop is idempotent by arithmetic rather than
   by a deduplication key.

2. **Order up to a target, not by a fixed lump.** Topping up by exactly the
   shortfall leaves the part sitting on its reorder point, where the very
   next issue trips the alert again. The target is ``reorderPoint +
   reorderQuantity`` — the classic min/max model — so a replenished part
   lands comfortably above the line.

3. **Respect what the supplier will actually sell.** A computed need of 3
   when the supplier's ``minimumOrderQty`` is 10 is not an order anybody can
   place, so the quantity is raised to the minimum.

``reorderQuantity`` is optional. A warehouse that has never filled it in
still gets a working loop: the quantity falls back to the reorder point
itself, which makes the target twice the minimum — a defensible default and,
more importantly, one that does not require a data-entry project before the
feature does anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

#: Quantities are stored as ``DecimalField(decimal_places=3)`` throughout the
#: warehouse and procurement tables. Rounding to the same precision here keeps
#: a suggested quantity from being rejected by the database it is headed for.
QUANTITY_STEP = Decimal("0.001")

#: Priority stamped on a generated requisition. These are the values the
#: requisition staleness thresholds are keyed by (critical 2 days, high 4,
#: normal 7), so an urgent replenishment is also chased up sooner — the two
#: features agree without either knowing about the other.
URGENCY_CRITICAL = "critical"
URGENCY_HIGH = "high"
URGENCY_NORMAL = "normal"


@dataclass(frozen=True)
class ReorderVerdict:
    """Whether one part needs ordering, how much, and why."""

    shouldOrder: bool
    #: On-hand plus everything already on order. The number the decision is
    #: actually made on.
    netAvailable: Decimal
    #: The level that triggers an order (the part's minimum stock).
    reorderPoint: Decimal
    #: The level an order is meant to restore the part to.
    targetLevel: Decimal
    #: How far below the reorder point the net position is; 0 when healthy.
    shortfall: Decimal
    #: What to buy, after the target top-up and the supplier's minimum.
    suggestedQuantity: Decimal
    #: Quantity already inbound, broken out so the UI can explain itself.
    onOrderQuantity: Decimal
    #: ``critical`` / ``high`` / ``normal`` — see the constants above.
    urgency: str
    #: Short Persian sentence naming the reason. Shown in the suggestion
    #: list and copied onto the requisition line, so the buyer is never
    #: looking at a number with no provenance.
    reason: str


def _quantize(value: Decimal) -> Decimal:
    """Round *up* to the stored precision.

    Up, not nearest: rounding a need of 0.4 down to 0 would propose an order
    for nothing, and the scan would then repeat that non-decision forever.
    """
    return value.quantize(QUANTITY_STEP, rounding=ROUND_CEILING)


def _urgencyFor(netAvailable: Decimal, reorderPoint: Decimal) -> str:
    """How badly this part is needed.

    Out of stock outranks everything: a part at zero is stopping work right
    now, whatever its minimum says. Below half the minimum is the warning
    band. Anything else is routine topping-up.
    """
    if netAvailable <= 0:
        return URGENCY_CRITICAL
    if reorderPoint > 0 and netAvailable * 2 <= reorderPoint:
        return URGENCY_HIGH
    return URGENCY_NORMAL


def _reasonFor(urgency: str, netAvailable: Decimal, reorderPoint: Decimal, unit: str) -> str:
    if urgency == URGENCY_CRITICAL:
        return "موجودی قابل‌استفاده صفر است"
    return f"موجودی خالص {netAvailable:g} {unit} / حداقل {reorderPoint:g} {unit}".strip()


def evaluateReorder(
    *,
    quantityOnHand: Decimal,
    minimumStock: Decimal,
    reorderQuantity: Decimal = Decimal("0"),
    onOrderQuantity: Decimal = Decimal("0"),
    supplierMinimumOrderQty: Decimal = Decimal("0"),
    unit: str = "",
    autoReorder: bool = True,
) -> ReorderVerdict:
    """Decide whether to buy this part, and how much.

    ``autoReorder=False`` is an explicit opt-out for parts the warehouse
    never wants proposed automatically — items bought against a project,
    obsolete stock being run down, anything consigned. The verdict is still
    returned with its numbers filled in so the caller can display the
    position; only ``shouldOrder`` is forced false.
    """
    onHand = Decimal(quantityOnHand or 0)
    reorderPoint = max(Decimal("0"), Decimal(minimumStock or 0))
    onOrder = max(Decimal("0"), Decimal(onOrderQuantity or 0))
    netAvailable = onHand + onOrder

    # An unset reorder quantity means "top up to twice the minimum". See the
    # module docstring: the alternative is a feature that does nothing until
    # somebody edits every part.
    topUp = Decimal(reorderQuantity or 0)
    if topUp <= 0:
        topUp = reorderPoint
    targetLevel = reorderPoint + topUp

    # `<=` deliberately, matching SparePart.lowStock: a part sitting exactly
    # on its minimum is already a problem, and the two features must not
    # disagree about which parts are in trouble.
    needed = netAvailable <= reorderPoint
    shortfall = max(Decimal("0"), reorderPoint - netAvailable)

    if not needed:
        return ReorderVerdict(
            shouldOrder=False,
            netAvailable=netAvailable,
            reorderPoint=reorderPoint,
            targetLevel=targetLevel,
            shortfall=Decimal("0"),
            suggestedQuantity=Decimal("0"),
            onOrderQuantity=onOrder,
            urgency=URGENCY_NORMAL,
            reason="موجودی کافی است",
        )

    quantity = max(Decimal("0"), targetLevel - netAvailable)
    moq = max(Decimal("0"), Decimal(supplierMinimumOrderQty or 0))
    if moq > 0:
        quantity = max(quantity, moq)
    quantity = _quantize(quantity)

    urgency = _urgencyFor(netAvailable, reorderPoint)

    if not autoReorder:
        return ReorderVerdict(
            shouldOrder=False,
            netAvailable=netAvailable,
            reorderPoint=reorderPoint,
            targetLevel=targetLevel,
            shortfall=shortfall,
            suggestedQuantity=Decimal("0"),
            onOrderQuantity=onOrder,
            urgency=urgency,
            reason="تأمین خودکار برای این قطعه خاموش است",
        )

    # Degenerate but reachable: minimum 0, nothing on hand, no reorder
    # quantity. There is no number to order, so propose nothing rather than
    # a zero-quantity line the database would reject.
    if quantity <= 0:
        return ReorderVerdict(
            shouldOrder=False,
            netAvailable=netAvailable,
            reorderPoint=reorderPoint,
            targetLevel=targetLevel,
            shortfall=shortfall,
            suggestedQuantity=Decimal("0"),
            onOrderQuantity=onOrder,
            urgency=urgency,
            reason="مقدار سفارش تعیین نشده است",
        )

    return ReorderVerdict(
        shouldOrder=True,
        netAvailable=netAvailable,
        reorderPoint=reorderPoint,
        targetLevel=targetLevel,
        shortfall=shortfall,
        suggestedQuantity=quantity,
        onOrderQuantity=onOrder,
        urgency=urgency,
        reason=_reasonFor(urgency, netAvailable, reorderPoint, unit),
    )
