"""Work timer — the stopwatch a technician runs on a work order.

Why an entity and not two timestamps on the work order: several technicians
may work the same order at the same time, a technician may work an order in
several spans across a shift, and each span must survive as evidence even
after it has been converted into a labour entry. The invariants below are the
ones that protect the cost report from fiction.

Time rules (BR-WO-TIME):

* a span cannot end before it started;
* a span cannot start in the future (beyond a small clock-skew allowance) —
  an offline phone with a wrong clock must not invent work that has not
  happened yet;
* a span longer than :data:`MAX_SPAN_HOURS` is refused: it is almost always a
  technician who forgot to press stop, and silently billing 40 hours of
  labour is worse than refusing the stop and asking for a manual entry;
* the measured duration is rounded to 1/100 of an hour (36 seconds), the same
  scale the labour entry stores, so hours never drift between the two tables.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from apps.maintenance.domain.exceptions.fieldOpsErrors import (
    TimerAlreadyRunningError,
    TimerNotRunningError,
    TimerSpanInvalidError,
)

#: A stop is refused beyond this span — a forgotten stopwatch, not real work.
MAX_SPAN_HOURS = Decimal("24")

#: Phones drift. Accept a start/stop stamped slightly in the future.
CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)

#: Hours are stored at 1/100 (36 seconds) — the labour entry's own scale.
HOURS_QUANTUM = Decimal("0.01")

#: A span shorter than this still bills one quantum: pressing start/stop
#: within a few seconds is a mis-tap, but a 30-second genuine check should
#: not round away to zero and fail the «hours > 0» database check.
MINIMUM_BILLABLE_HOURS = Decimal("0.01")


def quantiseHours(seconds: Decimal | int | float) -> Decimal:
    """Seconds → billable hours at the labour-entry scale (never zero)."""
    total = Decimal(str(seconds)) / Decimal("3600")
    rounded = total.quantize(HOURS_QUANTUM, rounding=ROUND_HALF_UP)
    return max(rounded, MINIMUM_BILLABLE_HOURS)


@dataclass
class WorkTimer:
    """One technician's span of work on one order."""

    id: uuid.UUID
    tenantId: uuid.UUID
    workOrderId: uuid.UUID
    technicianName: str
    startedAt: datetime
    endedAt: datetime | None = None
    pausedSeconds: int = 0
    hourlyRate: Decimal = Decimal("0")
    startNote: str = ""
    endNote: str = ""
    labourEntryId: uuid.UUID | None = None
    capturedOffline: bool = False
    startedVia: str = "online"
    technicianUserId: uuid.UUID | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None
    events: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    # -- queries ---------------------------------------------------------------
    @property
    def isRunning(self) -> bool:
        return self.endedAt is None

    def elapsedSeconds(self, asOf: datetime) -> int:
        """Seconds of work so far, excluding paused time, never negative."""
        end = self.endedAt or asOf
        raw = int((end - self.startedAt).total_seconds()) - int(self.pausedSeconds)
        return max(raw, 0)

    def billableHours(self, asOf: datetime) -> Decimal:
        return quantiseHours(self.elapsedSeconds(asOf))

    # -- behaviour -------------------------------------------------------------
    @staticmethod
    def start(
        *,
        tenantId: uuid.UUID,
        workOrderId: uuid.UUID,
        technicianName: str,
        startedAt: datetime,
        now: datetime,
        hourlyRate: Decimal = Decimal("0"),
        note: str = "",
        capturedOffline: bool = False,
        technicianUserId: uuid.UUID | None = None,
        timerId: uuid.UUID | None = None,
    ) -> WorkTimer:
        if startedAt > now + CLOCK_SKEW_TOLERANCE:
            raise TimerSpanInvalidError(
                "A work timer cannot start in the future.",
                fieldErrors={"startedAt": "future"},
            )
        timer = WorkTimer(
            id=timerId or uuid.uuid4(),
            tenantId=tenantId,
            workOrderId=workOrderId,
            technicianName=technicianName.strip(),
            startedAt=startedAt,
            hourlyRate=hourlyRate,
            startNote=note.strip()[:500],
            capturedOffline=capturedOffline,
            startedVia="offline" if capturedOffline else "online",
            technicianUserId=technicianUserId,
        )
        timer.events.append(
            (
                "workTimerStarted",
                {
                    "timerId": str(timer.id),
                    "workOrderId": str(workOrderId),
                    "technicianName": timer.technicianName,
                    "startedAt": startedAt.isoformat(),
                    "capturedOffline": capturedOffline,
                },
            )
        )
        return timer

    def stop(self, endedAt: datetime, now: datetime, note: str = "") -> Decimal:
        """Close the span and return the billable hours it produced."""
        if not self.isRunning:
            raise TimerNotRunningError(
                "This work timer has already been stopped.",
                fieldErrors={"timerId": str(self.id)},
            )
        if endedAt > now + CLOCK_SKEW_TOLERANCE:
            raise TimerSpanInvalidError(
                "A work timer cannot end in the future.",
                fieldErrors={"endedAt": "future"},
            )
        if endedAt < self.startedAt:
            raise TimerSpanInvalidError(
                "A work timer cannot end before it started.",
                fieldErrors={"endedAt": "beforeStart"},
            )
        spanSeconds = int((endedAt - self.startedAt).total_seconds())
        if Decimal(spanSeconds) / Decimal("3600") > MAX_SPAN_HOURS:
            raise TimerSpanInvalidError(
                "This timer has been running for more than 24 hours; stop it "
                "with a manual duration instead.",
                fieldErrors={"endedAt": "tooLong"},
            )
        if int(self.pausedSeconds) > spanSeconds:
            raise TimerSpanInvalidError(
                "Paused time cannot exceed the elapsed span.",
                fieldErrors={"pausedSeconds": "exceedsSpan"},
            )
        self.endedAt = endedAt
        self.endNote = note.strip()[:500]
        self.updatedAt = now
        hours = self.billableHours(now)
        self.events.append(
            (
                "workTimerStopped",
                {
                    "timerId": str(self.id),
                    "workOrderId": str(self.workOrderId),
                    "technicianName": self.technicianName,
                    "startedAt": self.startedAt.isoformat(),
                    "endedAt": endedAt.isoformat(),
                    "hours": str(hours),
                },
            )
        )
        return hours

    def attachLabourEntry(self, labourEntryId: uuid.UUID) -> None:
        self.labourEntryId = labourEntryId

    def ensureStartable(self, running: WorkTimer | None) -> None:
        """Guard used by the repository layer before inserting a new span."""
        if running is not None and running.isRunning:
            raise TimerAlreadyRunningError(
                "This technician already has a running timer on this order.",
                fieldErrors={"timerId": str(running.id)},
            )

    def snapshot(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "workOrderId": str(self.workOrderId),
            "technicianName": self.technicianName,
            "startedAt": self.startedAt.isoformat(),
            "endedAt": self.endedAt.isoformat() if self.endedAt else "",
            "hourlyRate": str(self.hourlyRate),
            "capturedOffline": self.capturedOffline,
        }
