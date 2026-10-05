"""End-to-end tests for the work calendar, shifts and capacity planning.

A Jalali date picker tells you how to *write* a date. These endpoints answer
the questions scheduling actually asks: is the plant open that day, who is on
shift, and can the crew absorb the PM load already booked onto it.

The tests drive real HTTP and then re-read the database, because the promise
that matters is "the closure took effect on the schedule", not "the response
had the right shape".
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.maintenance.infrastructure.models import (
    CalendarHolidayModel,
    DeviceModel,
    MaintenanceLocationModel,
    MaintenancePersonnelModel,
    PmPlanModel,
    ShiftAssignmentModel,
    WorkCalendarModel,
    WorkShiftModel,
)
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform

BASE = "/api/v1/maintenance"

# A known-good week. 2026-10-03 شنبه … 2026-10-09 جمعه.
SATURDAY = date(2026, 10, 3)
MONDAY = date(2026, 10, 5)
THURSDAY = date(2026, 10, 8)
FRIDAY = date(2026, 10, 9)


class WorkCalendarApiTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

        self.site = self._location("SITE-A", "سایت الف", "site", None)
        self.line = self._location("LINE-A", "خط ۱", "line", self.site)
        self.calendar = self._calendar("CAL-A", "تقویم سایت الف", self.site, isDefault=True)

    # -- helpers ------------------------------------------------------------------
    def _location(self, code: str, name: str, kind: str, parent: uuid.UUID | None) -> uuid.UUID:
        from django.utils import timezone as djtz

        parentRow = MaintenanceLocationModel.objects.filter(id=parent).first() if parent else None
        path = f"{parentRow.path} / {name}" if parentRow else name
        row = MaintenanceLocationModel.objects.create(
            tenantId=self.tenantId,
            code=code,
            name=name,
            kind=kind,
            parentId=parent,
            path=path,
            createdAt=djtz.now(),
        )
        return row.id

    def _calendar(
        self,
        code: str,
        name: str,
        locationId: uuid.UUID | None,
        *,
        weekend: str = "4",
        isDefault: bool = False,
        rollPolicy: str = "forward",
    ) -> uuid.UUID:
        from django.utils import timezone as djtz

        row = WorkCalendarModel.objects.create(
            tenantId=self.tenantId,
            code=code,
            name=name,
            locationId=locationId,
            timezone="Asia/Tehran",
            weekendDays=weekend,
            rollPolicy=rollPolicy,
            isDefault=isDefault,
            createdAt=djtz.now(),
        )
        return row.id

    def _holiday(self, calendarId: uuid.UUID, onDate: date, name: str) -> uuid.UUID:
        from django.utils import timezone as djtz

        row = CalendarHolidayModel.objects.create(
            tenantId=self.tenantId,
            calendarId=calendarId,
            onDate=onDate,
            name=name,
            kind="official",
            createdAt=djtz.now(),
        )
        return row.id

    def _shift(
        self,
        calendarId: uuid.UUID,
        code: str,
        start: str,
        end: str,
        crew: int,
        weekdays: str = "",
    ) -> uuid.UUID:
        from datetime import time as dtime

        from django.utils import timezone as djtz

        startH, startM = (int(part) for part in start.split(":"))
        endH, endM = (int(part) for part in end.split(":"))
        row = WorkShiftModel.objects.create(
            tenantId=self.tenantId,
            calendarId=calendarId,
            code=code,
            name=code,
            kind="general",
            startTime=dtime(startH, startM),
            endTime=dtime(endH, endM),
            weekdays=weekdays,
            headcount=crew,
            createdAt=djtz.now(),
        )
        return row.id

    def _device(self, code: str, locationId: uuid.UUID | None = None) -> uuid.UUID:
        from django.utils import timezone as djtz

        row = DeviceModel.objects.create(
            tenantId=self.tenantId,
            code=code,
            name=code,
            status="operational",
            locationId=locationId,
            createdAt=djtz.now(),
        )
        return row.id

    def _plan(
        self, deviceId: uuid.UUID, title: str, lastExecutedOn: date, minutes: int = 0
    ) -> uuid.UUID:
        from django.utils import timezone as djtz

        row = PmPlanModel.objects.create(
            tenantId=self.tenantId,
            deviceId=deviceId,
            title=title,
            frequencyEvery=1,
            frequencyUnit="week",
            estimatedMinutes=minutes,
            lastExecutedOn=lastExecutedOn,
            active=True,
            createdAt=djtz.now(),
        )
        return row.id

    # =============================================================================
    # Calendars
    # =============================================================================
    def testListsCalendarsWithTheirShiftsAndHolidayCount(self) -> None:
        self._shift(self.calendar, "SH-A", "06:00", "14:00", 4)
        self._holiday(self.calendar, MONDAY, "تعطیل آزمایشی")

        response = self.client.get(f"{BASE}/work-calendars", **self.auth)

        self.assertEqual(response.status_code, 200)
        items = response.json()["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["code"], "CAL-A")
        self.assertEqual(items[0]["holidayCount"], 1)
        self.assertEqual(len(items[0]["shifts"]), 1)
        self.assertEqual(items[0]["weekendDays"], [4])

    def testCreatesACalendarAndMakesItTheOnlyDefault(self) -> None:
        """Two defaults would make the fallback ambiguous."""
        response = self.client.post(
            f"{BASE}/work-calendars",
            {
                "code": "CAL-B",
                "name": "تقویم دوم",
                "weekendDays": [3, 4],
                "isDefault": True,
                "timezone": "Asia/Tehran",
            },
            format="json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["data"]["weekendDays"], [3, 4])
        defaults = WorkCalendarModel.objects.filter(
            tenantId=self.tenantId, isDefault=True, deletedAt__isnull=True
        )
        self.assertEqual(defaults.count(), 1)
        self.assertEqual(defaults.first().code, "CAL-B")

    def testRejectsACalendarWithNoWorkingDayLeft(self) -> None:
        response = self.client.post(
            f"{BASE}/work-calendars",
            {"code": "CAL-X", "name": "هیچ", "weekendDays": [0, 1, 2, 3, 4, 5, 6]},
            format="json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertFalse(
            WorkCalendarModel.objects.filter(tenantId=self.tenantId, code="CAL-X").exists()
        )

    def testRejectsAnUnknownRollPolicy(self) -> None:
        response = self.client.post(
            f"{BASE}/work-calendars",
            {"code": "CAL-Y", "name": "بد", "rollPolicy": "sideways"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def testDeletingACalendarTakesItsHolidaysAndShiftsWithIt(self) -> None:
        """Orphans would be inherited by any calendar reusing the id."""
        self._holiday(self.calendar, MONDAY, "x")
        self._shift(self.calendar, "SH-A", "06:00", "14:00", 2)

        response = self.client.delete(f"{BASE}/work-calendars/{self.calendar}", **self.auth)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            CalendarHolidayModel.objects.filter(
                calendarId=self.calendar, deletedAt__isnull=True
            ).exists()
        )
        self.assertFalse(
            WorkShiftModel.objects.filter(calendarId=self.calendar, deletedAt__isnull=True).exists()
        )

    # =============================================================================
    # Holidays
    # =============================================================================
    def testAddsAHolidayAndItClosesTheDay(self) -> None:
        response = self.client.post(
            f"{BASE}/work-calendars/holidays",
            {
                "calendarId": str(self.calendar),
                "onDate": MONDAY.isoformat(),
                "name": "نوروز",
                "kind": "official",
                "recursAnnually": True,
                "jalaliMonth": 1,
                "jalaliDay": 1,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)

        check = self.client.get(
            f"{BASE}/work-calendars/working-day",
            {"calendarId": str(self.calendar), "onDate": MONDAY.isoformat()},
            **self.auth,
        ).json()["data"]
        self.assertFalse(check["isWorkingDay"])
        self.assertTrue(check["isHoliday"])

    def testRejectsAHolidayWithoutAValidDate(self) -> None:
        response = self.client.post(
            f"{BASE}/work-calendars/holidays",
            {"calendarId": str(self.calendar), "onDate": "not-a-date", "name": "x"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def testRejectsAnUnknownHolidayKind(self) -> None:
        response = self.client.post(
            f"{BASE}/work-calendars/holidays",
            {
                "calendarId": str(self.calendar),
                "onDate": MONDAY.isoformat(),
                "name": "x",
                "kind": "invented",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def testListsHolidaysInsideAWindowOnly(self) -> None:
        self._holiday(self.calendar, MONDAY, "داخل")
        self._holiday(self.calendar, date(2027, 1, 1), "بیرون")

        response = self.client.get(
            f"{BASE}/work-calendars/holidays",
            {
                "calendarId": str(self.calendar),
                "fromDate": SATURDAY.isoformat(),
                "toDate": FRIDAY.isoformat(),
            },
            **self.auth,
        )

        names = [row["name"] for row in response.json()["data"]["items"]]
        self.assertEqual(names, ["داخل"])

    def testDeletingAHolidayReopensTheDay(self) -> None:
        holidayId = self._holiday(self.calendar, MONDAY, "موقت")

        self.client.delete(f"{BASE}/work-calendars/holidays/{holidayId}", **self.auth)

        check = self.client.get(
            f"{BASE}/work-calendars/working-day",
            {"calendarId": str(self.calendar), "onDate": MONDAY.isoformat()},
            **self.auth,
        ).json()["data"]
        self.assertTrue(check["isWorkingDay"])

    # =============================================================================
    # Working day / rolling
    # =============================================================================
    def testFridayIsNotAWorkingDayAndRollsForward(self) -> None:
        response = self.client.get(
            f"{BASE}/work-calendars/working-day",
            {"calendarId": str(self.calendar), "onDate": FRIDAY.isoformat()},
            **self.auth,
        )

        data = response.json()["data"]
        self.assertFalse(data["isWorkingDay"])
        self.assertTrue(data["isWeekend"])
        self.assertTrue(data["rolled"])
        self.assertEqual(data["plannedOn"], "2026-10-10")

    def testBackwardPolicyPullsTheJobEarlierInstead(self) -> None:
        backward = self._calendar("CAL-BK", "عقب‌رو", None, rollPolicy="backward")
        response = self.client.get(
            f"{BASE}/work-calendars/working-day",
            {"calendarId": str(backward), "onDate": FRIDAY.isoformat()},
            **self.auth,
        )
        self.assertEqual(response.json()["data"]["plannedOn"], THURSDAY.isoformat())

    def testRollSkipsAMultiDayHolidayRun(self) -> None:
        """نوروز closes four days; the job must clear all of them."""
        for offset in range(4):
            self._holiday(self.calendar, SATURDAY + timedelta(days=offset), "نوروز")

        response = self.client.get(
            f"{BASE}/work-calendars/working-day",
            {"calendarId": str(self.calendar), "onDate": SATURDAY.isoformat()},
            **self.auth,
        )
        self.assertEqual(response.json()["data"]["plannedOn"], "2026-10-07")

    def testAddWorkingDaysSkipsClosures(self) -> None:
        response = self.client.get(
            f"{BASE}/work-calendars/working-day",
            {
                "calendarId": str(self.calendar),
                "onDate": "2026-10-07",
                "addWorkingDays": 3,
            },
            **self.auth,
        )
        self.assertEqual(response.json()["data"]["addWorkingDays"], "2026-10-11")

    def testADeviceInheritsItsSitesCalendar(self) -> None:
        """A machine on a line under a site must resolve the site's calendar."""
        deviceId = self._device("DEV-1", self.line)

        response = self.client.get(
            f"{BASE}/work-calendars/working-day",
            {"deviceId": str(deviceId), "onDate": FRIDAY.isoformat()},
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["calendarId"], str(self.calendar))
        self.assertFalse(response.json()["data"]["isWorkingDay"])

    def testASiteWithItsOwnCalendarOverridesTheTenantDefault(self) -> None:
        """Multi-site: the nearer calendar wins."""
        otherSite = self._location("SITE-B", "سایت ب", "site", None)
        otherLine = self._location("LINE-B", "خط ب", "line", otherSite)
        # سایت ب also closes پنجشنبه.
        self._calendar("CAL-B", "تقویم سایت ب", otherSite, weekend="3,4")
        deviceId = self._device("DEV-B", otherLine)

        response = self.client.get(
            f"{BASE}/work-calendars/working-day",
            {"deviceId": str(deviceId), "onDate": THURSDAY.isoformat()},
            **self.auth,
        )

        data = response.json()["data"]
        self.assertFalse(data["isWorkingDay"], "سایت ب پنجشنبه تعطیل است")

        # …while the first site is still open that day.
        atSiteA = self.client.get(
            f"{BASE}/work-calendars/working-day",
            {"calendarId": str(self.calendar), "onDate": THURSDAY.isoformat()},
            **self.auth,
        ).json()["data"]
        self.assertTrue(atSiteA["isWorkingDay"])

    def testUnknownCalendarIdIs404(self) -> None:
        response = self.client.get(
            f"{BASE}/work-calendars/working-day",
            {"calendarId": str(uuid.uuid4()), "onDate": MONDAY.isoformat()},
            **self.auth,
        )
        self.assertEqual(response.status_code, 404)

    # =============================================================================
    # Shifts
    # =============================================================================
    def testCreatesAShiftAndReportsItsDurationAndCapacity(self) -> None:
        response = self.client.post(
            f"{BASE}/work-calendars/shifts",
            {
                "calendarId": str(self.calendar),
                "code": "SH-A",
                "name": "صبح",
                "kind": "morning",
                "startTime": "06:00",
                "endTime": "14:00",
                "headcount": 4,
            },
            format="json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]
        self.assertEqual(data["durationHours"], "8.00")
        self.assertEqual(data["capacityHours"], "32.00")
        self.assertFalse(data["crossesMidnight"])

    def testNightShiftIsStoredAsCrossingMidnight(self) -> None:
        response = self.client.post(
            f"{BASE}/work-calendars/shifts",
            {
                "calendarId": str(self.calendar),
                "code": "SH-C",
                "name": "شب",
                "kind": "night",
                "startTime": "22:00",
                "endTime": "06:00",
                "headcount": 2,
            },
            format="json",
            **self.auth,
        )

        data = response.json()["data"]
        self.assertTrue(data["crossesMidnight"])
        self.assertEqual(data["durationHours"], "8.00")

    def testRejectsAnUnknownShiftKind(self) -> None:
        response = self.client.post(
            f"{BASE}/work-calendars/shifts",
            {
                "calendarId": str(self.calendar),
                "code": "SH-Z",
                "name": "z",
                "kind": "twilight",
                "startTime": "06:00",
                "endTime": "14:00",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def testRosteredCrewOverridesThePlannedHeadcount(self) -> None:
        """Once people are assigned, capacity follows the roster."""
        from django.utils import timezone as djtz

        shiftId = self._shift(self.calendar, "SH-A", "06:00", "14:00", crew=1)
        for index in range(3):
            person = MaintenancePersonnelModel.objects.create(
                tenantId=self.tenantId,
                personnelCode=f"P-{index}",
                fullName=f"تکنسین {index}",
                createdAt=djtz.now(),
            )
            ShiftAssignmentModel.objects.create(
                tenantId=self.tenantId,
                shiftId=shiftId,
                personnelId=person.id,
                fromDate=date(2020, 1, 1),
                createdAt=djtz.now(),
            )

        plan = self.client.get(
            f"{BASE}/work-calendars/capacity",
            {
                "calendarId": str(self.calendar),
                "fromDate": SATURDAY.isoformat(),
                "toDate": SATURDAY.isoformat(),
            },
            **self.auth,
        ).json()["data"]

        # 8 hours × 3 rostered, not × 1 planned.
        self.assertEqual(plan["days"][0]["capacityHours"], "24.00")

    def testAnExpiredAssignmentStopsCountingTowardsCapacity(self) -> None:
        from django.utils import timezone as djtz

        shiftId = self._shift(self.calendar, "SH-A", "06:00", "14:00", crew=0)
        person = MaintenancePersonnelModel.objects.create(
            tenantId=self.tenantId,
            personnelCode="P-OLD",
            fullName="رفته",
            createdAt=djtz.now(),
        )
        ShiftAssignmentModel.objects.create(
            tenantId=self.tenantId,
            shiftId=shiftId,
            personnelId=person.id,
            fromDate=date(2020, 1, 1),
            toDate=date(2020, 6, 1),
            createdAt=djtz.now(),
        )

        plan = self.client.get(
            f"{BASE}/work-calendars/capacity",
            {
                "calendarId": str(self.calendar),
                "fromDate": SATURDAY.isoformat(),
                "toDate": SATURDAY.isoformat(),
            },
            **self.auth,
        ).json()["data"]
        self.assertEqual(plan["days"][0]["capacityHours"], "0.00")

    def testAssignmentCannotEndBeforeItStarts(self) -> None:
        shiftId = self._shift(self.calendar, "SH-A", "06:00", "14:00", crew=1)
        from django.utils import timezone as djtz

        person = MaintenancePersonnelModel.objects.create(
            tenantId=self.tenantId,
            personnelCode="P-1",
            fullName="تکنسین",
            createdAt=djtz.now(),
        )

        response = self.client.post(
            f"{BASE}/work-calendars/assignments",
            {
                "shiftId": str(shiftId),
                "personnelId": str(person.id),
                "fromDate": "2026-10-10",
                "toDate": "2026-10-01",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    # =============================================================================
    # Capacity planning
    # =============================================================================
    def testCapacityPlanReportsZeroOnClosedDaysAndFullOnOpenOnes(self) -> None:
        self._shift(self.calendar, "SH-A", "06:00", "14:00", crew=4)

        plan = self.client.get(
            f"{BASE}/work-calendars/capacity",
            {
                "calendarId": str(self.calendar),
                "fromDate": SATURDAY.isoformat(),
                "toDate": FRIDAY.isoformat(),
            },
            **self.auth,
        ).json()["data"]

        byDate = {day["onDate"]: day for day in plan["days"]}
        self.assertEqual(byDate[SATURDAY.isoformat()]["capacityHours"], "32.00")
        self.assertEqual(byDate[FRIDAY.isoformat()]["capacityHours"], "0")
        self.assertFalse(byDate[FRIDAY.isoformat()]["isWorkingDay"])
        self.assertEqual(plan["summary"]["workingDays"], 6)
        self.assertEqual(plan["summary"]["closedDays"], 1)

    def testPmDueOnAClosedDayIsPlannedOntoTheNextWorkingDay(self) -> None:
        """The whole point: demand lands where the work will really happen."""
        self._shift(self.calendar, "SH-A", "06:00", "14:00", crew=4)
        deviceId = self._device("DEV-1", self.line)
        # weekly plan last executed جمعه-7 ⇒ due جمعه 2026-10-09
        self._plan(deviceId, "روانکاری", FRIDAY - timedelta(days=7), minutes=120)

        plan = self.client.get(
            f"{BASE}/work-calendars/capacity",
            {
                "calendarId": str(self.calendar),
                "fromDate": SATURDAY.isoformat(),
                "toDate": date(2026, 10, 12).isoformat(),
            },
            **self.auth,
        ).json()["data"]

        byDate = {day["onDate"]: day for day in plan["days"]}
        self.assertEqual(byDate[FRIDAY.isoformat()]["jobCount"], 0, "جمعه کسی نیست")
        saturdayAfter = byDate["2026-10-10"]
        self.assertEqual(saturdayAfter["jobCount"], 1)
        self.assertEqual(saturdayAfter["demandHours"], "2.00")
        self.assertTrue(saturdayAfter["jobs"][0]["rolled"])
        self.assertEqual(saturdayAfter["jobs"][0]["dueOn"], FRIDAY.isoformat())

    def testEstimatedMinutesDriveDemandHours(self) -> None:
        self._shift(self.calendar, "SH-A", "06:00", "14:00", crew=1)
        deviceId = self._device("DEV-1", self.line)
        self._plan(deviceId, "بازرسی", SATURDAY - timedelta(days=7), minutes=90)

        plan = self.client.get(
            f"{BASE}/work-calendars/capacity",
            {
                "calendarId": str(self.calendar),
                "fromDate": SATURDAY.isoformat(),
                "toDate": SATURDAY.isoformat(),
            },
            **self.auth,
        ).json()["data"]

        self.assertEqual(plan["days"][0]["demandHours"], "1.50")

    def testAnUnestimatedPlanUsesTheConservativeDefault(self) -> None:
        """Zero would claim the job is free and hide the over-commitment."""
        self._shift(self.calendar, "SH-A", "06:00", "14:00", crew=1)
        deviceId = self._device("DEV-1", self.line)
        self._plan(deviceId, "بدون برآورد", SATURDAY - timedelta(days=7), minutes=0)

        plan = self.client.get(
            f"{BASE}/work-calendars/capacity",
            {
                "calendarId": str(self.calendar),
                "fromDate": SATURDAY.isoformat(),
                "toDate": SATURDAY.isoformat(),
            },
            **self.auth,
        ).json()["data"]
        self.assertEqual(plan["days"][0]["demandHours"], "2")

    def testOverCommitmentIsFlagged(self) -> None:
        """One technician, eight hours, five two-hour jobs on the same day."""
        self._shift(self.calendar, "SH-A", "06:00", "14:00", crew=1)
        for index in range(5):
            deviceId = self._device(f"DEV-{index}", self.line)
            self._plan(deviceId, f"کار {index}", SATURDAY - timedelta(days=7), minutes=120)

        plan = self.client.get(
            f"{BASE}/work-calendars/capacity",
            {
                "calendarId": str(self.calendar),
                "fromDate": SATURDAY.isoformat(),
                "toDate": SATURDAY.isoformat(),
            },
            **self.auth,
        ).json()["data"]

        day = plan["days"][0]
        self.assertEqual(day["demandHours"], "10.00")
        self.assertEqual(day["capacityHours"], "8.00")
        self.assertEqual(day["utilisationPercent"], "125.0")
        self.assertEqual(plan["summary"]["overloadedDays"], 1)

    def testADeviceCoveredByAPlanIsNotCountedTwice(self) -> None:
        """Legacy pmIntervalDays must not double-book a planned device."""

        self._shift(self.calendar, "SH-A", "06:00", "14:00", crew=2)
        deviceId = self._device("DEV-1", self.line)
        DeviceModel.objects.filter(id=deviceId).update(
            pmIntervalDays=7, lastPmDate=SATURDAY - timedelta(days=7)
        )
        self._plan(deviceId, "برنامهٔ نام‌دار", SATURDAY - timedelta(days=7), minutes=60)

        plan = self.client.get(
            f"{BASE}/work-calendars/capacity",
            {
                "calendarId": str(self.calendar),
                "fromDate": SATURDAY.isoformat(),
                "toDate": SATURDAY.isoformat(),
            },
            **self.auth,
        ).json()["data"]

        self.assertEqual(plan["days"][0]["jobCount"], 1)
        self.assertEqual(plan["days"][0]["demandHours"], "1.00")

    def testMeterDrivenPlansAreNotGivenAnInventedDate(self) -> None:
        self._shift(self.calendar, "SH-A", "06:00", "14:00", crew=2)
        deviceId = self._device("DEV-1", self.line)
        PmPlanModel.objects.create(
            tenantId=self.tenantId,
            deviceId=deviceId,
            title="بر اساس کارکرد",
            frequencyEvery=500,
            frequencyUnit="runningHour",
            lastExecutedOn=SATURDAY - timedelta(days=7),
            active=True,
            createdAt=__import__("django.utils.timezone", fromlist=["now"]).now(),
        )

        plan = self.client.get(
            f"{BASE}/work-calendars/capacity",
            {
                "calendarId": str(self.calendar),
                "fromDate": SATURDAY.isoformat(),
                "toDate": FRIDAY.isoformat(),
            },
            **self.auth,
        ).json()["data"]

        self.assertEqual(sum(day["jobCount"] for day in plan["days"]), 0)

    def testPlanWindowIsBounded(self) -> None:
        """An open-ended range would materialise a dict per day forever."""
        plan = self.client.get(
            f"{BASE}/work-calendars/capacity",
            {
                "calendarId": str(self.calendar),
                "fromDate": "2026-01-01",
                "toDate": "2035-01-01",
            },
            **self.auth,
        ).json()["data"]

        self.assertLessEqual(len(plan["days"]), 371)

    def testInvertedWindowIsSwappedNotRejected(self) -> None:
        plan = self.client.get(
            f"{BASE}/work-calendars/capacity",
            {
                "calendarId": str(self.calendar),
                "fromDate": FRIDAY.isoformat(),
                "toDate": SATURDAY.isoformat(),
            },
            **self.auth,
        ).json()["data"]

        self.assertEqual(plan["fromDate"], SATURDAY.isoformat())
        self.assertEqual(plan["toDate"], FRIDAY.isoformat())

    # =============================================================================
    # Auth
    # =============================================================================
    def testEveryEndpointRefusesAnAnonymousCaller(self) -> None:
        anonymous = APIClient()
        for method, url in (
            ("get", f"{BASE}/work-calendars"),
            ("get", f"{BASE}/work-calendars/capacity"),
            ("get", f"{BASE}/work-calendars/working-day"),
            ("post", f"{BASE}/work-calendars"),
            ("post", f"{BASE}/work-calendars/holidays"),
            ("post", f"{BASE}/work-calendars/shifts"),
        ):
            with self.subTest(url=url, method=method):
                response = getattr(anonymous, method)(url)
                self.assertIn(response.status_code, (401, 403))


class RecurringHolidayTests(TestCase):
    """A holiday ticked «هر سال تکرار می‌شود» must actually recur (Phase 28.1).

    Before this, `recursAnnually` was stored and echoed back by the API but
    never consulted, so نوروز entered for 1405 left the plant wide open on
    نوروز 1406. These tests pin the behaviour the checkbox promises.
    """

    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        from django.utils import timezone as djtz

        self.calendar = WorkCalendarModel.objects.create(
            tenantId=self.tenantId,
            code="CAL-R",
            name="تقویم تکرار",
            timezone="Asia/Tehran",
            weekendDays="4",
            rollPolicy="forward",
            isDefault=True,
            active=True,
            createdAt=djtz.now(),
        ).id

    def _addHoliday(self, onDate: date, name: str, recurs: bool) -> dict:
        response = self.client.post(
            f"{BASE}/work-calendars/holidays",
            {
                "calendarId": str(self.calendar),
                "onDate": onDate.isoformat(),
                "name": name,
                "kind": "official",
                "recursAnnually": recurs,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def _workingDay(self, onDate: date) -> dict:
        return self.client.get(
            f"{BASE}/work-calendars/working-day",
            {"calendarId": str(self.calendar), "onDate": onDate.isoformat()},
            **self.auth,
        ).json()["data"]

    def testServerDerivesJalaliPartsEvenWhenTheClientSendsNone(self) -> None:
        """The web form never sent them, which silently disabled recurrence."""
        saved = self._addHoliday(date(2026, 3, 21), "نوروز", recurs=True)
        self.assertEqual(saved["jalaliMonth"], 1)
        self.assertEqual(saved["jalaliDay"], 1)

    def testRecurringHolidayClosesTheSameJalaliDayNextYear(self) -> None:
        self._addHoliday(date(2026, 3, 21), "نوروز", recurs=True)
        # Entered for 1405 only; 1406's نوروز is a different Gregorian date.
        nextYear = self._workingDay(date(2027, 3, 21))
        self.assertTrue(nextYear["isHoliday"])
        self.assertFalse(nextYear["isWorkingDay"])

    def testRecurrenceTracksTheJalaliDateNotTheGregorianOne(self) -> None:
        """نوروز 1407 is 20 March, not 21 — the drift that makes this hard."""
        self._addHoliday(date(2026, 3, 21), "نوروز", recurs=True)
        self.assertTrue(self._workingDay(date(2028, 3, 20))["isHoliday"])
        self.assertFalse(self._workingDay(date(2028, 3, 21))["isHoliday"])

    def testNonRecurringHolidayStaysInItsOwnYear(self) -> None:
        """The checkbox has to mean something in both positions."""
        self._addHoliday(date(2026, 6, 10), "توقف موردی", recurs=False)
        self.assertTrue(self._workingDay(date(2026, 6, 10))["isHoliday"])
        self.assertFalse(self._workingDay(date(2027, 6, 10))["isHoliday"])

    def testCapacityPlanTreatsAProjectedHolidayAsClosed(self) -> None:
        self._addHoliday(date(2026, 3, 21), "نوروز", recurs=True)
        plan = self.client.get(
            f"{BASE}/work-calendars/capacity",
            {
                "calendarId": str(self.calendar),
                "fromDate": "2027-03-20",
                "toDate": "2027-03-23",
            },
            **self.auth,
        ).json()["data"]
        byDate = {day["onDate"]: day for day in plan["days"]}
        self.assertFalse(byDate["2027-03-21"]["isWorkingDay"])
        self.assertTrue(byDate["2027-03-21"]["isHoliday"])
        # A shut day buys no hours; the API may format that as "0" or "0.00".
        self.assertEqual(float(byDate["2027-03-21"]["capacityHours"]), 0.0)

    def testARolledJobSkipsAProjectedHoliday(self) -> None:
        """The point of the whole feature: work moves off a recurring holiday."""
        self._addHoliday(date(2026, 3, 21), "نوروز", recurs=True)
        answer = self.client.get(
            f"{BASE}/work-calendars/working-day",
            {"calendarId": str(self.calendar), "onDate": "2027-03-21"},
            **self.auth,
        ).json()["data"]
        self.assertFalse(answer["isWorkingDay"])
        self.assertTrue(answer["rolled"])
        self.assertNotEqual(answer["plannedOn"], "2027-03-21")

    def testWindowedListProjectsOccurrencesWithTheirName(self) -> None:
        self._addHoliday(date(2026, 3, 21), "نوروز", recurs=True)
        payload = self.client.get(
            f"{BASE}/work-calendars/holidays",
            {
                "calendarId": str(self.calendar),
                "fromDate": "2027-01-01",
                "toDate": "2027-12-31",
            },
            **self.auth,
        ).json()["data"]
        items = payload["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["onDate"], "2027-03-21")
        self.assertEqual(items[0]["name"], "نوروز")
        self.assertTrue(items[0]["projected"])

    def testUnwindowedListStillReturnsOnlyRealRows(self) -> None:
        """The management table must not offer a delete button for a ghost."""
        self._addHoliday(date(2026, 3, 21), "نوروز", recurs=True)
        payload = self.client.get(
            f"{BASE}/work-calendars/holidays",
            {"calendarId": str(self.calendar)},
            **self.auth,
        ).json()["data"]
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["onDate"], "2026-03-21")
        self.assertFalse(payload["items"][0]["projected"])
        self.assertEqual(
            CalendarHolidayModel.objects.filter(
                calendarId=self.calendar, deletedAt__isnull=True
            ).count(),
            1,
        )

    def testDeletingTheSourceStopsEveryFutureOccurrence(self) -> None:
        saved = self._addHoliday(date(2026, 3, 21), "نوروز", recurs=True)
        self.assertTrue(self._workingDay(date(2027, 3, 21))["isHoliday"])
        response = self.client.delete(f"{BASE}/work-calendars/holidays/{saved['id']}", **self.auth)
        self.assertIn(response.status_code, (200, 204))
        self.assertFalse(self._workingDay(date(2027, 3, 21))["isHoliday"])
