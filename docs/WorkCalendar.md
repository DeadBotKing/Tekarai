# Work calendar, shifts and capacity (Phase 28)

## Why this exists

Tekarai could already *display* Jalali dates. That is not scheduling. Before this
phase the platform had no notion of when the plant is actually open:

| Capability | Before |
| --- | --- |
| Official holiday calendar | absent |
| Work shifts | a `CharField(60)` label on personnel — a word, not a time window |
| Overtime | absent |
| Multi-site calendar | absent |
| Time zone | one global `TIME_ZONE` setting |
| Per-site working days | absent |
| Maintenance-team capacity | absent |
| Shift-based planning | absent |

Consequence: a PM falling on نوروز or a جمعه was simply "due", and nothing in the
system knew that nobody would be there. This phase supplies the missing fact —
**when is this site open, who is on, and how many hours does that buy** — and
feeds it into PM planning.

## Scope decisions

- **A calendar belongs to a site.** It binds to an existing `location` whose
  `kind` is `site`. A tenant-level default covers sites with no calendar of
  their own, so nothing is ever un-scheduled.
- **PM dates are annotated, never mutated.** The capacity read model buckets a
  job onto the day it will *really* be done (`plannedOn`), while `nextDueOn`
  stays exactly as the PM plan computed it. Existing behaviour and existing
  tests therefore cannot change.
- **Overtime is a scheduling fact, not a payroll one.** It means labour hours
  that fall outside every staffed shift window. Rates and multipliers are
  deliberately out of scope — that is a payroll product.
- **Capacity = shift duration × headcount**, zero on a closed day. The
  configured headcount is overridable by the live roster so what-if planning
  and reality can disagree on purpose.

## Domain rules

`apps/maintenance/domain/services/workCalendarRules.py` (55 unit tests).

- Weekdays are python's: Monday 0 … **جمعه 4** … Sunday 6. The Iranian
  شنبه-first *display* order is a UI concern only; converting in the domain
  would mean two conventions fighting over the same integers.
- `DEFAULT_WEEKEND_DAYS = (FRIDAY,)`. `normaliseWeekendDays` accepts a CSV
  string, list or set, dedupes, sorts and **never raises** — a malformed
  weekend must not take a site offline.
- Roll policies: `forward | backward | none`. A working day is never moved.
  Rolling is bounded by `MAX_ROLL_DAYS = 30` so a calendar that closes every
  day cannot hang a request.
- **The calendar outranks the roster.** A shift rostered on a closed day
  contributes nothing; the plant being shut is the stronger fact.
- A `ShiftSpec` whose start equals its end is **24 hours**, not zero. An empty
  `weekdays` list means every open day.
- `coveringShift` attributes 01:00 to the previous night's shift, not to a
  morning that has not started.
- `utilisationPercent` is 0 when demand and capacity are both 0, and returns
  the **999 sentinel** when demand exists against zero capacity — work stranded
  on a day nobody is in.

## Data model

Migration `apps/maintenance/infrastructure/migrations/0018_workCalendar.py`.

| Table | Notes |
| --- | --- |
| `MaintenanceWorkCalendar` | `tenantId`, `code`, `name`, nullable `locationId`, `timezone` (default `Asia/Tehran`), `weekendDays` CSV (default `"4"`), `rollPolicy`, `isDefault`, `active`. Unique on `(tenantId, code)` and on `(tenantId, locationId)` where `locationId` is not null. |
| `MaintenanceCalendarHoliday` | `onDate`, `name`, `kind`, `recursAnnually`, `jalaliMonth`/`jalaliDay`. Unique on `(tenantId, calendarId, onDate)`. |
| `MaintenanceWorkShift` | `code`, `name`, `kind`, `startTime`, `endTime`, `weekdays` CSV, `headcount`. Unique on `(tenantId, calendarId, code)`. |
| `MaintenanceShiftAssignment` | `shiftId`, `personnelId`, `fromDate`, nullable `toDate`. |

Repository policies, all confirmed by mutation testing:

- One `isDefault` per tenant, enforced on save — newest wins.
- Deleting a calendar soft-deletes its holidays and shifts with it.
- `resolveCalendarIdForLocation` walks `parentId` upward (cycle-guarded) before
  falling back to the tenant default, so a building inherits its site's
  calendar.
- `loadShiftSpecs` prefers live rostered headcount over the configured figure;
  expired assignments stop counting.

### PM demand

`listPmDemand` merges active `PmPlanModel` rows (due = `lastExecutedOn +
FREQUENCY_DAYS[unit] × frequencyEvery`) with device-level
`pmIntervalDays`/`lastPmDate` — but **only for devices with no active plan**, so
a device covered by both is never counted twice. Meter-driven units and
never-executed plans are skipped. A job with no `estimatedMinutes` falls back to
`DEFAULT_JOB_HOURS = 2`.

## API

All under `/api/v1/maintenance`:

```
GET    | POST   work-calendars
DELETE         work-calendars/<uuid:calendarId>
GET    | POST   work-calendars/holidays
DELETE         work-calendars/holidays/<uuid:holidayId>
POST           work-calendars/shifts
DELETE         work-calendars/shifts/<uuid:shiftId>
POST           work-calendars/assignments
DELETE         work-calendars/assignments/<uuid:assignmentId>
GET            work-calendars/capacity?calendarId=&locationId=&fromDate=&toDate=
GET            work-calendars/working-day?onDate=&calendarId=|locationId=|deviceId=&addWorkingDays=
```

The capacity response carries one entry per day — `{onDate, isWorkingDay,
isWeekend, isHoliday, shiftCount, capacityHours, demandHours,
utilisationPercent, jobCount, jobs[]}` — plus a `summary` with
`totalCapacityHours`, `totalDemandHours`, `utilisationPercent`, `workingDays`,
`closedDays` and `overloadedDays`. An inverted date range is swapped, not
rejected. The window is bounded by `MAX_PLAN_DAYS = 370`.

## Screens

**`/app/maintenance/work-calendar`** — four tabs:

- **تقویم‌ها** — the calendars, their site, time zone, weekend days and roll policy.
- **تعطیلات** — holidays on the selected calendar. Lunar holidays (عید فطر,
  تاسوعا, عاشورا) move every year and are entered per year; only the fixed
  solar dates are seeded.
- **شیفت‌ها** — shift windows, crew size, computed length and capacity. A window
  that crosses midnight is labelled as such.
- **ظرفیت** — a Jalali month grid of capacity against scheduled PM demand. Each
  cell is toned `closed > over > tight > ok > idle`; **`closed` outranks
  everything**, because colouring a shut day green invites someone to book work
  onto it.

**`/app/maintenance/pm-calendar`** gained closed-day shading and a «روز تعطیل»
marker on any day that is shut but still carries a PM. This is read-only and
fails silently: if the calendar cannot be loaded the page behaves exactly as it
did before Phase 28.

## Iranian 1405 holidays (seeded)

Nowruz 1405 begins 2026-03-21. Months 1–6 are 31 days, 7–11 are 30.

| Date | Occasion |
| --- | --- |
| 2026-03-21 … 24 | نوروز |
| 2026-04-01 | روز جمهوری اسلامی |
| 2026-04-02 | روز طبیعت |
| 2026-06-04 | رحلت امام خمینی |
| 2026-06-05 | قیام ۱۵ خرداد (a جمعه — already closed) |
| 2027-02-11 | پیروزی انقلاب اسلامی |
| 2027-03-20 | ملی‌شدن صنعت نفت |

Lunar/Hijri holidays are deliberately **not** seeded: they shift against the
solar calendar every year, so a hardcoded list would be wrong by next year.
Enter them from the holidays tab.

## Tests

| Suite | Count |
| --- | --- |
| `apps/maintenance/tests/testWorkCalendarRules.py` | 55 |
| `backend/tests/integration/testWorkCalendarApi.py` | 33 |
| `frontend-web/src/tests/workCalendar.test.ts` | 36 |

Both the API slice (5 mutants) and the frontend math (6 mutants) were mutation
tested; every mutant was killed. Two of them earned their keep: the frontend
round initially let "over capacity" outrank "closed", and the test that was
supposed to protect that ordering never exercised it.

## Trying it

```
cd backend
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seedDemo   # idempotent; run_dev does NOT seed
```

Then open **نگهداری و تعمیرات → عملیات → تقویم کاری**.
