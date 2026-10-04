"""Persistence for work calendars, holidays and shifts — Phase 28.

Django lives here and nowhere above. Everything handed upwards is either a
plain dict (for the API) or one of the pure value objects from
``workCalendarRules``, so the scheduling arithmetic never sees an ORM row.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import date, datetime, time, timedelta, timezone

from apps.maintenance.domain.services.workCalendarRules import (
    CalendarSpec,
    ShiftSpec,
    normaliseWeekendDays,
)
from apps.maintenance.domain.valueObjects.maintenanceState import ROLL_FORWARD
from apps.maintenance.infrastructure.models import (
    CalendarHolidayModel,
    MaintenanceLocationModel,
    MaintenancePersonnelModel,
    ShiftAssignmentModel,
    WorkCalendarModel,
    WorkShiftModel,
)


def _timeToText(value: time) -> str:
    return value.strftime("%H:%M")


def _parseTime(value: str, fallback: time) -> time:
    """HH:MM from the API, tolerant of seconds and whitespace."""
    text = (value or "").strip()
    if not text:
        return fallback
    for shape in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, shape).time()
        except ValueError:
            continue
    return fallback


def _weekdaysToCsv(days: object) -> str:
    return ",".join(str(day) for day in normaliseWeekendDays(days))


class WorkCalendarRepositoryDjango:
    """Calendars, their holidays and their shifts."""

    # -- calendars ----------------------------------------------------------------
    def listCalendars(self, tenantId: uuid.UUID) -> list[dict]:
        rows = WorkCalendarModel.objects.filter(
            tenantId=tenantId, deletedAt__isnull=True
        ).order_by("-isDefault", "name")
        locationNames = self._locationNames(tenantId)
        return [self._calendarDict(row, locationNames) for row in rows]

    def getCalendar(self, tenantId: uuid.UUID, calendarId: uuid.UUID) -> dict | None:
        row = WorkCalendarModel.objects.filter(
            tenantId=tenantId, id=calendarId, deletedAt__isnull=True
        ).first()
        return None if row is None else self._calendarDict(row, self._locationNames(tenantId))

    def saveCalendar(self, tenantId: uuid.UUID, values: dict, now: datetime) -> dict:
        calendarId = values.get("id")
        defaults = {
            "code": values.get("code", ""),
            "name": values.get("name", ""),
            "locationId": values.get("locationId") or None,
            "timezone": values.get("timezone") or "Asia/Tehran",
            "weekendDays": _weekdaysToCsv(values.get("weekendDays", "4")),
            "rollPolicy": values.get("rollPolicy") or ROLL_FORWARD,
            "isDefault": bool(values.get("isDefault", False)),
            "active": bool(values.get("active", True)),
            "note": values.get("note", ""),
            "updatedAt": now,
        }
        if calendarId:
            WorkCalendarModel.objects.filter(tenantId=tenantId, id=calendarId).update(**defaults)
            row = WorkCalendarModel.objects.get(tenantId=tenantId, id=calendarId)
        else:
            row = WorkCalendarModel.objects.create(
                tenantId=tenantId, createdAt=now, **defaults
            )
        if row.isDefault:
            # Exactly one tenant-wide default, enforced here rather than by a
            # constraint: partial-unique-on-boolean is not portable, and the
            # intent ("the newest wins") is a policy, not a schema rule.
            WorkCalendarModel.objects.filter(
                tenantId=tenantId, isDefault=True, deletedAt__isnull=True
            ).exclude(id=row.id).update(isDefault=False, updatedAt=now)
        return self._calendarDict(row, self._locationNames(tenantId))

    def deleteCalendar(self, tenantId: uuid.UUID, calendarId: uuid.UUID, now: datetime) -> bool:
        updated = WorkCalendarModel.objects.filter(
            tenantId=tenantId, id=calendarId, deletedAt__isnull=True
        ).update(deletedAt=now)
        if updated:
            # Holidays and shifts go with their calendar; leaving them behind
            # would let a new calendar reusing the id inherit someone else's
            # closures.
            CalendarHolidayModel.objects.filter(
                tenantId=tenantId, calendarId=calendarId, deletedAt__isnull=True
            ).update(deletedAt=now)
            WorkShiftModel.objects.filter(
                tenantId=tenantId, calendarId=calendarId, deletedAt__isnull=True
            ).update(deletedAt=now)
        return bool(updated)

    # -- resolution ---------------------------------------------------------------
    def resolveCalendarIdForLocation(
        self, tenantId: uuid.UUID, locationId: uuid.UUID | None
    ) -> uuid.UUID | None:
        """The calendar governing a location: its own, else its nearest parent's.

        Walking up the location tree is what makes a multi-site calendar
        workable: a group sets one calendar on each سایت and every hall, line
        and machine beneath it inherits without further configuration.
        """
        byLocation = {
            row.locationId: row.id
            for row in WorkCalendarModel.objects.filter(
                tenantId=tenantId, deletedAt__isnull=True, active=True
            ).exclude(locationId__isnull=True)
        }
        cursor = locationId
        seen: set[uuid.UUID] = set()
        while cursor is not None and cursor not in seen:
            seen.add(cursor)
            if cursor in byLocation:
                return byLocation[cursor]
            parent = (
                MaintenanceLocationModel.objects.filter(
                    tenantId=tenantId, id=cursor, deletedAt__isnull=True
                )
                .values_list("parentId", flat=True)
                .first()
            )
            cursor = parent
        fallback = WorkCalendarModel.objects.filter(
            tenantId=tenantId, deletedAt__isnull=True, active=True, isDefault=True
        ).first()
        return None if fallback is None else fallback.id

    def loadSpec(
        self, tenantId: uuid.UUID, calendarId: uuid.UUID, start: date, end: date
    ) -> CalendarSpec:
        """A `CalendarSpec` carrying only the holidays in the window asked for.

        Scoping the holiday set to the window keeps a calendar with twenty
        years of history from loading all of it to answer one month.
        """
        row = WorkCalendarModel.objects.filter(
            tenantId=tenantId, id=calendarId, deletedAt__isnull=True
        ).first()
        if row is None:
            return CalendarSpec()
        holidays = frozenset(
            CalendarHolidayModel.objects.filter(
                tenantId=tenantId,
                calendarId=calendarId,
                deletedAt__isnull=True,
                onDate__gte=start,
                onDate__lte=end,
            ).values_list("onDate", flat=True)
        )
        return CalendarSpec(
            weekendDays=normaliseWeekendDays(row.weekendDays),
            holidays=holidays,
            rollPolicy=row.rollPolicy or ROLL_FORWARD,
        )

    # -- holidays -----------------------------------------------------------------
    def listHolidays(
        self,
        tenantId: uuid.UUID,
        calendarId: uuid.UUID,
        start: date | None = None,
        end: date | None = None,
    ) -> list[dict]:
        rows = CalendarHolidayModel.objects.filter(
            tenantId=tenantId, calendarId=calendarId, deletedAt__isnull=True
        )
        if start is not None:
            rows = rows.filter(onDate__gte=start)
        if end is not None:
            rows = rows.filter(onDate__lte=end)
        return [self._holidayDict(row) for row in rows.order_by("onDate")]

    def saveHoliday(self, tenantId: uuid.UUID, values: dict, now: datetime) -> dict:
        holidayId = values.get("id")
        defaults = {
            "calendarId": values["calendarId"],
            "onDate": values["onDate"],
            "name": values.get("name", ""),
            "kind": values.get("kind") or "official",
            "recursAnnually": bool(values.get("recursAnnually", False)),
            "jalaliMonth": int(values.get("jalaliMonth") or 0),
            "jalaliDay": int(values.get("jalaliDay") or 0),
        }
        if holidayId:
            CalendarHolidayModel.objects.filter(tenantId=tenantId, id=holidayId).update(**defaults)
            row = CalendarHolidayModel.objects.get(tenantId=tenantId, id=holidayId)
        else:
            row = CalendarHolidayModel.objects.create(
                tenantId=tenantId, createdAt=now, **defaults
            )
        return self._holidayDict(row)

    def deleteHoliday(self, tenantId: uuid.UUID, holidayId: uuid.UUID, now: datetime) -> bool:
        return bool(
            CalendarHolidayModel.objects.filter(
                tenantId=tenantId, id=holidayId, deletedAt__isnull=True
            ).update(deletedAt=now)
        )

    # -- shifts -------------------------------------------------------------------
    def listShifts(self, tenantId: uuid.UUID, calendarId: uuid.UUID) -> list[dict]:
        rows = WorkShiftModel.objects.filter(
            tenantId=tenantId, calendarId=calendarId, deletedAt__isnull=True
        ).order_by("startTime")
        counts = self._assignmentCounts(tenantId, [row.id for row in rows])
        return [self._shiftDict(row, counts.get(row.id, 0)) for row in rows]

    def loadShiftSpecs(self, tenantId: uuid.UUID, calendarId: uuid.UUID) -> tuple[ShiftSpec, ...]:
        """Active shifts as pure specs, with the rostered crew as headcount.

        A real assignment outranks the planned figure: once a plant rosters
        people, capacity should follow the roster, not the intention. The
        configured ``headcount`` remains the fallback so capacity is non-zero
        before anybody has been assigned.
        """
        rows = list(
            WorkShiftModel.objects.filter(
                tenantId=tenantId, calendarId=calendarId, deletedAt__isnull=True, active=True
            ).order_by("startTime")
        )
        counts = self._assignmentCounts(tenantId, [row.id for row in rows])
        return tuple(
            ShiftSpec(
                code=row.code,
                startTime=row.startTime,
                endTime=row.endTime,
                weekdays=normaliseWeekendDays(row.weekdays),
                headcount=counts.get(row.id) or row.headcount,
            )
            for row in rows
        )

    def saveShift(self, tenantId: uuid.UUID, values: dict, now: datetime) -> dict:
        shiftId = values.get("id")
        defaults = {
            "calendarId": values["calendarId"],
            "code": values.get("code", ""),
            "name": values.get("name", ""),
            "kind": values.get("kind") or "general",
            "startTime": _parseTime(values.get("startTime", ""), time(8, 0)),
            "endTime": _parseTime(values.get("endTime", ""), time(16, 0)),
            "weekdays": _weekdaysToCsv(values.get("weekdays", "")),
            "headcount": int(values.get("headcount") or 0),
            "active": bool(values.get("active", True)),
            "updatedAt": now,
        }
        if shiftId:
            WorkShiftModel.objects.filter(tenantId=tenantId, id=shiftId).update(**defaults)
            row = WorkShiftModel.objects.get(tenantId=tenantId, id=shiftId)
        else:
            row = WorkShiftModel.objects.create(tenantId=tenantId, createdAt=now, **defaults)
        counts = self._assignmentCounts(tenantId, [row.id])
        return self._shiftDict(row, counts.get(row.id, 0))

    def deleteShift(self, tenantId: uuid.UUID, shiftId: uuid.UUID, now: datetime) -> bool:
        updated = WorkShiftModel.objects.filter(
            tenantId=tenantId, id=shiftId, deletedAt__isnull=True
        ).update(deletedAt=now)
        if updated:
            ShiftAssignmentModel.objects.filter(
                tenantId=tenantId, shiftId=shiftId, deletedAt__isnull=True
            ).update(deletedAt=now)
        return bool(updated)

    # -- assignments --------------------------------------------------------------
    def listAssignments(self, tenantId: uuid.UUID, shiftId: uuid.UUID) -> list[dict]:
        rows = ShiftAssignmentModel.objects.filter(
            tenantId=tenantId, shiftId=shiftId, deletedAt__isnull=True
        ).order_by("-fromDate")
        names = dict(
            MaintenancePersonnelModel.objects.filter(
                tenantId=tenantId, id__in=[row.personnelId for row in rows]
            ).values_list("id", "fullName")
        )
        return [
            {
                "id": str(row.id),
                "shiftId": str(row.shiftId),
                "personnelId": str(row.personnelId),
                "personnelName": names.get(row.personnelId, ""),
                "fromDate": row.fromDate.isoformat(),
                "toDate": row.toDate.isoformat() if row.toDate else "",
            }
            for row in rows
        ]

    def saveAssignment(self, tenantId: uuid.UUID, values: dict, now: datetime) -> dict:
        row = ShiftAssignmentModel.objects.create(
            tenantId=tenantId,
            shiftId=values["shiftId"],
            personnelId=values["personnelId"],
            fromDate=values["fromDate"],
            toDate=values.get("toDate") or None,
            createdAt=now,
        )
        return {
            "id": str(row.id),
            "shiftId": str(row.shiftId),
            "personnelId": str(row.personnelId),
            "fromDate": row.fromDate.isoformat(),
            "toDate": row.toDate.isoformat() if row.toDate else "",
        }

    def deleteAssignment(
        self, tenantId: uuid.UUID, assignmentId: uuid.UUID, now: datetime
    ) -> bool:
        return bool(
            ShiftAssignmentModel.objects.filter(
                tenantId=tenantId, id=assignmentId, deletedAt__isnull=True
            ).update(deletedAt=now)
        )

    # -- helpers ------------------------------------------------------------------
    def _assignmentCounts(self, tenantId: uuid.UUID, shiftIds: list[uuid.UUID]) -> dict:
        """Currently-open assignments per shift.

        "Currently" means no end date or an end date still ahead; a technician
        who left the shift last month must not keep inflating its capacity.
        """
        if not shiftIds:
            return {}
        today = datetime.now(timezone.utc).date()
        counts: dict[uuid.UUID, int] = {}
        rows = ShiftAssignmentModel.objects.filter(
            tenantId=tenantId, shiftId__in=shiftIds, deletedAt__isnull=True, fromDate__lte=today
        )
        for row in rows:
            if row.toDate is not None and row.toDate < today:
                continue
            counts[row.shiftId] = counts.get(row.shiftId, 0) + 1
        return counts

    def _locationNames(self, tenantId: uuid.UUID) -> dict:
        return {
            row["id"]: row["path"] or row["name"]
            for row in MaintenanceLocationModel.objects.filter(
                tenantId=tenantId, deletedAt__isnull=True
            ).values("id", "name", "path")
        }

    def _calendarDict(self, row: WorkCalendarModel, locationNames: dict) -> dict:
        return {
            "id": str(row.id),
            "code": row.code,
            "name": row.name,
            "locationId": str(row.locationId) if row.locationId else "",
            "locationPath": locationNames.get(row.locationId, ""),
            "timezone": row.timezone,
            "weekendDays": list(normaliseWeekendDays(row.weekendDays)),
            "rollPolicy": row.rollPolicy,
            "isDefault": row.isDefault,
            "active": row.active,
            "note": row.note,
        }

    def _holidayDict(self, row: CalendarHolidayModel) -> dict:
        return {
            "id": str(row.id),
            "calendarId": str(row.calendarId),
            "onDate": row.onDate.isoformat(),
            "name": row.name,
            "kind": row.kind,
            "recursAnnually": row.recursAnnually,
            "jalaliMonth": row.jalaliMonth,
            "jalaliDay": row.jalaliDay,
        }

    def _shiftDict(self, row: WorkShiftModel, assignedCount: int) -> dict:
        spec = ShiftSpec(
            code=row.code,
            startTime=row.startTime,
            endTime=row.endTime,
            weekdays=normaliseWeekendDays(row.weekdays),
            headcount=assignedCount or row.headcount,
        )
        return {
            "id": str(row.id),
            "calendarId": str(row.calendarId),
            "code": row.code,
            "name": row.name,
            "kind": row.kind,
            "startTime": _timeToText(row.startTime),
            "endTime": _timeToText(row.endTime),
            "weekdays": list(normaliseWeekendDays(row.weekdays)),
            "headcount": row.headcount,
            "assignedCount": assignedCount,
            "effectiveHeadcount": spec.headcount,
            "durationHours": str(spec.durationHours),
            "capacityHours": str(spec.durationHours * spec.headcount),
            "crossesMidnight": spec.crossesMidnight,
            "active": row.active,
        }

    # -- PM demand ----------------------------------------------------------------
    def listPmDemand(self, tenantId: uuid.UUID, start: date, end: date) -> list[dict]:
        """Every PM occurrence due in the window, with its estimated hours.

        Mirrors the two sources the maintenance calendar already merges, and
        merges them the same way, so capacity and the calendar can never
        disagree about what is due:

        1. active PM plans whose derived ``nextDueOn`` lands in the window;
        2. device-level ``pmIntervalDays`` — but only for devices carrying no
           active plan, so a device covered by a named plan is not counted
           twice.

        The window is widened by the caller, not here: a job due just before
        ``start`` may still roll *into* the window off a holiday.
        """
        from apps.maintenance.domain.valueObjects.maintenanceState import FREQUENCY_DAYS
        from apps.maintenance.infrastructure.models import DeviceModel, PmPlanModel

        # Look a little either side: a job due just outside the window can roll
        # into it, and one due inside can roll out.
        lowerBound = start - timedelta(days=40)
        upperBound = end + timedelta(days=40)

        deviceRows = {
            row["id"]: row
            for row in DeviceModel.objects.filter(
                tenantId=tenantId, deletedAt__isnull=True
            ).values("id", "code", "name", "pmIntervalDays", "lastPmDate", "status")
        }

        jobs: list[dict] = []
        plannedDeviceIds: set[uuid.UUID] = set()
        plans = PmPlanModel.objects.filter(
            tenantId=tenantId, deletedAt__isnull=True, active=True
        ).values(
            "id",
            "deviceId",
            "title",
            "frequencyEvery",
            "frequencyUnit",
            "estimatedMinutes",
            "lastExecutedOn",
        )
        for plan in plans:
            plannedDeviceIds.add(plan["deviceId"])
            perUnit = FREQUENCY_DAYS.get(plan["frequencyUnit"])
            if perUnit is None or plan["lastExecutedOn"] is None:
                # Meter-driven or never executed: it has no calendar date, so
                # it cannot be placed on a day. The PM calendar lists it
                # separately as undated; capacity must not invent a date.
                continue
            period = perUnit * max(1, plan["frequencyEvery"])
            due = plan["lastExecutedOn"] + timedelta(days=period)
            if due < lowerBound or due > upperBound:
                continue
            device = deviceRows.get(plan["deviceId"], {})
            jobs.append(
                {
                    "deviceId": str(plan["deviceId"]),
                    "deviceCode": device.get("code", ""),
                    "deviceName": device.get("name", ""),
                    "title": plan["title"],
                    "dueOn": due,
                    "estimatedHours": self._minutesToHours(plan["estimatedMinutes"]),
                }
            )

        for deviceId, device in deviceRows.items():
            if deviceId in plannedDeviceIds:
                continue
            interval = device.get("pmIntervalDays") or 0
            lastPm = device.get("lastPmDate")
            if interval <= 0 or lastPm is None:
                continue
            due = lastPm + timedelta(days=interval)
            if due < lowerBound or due > upperBound:
                continue
            jobs.append(
                {
                    "deviceId": str(deviceId),
                    "deviceCode": device.get("code", ""),
                    "deviceName": device.get("name", ""),
                    "title": "",
                    "dueOn": due,
                    "estimatedHours": None,
                }
            )
        return jobs

    @staticmethod
    def _minutesToHours(minutes: object) -> object:
        """Estimated minutes to hours; None when the plan never estimated one.

        Returning None rather than zero matters: the use case substitutes a
        conservative default for an unestimated job, and a zero would instead
        claim the job is free.
        """
        try:
            value = int(minutes or 0)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return (Decimal(value) / Decimal("60")).quantize(Decimal("0.01"))
