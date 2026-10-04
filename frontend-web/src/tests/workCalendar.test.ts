import { describe, expect, it } from "vitest";

import {
  MAX_ROLL_DAYS,
  addDays,
  capacityTone,
  dateRange,
  isHolidayDay,
  isWeekendDay,
  isWorkingDay,
  isoDate,
  monthGridOffset,
  parseIso,
  pyWeekday,
  rollToWorkingDay,
  shiftDurationHours,
  expandRecurringDates,
  type CalendarShape,
} from "../features/maintenance/workCalendarMath";
import {
  toCapacityPlan,
  toHoliday,
  toWorkCalendar,
  toWorkShift,
} from "../features/maintenance/workCalendarService";
import { createDemoWorkCalendarService } from "../features/maintenance/workCalendarDemoData";
import { WEEKDAY_ORDER_IR } from "../shared/types/domain";

/** A plant that rests on جمعه only, with Nowruz 1405 shut. */
const iranian = (overrides: Partial<CalendarShape> = {}): CalendarShape => ({
  weekendDays: [4],
  holidays: new Set(["2026-03-21", "2026-03-22", "2026-03-23", "2026-03-24"]),
  rollPolicy: "forward",
  ...overrides,
});

describe("weekday conversion", () => {
  it("maps JS weekdays onto python's Monday-zero convention", () => {
    // 2026-03-21 is a Saturday; python calls Saturday 5.
    expect(pyWeekday(parseIso("2026-03-21"))).toBe(5);
    expect(pyWeekday(parseIso("2026-03-22"))).toBe(6); // Sunday
    expect(pyWeekday(parseIso("2026-03-23"))).toBe(0); // Monday
    expect(pyWeekday(parseIso("2026-03-27"))).toBe(4); // جمعه
  });

  it("round-trips a date through parseIso and isoDate without a UTC shift", () => {
    // Naive `new Date("2026-03-21")` parses as UTC and can slip a day west of
    // Greenwich; the local-midnight parse must not.
    expect(isoDate(parseIso("2026-03-21"))).toBe("2026-03-21");
    expect(isoDate(parseIso("2026-01-01"))).toBe("2026-01-01");
    expect(isoDate(parseIso("2026-12-31"))).toBe("2026-12-31");
  });

  it("steps across month and year boundaries", () => {
    expect(isoDate(addDays(parseIso("2026-03-31"), 1))).toBe("2026-04-01");
    expect(isoDate(addDays(parseIso("2026-01-01"), -1))).toBe("2025-12-31");
  });
});

describe("open and closed days", () => {
  it("treats the configured weekend as closed", () => {
    const shape = iranian();
    expect(isWeekendDay(shape, "2026-03-27")).toBe(true); // جمعه
    expect(isWeekendDay(shape, "2026-03-26")).toBe(false); // پنجشنبه
    expect(isWorkingDay(shape, "2026-03-27")).toBe(false);
  });

  it("supports a two-day weekend for a site that keeps one", () => {
    const shape = iranian({ weekendDays: [3, 4] });
    expect(isWeekendDay(shape, "2026-03-26")).toBe(true);
    expect(isWeekendDay(shape, "2026-03-27")).toBe(true);
    expect(isWeekendDay(shape, "2026-03-28")).toBe(false); // شنبه, back to work
  });

  it("closes holidays independently of the weekend", () => {
    const shape = iranian();
    expect(isHolidayDay(shape, "2026-03-21")).toBe(true);
    expect(isWeekendDay(shape, "2026-03-21")).toBe(false);
    expect(isWorkingDay(shape, "2026-03-21")).toBe(false);
  });
});

describe("rollToWorkingDay", () => {
  it("leaves a working day exactly where it is", () => {
    expect(rollToWorkingDay(iranian(), "2026-03-25")).toBe("2026-03-25");
  });

  it("rolls forward past a holiday block onto the next open day", () => {
    // 21–24 are Nowruz; 25 (چهارشنبه) is the first day back.
    expect(rollToWorkingDay(iranian(), "2026-03-21")).toBe("2026-03-25");
  });

  it("rolls backward when the calendar says so, skipping weekend and holiday alike", () => {
    // Walking back from 22: 21 is Nowruz, 20 is جمعه, so 19 (پنجشنبه) is the
    // last day anyone was actually at the plant.
    const shape = iranian({ rollPolicy: "backward" });
    expect(rollToWorkingDay(shape, "2026-03-22")).toBe("2026-03-19");
  });

  it("honours the 'none' policy by leaving the date closed", () => {
    const shape = iranian({ rollPolicy: "none" });
    expect(rollToWorkingDay(shape, "2026-03-21")).toBe("2026-03-21");
  });

  it("skips a weekend that follows the holiday rather than landing on it", () => {
    // 2026-03-26 پنجشنبه is shut for a local reason, 27 is جمعه ⇒ land on 28.
    const shape = iranian({ holidays: new Set(["2026-03-26"]) });
    expect(rollToWorkingDay(shape, "2026-03-26")).toBe("2026-03-28");
  });

  it("gives up instead of looping forever when nothing is ever open", () => {
    const shape: CalendarShape = {
      weekendDays: [0, 1, 2, 3, 4, 5, 6],
      holidays: new Set(),
      rollPolicy: "forward",
    };
    expect(rollToWorkingDay(shape, "2026-03-21")).toBe("2026-03-21");
    expect(MAX_ROLL_DAYS).toBe(30);
  });
});

describe("dateRange", () => {
  it("is inclusive at both ends", () => {
    expect(dateRange("2026-03-21", "2026-03-24")).toEqual([
      "2026-03-21",
      "2026-03-22",
      "2026-03-23",
      "2026-03-24",
    ]);
  });

  it("returns a single day when the ends meet", () => {
    expect(dateRange("2026-03-21", "2026-03-21")).toEqual(["2026-03-21"]);
  });

  it("returns nothing for an inverted range instead of running away", () => {
    expect(dateRange("2026-03-24", "2026-03-21")).toEqual([]);
  });

  it("caps a runaway window so one bad date cannot freeze the tab", () => {
    expect(dateRange("2020-01-01", "2030-01-01")).toHaveLength(400);
  });
});

describe("shiftDurationHours", () => {
  it("measures an ordinary day shift", () => {
    expect(shiftDurationHours({ startTime: "06:00", endTime: "14:00" })).toBe(8);
  });

  it("measures a night shift that crosses midnight", () => {
    expect(shiftDurationHours({ startTime: "22:00", endTime: "06:00" })).toBe(8);
  });

  it("reads equal start and end as a continuous 24 hours, not zero", () => {
    expect(shiftDurationHours({ startTime: "08:00", endTime: "08:00" })).toBe(24);
  });

  it("handles half hours", () => {
    expect(shiftDurationHours({ startTime: "07:30", endTime: "16:00" })).toBe(8.5);
  });
});

describe("capacityTone", () => {
  const day = (
    extra: Partial<{ isWorkingDay: boolean; utilisationPercent: string; demandHours: string }>,
  ) => ({
    isWorkingDay: true,
    utilisationPercent: "0",
    demandHours: "0",
    ...extra,
  });

  it("calls a closed day closed even when nothing is demanded of it", () => {
    expect(capacityTone(day({ isWorkingDay: false }))).toBe("closed");
  });

  it("keeps 'closed' ahead of 'over' when work is stranded on a shut day", () => {
    // A closed day with demand on it has zero capacity, so the API sends the
    // 999 sentinel. 'closed' must still win: the honest reading is "the plant
    // is shut", not "this day is 999% busy" — and red-for-overload here would
    // read as a day to relieve rather than a day nobody is in.
    expect(
      capacityTone(day({ isWorkingDay: false, demandHours: "12", utilisationPercent: "999" })),
    ).toBe("closed");
  });

  it("flags over-commitment above 100%", () => {
    expect(capacityTone(day({ utilisationPercent: "101", demandHours: "9" }))).toBe("over");
  });

  it("treats exactly 100% as tight, not over", () => {
    expect(capacityTone(day({ utilisationPercent: "100", demandHours: "8" }))).toBe("tight");
  });

  it("treats the 80% threshold as tight", () => {
    expect(capacityTone(day({ utilisationPercent: "80", demandHours: "6.4" }))).toBe("tight");
  });

  it("is comfortable below the threshold but with work on it", () => {
    expect(capacityTone(day({ utilisationPercent: "25", demandHours: "2" }))).toBe("ok");
  });

  it("is idle when an open day has no work at all", () => {
    expect(capacityTone(day({}))).toBe("idle");
  });

  it("reads the backend's 999 overload sentinel as over capacity", () => {
    // The API sends 999 when demand exists but capacity is zero.
    expect(capacityTone(day({ utilisationPercent: "999", demandHours: "4" }))).toBe("over");
  });
});

describe("monthGridOffset", () => {
  it("puts شنبه in the first column and جمعه in the last", () => {
    expect(monthGridOffset("2026-03-21")).toBe(0); // Saturday
    expect(monthGridOffset("2026-03-22")).toBe(1);
    expect(monthGridOffset("2026-03-27")).toBe(6); // Friday
  });

  it("agrees with the display order the weekday picker uses", () => {
    // Column n of the grid must be the same weekday the picker labels at n.
    for (let column = 0; column < 7; column += 1) {
      const iso = isoDate(addDays(parseIso("2026-03-21"), column));
      expect(monthGridOffset(iso)).toBe(column);
      expect(WEEKDAY_ORDER_IR[column]).toBe(pyWeekday(parseIso(iso)));
    }
  });
});

describe("API mappers", () => {
  it("tolerates a sparse shift payload without producing NaN", () => {
    const shift = toWorkShift({ id: "s1", code: "A" });
    expect(shift.id).toBe("s1");
    expect(shift.weekdays).toEqual([]);
    expect(shift.headcount).toBe(0);
    expect(Number.isNaN(Number(shift.capacityHours))).toBe(false);
  });

  it("reads a calendar's weekend days and nested shifts", () => {
    const calendar = toWorkCalendar({
      id: "c1",
      code: "CAL-MAIN",
      name: "اصلی",
      weekendDays: [4],
      rollPolicy: "forward",
      isDefault: true,
      shifts: [{ id: "s1", code: "A", startTime: "06:00", endTime: "14:00" }],
    });
    expect(calendar.weekendDays).toEqual([4]);
    expect(calendar.rollPolicy).toBe("forward");
    expect(calendar.isDefault).toBe(true);
    expect(calendar.shifts).toHaveLength(1);
    expect(calendar.shifts[0].code).toBe("A");
  });

  it("falls back to the forward policy when the API omits one", () => {
    expect(toWorkCalendar({ id: "c1" }).rollPolicy).toBe("forward");
  });

  it("keeps a holiday's Persian name intact", () => {
    const holiday = toHoliday({
      id: "h1",
      onDate: "2026-03-21",
      name: "نوروز",
      kind: "official",
      recursAnnually: true,
    });
    expect(holiday.name).toBe("نوروز");
    expect(holiday.recursAnnually).toBe(true);
  });

  it("builds a plan with a usable summary even from an empty payload", () => {
    const plan = toCapacityPlan({ calendarId: "c1", days: [], summary: {} });
    expect(plan.days).toEqual([]);
    expect(plan.summary.overloadedDays).toBe(0);
    expect(plan.summary.workingDays).toBe(0);
  });

  it("carries each job's rolled flag and original due date through", () => {
    const plan = toCapacityPlan({
      calendarId: "c1",
      days: [
        {
          onDate: "2026-03-25",
          isWorkingDay: true,
          capacityHours: "16.00",
          demandHours: "4.00",
          utilisationPercent: "25.00",
          jobCount: 1,
          jobs: [
            {
              deviceId: "d1",
              deviceCode: "PRS-101",
              dueOn: "2026-03-21",
              rolled: true,
              estimatedHours: "4.00",
            },
          ],
        },
      ],
      summary: { overloadedDays: 0 },
    });
    expect(plan.days[0].jobs[0].rolled).toBe(true);
    expect(plan.days[0].jobs[0].dueOn).toBe("2026-03-21");
    expect(capacityTone(plan.days[0])).toBe("ok");
  });
});

describe("first-run flow", () => {
  // Regression guard for the dead-end a fresh install used to hit: the plant
  // migrates the database but never seeds it, so there is no work calendar,
  // and holidays/shifts/capacity have nothing to attach to. The page must stay
  // usable and the very first calendar must become the tenant default —
  // otherwise `resolveCalendarIdForLocation` falls back to a default that does
  // not exist and no device ever resolves a calendar.
  it("makes a saved calendar immediately listable", async () => {
    const service = createDemoWorkCalendarService();
    const before = await service.listCalendars();
    await service.saveCalendar({
      code: "CAL-TEST",
      name: "تقویم آزمایشی",
      weekendDays: [4],
      rollPolicy: "forward",
      isDefault: false,
    });
    const after = await service.listCalendars();
    expect(after).toHaveLength(before.length + 1);
    expect(after.some((row) => row.code === "CAL-TEST")).toBe(true);
  });

  it("keeps exactly one tenant default when a new calendar claims it", async () => {
    const service = createDemoWorkCalendarService();
    await service.saveCalendar({
      code: "CAL-CLAIM",
      name: "تقویم پیش‌فرض تازه",
      weekendDays: [4],
      rollPolicy: "forward",
      isDefault: true,
    });
    const rows = await service.listCalendars();
    const defaults = rows.filter((row) => row.isDefault);
    expect(defaults).toHaveLength(1);
    expect(defaults[0].code).toBe("CAL-CLAIM");
  });

  it("gives a brand-new calendar a usable shape rather than undefined fields", async () => {
    const service = createDemoWorkCalendarService();
    const saved = await service.saveCalendar({ code: "CAL-BARE", name: "کمینه" });
    expect(saved.timezone).toBe("Asia/Tehran");
    expect(saved.weekendDays).toEqual([4]);
    expect(saved.rollPolicy).toBe("forward");
    expect(saved.shifts).toEqual([]);
  });
});

describe("expandRecurringDates", () => {
  it("follows the Jalali date, not the Gregorian one", () => {
    // نوروز is 21 March in 1405/1406 but 20 March in 1407/1408. A naive
    // repeat of the stored Gregorian date would be wrong half the time.
    expect(expandRecurringDates(1, 1, "2026-01-01", "2030-12-31")).toEqual([
      "2026-03-21",
      "2027-03-21",
      "2028-03-20",
      "2029-03-20",
      "2030-03-21",
    ]);
  });

  it("skips ۳۰ اسفند in ordinary years instead of clamping it", () => {
    // 1408 is a leap year; the surrounding ones are not.
    expect(expandRecurringDates(12, 30, "2026-03-21", "2031-03-20")).toEqual(["2030-03-20"]);
  });

  it("keeps a mid-year holiday on its Jalali anniversary", () => {
    expect(expandRecurringDates(11, 22, "2027-01-01", "2029-12-31")).toEqual([
      "2027-02-11",
      "2028-02-11",
      "2029-02-10",
    ]);
  });

  it("returns nothing for an inverted window or impossible parts", () => {
    expect(expandRecurringDates(1, 1, "2027-01-01", "2026-01-01")).toEqual([]);
    expect(expandRecurringDates(0, 1, "2026-01-01", "2030-01-01")).toEqual([]);
    expect(expandRecurringDates(13, 1, "2026-01-01", "2030-01-01")).toEqual([]);
    expect(expandRecurringDates(1, 0, "2026-01-01", "2030-01-01")).toEqual([]);
  });

  it("clips to the window rather than returning the whole year", () => {
    expect(expandRecurringDates(1, 1, "2026-04-01", "2027-03-20")).toEqual([]);
    expect(expandRecurringDates(1, 1, "2026-03-21", "2026-03-21")).toEqual(["2026-03-21"]);
  });
});

describe("demo work calendar recurrence", () => {
  it("projects a recurring holiday into a later year, matching the API", async () => {
    const service = createDemoWorkCalendarService();
    const rows = await service.listHolidays({
      calendarId: "cal-main",
      fromDate: "2029-03-01",
      toDate: "2029-03-31",
    });
    const nowruz = rows.find((row) => row.onDate === "2029-03-20");
    expect(nowruz).toBeDefined();
    expect(nowruz?.name).toBe("نوروز");
    expect(nowruz?.projected).toBe(true);
  });

  it("returns only real, deletable rows when no window is given", async () => {
    const service = createDemoWorkCalendarService();
    const rows = await service.listHolidays({ calendarId: "cal-main" });
    expect(rows.every((row) => row.projected === false)).toBe(true);
    expect(rows).toHaveLength(10);
  });

  it("treats a projected holiday as a closed day", async () => {
    const service = createDemoWorkCalendarService();
    const answer = await service.getWorkingDay({
      onDate: "2029-03-20",
      calendarId: "cal-main",
    });
    expect(answer.isWorkingDay).toBe(false);
    expect(answer.isHoliday).toBe(true);
  });

  it("derives the Jalali parts on save instead of trusting the caller", async () => {
    const service = createDemoWorkCalendarService();
    const saved = await service.saveHoliday({
      calendarId: "cal-main",
      onDate: "2026-04-02",
      name: "روز طبیعت",
      kind: "official",
      recursAnnually: true,
      jalaliMonth: 99,
      jalaliDay: 99,
    });
    expect(saved.jalaliMonth).toBe(1);
    expect(saved.jalaliDay).toBe(13);
  });
});
