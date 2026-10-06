"""How long a purchase requisition has been waiting, and whether that is too long.

Pure domain rules — no ORM, no clock of its own. ``now`` is always passed in
so the API, the alert scan and the tests all agree on one answer, and so the
tests can age a requisition without sleeping.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.procurement.domain.valueObjects.requisitionState import (
    OPEN_REQUISITION_STATUSES,
    staleThresholdDaysFor,
)


@dataclass(frozen=True)
class RequisitionAging:
    """Ageing verdict for one requisition."""

    isOpen: bool
    isStale: bool
    daysWaiting: int
    thresholdDays: int
    #: Days past the threshold; 0 while still inside it. Drives "how badly
    #: late" ordering without the caller redoing the subtraction.
    daysOverdue: int


def evaluateRequisitionAging(
    *,
    status: str,
    priority: str,
    submittedAt: datetime | None,
    now: datetime,
) -> RequisitionAging:
    """Age ``submittedAt`` against the threshold for ``priority``.

    A requisition that was never submitted has no clock running: a draft
    sitting in someone's screen is not the buyer's overdue work, and the
    user asked for the week to start at submission. Terminal statuses are
    likewise never stale — the request already ended, well or badly.
    """
    thresholdDays = staleThresholdDaysFor(priority)
    isOpen = status in OPEN_REQUISITION_STATUSES

    if not isOpen or submittedAt is None:
        return RequisitionAging(
            isOpen=isOpen,
            isStale=False,
            daysWaiting=0,
            thresholdDays=thresholdDays,
            daysOverdue=0,
        )

    # Whole days only: a requisition submitted at 09:00 last Monday is "7
    # days old" all through this Monday, not 6 at breakfast and 7 by lunch.
    elapsedDays = max(0, (now - submittedAt).days)
    isStale = elapsedDays >= thresholdDays
    return RequisitionAging(
        isOpen=True,
        isStale=isStale,
        daysWaiting=elapsedDays,
        thresholdDays=thresholdDays,
        daysOverdue=max(0, elapsedDays - thresholdDays) if isStale else 0,
    )
