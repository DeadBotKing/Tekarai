// منطق خالص گزارشنامه‌ی هفتگی — گروه‌بندی دستگاه‌محور، شنبه‌آغاز (UTC → سازگار با ISO درخواست‌ها).
import type { WorkOrder } from "../../shared/types/domain";

export interface WeeklyDeviceGroup {
  deviceId: string;
  deviceLabel: string;
  orders: WorkOrder[];
  totalCount: number;
  completedCount: number;
  totalDowntimeMinutes: number;
  totalLabourHours: number;
  totalRepairCost: number;
}

export interface WeeklySummary {
  totalOrders: number;
  completedOrders: number;
  totalDowntimeMinutes: number;
  totalLabourHours: number;
  totalCost: number;
}

export interface WeekRange {
  fromIso: string;
  toIso: string;
}

const pad = (value: number): string => String(value).padStart(2, "0");
export const toIsoDate = (date: Date): string =>
  `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;

/** بازه‌ی هفته‌ی ایرانی (شنبه تا جمعه) — حساب UTC تا با ISO تاریخ‌های درخواست‌ها بخواند. */
export const iranianWeekRange = (ref: Date, weekOffset: 0 | -1 = 0): WeekRange => {
  const day = ref.getUTCDay();
  const daysSinceSaturday = (day + 1) % 7;
  const startUtc = Date.UTC(ref.getUTCFullYear(), ref.getUTCMonth(), ref.getUTCDate() - daysSinceSaturday + weekOffset * 7);
  const start = new Date(startUtc);
  const end = new Date(startUtc + 6 * 86_400_000);
  return { fromIso: toIsoDate(start), toIso: toIsoDate(end) };
};

export const isoInRange = (iso: string, fromIso: string, toIso: string): boolean => {
  const date = iso.slice(0, 10);
  return date >= fromIso && date <= toIso;
};

export const filterOrdersInRange = (orders: WorkOrder[], fromIso: string, toIso: string): WorkOrder[] =>
  orders.filter((order) => isoInRange(order.createdAt, fromIso, toIso));

export const groupOrdersByDevice = (
  orders: WorkOrder[],
  labelOfDevice: (deviceId: string) => string,
): WeeklyDeviceGroup[] => {
  const map = new Map<string, WeeklyDeviceGroup>();
  for (const order of orders) {
    let group = map.get(order.deviceId);
    if (!group) {
      group = {
        deviceId: order.deviceId,
        deviceLabel: labelOfDevice(order.deviceId),
        orders: [],
        totalCount: 0,
        completedCount: 0,
        totalDowntimeMinutes: 0,
        totalLabourHours: 0,
        totalRepairCost: 0,
      };
      map.set(order.deviceId, group);
    }
    group.orders.push(order);
    group.totalCount += 1;
    if (order.status === "completed") group.completedCount += 1;
    group.totalDowntimeMinutes += order.downtimeMinutes ?? 0;
    group.totalLabourHours += order.labourHours ?? 0;
    group.totalRepairCost += (order.labourCost ?? 0) + (order.partsCost ?? 0);
  }
  return [...map.values()].sort((a, b) => b.totalCount - a.totalCount);
};

export const summarizeWeek = (orders: WorkOrder[]): WeeklySummary => ({
  totalOrders: orders.length,
  completedOrders: orders.filter((order) => order.status === "completed").length,
  totalDowntimeMinutes: orders.reduce((sum, order) => sum + (order.downtimeMinutes ?? 0), 0),
  totalLabourHours: orders.reduce((sum, order) => sum + (order.labourHours ?? 0), 0),
  totalCost: orders.reduce(
    (sum, order) => sum + ((order.labourCost ?? 0) + (order.partsCost ?? 0)),
    0,
  ),
});

export const buildWeeklyCsv = (
  groups: WeeklyDeviceGroup[],
  statusLabel: (status: string) => string,
): string => {
  const rows: string[] = ["دستگاه,عنوان اقدام,وضعیت,تاریخ ثبت,توقف (دقیقه),ساعت تعمیر,هزینه کل"];
  for (const group of groups) {
    rows.push(
      `"${group.deviceLabel}","${group.totalCount} کار — ${group.completedCount} تکمیل — ${group.totalLabourHours} ساعت — ${group.totalRepairCost} ریال",,,,,`,
    );
    for (const order of group.orders) {
      rows.push(
        `"","${order.title.replace(/"/g, "'")}","${statusLabel(order.status)}","${order.createdAt.slice(0, 10)}","${order.downtimeMinutes ?? 0}","${order.labourHours ?? 0}","${(order.labourCost ?? 0) + (order.partsCost ?? 0)}"`,
      );
    }
  }
  return rows.join("\n");
};

export const weeklyReportFileName = (fromIso: string): string => `tekarai-week-report-${fromIso}.csv`;
