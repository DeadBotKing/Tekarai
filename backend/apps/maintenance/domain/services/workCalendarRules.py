"""Work calendar arithmetic (تقویم کاری، شیفت و ظرفیت) — Phase 28.

Pure functions. No ORM, no Django, no clock: every answer is derived from the
arguments so the whole module is testable without a database and gives the same
answer in a test, a task queue and a request.

The problem this solves is that a Jalali date picker tells you how to *write* a
date, not whether anyone is at work on it. Scheduling needs:

* which weekdays a site works,
* which of those are holidays,
* which shifts cover the working day and how many people they carry,
* and what to do with a PM that lands on a day nobody is there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from apps.maintenance.domain.valueObjects.maintenanceState import (
    DEFAULT_WEEKEND_DAYS,
    MAX_ROLL_DAYS,
    ROLL_BACKWARD,
    ROLL_FORWARD,
    ROLL_NONE,
)

# A day is 24 hours; used to close a shift that runs past midnight.
_DAY = timedelta(days=1)


# =================================================================================
# Working days
# =================================================================================


def normaliseWeekendDays(days: object) -> tuple[int, ...]:
    """Coerce stored weekend days into a clean, ordered tuple of 0-6.

    Weekend days arrive from a CSV column, a JSON body or a test as strings,
    ints, None or junk. Everything outside 0-6 is dropped rather than raising:
    a malformed row should degrade to "this day is not a weekend", never take
    the schedule down.
    """
    if days is None:
        return ()
    if isinstance(days, str):
        parts: list[str] = [part.strip() for part in days.split(",")]
    elif isinstance(days, (list, tuple, set, frozenset)):
        parts = [str(part).strip() for part in days]
    else:
        return ()
    out: set[int] = set()
    for part in parts:
        if not part:
            continue
        try:
            value = int(part)
        except (TypeError, ValueError):
            continue
        if 0 <= value <= 6:
            out.add(value)
    return tuple(sorted(out))


@dataclass(frozen=True)
class CalendarSpec:
    """Everything the arithmetic needs to know about one site's calendar.

    Deliberately a plain value object rather than the ORM row: the rules are
    then usable against a calendar that has not been saved yet (a preview), and
    the repository decides how to load holidays.
    """

    weekendDays: tuple[int, ...] = DEFAULT_WEEKEND_DAYS
    holidays: frozenset[date] = frozenset()
    rollPolicy: str = ROLL_FORWARD

    @property
    def hasWorkingDay(self) -> bool:
        """False when every weekday is a weekend — an unusable calendar."""
        return len(set(self.weekendDays)) < 7


def isWeekend(spec: CalendarSpec, day: date) -> bool:
    return day.weekday() in set(spec.weekendDays)


def isHoliday(spec: CalendarSpec, day: date) -> bool:
    return day in spec.holidays


def isWorkingDay(spec: CalendarSpec, day: date) -> bool:
    """A day the site is open: not a weekend and not a holiday."""
    return not isWeekend(spec, day) and not isHoliday(spec, day)


def nextWorkingDay(spec: CalendarSpec, day: date, *, inclusive: bool = True) -> date:
    """First working day on or after ``day``.

    ``inclusive=False`` always moves at least one day, which is what "schedule
    the next one" means after a job has just been done.
    """
    return _roll(spec, day, step=1, inclusive=inclusive)


def previousWorkingDay(spec: CalendarSpec, day: date, *, inclusive: bool = True) -> date:
    """Last working day on or before ``day``."""
    return _roll(spec, day, step=-1, inclusive=inclusive)


def _roll(spec: CalendarSpec, day: date, *, step: int, inclusive: bool) -> date:
    """Walk day by day until a working day is found.

    Termination is guaranteed by ``MAX_ROLL_DAYS`` on the loop below — that is
    the real guard, and mutation testing confirms it is the one doing the work.
    The ``hasWorkingDay`` check in front of it is only a fast path for the
    obviously-broken calendar; deleting it changes cost, not correctness.

    Either way the original date comes back, so a bad configuration surfaces as
    a date that refused to move rather than as a hung request.
    """
    if not spec.hasWorkingDay:
        return day
    cursor = day if inclusive else day + timedelta(days=step)
    for _ in range(MAX_ROLL_DAYS):
        if isWorkingDay(spec, cursor):
            return cursor
        cursor = cursor + timedelta(days=step)
    return day


def rollToWorkingDay(spec: CalendarSpec, day: date) -> date:
    """Apply the calendar's own policy to a date that may be non-working.

    This is the function the scheduler calls. ``ROLL_NONE`` returns the date
    untouched, which is the right answer for a plant that genuinely runs PMs
    on holidays and only wants the day *flagged*.
    """
    if isWorkingDay(spec, day):
        return day
    if spec.rollPolicy == ROLL_NONE:
        return day
    if spec.rollPolicy == ROLL_BACKWARD:
        return previousWorkingDay(spec, day)
    return nextWorkingDay(spec, day)


def workingDaysBetween(spec: CalendarSpec, start: date, end: date) -> int:
    """Count working days in ``[start, end]`` inclusive.

    Returns 0 when the range is inverted rather than a negative count — a
    backwards range is a caller bug, not a negative quantity of work.
    """
    if end < start:
        return 0
    total = 0
    cursor = start
    while cursor <= end:
        if isWorkingDay(spec, cursor):
            total += 1
        cursor += _DAY
    return total


def addWorkingDays(spec: CalendarSpec, start: date, count: int) -> date:
    """``start`` plus ``count`` working days, skipping closures.

    Used for lead times that are quoted in working days ("the part arrives in
    three working days") rather than calendar days.
    """
    if count <= 0 or not spec.hasWorkingDay:
        return start
    cursor = start
    remaining = count
    guard = 0
    while remaining > 0 and guard < MAX_ROLL_DAYS * max(1, count):
        cursor += _DAY
        guard += 1
        if isWorkingDay(spec, cursor):
            remaining -= 1
    return cursor


# =================================================================================
# Shifts
# =================================================================================


@dataclass(frozen=True)
class ShiftSpec:
    """One shift window, as configured — not yet bound to a date."""

    code: str
    startTime: time
    endTime: time
    weekdays: tuple[int, ...] = ()
    headcount: int = 0

    @property
    def crossesMidnight(self) -> bool:
        """A night shift ending at or before it starts runs into the next day.

        Equality counts as crossing: 22:00 → 22:00 is a 24-hour shift, not a
        zero-length one. A zero-length shift is never what anybody configured.
        """
        return self.endTime <= self.startTime

    @property
    def durationHours(self) -> Decimal:
        """Length of one occurrence of this shift, in hours."""
        start = datetime.combine(date(2000, 1, 1), self.startTime)
        end = datetime.combine(date(2000, 1, 1), self.endTime)
        if self.crossesMidnight:
            end += _DAY
        return _hours(end - start)

    def runsOn(self, day: date) -> bool:
        """True when this shift is staffed on ``day``.

        An empty ``weekdays`` means "every day the site is open" — the common
        case for a continuous three-shift plant, and it keeps the configuration
        from having to list all seven days.
        """
        return not self.weekdays or day.weekday() in set(self.weekdays)

    def windowOn(self, day: date) -> tuple[datetime, datetime]:
        """Concrete start/end datetimes for this shift on ``day``.

        Naive datetimes on purpose: they are anchored to the *site's* calendar
        day, and the site's timezone is applied by the caller that knows it.
        Mixing a tz-aware conversion in here would silently re-date a night
        shift.
        """
        start = datetime.combine(day, self.startTime)
        end = datetime.combine(day, self.endTime)
        if self.crossesMidnight:
            end += _DAY
        return start, end


def shiftsOn(shifts: tuple[ShiftSpec, ...], spec: CalendarSpec, day: date) -> tuple[ShiftSpec, ...]:
    """Shifts actually staffed on ``day``.

    A closed day has no shifts, whatever the shift's own weekday list says —
    the calendar outranks the roster, otherwise a holiday would still show
    capacity.
    """
    if not isWorkingDay(spec, day):
        return ()
    return tuple(shift for shift in shifts if shift.runsOn(day))


def coveringShift(shifts: tuple[ShiftSpec, ...], moment: datetime) -> ShiftSpec | None:
    """The shift whose window contains ``moment``, if any.

    Checks the previous day too, so a night shift that began at 22:00 still
    owns 01:00 of the following morning.
    """
    for offset in (0, -1):
        day = moment.date() + timedelta(days=offset)
        for shift in shifts:
            if not shift.runsOn(day):
                continue
            start, end = shift.windowOn(day)
            if start <= moment < end:
                return shift
    return None


# =================================================================================
# Capacity
# =================================================================================


def shiftCapacityHours(shift: ShiftSpec, headcount: int | None = None) -> Decimal:
    """Technician-hours one shift provides: duration × people.

    ``headcount`` overrides the configured figure so a planner can ask "what if
    I put four people on nights?" without editing the roster.
    """
    people = shift.headcount if headcount is None else headcount
    return shift.durationHours * Decimal(max(0, people))


def dailyCapacityHours(shifts: tuple[ShiftSpec, ...], spec: CalendarSpec, day: date) -> Decimal:
    """Total technician-hours available on ``day``. Zero on a closed day."""
    return sum(
        (shiftCapacityHours(shift) for shift in shiftsOn(shifts, spec, day)),
        Decimal("0"),
    )


def utilisationPercent(demandHours: Decimal, capacityHours: Decimal) -> Decimal:
    """Load as a percentage of capacity.

    Returns 0 when there is no demand and no capacity — a closed day with
    nothing scheduled is not "infinitely over capacity". But demand on a day
    with *zero* capacity is reported as 999: work has been scheduled onto a day
    nobody is working, and that must read as alarming rather than as a quiet
    divide-by-zero.
    """
    if capacityHours <= 0:
        return Decimal("999") if demandHours > 0 else Decimal("0")
    return (demandHours / capacityHours * Decimal("100")).quantize(Decimal("0.1"))


# =================================================================================
# Overtime
# =================================================================================


def overtimeHours(start: datetime, end: datetime, shifts: tuple[ShiftSpec, ...]) -> Decimal:
    """Portion of a labour span that falls outside every shift window.

    Overtime here is a *scheduling* fact, not a payroll one: hours worked when
    no shift was staffed. It deliberately says nothing about rates or
    multipliers, which belong to a payroll system this product does not have.

    Computed by subtracting covered time from the span, so overlapping or
    back-to-back shifts cannot double-count a minute.
    """
    if end <= start:
        return Decimal("0")
    covered = _coveredSpans(start, end, shifts)
    coveredDelta = sum((span[1] - span[0] for span in covered), timedelta())
    outside = _hours(end - start) - _hours(coveredDelta)
    # Quantize the floor too, so callers always get the same two-decimal shape
    # whether or not there was any overtime.
    return outside if outside > 0 else Decimal("0.00")


def _coveredSpans(
    start: datetime, end: datetime, shifts: tuple[ShiftSpec, ...]
) -> list[tuple[datetime, datetime]]:
    """Merged list of in-shift intervals intersecting ``[start, end)``."""
    raw: list[tuple[datetime, datetime]] = []
    # Walk a day either side so a night shift starting before `start` and a
    # shift starting on the final day are both considered.
    day = start.date() - _DAY
    last = end.date() + _DAY
    while day <= last:
        for shift in shifts:
            if shift.runsOn(day):
                windowStart, windowEnd = shift.windowOn(day)
                low = max(windowStart, start)
                high = min(windowEnd, end)
                if low < high:
                    raw.append((low, high))
        day += _DAY
    if not raw:
        return []
    raw.sort()
    merged = [raw[0]]
    for low, high in raw[1:]:
        lastLow, lastHigh = merged[-1]
        if low <= lastHigh:
            merged[-1] = (lastLow, max(lastHigh, high))
        else:
            merged.append((low, high))
    return merged


def _hours(delta: timedelta) -> Decimal:
    """Timedelta to hours, two decimals, half-up like the rest of costing."""
    return (Decimal(delta.total_seconds()) / Decimal("3600")).quantize(Decimal("0.01"))
