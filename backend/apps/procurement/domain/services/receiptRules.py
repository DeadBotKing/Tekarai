"""Quantity rules that decide whether a delivery may touch stock.

Deliberately free of Django and DRF so the arithmetic can be exercised
without a database. A goods receipt is the moment a purchase turns into
inventory and into cost, so it is the one place in procurement where a wrong
number is expensive: over-receiving inflates `quantityOnHand`, inflates the
part's cost basis, and closes a purchase order that was never fully
delivered. Every refusal below describes what the user must change.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from apps.sharedKernel.domain.errors import DomainError

ZERO = Decimal("0")

#: Purchase order states that may still take a delivery.
RECEIVABLE_ORDER_STATUSES = frozenset({"draft", "submitted", "approved", "partiallyReceived"})


class ReceiptQuantityError(DomainError):
    """A receipt that must not be posted (422, message shown to the user).

    Subclasses the shared domain error on purpose: the API exception handler
    passes its ``message`` straight into the error envelope, while a DRF
    ``ValidationError`` is flattened to a generic "Validation failed." and the
    user would be told only that something went wrong.
    """


def asQuantity(value: object, label: str) -> Decimal:
    """Parse a wire value as a quantity, refusing anything non-numeric."""
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ReceiptQuantityError(f"{label} عددی نیست.") from error
    if quantity.is_nan() or quantity.is_infinite():
        raise ReceiptQuantityError(f"{label} عددی نیست.")
    return quantity


def formatQuantity(value: Decimal) -> str:
    """Render a quantity without trailing zeros: 3.000 reads as 3."""
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        normalized = normalized.quantize(Decimal("1"))
    return format(normalized, "f")


def acceptedQuantity(quantity: Decimal, rejectedQuantity: Decimal, label: str) -> Decimal:
    """The part of a delivery that actually enters stock.

    Rejected goods are recorded on the receipt line but never added to
    inventory — they are going back to the supplier.
    """
    if quantity <= ZERO:
        raise ReceiptQuantityError(f"مقدار دریافتی «{label}» باید بزرگ‌تر از صفر باشد.")
    if rejectedQuantity < ZERO:
        raise ReceiptQuantityError(f"مقدار مردودی «{label}» نمی‌تواند منفی باشد.")
    if rejectedQuantity > quantity:
        raise ReceiptQuantityError(
            f"مقدار مردودی «{label}» ({formatQuantity(rejectedQuantity)}) "
            f"از مقدار دریافتی ({formatQuantity(quantity)}) بیشتر است."
        )
    return quantity - rejectedQuantity


def remainingQuantity(
    orderedQuantity: Decimal,
    receivedQuantity: Decimal,
    pendingQuantity: Decimal = ZERO,
) -> Decimal:
    """What is still owed on a purchase order line, never below zero.

    `pendingQuantity` covers earlier lines of the *same* receipt that point at
    this order line: each would pass on its own, yet together they overshoot.
    """
    return max(ZERO, orderedQuantity - receivedQuantity - pendingQuantity)


def guardReceiptLine(
    label: str,
    orderedQuantity: Decimal,
    receivedQuantity: Decimal,
    pendingQuantity: Decimal,
    quantity: Decimal,
    rejectedQuantity: Decimal,
) -> Decimal:
    """Validate one receipt line and return the quantity entering stock."""
    accepted = acceptedQuantity(quantity, rejectedQuantity, label)
    remaining = remainingQuantity(orderedQuantity, receivedQuantity, pendingQuantity)
    if remaining <= ZERO:
        raise ReceiptQuantityError(
            f"«{label}» پیش از این به‌طور کامل تحویل شده است؛ باقیماندهٔ سفارش صفر است."
        )
    if accepted > remaining:
        raise ReceiptQuantityError(
            f"مقدار پذیرفته‌شدهٔ «{label}» ({formatQuantity(accepted)}) "
            f"از باقیماندهٔ سفارش ({formatQuantity(remaining)}) بیشتر است."
        )
    return accepted


def guardOrderAcceptsDelivery(orderStatus: str, orderNumber: str) -> None:
    """A cancelled or already-closed order must not pull goods into stock."""
    if orderStatus not in RECEIVABLE_ORDER_STATUSES:
        raise ReceiptQuantityError(
            f"سفارش خرید «{orderNumber}» در وضعیت «{orderStatus}» است و رسید نمی‌پذیرد."
        )
