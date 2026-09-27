"""Technician labour time entries logged against a work order (Phase 26 time & cost).

A labour entry is one chunk of work — "۲ ساعت باز و بست کوپلینگ توسط حسینی" —
with the hourly rate that was in effect when the work was logged. Rates are
captured per entry on purpose: a technician's rate changes over time, so the
historical cost of a work order must never be recomputed from today's rate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class LabourEntry:
    id: uuid.UUID
    tenantId: uuid.UUID
    workOrderId: uuid.UUID
    technicianName: str
    hours: Decimal
    hourlyRate: Decimal
    workedAt: datetime
    note: str
    createdAt: datetime

    @property
    def totalCost(self) -> Decimal:
        """Cost of this entry — hours × the rate captured at logging time."""
        return (self.hours * self.hourlyRate).quantize(Decimal("0.01"))
