"""Domain entities — رزرو قطعات و چک‌لیست‌های بازرسی تیمی."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PartReservation:
    id: str
    tenantId: uuid.UUID
    workOrderId: uuid.UUID
    partCode: str
    quantity: Decimal
    status: str  # active / consumed / released
    reservedByName: str
    createdAt: str
    closedAt: str = ""


@dataclass(frozen=True)
class InspectionTemplate:
    id: str
    tenantId: uuid.UUID
    name: str
    description: str
    deviceCode: str
    checks: tuple[str, ...]
    isCommitted: bool


@dataclass(frozen=True)
class InspectionRecord:
    id: str
    tenantId: uuid.UUID
    templateId: str
    workOrderId: uuid.UUID
    deviceId: uuid.UUID
    passedChecks: tuple[str, ...]
    failedChecks: tuple[str, ...]
    performedByName: str
    createdAt: str
