export interface MetricDetails {
  columns: string[];
  rows: string[][];
  note?: string;
  links?: (string | undefined)[];
}
const labels: Record<string, string> = {
  submitted: "ثبت‌شده", routed: "ارجاع‌شده", assigned: "تخصیص‌یافته", inProgress: "در حال انجام", onHold: "متوقف", pendingApproval: "در انتظار تأیید", completed: "تکمیل‌شده", cancelled: "لغوشده",
  active: "فعال", inactive: "غیرفعال", pending: "در انتظار", archived: "بایگانی", atRisk: "در معرض ریسک", backlog: "در انتظار", review: "در حال بررسی", done: "انجام‌شده",
  operational: "فعال", underMaintenance: "در حال تعمیر", outOfService: "خارج از سرویس", retired: "از رده خارج", manual: "دستی", sensor: "حسگر", critical: "بحرانی", high: "زیاد", medium: "متوسط", low: "کم",
  good: "معتبر", suspect: "مشکوک", estimated: "برآوردی", bad: "نامعتبر", normal: "عادی", vital: "حیاتی",
  mechanical: "مکانیک", electrical: "برق", general: "عمومی", hydraulic: "هیدرولیک", instrumentation: "ابزار دقیق", site: "سایت", building: "ساختمان", room: "اتاق",
};
function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "بله" : "خیر";
  if (Array.isArray(value)) return value.map(display).join("، ");
  return labels[String(value)] ?? String(value);
}
/** Explicit field lists keep details meaningful and never dump arbitrary/private objects. */
export function metricDetail<T>(rows: readonly T[], fields: readonly (readonly [keyof T, string])[], note?: string, link?: (row: T) => string | undefined): MetricDetails {
  return { links: link ? rows.map(link) : undefined, columns: fields.map(f => f[1]), rows: rows.map(row => fields.map(([key]) => display(row[key]))), note };
}
