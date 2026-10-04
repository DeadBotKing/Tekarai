"""Work calendar, shift and capacity use cases — Phase 28.

The payoff of this slice is :class:`GetCapacityPlanUseCase`: one read model
that answers, day by day, *can this plant actually do the maintenance it has
scheduled?* — by putting the PM demand it already knows about next to the
technician-hours the roster actually buys.

Everything else here exists to make that question answerable: calendars say
which days a site opens, holidays close individual days, shifts say who is
there and for how long.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from apps.maintenance.application.services.tenantResolver import (
    parseDateOrNone,
    resolveTenantId,
)
from apps.maintenance.application.useCases.registryUseCases import (
    PERMISSION_REGISTRY_MANAGE,
    PERMISSION_REGISTRY_VIEW,
)
from apps.maintenance.domain.services.jalaliCalendar import dateToJalali
from apps.maintenance.domain.services.workCalendarRules import (
    CalendarSpec,
    dailyCapacityHours,
    isHoliday,
    isWeekend,
    isWorkingDay,
    rollToWorkingDay,
    shiftsOn,
    utilisationPercent,
)
from apps.maintenance.domain.valueObjects.maintenanceState import (
    HOLIDAY_KINDS,
    ROLL_POLICIES,
    SHIFT_KINDS,
)
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_DELETE, UseCase
from apps.sharedKernel.domain.errors import DomainError, EntityNotFoundError

#: Planning windows are bounded: the capacity plan materialises one dict per
#: day, so an open-ended range would be an easy way to exhaust memory.
MAX_PLAN_DAYS = 370
DEFAULT_PLAN_DAYS = 30

#: Hours assumed for a PM occurrence when the plan does not estimate one.
#: Deliberately conservative — under-stating demand hides over-commitment,
#: which is the failure this report exists to reveal.
DEFAULT_JOB_HOURS = Decimal("2")


class WorkCalendarError(DomainError):
    """A calendar or shift was configured in a way that cannot be scheduled."""


# =====================================================================================
# Commands / queries
# =====================================================================================
@dataclass(frozen=True)
class CalendarQuery:
    calendarId: str = ""


@dataclass(frozen=True)
class SaveCalendarCommand:
    id: str = ""
    code: str = ""
    name: str = ""
    locationId: str = ""
    timezone: str = "Asia/Tehran"
    weekendDays: tuple[int, ...] = ()
    rollPolicy: str = "forward"
    isDefault: bool = False
    active: bool = True
    note: str = ""


@dataclass(frozen=True)
class SaveHolidayCommand:
    calendarId: str
    onDate: str
    name: str
    id: str = ""
    kind: str = "official"
    recursAnnually: bool = False
    jalaliMonth: int = 0
    jalaliDay: int = 0


@dataclass(frozen=True)
class SaveShiftCommand:
    calendarId: str
    code: str
    name: str
    startTime: str
    endTime: str
    id: str = ""
    kind: str = "general"
    weekdays: tuple[int, ...] = ()
    headcount: int = 0
    active: bool = True


@dataclass(frozen=True)
class SaveShiftAssignmentCommand:
    shiftId: str
    personnelId: str
    fromDate: str
    toDate: str = ""


@dataclass(frozen=True)
class CapacityPlanQuery:
    calendarId: str = ""
    locationId: str = ""
    fromDate: str = ""
    toDate: str = ""


@dataclass(frozen=True)
class DeleteCommand:
    id: str
    kind: str = ""


@dataclass(frozen=True)
class WorkingDayQuery:
    """Ask the calendar a direct question about one date."""

    onDate: str
    calendarId: str = ""
    locationId: str = ""
    deviceId: str = ""
    addWorkingDays: int = 0


# =====================================================================================
# Base
# =====================================================================================
class WorkCalendarUseCaseBase(UseCase):
    """Shared wiring. Mirrors the registry use cases so the container matches."""

    def __init__(
        self,
        *,
        calendarRepository,  # noqa: ANN001 — protocol, injected by the container
        deviceRepository,  # noqa: ANN001
        locationRepository,  # noqa: ANN001
        unitOfWork,  # noqa: ANN001
        auditRecorder,  # noqa: ANN001
        eventDispatcher,  # noqa: ANN001
        permissionGate,  # noqa: ANN001
        clock,  # noqa: ANN001
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.calendarRepository = calendarRepository
        self.deviceRepository = deviceRepository
        self.locationRepository = locationRepository

    def requireCalendarId(
        self, tenantId: uuid.UUID, calendarId: str, locationId: str = ""
    ) -> uuid.UUID:
        """Resolve an explicit id, or fall back to the location's calendar.

        A caller that names neither gets the tenant default, which is what
        makes the common single-site case require no configuration at all.
        """
        if calendarId:
            found = self.calendarRepository.getCalendar(tenantId, uuid.UUID(calendarId))
            if found is None:
                raise EntityNotFoundError("Work calendar not found.")
            return uuid.UUID(calendarId)
        resolved = self.calendarRepository.resolveCalendarIdForLocation(
            tenantId, uuid.UUID(locationId) if locationId else None
        )
        if resolved is None:
            raise EntityNotFoundError(
                "No work calendar is configured for this tenant."
            )
        return resolved

    def resolveWindow(self, fromDate: str, toDate: str) -> tuple[date, date]:
        today = self.clock.nowUtc().date()
        start = parseDateOrNone(fromDate) or today
        end = parseDateOrNone(toDate) or (start + timedelta(days=DEFAULT_PLAN_DAYS))
        if end < start:
            start, end = end, start
        span = (end - start).days
        if span > MAX_PLAN_DAYS:
            end = start + timedelta(days=MAX_PLAN_DAYS)
        return start, end


# =====================================================================================
# Reads
# =====================================================================================
class ListWorkCalendarsUseCase(WorkCalendarUseCaseBase):
    """Every calendar for the tenant, default first."""

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: CalendarQuery) -> dict:
        tenantId = resolveTenantId("")
        calendars = self.calendarRepository.listCalendars(tenantId)
        for calendar in calendars:
            calendarId = uuid.UUID(calendar["id"])
            calendar["shifts"] = self.calendarRepository.listShifts(tenantId, calendarId)
            calendar["holidayCount"] = len(
                self.calendarRepository.listHolidays(tenantId, calendarId)
            )
        return {"items": calendars, "count": len(calendars)}


class ListHolidaysUseCase(WorkCalendarUseCaseBase):
    """Holidays on one calendar, optionally inside a window."""

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: CapacityPlanQuery) -> dict:
        tenantId = resolveTenantId("")
        calendarId = self.requireCalendarId(tenantId, query.calendarId, query.locationId)
        start = parseDateOrNone(query.fromDate)
        end = parseDateOrNone(query.toDate)
        items = self.calendarRepository.listHolidays(tenantId, calendarId, start, end)
        return {"calendarId": str(calendarId), "items": items, "count": len(items)}


class GetWorkingDayUseCase(WorkCalendarUseCaseBase):
    """Is this date a working day for this site — and if not, when is?

    Exposed as its own endpoint because every other module that wants to be
    calendar-aware (procurement lead times, work-order due dates) needs this
    one answer and should not re-implement it.
    """

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: WorkingDayQuery) -> dict:
        tenantId = resolveTenantId("")
        locationId = query.locationId
        if query.deviceId and not locationId:
            device = self.deviceRepository.getById(tenantId, uuid.UUID(query.deviceId))
            if device is None:
                raise EntityNotFoundError("Device not found.")
            locationId = str(getattr(device, "locationId", "") or "")
        calendarId = self.requireCalendarId(tenantId, query.calendarId, locationId)
        day = parseDateOrNone(query.onDate) or self.clock.nowUtc().date()
        # Pad the window so a roll crossing a long closure still sees the
        # holidays it has to skip.
        spec = self.calendarRepository.loadSpec(
            tenantId, calendarId, day - timedelta(days=40), day + timedelta(days=40)
        )
        rolled = rollToWorkingDay(spec, day)
        result = {
            "calendarId": str(calendarId),
            "onDate": day.isoformat(),
            "isWorkingDay": isWorkingDay(spec, day),
            "isWeekend": isWeekend(spec, day),
            "isHoliday": isHoliday(spec, day),
            "rollPolicy": spec.rollPolicy,
            "plannedOn": rolled.isoformat(),
            "rolled": rolled != day,
        }
        if query.addWorkingDays:
            from apps.maintenance.domain.services.workCalendarRules import addWorkingDays

            result["addWorkingDays"] = addWorkingDays(
                spec, day, int(query.addWorkingDays)
            ).isoformat()
        return result


@dataclass
class _DayBucket:
    """Mutable accumulator for one day of the plan."""

    demandHours: Decimal = Decimal("0")
    jobs: list[dict] = field(default_factory=list)


class GetCapacityPlanUseCase(WorkCalendarUseCaseBase):
    """Day-by-day capacity against scheduled PM demand.

    Demand is read from the same PM sources the maintenance calendar already
    draws, so the two can never disagree. Each job is placed on the day the
    calendar says it will actually be done — its rolled date — because asking
    "is this day over-committed?" about a date nobody works is meaningless.
    """

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: CapacityPlanQuery) -> dict:
        tenantId = resolveTenantId("")
        calendarId = self.requireCalendarId(tenantId, query.calendarId, query.locationId)
        start, end = self.resolveWindow(query.fromDate, query.toDate)
        spec = self.calendarRepository.loadSpec(
            tenantId, calendarId, start - timedelta(days=40), end + timedelta(days=40)
        )
        shifts = self.calendarRepository.loadShiftSpecs(tenantId, calendarId)

        buckets = self._collectDemand(tenantId, spec, start, end)

        days: list[dict] = []
        cursor = start
        totalDemand = Decimal("0")
        totalCapacity = Decimal("0")
        overloaded = 0
        while cursor <= end:
            bucket = buckets.get(cursor, _DayBucket())
            capacity = dailyCapacityHours(shifts, spec, cursor)
            working = isWorkingDay(spec, cursor)
            utilisation = utilisationPercent(bucket.demandHours, capacity)
            if utilisation > 100:
                overloaded += 1
            totalDemand += bucket.demandHours
            totalCapacity += capacity
            days.append(
                {
                    "onDate": cursor.isoformat(),
                    "isWorkingDay": working,
                    "isWeekend": isWeekend(spec, cursor),
                    "isHoliday": isHoliday(spec, cursor),
                    "shiftCount": len(shiftsOn(shifts, spec, cursor)),
                    "capacityHours": str(capacity),
                    "demandHours": str(bucket.demandHours),
                    "utilisationPercent": str(utilisation),
                    "jobCount": len(bucket.jobs),
                    "jobs": bucket.jobs,
                }
            )
            cursor += timedelta(days=1)

        return {
            "calendarId": str(calendarId),
            "fromDate": start.isoformat(),
            "toDate": end.isoformat(),
            "days": days,
            "shifts": self.calendarRepository.listShifts(tenantId, calendarId),
            "summary": {
                "totalCapacityHours": str(totalCapacity),
                "totalDemandHours": str(totalDemand),
                "utilisationPercent": str(utilisationPercent(totalDemand, totalCapacity)),
                "workingDays": sum(1 for day in days if day["isWorkingDay"]),
                "closedDays": sum(1 for day in days if not day["isWorkingDay"]),
                "overloadedDays": overloaded,
            },
        }

    def _collectDemand(
        self, tenantId: uuid.UUID, spec: CalendarSpec, start: date, end: date
    ) -> dict:
        """Bucket every PM due in the window onto the day it will be worked."""
        buckets: dict[date, _DayBucket] = {}
        for job in self.calendarRepository.listPmDemand(tenantId, start, end):
            due = job.get("dueOn")
            if due is None:
                continue
            planned = rollToWorkingDay(spec, due)
            if planned < start or planned > end:
                # Rolled out of the window — it is someone else's day.
                continue
            bucket = buckets.setdefault(planned, _DayBucket())
            hours = job.get("estimatedHours") or DEFAULT_JOB_HOURS
            bucket.demandHours += Decimal(str(hours))
            bucket.jobs.append(
                {
                    "deviceId": job.get("deviceId", ""),
                    "deviceCode": job.get("deviceCode", ""),
                    "deviceName": job.get("deviceName", ""),
                    "title": job.get("title", ""),
                    "dueOn": due.isoformat(),
                    "rolled": planned != due,
                    "estimatedHours": str(hours),
                }
            )
        return buckets


# =====================================================================================
# Writes
# =====================================================================================
class SaveWorkCalendarUseCase(WorkCalendarUseCaseBase):
    """Create or update a calendar."""

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: SaveCalendarCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        if not command.code.strip() or not command.name.strip():
            raise WorkCalendarError("A calendar needs a code and a name.")
        if command.rollPolicy not in ROLL_POLICIES:
            raise WorkCalendarError(
                f"Unknown roll policy «{command.rollPolicy}»."
            )
        weekend = tuple(command.weekendDays)
        if len(set(weekend)) >= 7:
            # Every day off is not a calendar, it is a closed plant; refusing
            # it here is kinder than letting every later roll silently no-op.
            raise WorkCalendarError(
                "A calendar must leave at least one working day in the week."
            )
        values = {
            "id": command.id or None,
            "code": command.code.strip(),
            "name": command.name.strip(),
            "locationId": command.locationId or None,
            "timezone": command.timezone or "Asia/Tehran",
            "weekendDays": weekend,
            "rollPolicy": command.rollPolicy,
            "isDefault": command.isDefault,
            "active": command.active,
            "note": command.note,
        }
        saved = self.calendarRepository.saveCalendar(tenantId, values, now)
        self.audit(AUDIT_CREATE, resourceType="WorkCalendar", resourceId=saved["id"], tenantId=tenantId)
        return saved


class SaveHolidayUseCase(WorkCalendarUseCaseBase):
    """Add or amend one closure."""

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: SaveHolidayCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        onDate = parseDateOrNone(command.onDate)
        if onDate is None:
            raise WorkCalendarError("A holiday needs a valid date.")
        if not command.name.strip():
            raise WorkCalendarError("A holiday needs a name.")
        if command.kind not in HOLIDAY_KINDS:
            raise WorkCalendarError(f"Unknown holiday kind «{command.kind}».")
        calendarId = self.requireCalendarId(tenantId, command.calendarId)
        _, jalaliMonth, jalaliDay = dateToJalali(onDate)
        values = {
            "id": command.id or None,
            "calendarId": calendarId,
            "onDate": onDate,
            "name": command.name.strip(),
            "kind": command.kind,
            "recursAnnually": command.recursAnnually,
            # Derived here, never taken from the caller. The Jalali parts are
            # what `recursAnnually` projects on, so they must agree with
            # `onDate` or a holiday would recur on the wrong day. The web form
            # was sending zeros, which silently made every holiday
            # non-recurring however the box was ticked.
            "jalaliMonth": jalaliMonth,
            "jalaliDay": jalaliDay,
        }
        saved = self.calendarRepository.saveHoliday(tenantId, values, now)
        self.audit(AUDIT_CREATE, resourceType="CalendarHoliday", resourceId=saved["id"], tenantId=tenantId)
        return saved


class SaveShiftUseCase(WorkCalendarUseCaseBase):
    """Create or update a shift window."""

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: SaveShiftCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        if not command.code.strip() or not command.name.strip():
            raise WorkCalendarError("A shift needs a code and a name.")
        if command.kind not in SHIFT_KINDS:
            raise WorkCalendarError(f"Unknown shift kind «{command.kind}».")
        if command.headcount < 0:
            raise WorkCalendarError("Headcount cannot be negative.")
        calendarId = self.requireCalendarId(tenantId, command.calendarId)
        values = {
            "id": command.id or None,
            "calendarId": calendarId,
            "code": command.code.strip(),
            "name": command.name.strip(),
            "kind": command.kind,
            "startTime": command.startTime,
            "endTime": command.endTime,
            "weekdays": tuple(command.weekdays),
            "headcount": command.headcount,
            "active": command.active,
        }
        saved = self.calendarRepository.saveShift(tenantId, values, now)
        self.audit(AUDIT_CREATE, resourceType="WorkShift", resourceId=saved["id"], tenantId=tenantId)
        return saved


class SaveShiftAssignmentUseCase(WorkCalendarUseCaseBase):
    """Roster one technician onto one shift."""

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: SaveShiftAssignmentCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        fromDate = parseDateOrNone(command.fromDate)
        if fromDate is None:
            raise WorkCalendarError("An assignment needs a start date.")
        toDate = parseDateOrNone(command.toDate) if command.toDate else None
        if toDate is not None and toDate < fromDate:
            raise WorkCalendarError("An assignment cannot end before it starts.")
        values = {
            "shiftId": uuid.UUID(command.shiftId),
            "personnelId": uuid.UUID(command.personnelId),
            "fromDate": fromDate,
            "toDate": toDate,
        }
        saved = self.calendarRepository.saveAssignment(tenantId, values, now)
        self.audit(AUDIT_CREATE, resourceType="ShiftAssignment", resourceId=saved["id"], tenantId=tenantId)
        return saved


class DeleteCalendarEntryUseCase(WorkCalendarUseCaseBase):
    """Soft-delete a calendar, holiday, shift or assignment."""

    requiredAction = PERMISSION_REGISTRY_MANAGE

    def perform(self, command: DeleteCommand) -> dict:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        entityId = uuid.UUID(command.id)
        remover = {
            "calendar": self.calendarRepository.deleteCalendar,
            "holiday": self.calendarRepository.deleteHoliday,
            "shift": self.calendarRepository.deleteShift,
            "assignment": self.calendarRepository.deleteAssignment,
        }.get(command.kind)
        if remover is None:
            raise WorkCalendarError(f"Unknown entry kind «{command.kind}».")
        if not remover(tenantId, entityId, now):
            raise EntityNotFoundError("Calendar entry not found.")
        self.audit(AUDIT_DELETE, resourceType=f"WorkCalendar:{command.kind}", resourceId=command.id, tenantId=tenantId)
        return {"id": command.id, "kind": command.kind, "deleted": True}
