"""Spare-parts inventory records for the maintenance bounded context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class SparePart:
    id: uuid.UUID
    tenantId: uuid.UUID
    code: str
    name: str
    unit: str
    quantityOnHand: Decimal
    minimumStock: Decimal
    unitCost: Decimal
    createdAt: datetime
    updatedAt: datetime | None = None
    #: How much to buy when the part trips its minimum. Zero means "not
    #: configured" — the reorder policy then tops up to twice the minimum.
    reorderQuantity: Decimal = Decimal("0")
    #: False excludes the part from automatic purchase suggestions. The
    #: low-stock alert still fires; only the buying proposal is suppressed.
    autoReorder: bool = True

    @property
    def lowStock(self) -> bool:
        return self.quantityOnHand <= self.minimumStock


@dataclass(frozen=True)
class WorkOrderPartUsage:
    id: uuid.UUID
    tenantId: uuid.UUID
    workOrderId: uuid.UUID
    partId: uuid.UUID
    partCode: str
    partName: str
    unit: str
    quantity: Decimal
    unitCost: Decimal
    note: str
    consumedAt: datetime

    @property
    def totalCost(self) -> Decimal:
        """Cost of this consumption — quantity × the price captured at issue time."""
        return (self.quantity * self.unitCost).quantize(Decimal("0.01"))


# --- Part transaction ledger (دفتر تراکنش انبار) ---------------------------
PART_TRANSACTION_RECEIPT = "RECEIPT"  # رسید — ورود کالا
PART_TRANSACTION_ISSUE = "ISSUE"  # حواله — خروج کالا
PART_TRANSACTION_RETURN = "RETURN"  # برگشت — بازگشت کالا
PART_TRANSACTION_ADJUSTMENT = "ADJUSTMENT"  # تعدیل / انبارگردانی (علامت‌دار)
PART_TRANSACTION_TYPES = (
    PART_TRANSACTION_RECEIPT,
    PART_TRANSACTION_ISSUE,
    PART_TRANSACTION_RETURN,
    PART_TRANSACTION_ADJUSTMENT,
)


@dataclass(frozen=True)
class PartTransaction:
    """Immutable ledger row — مقدار ``quantity`` علامت‌دار است.

    RECEIPT/RETURN همیشه مثبت، ISSUE همیشه منفی و ADJUSTMENT علامت‌دار.
    ``balanceAfter`` موجودی لحظه‌ی بعد از ثبت تراکنش است تا دفتر بدون محاسبه‌ی
    مجدد قابل خواندن باشد.
    """

    id: uuid.UUID
    tenantId: uuid.UUID
    partId: uuid.UUID
    partCode: str
    partName: str
    unit: str
    transactionType: str
    quantity: Decimal
    balanceAfter: Decimal
    note: str
    reference: str
    actorId: uuid.UUID | None
    createdAt: datetime
