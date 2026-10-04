import type {
  CalendarHoliday,
  CapacityDay,
  CapacityPlan,
  WorkCalendar,
  WorkShift,
  WorkingDayAnswer,
} from "../../shared/types/domain";
import type {
  SaveCalendarInput,
  SaveHolidayInput,
  SaveShiftInput,
  WorkCalendarService,
} from "./workCalendarService";
import {
  type CalendarShape,
  dateRange,
  isHolidayDay,
  isWeekendDay,
  isWorkingDay,
  isoDate,
  rollToWorkingDay,
  shiftDurationHours,
} from "./workCalendarMath";

/**
 * Demo-mode work calendar (Phase 28).
 *
 * Computes its answers with the same `workCalendarMath` helpers the UI uses,
 * so the offline demo and the live API tell the same story about which days
 * are workable.
 */

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

let nextId = 1;
const makeId = (prefix: string): string => `${prefix}-${nextId++}`;

const demoShifts: WorkShift[] = [
  {
    id: "shift-a",
    calendarId: "cal-main",
    code: "SH-A",
    name: "شیفت صبح",
    kind: "morning",
    startTime: "06:00",
    endTime: "14:00",
    weekdays: [],
    headcount: 4,
    assignedCount: 4,
    effectiveHeadcount: 4,
    durationHours: "8.00",
    capacityHours: "32.00",
    crossesMidnight: false,
    active: true,
  },
  {
    id: "shift-b",
    calendarId: "cal-main",
    code: "SH-B",
    name: "شیفت عصر",
    kind: "evening",
    startTime: "14:00",
    endTime: "22:00",
    weekdays: [],
    headcount: 3,
    assignedCount: 3,
    effectiveHeadcount: 3,
    durationHours: "8.00",
    capacityHours: "24.00",
    crossesMidnight: false,
    active: true,
  },
  {
    id: "shift-c",
    calendarId: "cal-main",
    code: "SH-C",
    name: "شیفت شب",
    kind: "night",
    startTime: "22:00",
    endTime: "06:00",
    weekdays: [],
    headcount: 2,
    assignedCount: 2,
    effectiveHeadcount: 2,
    durationHours: "8.00",
    capacityHours: "16.00",
    crossesMidnight: true,
    active: true,
  },
];

const demoCalendars: WorkCalendar[] = [
  {
    id: "cal-main",
    code: "CAL-MAIN",
    name: "تقویم کاری سایت اصفهان",
    locationId: "loc-site-1",
    locationPath: "سایت اصفهان",
    timezone: "Asia/Tehran",
    weekendDays: [4],
    rollPolicy: "forward",
    isDefault: true,
    active: true,
    note: "هفتهٔ کاری شنبه تا پنجشنبه، جمعه تعطیل.",
    shifts: demoShifts,
    holidayCount: 0,
  },
  {
    id: "cal-north",
    code: "CAL-NORTH",
    name: "تقویم سایت شمال",
    locationId: "loc-bld-2",
    locationPath: "سایت شمال",
    timezone: "Asia/Tehran",
    weekendDays: [3, 4],
    rollPolicy: "forward",
    isDefault: false,
    active: true,
    note: "پنجشنبه و جمعه تعطیل.",
    shifts: [],
    holidayCount: 0,
  },
];

/** Fixed-date Iranian public holidays for 1405, as the backend seeds them. */
const demoHolidays: CalendarHoliday[] = [
  { id: "hol-1", calendarId: "cal-main", onDate: "2026-03-21", name: "نوروز", kind: "official", recursAnnually: true, jalaliMonth: 1, jalaliDay: 1 },
  { id: "hol-2", calendarId: "cal-main", onDate: "2026-03-22", name: "نوروز", kind: "official", recursAnnually: true, jalaliMonth: 1, jalaliDay: 2 },
  { id: "hol-3", calendarId: "cal-main", onDate: "2026-03-23", name: "نوروز", kind: "official", recursAnnually: true, jalaliMonth: 1, jalaliDay: 3 },
  { id: "hol-4", calendarId: "cal-main", onDate: "2026-03-24", name: "نوروز", kind: "official", recursAnnually: true, jalaliMonth: 1, jalaliDay: 4 },
  { id: "hol-5", calendarId: "cal-main", onDate: "2026-04-01", name: "روز جمهوری اسلامی", kind: "official", recursAnnually: true, jalaliMonth: 1, jalaliDay: 12 },
  { id: "hol-6", calendarId: "cal-main", onDate: "2026-04-02", name: "روز طبیعت", kind: "official", recursAnnually: true, jalaliMonth: 1, jalaliDay: 13 },
  { id: "hol-7", calendarId: "cal-main", onDate: "2026-06-04", name: "رحلت امام خمینی", kind: "official", recursAnnually: true, jalaliMonth: 3, jalaliDay: 14 },
  { id: "hol-8", calendarId: "cal-main", onDate: "2026-06-05", name: "قیام ۱۵ خرداد", kind: "official", recursAnnually: true, jalaliMonth: 3, jalaliDay: 15 },
  { id: "hol-9", calendarId: "cal-main", onDate: "2027-02-11", name: "پیروزی انقلاب اسلامی", kind: "official", recursAnnually: true, jalaliMonth: 11, jalaliDay: 22 },
  { id: "hol-10", calendarId: "cal-main", onDate: "2027-03-20", name: "ملی‌شدن صنعت نفت", kind: "official", recursAnnually: true, jalaliMonth: 12, jalaliDay: 29 },
];

/** A little synthetic PM demand so the capacity grid is not empty. */
const demoDemand: { deviceCode: string; deviceName: string; title: string; dueOffset: number; hours: number }[] = [
  { deviceCode: "PUMP-01", deviceName: "پمپ تغذیه بویلر", title: "روانکاری", dueOffset: 1, hours: 2 },
  { deviceCode: "CNC-14", deviceName: "تراش CNC", title: "بازرسی دوره‌ای", dueOffset: 2, hours: 3.5 },
  { deviceCode: "COMP-07", deviceName: "کمپرسور هوا", title: "تعویض فیلتر", dueOffset: 2, hours: 1.5 },
  { deviceCode: "GEN-02", deviceName: "ژنراتور اضطراری", title: "تست بارگذاری", dueOffset: 5, hours: 4 },
  { deviceCode: "PUMP-01", deviceName: "پمپ تغذیه بویلر", title: "ارتعاش‌سنجی", dueOffset: 6, hours: 2 },
];

const store = {
  calendars: clone(demoCalendars),
  holidays: clone(demoHolidays),
};

const shapeFor = (calendarId: string): CalendarShape => {
  const calendar = store.calendars.find((row) => row.id === calendarId) ?? store.calendars[0];
  return {
    weekendDays: calendar?.weekendDays ?? [4],
    holidays: new Set(
      store.holidays.filter((row) => row.calendarId === calendar?.id).map((row) => row.onDate),
    ),
    rollPolicy: calendar?.rollPolicy ?? "forward",
  };
};

const resolveCalendar = (calendarId?: string): WorkCalendar =>
  store.calendars.find((row) => row.id === calendarId) ??
  store.calendars.find((row) => row.isDefault) ??
  store.calendars[0];

const round2 = (value: number): string => (Math.round(value * 100) / 100).toFixed(2);

export const createDemoWorkCalendarService = (): WorkCalendarService => ({
  listCalendars: async () =>
    clone(
      store.calendars.map((calendar) => ({
        ...calendar,
        holidayCount: store.holidays.filter((row) => row.calendarId === calendar.id).length,
      })),
    ),

  saveCalendar: async (input: SaveCalendarInput) => {
    const existing = input.id ? store.calendars.find((row) => row.id === input.id) : undefined;
    const saved: WorkCalendar = {
      id: existing?.id ?? makeId("cal"),
      code: input.code,
      name: input.name,
      locationId: input.locationId ?? "",
      locationPath: existing?.locationPath ?? "",
      timezone: input.timezone ?? "Asia/Tehran",
      weekendDays: input.weekendDays ?? [4],
      rollPolicy: input.rollPolicy ?? "forward",
      isDefault: input.isDefault ?? false,
      active: input.active ?? true,
      note: input.note ?? "",
      shifts: existing?.shifts ?? [],
      holidayCount: existing?.holidayCount ?? 0,
    };
    if (existing) {
      store.calendars = store.calendars.map((row) => (row.id === saved.id ? saved : row));
    } else {
      store.calendars.push(saved);
    }
    if (saved.isDefault) {
      store.calendars = store.calendars.map((row) =>
        row.id === saved.id ? row : { ...row, isDefault: false },
      );
    }
    return clone(saved);
  },

  deleteCalendar: async (calendarId: string) => {
    store.calendars = store.calendars.filter((row) => row.id !== calendarId);
    store.holidays = store.holidays.filter((row) => row.calendarId !== calendarId);
  },

  listHolidays: async ({ calendarId, fromDate, toDate }) =>
    clone(
      store.holidays
        .filter((row) => row.calendarId === calendarId)
        .filter((row) => (fromDate ? row.onDate >= fromDate : true))
        .filter((row) => (toDate ? row.onDate <= toDate : true))
        .sort((left, right) => left.onDate.localeCompare(right.onDate)),
    ),

  saveHoliday: async (input: SaveHolidayInput) => {
    const saved: CalendarHoliday = {
      id: input.id || makeId("hol"),
      calendarId: input.calendarId,
      onDate: input.onDate,
      name: input.name,
      kind: input.kind ?? "official",
      recursAnnually: input.recursAnnually ?? false,
      jalaliMonth: input.jalaliMonth ?? 0,
      jalaliDay: input.jalaliDay ?? 0,
    };
    const index = store.holidays.findIndex((row) => row.id === saved.id);
    if (index >= 0) store.holidays[index] = saved;
    else store.holidays.push(saved);
    return clone(saved);
  },

  deleteHoliday: async (holidayId: string) => {
    store.holidays = store.holidays.filter((row) => row.id !== holidayId);
  },

  saveShift: async (input: SaveShiftInput) => {
    const calendar = resolveCalendar(input.calendarId);
    const duration = shiftDurationHours({ startTime: input.startTime, endTime: input.endTime });
    const headcount = input.headcount ?? 0;
    const saved: WorkShift = {
      id: input.id || makeId("shift"),
      calendarId: calendar.id,
      code: input.code,
      name: input.name,
      kind: input.kind ?? "general",
      startTime: input.startTime,
      endTime: input.endTime,
      weekdays: input.weekdays ?? [],
      headcount,
      assignedCount: 0,
      effectiveHeadcount: headcount,
      durationHours: duration.toFixed(2),
      capacityHours: (duration * headcount).toFixed(2),
      crossesMidnight: input.endTime <= input.startTime,
      active: input.active ?? true,
    };
    const index = calendar.shifts.findIndex((row) => row.id === saved.id);
    if (index >= 0) calendar.shifts[index] = saved;
    else calendar.shifts.push(saved);
    return clone(saved);
  },

  deleteShift: async (shiftId: string) => {
    store.calendars.forEach((calendar) => {
      calendar.shifts = calendar.shifts.filter((row) => row.id !== shiftId);
    });
  },

  getCapacityPlan: async ({ calendarId, fromDate, toDate }) => {
    const calendar = resolveCalendar(calendarId);
    const shape = shapeFor(calendar.id);
    const today = isoDate(new Date());
    const start = fromDate || today;
    const end = toDate || isoDate(new Date(Date.now() + 29 * 86_400_000));

    // Place the synthetic demand the same way the backend does: on the day
    // the calendar says the work will really be done.
    const demandByDay = new Map<string, { hours: number; jobs: CapacityDay["jobs"] }>();
    demoDemand.forEach((job) => {
      const due = isoDate(new Date(Date.now() + job.dueOffset * 86_400_000));
      const planned = rollToWorkingDay(shape, due);
      if (planned < start || planned > end) return;
      const bucket = demandByDay.get(planned) ?? { hours: 0, jobs: [] };
      bucket.hours += job.hours;
      bucket.jobs.push({
        deviceId: job.deviceCode,
        deviceCode: job.deviceCode,
        deviceName: job.deviceName,
        title: job.title,
        dueOn: due,
        rolled: planned !== due,
        estimatedHours: job.hours.toFixed(2),
      });
      demandByDay.set(planned, bucket);
    });

    const dailyCapacity = calendar.shifts
      .filter((shift) => shift.active)
      .reduce(
        (total, shift) =>
          total + shiftDurationHours(shift) * (shift.effectiveHeadcount || shift.headcount),
        0,
      );

    let totalDemand = 0;
    let totalCapacity = 0;
    let overloaded = 0;
    const days: CapacityDay[] = dateRange(start, end).map((iso) => {
      const working = isWorkingDay(shape, iso);
      const capacity = working ? dailyCapacity : 0;
      const bucket = demandByDay.get(iso) ?? { hours: 0, jobs: [] };
      const utilisation =
        capacity > 0
          ? Math.round((bucket.hours / capacity) * 1000) / 10
          : bucket.hours > 0
            ? 999
            : 0;
      if (utilisation > 100) overloaded += 1;
      totalDemand += bucket.hours;
      totalCapacity += capacity;
      return {
        onDate: iso,
        isWorkingDay: working,
        isWeekend: isWeekendDay(shape, iso),
        isHoliday: isHolidayDay(shape, iso),
        shiftCount: working ? calendar.shifts.filter((shift) => shift.active).length : 0,
        capacityHours: round2(capacity),
        demandHours: round2(bucket.hours),
        utilisationPercent: String(utilisation),
        jobCount: bucket.jobs.length,
        jobs: bucket.jobs,
      };
    });

    const plan: CapacityPlan = {
      calendarId: calendar.id,
      fromDate: start,
      toDate: end,
      days,
      shifts: calendar.shifts,
      summary: {
        totalCapacityHours: round2(totalCapacity),
        totalDemandHours: round2(totalDemand),
        utilisationPercent:
          totalCapacity > 0
            ? String(Math.round((totalDemand / totalCapacity) * 1000) / 10)
            : "0",
        workingDays: days.filter((day) => day.isWorkingDay).length,
        closedDays: days.filter((day) => !day.isWorkingDay).length,
        overloadedDays: overloaded,
      },
    };
    return clone(plan);
  },

  getWorkingDay: async ({ onDate, calendarId }) => {
    const calendar = resolveCalendar(calendarId);
    const shape = shapeFor(calendar.id);
    const planned = rollToWorkingDay(shape, onDate);
    const answer: WorkingDayAnswer = {
      calendarId: calendar.id,
      onDate,
      isWorkingDay: isWorkingDay(shape, onDate),
      isWeekend: isWeekendDay(shape, onDate),
      isHoliday: isHolidayDay(shape, onDate),
      rollPolicy: calendar.rollPolicy,
      plannedOn: planned,
      rolled: planned !== onDate,
    };
    return clone(answer);
  },
});
