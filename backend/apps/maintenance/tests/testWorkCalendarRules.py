"""Unit tests for the pure work-calendar rules.

No database. This is the arithmetic that decides when maintenance can actually
happen, so it is asserted exhaustively — including the awkward cases that a
Jalali date picker never has to think about: night shifts crossing midnight,
holidays landing on an already-closed day, and a calendar configured so badly
that nobody ever works.

Weekday reference used throughout (python ``date.weekday()``):
    2026-10-03 شنبه = 5   2026-10-04 یکشنبه = 6   2026-10-05 دوشنبه = 0
    2026-10-06 سه‌شنبه = 1  2026-10-07 چهارشنبه = 2  2026-10-08 پنجشنبه = 3
    2026-10-09 جمعه = 4
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.test import SimpleTestCase

from apps.maintenance.domain.services.workCalendarRules import (
    CalendarSpec,
    ShiftSpec,
    addWorkingDays,
    coveringShift,
    dailyCapacityHours,
    isHoliday,
    isWeekend,
    isWorkingDay,
    nextWorkingDay,
    normaliseWeekendDays,
    overtimeHours,
    previousWorkingDay,
    rollToWorkingDay,
    shiftCapacityHours,
    shiftsOn,
    utilisationPercent,
    workingDaysBetween,
)
from apps.maintenance.domain.valueObjects.maintenanceState import (
    FRIDAY,
    ROLL_BACKWARD,
    ROLL_FORWARD,
    ROLL_NONE,
    THURSDAY,
)

FRIDAY_DATE = date(2026, 10, 9)
SATURDAY_DATE = date(2026, 10, 3)
THURSDAY_DATE = date(2026, 10, 8)
NOWRUZ = date(2027, 3, 21)


def irCalendar(**overrides: object) -> CalendarSpec:
    """A plain Iranian week: جمعه off, nothing else."""
    base: dict[str, object] = {"weekendDays": (FRIDAY,), "holidays": frozenset()}
    base.update(overrides)
    return CalendarSpec(**base)  # type: ignore[arg-type]


# =================================================================================
# Weekend parsing
# =================================================================================


class NormaliseWeekendDaysTests(SimpleTestCase):
    def testParsesCsvFromTheDatabaseColumn(self) -> None:
        self.assertEqual(normaliseWeekendDays("4,3"), (3, 4))

    def testAcceptsListsAndSets(self) -> None:
        self.assertEqual(normaliseWeekendDays([4, 3, 3]), (3, 4))
        self.assertEqual(normaliseWeekendDays({4}), (4,))

    def testDropsJunkRatherThanRaising(self) -> None:
        """A malformed column must degrade, never take scheduling down."""
        self.assertEqual(normaliseWeekendDays("4,abc,,9,-1"), (4,))

    def testNoneAndNonsenseGiveEmpty(self) -> None:
        self.assertEqual(normaliseWeekendDays(None), ())
        self.assertEqual(normaliseWeekendDays(42), ())

    def testDeduplicatesAndSorts(self) -> None:
        self.assertEqual(normaliseWeekendDays("6,0,6,0"), (0, 6))


# =================================================================================
# Working days
# =================================================================================


class WorkingDayTests(SimpleTestCase):
    def testFridayIsTheWeekend(self) -> None:
        self.assertTrue(isWeekend(irCalendar(), FRIDAY_DATE))
        self.assertFalse(isWorkingDay(irCalendar(), FRIDAY_DATE))

    def testSaturdayIsAWorkingDay(self) -> None:
        self.assertTrue(isWorkingDay(irCalendar(), SATURDAY_DATE))

    def testAPlantCanAlsoCloseThursday(self) -> None:
        spec = irCalendar(weekendDays=(THURSDAY, FRIDAY))
        self.assertFalse(isWorkingDay(spec, THURSDAY_DATE))
        self.assertTrue(isWorkingDay(spec, SATURDAY_DATE))

    def testHolidayClosesAnOtherwiseWorkingDay(self) -> None:
        spec = irCalendar(holidays=frozenset({SATURDAY_DATE}))
        self.assertTrue(isHoliday(spec, SATURDAY_DATE))
        self.assertFalse(isWorkingDay(spec, SATURDAY_DATE))

    def testHolidayOnAnAlreadyClosedDayIsNotAnError(self) -> None:
        """نوروز falling on جمعه must not double-count or misbehave."""
        spec = irCalendar(holidays=frozenset({FRIDAY_DATE}))
        self.assertFalse(isWorkingDay(spec, FRIDAY_DATE))
        self.assertEqual(nextWorkingDay(spec, FRIDAY_DATE), date(2026, 10, 10))


class NextWorkingDayTests(SimpleTestCase):
    def testReturnsTheSameDayWhenAlreadyWorking(self) -> None:
        self.assertEqual(nextWorkingDay(irCalendar(), SATURDAY_DATE), SATURDAY_DATE)

    def testExclusiveAlwaysMovesAtLeastOneDay(self) -> None:
        """"Schedule the next one" must not return the day just completed."""
        self.assertEqual(
            nextWorkingDay(irCalendar(), SATURDAY_DATE, inclusive=False),
            date(2026, 10, 4),
        )

    def testSkipsTheWeekend(self) -> None:
        self.assertEqual(nextWorkingDay(irCalendar(), FRIDAY_DATE), date(2026, 10, 10))

    def testSkipsAHolidayRunIntoTheFollowingWeek(self) -> None:
        closed = frozenset({date(2026, 10, 10), date(2026, 10, 11)})
        spec = irCalendar(holidays=closed)
        self.assertEqual(nextWorkingDay(spec, FRIDAY_DATE), date(2026, 10, 12))

    def testPreviousWorkingDayWalksBackwards(self) -> None:
        self.assertEqual(
            previousWorkingDay(irCalendar(), FRIDAY_DATE), THURSDAY_DATE
        )

    def testACalendarWithNoWorkingDayReturnsTheDateUnchanged(self) -> None:
        """A seven-day weekend must not hang the scheduler."""
        spec = irCalendar(weekendDays=(0, 1, 2, 3, 4, 5, 6))
        self.assertFalse(spec.hasWorkingDay)
        self.assertEqual(nextWorkingDay(spec, SATURDAY_DATE), SATURDAY_DATE)

    def testAYearOfHolidaysGivesUpRatherThanLooping(self) -> None:
        """Bounded by MAX_ROLL_DAYS; returns the input instead of spinning."""
        everyDay = frozenset(date(2026, 10, 3) + timedelta(days=n) for n in range(400))
        spec = irCalendar(holidays=everyDay)
        self.assertEqual(nextWorkingDay(spec, SATURDAY_DATE), SATURDAY_DATE)


class RollPolicyTests(SimpleTestCase):
    def testForwardIsTheDefault(self) -> None:
        spec = irCalendar(rollPolicy=ROLL_FORWARD)
        self.assertEqual(rollToWorkingDay(spec, FRIDAY_DATE), date(2026, 10, 10))

    def testBackwardPullsTheJobEarlier(self) -> None:
        """For work that must not slip past its due date."""
        spec = irCalendar(rollPolicy=ROLL_BACKWARD)
        self.assertEqual(rollToWorkingDay(spec, FRIDAY_DATE), THURSDAY_DATE)

    def testNoneLeavesTheDateAloneForPlantsThatRunOnHolidays(self) -> None:
        spec = irCalendar(rollPolicy=ROLL_NONE)
        self.assertEqual(rollToWorkingDay(spec, FRIDAY_DATE), FRIDAY_DATE)

    def testAWorkingDayIsNeverMovedByAnyPolicy(self) -> None:
        for policy in (ROLL_FORWARD, ROLL_BACKWARD, ROLL_NONE):
            with self.subTest(policy=policy):
                spec = irCalendar(rollPolicy=policy)
                self.assertEqual(rollToWorkingDay(spec, SATURDAY_DATE), SATURDAY_DATE)


class WorkingDayCountingTests(SimpleTestCase):
    def testCountsAFullWeekMinusFriday(self) -> None:
        total = workingDaysBetween(irCalendar(), date(2026, 10, 3), date(2026, 10, 9))
        self.assertEqual(total, 6)

    def testInvertedRangeIsZeroNotNegative(self) -> None:
        self.assertEqual(
            workingDaysBetween(irCalendar(), date(2026, 10, 9), date(2026, 10, 3)), 0
        )

    def testHolidaysComeOutOfTheCount(self) -> None:
        spec = irCalendar(holidays=frozenset({date(2026, 10, 5)}))
        self.assertEqual(
            workingDaysBetween(spec, date(2026, 10, 3), date(2026, 10, 9)), 5
        )

    def testAddWorkingDaysSkipsClosures(self) -> None:
        """Three working days from چهارشنبه jumps the جمعه."""
        self.assertEqual(
            addWorkingDays(irCalendar(), date(2026, 10, 7), 3), date(2026, 10, 11)
        )

    def testAddZeroOrNegativeIsANoop(self) -> None:
        self.assertEqual(addWorkingDays(irCalendar(), SATURDAY_DATE, 0), SATURDAY_DATE)
        self.assertEqual(addWorkingDays(irCalendar(), SATURDAY_DATE, -4), SATURDAY_DATE)


# =================================================================================
# Shifts
# =================================================================================


class ShiftWindowTests(SimpleTestCase):
    def testDayShiftDuration(self) -> None:
        shift = ShiftSpec("morning", time(7, 0), time(15, 0))
        self.assertFalse(shift.crossesMidnight)
        self.assertEqual(shift.durationHours, Decimal("8.00"))

    def testNightShiftCrossesMidnightAndStillMeasuresEightHours(self) -> None:
        shift = ShiftSpec("night", time(22, 0), time(6, 0))
        self.assertTrue(shift.crossesMidnight)
        self.assertEqual(shift.durationHours, Decimal("8.00"))

    def testEqualTimesMeanTwentyFourHoursNotZero(self) -> None:
        """A continuous shift, not a shift nobody works."""
        shift = ShiftSpec("continuous", time(6, 0), time(6, 0))
        self.assertEqual(shift.durationHours, Decimal("24.00"))

    def testNightShiftWindowEndsOnTheFollowingDay(self) -> None:
        shift = ShiftSpec("night", time(22, 0), time(6, 0))
        start, end = shift.windowOn(SATURDAY_DATE)
        self.assertEqual(start, datetime(2026, 10, 3, 22, 0))
        self.assertEqual(end, datetime(2026, 10, 4, 6, 0))

    def testEmptyWeekdaysMeansEveryOpenDay(self) -> None:
        shift = ShiftSpec("general", time(8, 0), time(16, 0))
        self.assertTrue(shift.runsOn(SATURDAY_DATE))
        self.assertTrue(shift.runsOn(THURSDAY_DATE))

    def testWeekdayListRestrictsTheShift(self) -> None:
        shift = ShiftSpec("sat", time(8, 0), time(16, 0), weekdays=(5,))
        self.assertTrue(shift.runsOn(SATURDAY_DATE))
        self.assertFalse(shift.runsOn(THURSDAY_DATE))


class ShiftsOnDayTests(SimpleTestCase):
    def setUp(self) -> None:
        self.morning = ShiftSpec("morning", time(6, 0), time(14, 0), headcount=4)
        self.evening = ShiftSpec("evening", time(14, 0), time(22, 0), headcount=3)
        self.night = ShiftSpec("night", time(22, 0), time(6, 0), headcount=2)
        self.all = (self.morning, self.evening, self.night)

    def testAllThreeRunOnAnOpenDay(self) -> None:
        self.assertEqual(len(shiftsOn(self.all, irCalendar(), SATURDAY_DATE)), 3)

    def testTheCalendarOutranksTheRoster(self) -> None:
        """A holiday has no shifts even though each shift says it runs daily."""
        spec = irCalendar(holidays=frozenset({SATURDAY_DATE}))
        self.assertEqual(shiftsOn(self.all, spec, SATURDAY_DATE), ())

    def testWeekendHasNoShifts(self) -> None:
        self.assertEqual(shiftsOn(self.all, irCalendar(), FRIDAY_DATE), ())

    def testCoveringShiftFindsTheDayShift(self) -> None:
        found = coveringShift(self.all, datetime(2026, 10, 3, 9, 0))
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.code, "morning")

    def testCoveringShiftAttributesEarlyMorningToTheNightBefore(self) -> None:
        """01:00 belongs to the night shift that began at 22:00 yesterday."""
        found = coveringShift(self.all, datetime(2026, 10, 4, 1, 0))
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.code, "night")

    def testUncoveredMomentReturnsNone(self) -> None:
        only = (ShiftSpec("morning", time(8, 0), time(16, 0)),)
        self.assertIsNone(coveringShift(only, datetime(2026, 10, 3, 18, 0)))


# =================================================================================
# Capacity
# =================================================================================


class CapacityTests(SimpleTestCase):
    def setUp(self) -> None:
        self.morning = ShiftSpec("morning", time(6, 0), time(14, 0), headcount=4)
        self.night = ShiftSpec("night", time(22, 0), time(6, 0), headcount=2)

    def testShiftCapacityIsDurationTimesHeadcount(self) -> None:
        self.assertEqual(shiftCapacityHours(self.morning), Decimal("32.00"))

    def testHeadcountCanBeOverriddenForWhatIfPlanning(self) -> None:
        self.assertEqual(shiftCapacityHours(self.morning, 10), Decimal("80.00"))

    def testNoCrewMeansNoCapacity(self) -> None:
        empty = ShiftSpec("ghost", time(6, 0), time(14, 0), headcount=0)
        self.assertEqual(shiftCapacityHours(empty), Decimal("0.00"))

    def testDailyCapacitySumsTheShifts(self) -> None:
        total = dailyCapacityHours((self.morning, self.night), irCalendar(), SATURDAY_DATE)
        self.assertEqual(total, Decimal("48.00"))

    def testClosedDayHasZeroCapacity(self) -> None:
        total = dailyCapacityHours((self.morning, self.night), irCalendar(), FRIDAY_DATE)
        self.assertEqual(total, Decimal("0"))


class UtilisationTests(SimpleTestCase):
    def testNormalLoad(self) -> None:
        self.assertEqual(utilisationPercent(Decimal("12"), Decimal("48")), Decimal("25.0"))

    def testIdleDayIsZeroNotUndefined(self) -> None:
        self.assertEqual(utilisationPercent(Decimal("0"), Decimal("0")), Decimal("0"))

    def testWorkScheduledOntoAClosedDayScreams(self) -> None:
        """Demand with zero capacity must be loud, not a silent divide-by-zero."""
        self.assertEqual(utilisationPercent(Decimal("6"), Decimal("0")), Decimal("999"))

    def testOverCommitmentExceedsOneHundred(self) -> None:
        self.assertEqual(utilisationPercent(Decimal("60"), Decimal("48")), Decimal("125.0"))


# =================================================================================
# Overtime
# =================================================================================


class OvertimeTests(SimpleTestCase):
    def setUp(self) -> None:
        self.morning = ShiftSpec("morning", time(7, 0), time(15, 0))
        self.evening = ShiftSpec("evening", time(15, 0), time(23, 0))
        self.night = ShiftSpec("night", time(22, 0), time(6, 0))

    def testWorkInsideTheShiftIsNotOvertime(self) -> None:
        hours = overtimeHours(
            datetime(2026, 10, 3, 8, 0), datetime(2026, 10, 3, 12, 0), (self.morning,)
        )
        self.assertEqual(hours, Decimal("0.00"))

    def testWorkAfterTheShiftIsOvertime(self) -> None:
        hours = overtimeHours(
            datetime(2026, 10, 3, 14, 0), datetime(2026, 10, 3, 18, 0), (self.morning,)
        )
        self.assertEqual(hours, Decimal("3.00"))

    def testBackToBackShiftsLeaveNoGapAndNoOvertime(self) -> None:
        """07:00-23:00 is fully covered by morning + evening."""
        hours = overtimeHours(
            datetime(2026, 10, 3, 7, 0),
            datetime(2026, 10, 3, 23, 0),
            (self.morning, self.evening),
        )
        self.assertEqual(hours, Decimal("0.00"))

    def testOverlappingShiftsDoNotDoubleCountCoverage(self) -> None:
        """Two overlapping shifts must not make overtime go negative."""
        wide = ShiftSpec("wide", time(6, 0), time(20, 0))
        hours = overtimeHours(
            datetime(2026, 10, 3, 7, 0),
            datetime(2026, 10, 3, 22, 0),
            (self.morning, wide),
        )
        self.assertEqual(hours, Decimal("2.00"))

    def testNightShiftCoversWorkPastMidnight(self) -> None:
        hours = overtimeHours(
            datetime(2026, 10, 3, 23, 0), datetime(2026, 10, 4, 5, 0), (self.night,)
        )
        self.assertEqual(hours, Decimal("0.00"))

    def testWorkWithNoShiftAtAllIsEntirelyOvertime(self) -> None:
        hours = overtimeHours(
            datetime(2026, 10, 9, 9, 0), datetime(2026, 10, 9, 14, 0), ()
        )
        self.assertEqual(hours, Decimal("5.00"))

    def testZeroLengthAndInvertedSpansAreZero(self) -> None:
        moment = datetime(2026, 10, 3, 9, 0)
        self.assertEqual(overtimeHours(moment, moment, (self.morning,)), Decimal("0"))
        self.assertEqual(
            overtimeHours(moment, moment.replace(hour=8), (self.morning,)), Decimal("0")
        )

    def testPartialOverlapCountsOnlyTheUncoveredTail(self) -> None:
        """05:00-09:00 against a 07:00 start = two hours before the shift."""
        hours = overtimeHours(
            datetime(2026, 10, 3, 5, 0), datetime(2026, 10, 3, 9, 0), (self.morning,)
        )
        self.assertEqual(hours, Decimal("2.00"))
