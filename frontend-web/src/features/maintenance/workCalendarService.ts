import type { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import type {
  CalendarHoliday,
  CapacityDay,
  CapacityJob,
  CapacityPlan,
  HolidayKind,
  RollPolicy,
  ShiftKind,
  WorkCalendar,
  WorkShift,
  WorkingDayAnswer,
} from "../../shared/types/domain";

/**
 * Work calendar, shift and capacity API (Phase 28).
 *
 * Kept out of `registryService` deliberately: scheduling is its own concern
 * and that file is already large. The mappers below are exported so they can
 * be unit tested without a network.
 */

const text = (value: unknown, fallback = ""): string =>
  typeof value === "string" ? value : value == null ? fallback : String(value);

const flag = (value: unknown): boolean => value === true || value === "true";

const count = (value: unknown): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const numberList = (value: unknown): number[] =>
  Array.isArray(value)
    ? value.map((entry) => Number(entry)).filter((entry) => Number.isFinite(entry))
    : [];

export const toWorkShift = (raw: Record<string, unknown>): WorkShift => ({
  id: text(raw.id),
  calendarId: text(raw.calendarId),
  code: text(raw.code),
  name: text(raw.name),
  kind: (text(raw.kind, "general") || "general") as ShiftKind,
  startTime: text(raw.startTime),
  endTime: text(raw.endTime),
  weekdays: numberList(raw.weekdays),
  headcount: count(raw.headcount),
  assignedCount: count(raw.assignedCount),
  effectiveHeadcount: count(raw.effectiveHeadcount),
  durationHours: text(raw.durationHours, "0"),
  capacityHours: text(raw.capacityHours, "0"),
  crossesMidnight: flag(raw.crossesMidnight),
  active: raw.active !== false,
});

export const toWorkCalendar = (raw: Record<string, unknown>): WorkCalendar => ({
  id: text(raw.id),
  code: text(raw.code),
  name: text(raw.name),
  locationId: text(raw.locationId),
  locationPath: text(raw.locationPath),
  timezone: text(raw.timezone, "Asia/Tehran"),
  weekendDays: numberList(raw.weekendDays),
  rollPolicy: (text(raw.rollPolicy, "forward") || "forward") as RollPolicy,
  isDefault: flag(raw.isDefault),
  active: raw.active !== false,
  note: text(raw.note),
  shifts: Array.isArray(raw.shifts)
    ? (raw.shifts as Record<string, unknown>[]).map(toWorkShift)
    : [],
  holidayCount: count(raw.holidayCount),
});

export const toHoliday = (raw: Record<string, unknown>): CalendarHoliday => ({
  id: text(raw.id),
  calendarId: text(raw.calendarId),
  onDate: text(raw.onDate),
  name: text(raw.name),
  kind: (text(raw.kind, "official") || "official") as HolidayKind,
  recursAnnually: flag(raw.recursAnnually),
  jalaliMonth: count(raw.jalaliMonth),
  jalaliDay: count(raw.jalaliDay),
  projected: Boolean(raw.projected ?? false),
});

const toCapacityJob = (raw: Record<string, unknown>): CapacityJob => ({
  deviceId: text(raw.deviceId),
  deviceCode: text(raw.deviceCode),
  deviceName: text(raw.deviceName),
  title: text(raw.title),
  dueOn: text(raw.dueOn),
  rolled: flag(raw.rolled),
  estimatedHours: text(raw.estimatedHours, "0"),
});

export const toCapacityDay = (raw: Record<string, unknown>): CapacityDay => ({
  onDate: text(raw.onDate),
  isWorkingDay: flag(raw.isWorkingDay),
  isWeekend: flag(raw.isWeekend),
  isHoliday: flag(raw.isHoliday),
  shiftCount: count(raw.shiftCount),
  capacityHours: text(raw.capacityHours, "0"),
  demandHours: text(raw.demandHours, "0"),
  utilisationPercent: text(raw.utilisationPercent, "0"),
  jobCount: count(raw.jobCount),
  jobs: Array.isArray(raw.jobs)
    ? (raw.jobs as Record<string, unknown>[]).map(toCapacityJob)
    : [],
});

export const toCapacityPlan = (raw: Record<string, unknown>): CapacityPlan => {
  const summary = (raw.summary ?? {}) as Record<string, unknown>;
  return {
    calendarId: text(raw.calendarId),
    fromDate: text(raw.fromDate),
    toDate: text(raw.toDate),
    days: Array.isArray(raw.days)
      ? (raw.days as Record<string, unknown>[]).map(toCapacityDay)
      : [],
    shifts: Array.isArray(raw.shifts)
      ? (raw.shifts as Record<string, unknown>[]).map(toWorkShift)
      : [],
    summary: {
      totalCapacityHours: text(summary.totalCapacityHours, "0"),
      totalDemandHours: text(summary.totalDemandHours, "0"),
      utilisationPercent: text(summary.utilisationPercent, "0"),
      workingDays: count(summary.workingDays),
      closedDays: count(summary.closedDays),
      overloadedDays: count(summary.overloadedDays),
    },
  };
};

export const toWorkingDayAnswer = (raw: Record<string, unknown>): WorkingDayAnswer => ({
  calendarId: text(raw.calendarId),
  onDate: text(raw.onDate),
  isWorkingDay: flag(raw.isWorkingDay),
  isWeekend: flag(raw.isWeekend),
  isHoliday: flag(raw.isHoliday),
  rollPolicy: (text(raw.rollPolicy, "forward") || "forward") as RollPolicy,
  plannedOn: text(raw.plannedOn),
  rolled: flag(raw.rolled),
  addWorkingDays: raw.addWorkingDays ? text(raw.addWorkingDays) : undefined,
});

export interface SaveCalendarInput {
  id?: string;
  code: string;
  name: string;
  locationId?: string;
  timezone?: string;
  weekendDays?: number[];
  rollPolicy?: RollPolicy;
  isDefault?: boolean;
  active?: boolean;
  note?: string;
}

export interface SaveHolidayInput {
  id?: string;
  calendarId: string;
  onDate: string;
  name: string;
  kind?: HolidayKind;
  recursAnnually?: boolean;
  jalaliMonth?: number;
  jalaliDay?: number;
}

export interface SaveShiftInput {
  id?: string;
  calendarId: string;
  code: string;
  name: string;
  kind?: ShiftKind;
  startTime: string;
  endTime: string;
  weekdays?: number[];
  headcount?: number;
  active?: boolean;
}

export interface WorkCalendarService {
  listCalendars: (signal?: AbortSignal) => Promise<WorkCalendar[]>;
  saveCalendar: (input: SaveCalendarInput, signal?: AbortSignal) => Promise<WorkCalendar>;
  deleteCalendar: (calendarId: string, signal?: AbortSignal) => Promise<void>;
  listHolidays: (
    options: { calendarId: string; fromDate?: string; toDate?: string },
    signal?: AbortSignal,
  ) => Promise<CalendarHoliday[]>;
  saveHoliday: (input: SaveHolidayInput, signal?: AbortSignal) => Promise<CalendarHoliday>;
  deleteHoliday: (holidayId: string, signal?: AbortSignal) => Promise<void>;
  saveShift: (input: SaveShiftInput, signal?: AbortSignal) => Promise<WorkShift>;
  deleteShift: (shiftId: string, signal?: AbortSignal) => Promise<void>;
  getCapacityPlan: (
    options: { calendarId?: string; locationId?: string; fromDate?: string; toDate?: string },
    signal?: AbortSignal,
  ) => Promise<CapacityPlan>;
  getWorkingDay: (
    options: { onDate: string; calendarId?: string; deviceId?: string; addWorkingDays?: number },
    signal?: AbortSignal,
  ) => Promise<WorkingDayAnswer>;
}

export const createWorkCalendarService = (api: ApiClient): WorkCalendarService => ({
  listCalendars: async (signal) => {
    const raw = await api.get<Record<string, unknown>>(
      apiEndpoints.maintenance.workCalendars,
      { signal },
    );
    const items = (raw?.items ?? []) as Record<string, unknown>[];
    return items.map(toWorkCalendar);
  },
  saveCalendar: async (input, signal) => {
    const raw = await api.post<Record<string, unknown>>(
      apiEndpoints.maintenance.workCalendars,
      {
        id: input.id ?? "",
        code: input.code,
        name: input.name,
        locationId: input.locationId ?? "",
        timezone: input.timezone ?? "Asia/Tehran",
        weekendDays: input.weekendDays ?? [],
        rollPolicy: input.rollPolicy ?? "forward",
        isDefault: input.isDefault ?? false,
        active: input.active ?? true,
        note: input.note ?? "",
      },
      // A save must not be silently replayed: a retry here could create a
      // second calendar when the first response was merely slow.
      { signal, retry: 0 },
    );
    return toWorkCalendar(raw ?? {});
  },
  deleteCalendar: async (calendarId, signal) => {
    await api.delete(apiEndpoints.maintenance.workCalendar(calendarId), { signal, retry: 0 });
  },
  listHolidays: async (options, signal) => {
    const raw = await api.get<Record<string, unknown>>(
      apiEndpoints.maintenance.calendarHolidays,
      {
        query: {
          calendarId: options.calendarId,
          fromDate: options.fromDate ?? "",
          toDate: options.toDate ?? "",
        },
        signal,
      },
    );
    const items = (raw?.items ?? []) as Record<string, unknown>[];
    return items.map(toHoliday);
  },
  saveHoliday: async (input, signal) => {
    const raw = await api.post<Record<string, unknown>>(
      apiEndpoints.maintenance.calendarHolidays,
      {
        id: input.id ?? "",
        calendarId: input.calendarId,
        onDate: input.onDate,
        name: input.name,
        kind: input.kind ?? "official",
        recursAnnually: input.recursAnnually ?? false,
        jalaliMonth: input.jalaliMonth ?? 0,
        jalaliDay: input.jalaliDay ?? 0,
      },
      { signal, retry: 0 },
    );
    return toHoliday(raw ?? {});
  },
  deleteHoliday: async (holidayId, signal) => {
    await api.delete(apiEndpoints.maintenance.calendarHoliday(holidayId), { signal, retry: 0 });
  },
  saveShift: async (input, signal) => {
    const raw = await api.post<Record<string, unknown>>(
      apiEndpoints.maintenance.workShifts,
      {
        id: input.id ?? "",
        calendarId: input.calendarId,
        code: input.code,
        name: input.name,
        kind: input.kind ?? "general",
        startTime: input.startTime,
        endTime: input.endTime,
        weekdays: input.weekdays ?? [],
        headcount: input.headcount ?? 0,
        active: input.active ?? true,
      },
      { signal, retry: 0 },
    );
    return toWorkShift(raw ?? {});
  },
  deleteShift: async (shiftId, signal) => {
    await api.delete(apiEndpoints.maintenance.workShift(shiftId), { signal, retry: 0 });
  },
  getCapacityPlan: async (options, signal) => {
    const raw = await api.get<Record<string, unknown>>(
      apiEndpoints.maintenance.capacityPlan,
      {
        query: {
          calendarId: options.calendarId ?? "",
          locationId: options.locationId ?? "",
          fromDate: options.fromDate ?? "",
          toDate: options.toDate ?? "",
        },
        signal,
      },
    );
    return toCapacityPlan(raw ?? {});
  },
  getWorkingDay: async (options, signal) => {
    const raw = await api.get<Record<string, unknown>>(
      apiEndpoints.maintenance.workingDay,
      {
        query: {
          onDate: options.onDate,
          calendarId: options.calendarId ?? "",
          deviceId: options.deviceId ?? "",
          addWorkingDays: options.addWorkingDays ? String(options.addWorkingDays) : "",
        },
        signal,
      },
    );
    return toWorkingDayAnswer(raw ?? {});
  },
});
