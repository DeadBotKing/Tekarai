import type { CapacityDay, WorkShift } from "../../shared/types/domain";

/**
 * Pure calendar arithmetic for the UI (Phase 28).
 *
 * Mirrors the backend's `workCalendarRules` closely enough for the demo
 * service and the month grid to agree with the API, and is kept free of React
 * so it can be tested directly.
 *
 * Weekday numbers are python's: Monday 0 … Sunday 6. `WEEKDAY_ORDER_IR`
 * handles the شنبه-first display order; it is a view concern only.
 */

export const ISO_DAY = 86_400_000;

/** `YYYY-MM-DD` for a Date, in local terms — never the UTC shift. */
export const isoDate = (value: Date): string => {
  const year = value.getFullYear();
  const month = `${value.getMonth() + 1}`.padStart(2, "0");
  const day = `${value.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
};

/** Parse `YYYY-MM-DD` into a local midnight Date. */
export const parseIso = (value: string): Date => {
  const [year, month, day] = value.split("-").map((part) => Number(part));
  return new Date(year, (month || 1) - 1, day || 1);
};

/**
 * Python-style weekday (Mon 0 … Sun 6) from a JS Date (Sun 0 … Sat 6).
 *
 * The two conventions differ by one rotation, and getting this wrong silently
 * shifts every weekend by a day — which is why it lives in one named function
 * rather than being inlined.
 */
export const pyWeekday = (value: Date): number => (value.getDay() + 6) % 7;

export const addDays = (value: Date, days: number): Date =>
  new Date(value.getFullYear(), value.getMonth(), value.getDate() + days);

export interface CalendarShape {
  weekendDays: number[];
  holidays: Set<string>;
  rollPolicy?: "forward" | "backward" | "none";
}

export const isWeekendDay = (shape: CalendarShape, iso: string): boolean =>
  shape.weekendDays.includes(pyWeekday(parseIso(iso)));

export const isHolidayDay = (shape: CalendarShape, iso: string): boolean =>
  shape.holidays.has(iso);

export const isWorkingDay = (shape: CalendarShape, iso: string): boolean =>
  !isWeekendDay(shape, iso) && !isHolidayDay(shape, iso);

/** Bounded like the backend's MAX_ROLL_DAYS so a bad calendar cannot hang the tab. */
export const MAX_ROLL_DAYS = 30;

export const rollToWorkingDay = (shape: CalendarShape, iso: string): string => {
  if (isWorkingDay(shape, iso)) return iso;
  const policy = shape.rollPolicy ?? "forward";
  if (policy === "none") return iso;
  const step = policy === "backward" ? -1 : 1;
  let cursor = parseIso(iso);
  for (let index = 0; index < MAX_ROLL_DAYS; index += 1) {
    cursor = addDays(cursor, step);
    const candidate = isoDate(cursor);
    if (isWorkingDay(shape, candidate)) return candidate;
  }
  return iso;
};

/** Every date from `from` to `to` inclusive, as ISO strings. */
export const dateRange = (from: string, to: string): string[] => {
  const start = parseIso(from);
  const end = parseIso(to);
  if (end < start) return [];
  const out: string[] = [];
  let cursor = start;
  // Bounded for the same reason the backend bounds its plan window.
  while (cursor <= end && out.length < 400) {
    out.push(isoDate(cursor));
    cursor = addDays(cursor, 1);
  }
  return out;
};

const toNumber = (value: string): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

/** Shift length in hours, honouring a window that crosses midnight. */
export const shiftDurationHours = (shift: Pick<WorkShift, "startTime" | "endTime">): number => {
  const [startH, startM] = shift.startTime.split(":").map((part) => Number(part) || 0);
  const [endH, endM] = shift.endTime.split(":").map((part) => Number(part) || 0);
  const start = startH * 60 + startM;
  const end = endH * 60 + endM;
  // Equal times mean a continuous 24h shift, not a zero-length one.
  const span = end > start ? end - start : end + 1440 - start;
  return Math.round((span / 60) * 100) / 100;
};

/**
 * Tone for a day cell in the capacity grid.
 *
 * `closed` outranks everything: a shut plant is not "idle capacity", and
 * colouring it green would invite someone to schedule work onto it.
 */
export type CapacityTone = "closed" | "over" | "tight" | "ok" | "idle";

export const capacityTone = (day: Pick<CapacityDay, "isWorkingDay" | "utilisationPercent" | "demandHours">): CapacityTone => {
  if (!day.isWorkingDay) return "closed";
  const used = toNumber(day.utilisationPercent);
  if (used > 100) return "over";
  if (used >= 80) return "tight";
  if (toNumber(day.demandHours) > 0) return "ok";
  return "idle";
};

/**
 * Pad a month so the grid starts on شنبه and ends on جمعه.
 *
 * Returns the ISO dates to render plus how many blanks precede them, so the
 * caller can lay out a seven-column grid without recomputing the offset.
 */
export const monthGridOffset = (firstIso: string): number => {
  // شنبه is python weekday 5; the grid's first column. Rotating by 5 maps
  // شنبه→0, یکشنبه→1 … جمعه→6.
  const weekday = pyWeekday(parseIso(firstIso));
  return (weekday + 2) % 7;
};
