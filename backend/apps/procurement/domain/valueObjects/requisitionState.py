"""Purchase requisition lifecycle vocabulary and the ageing thresholds.

The lifecycle used to stop at ``ordered``: raising a purchase order moved the
requisition there and nothing ever moved it on, so a requisition whose goods
had long since arrived was indistinguishable from one still waiting at the
supplier. ``purchased`` closes the loop — it is set when the purchase order
that fulfils the requisition is fully received.

Staleness mirrors the work-order SLA model (``SLA_HOURS_BY_PRIORITY``): the
waiting period a buyer is allowed before the request is escalated depends on
how urgent the requester said it was. Seven days is the ``normal`` case the
thresholds are built around.
"""

from __future__ import annotations

REQ_DRAFT = "draft"
REQ_SUBMITTED = "submitted"
REQ_APPROVED = "approved"
REQ_REJECTED = "rejected"
REQ_CANCELLED = "cancelled"
REQ_ORDERED = "ordered"
REQ_PURCHASED = "purchased"

REQUISITION_STATUSES = (
    REQ_DRAFT,
    REQ_SUBMITTED,
    REQ_APPROVED,
    REQ_REJECTED,
    REQ_CANCELLED,
    REQ_ORDERED,
    REQ_PURCHASED,
)

#: Statuses where the requester is still waiting for goods. These are the only
#: ones the staleness scan considers: a draft has not been handed over to
#: anybody yet, and the terminal three are nobody's outstanding work.
OPEN_REQUISITION_STATUSES = (REQ_SUBMITTED, REQ_APPROVED, REQ_ORDERED)

#: Nothing further is expected to happen to these.
TERMINAL_REQUISITION_STATUSES = (REQ_REJECTED, REQ_CANCELLED, REQ_PURCHASED)

#: Days a requisition may wait, from submission, before it is called stale.
#: Keyed by the requester's stated priority.
STALE_DAYS_BY_PRIORITY: dict[str, int] = {
    "critical": 2,
    "high": 4,
    "normal": 7,
    "low": 14,
}

#: Applied when a row carries a priority outside the table above. Old rows and
#: imports do turn up with unexpected values, and an alert scan must never
#: crash on one.
DEFAULT_STALE_DAYS = 7


def staleThresholdDaysFor(priority: str) -> int:
    """Waiting days allowed for ``priority`` before escalation."""
    return STALE_DAYS_BY_PRIORITY.get(priority, DEFAULT_STALE_DAYS)
