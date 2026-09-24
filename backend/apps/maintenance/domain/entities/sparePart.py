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
    createdAt: datetime
    updatedAt: datetime | None = None

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
    note: str
    consumedAt: datetime
