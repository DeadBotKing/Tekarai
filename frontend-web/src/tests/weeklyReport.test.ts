import { describe, expect, it } from "vitest";
import {
  filterOrdersInRange,
  groupOrdersByDevice,
  iranianWeekRange,
  summarizeWeek,
  buildWeeklyCsv,
  weeklyReportFileName,
} from "../features/maintenance/workReports";
import type { WorkOrder } from "../shared/types/domain";

const order = (partial: Partial<WorkOrder>): WorkOrder => ({
  id: partial.id ?? "w1",
  deviceId: partial.deviceId ?? "dev-1",
  title: partial.title ?? "تعویض بلبرینگ",
  description: "",
  orderType: partial.orderType ?? "corrective",
  priority: "normal",
  status: partial.status ?? "completed",
  department: "general",
  requestedByName: "",
  assignedToName: "",
  resolutionNote: "",
  createdAt: partial.createdAt ?? "2026-09-27T09:00:00",
  closedAt: "",
  ...partial,
});

describe("بازه‌ی هفته‌ی ایرانی", () => {
  it("روز پنجشنبه → بازه‌ی شنبه تا جمعه‌ی همان هفته (UTC)", () => {
    // 2026-09-30 = چهارشنبه — روز هفته 3 → شنبه 26, جمعه 2 اکتبر
    const { fromIso, toIso } = iranianWeekRange(new Date(Date.UTC(2026, 8, 30)));
    expect(fromIso).toBe("2026-09-26");
    expect(toIso).toBe("2026-10-02");
  });

  it("هفته‌ی گذشته = بازه با آفست -۱", () => {
    const current = iranianWeekRange(new Date(Date.UTC(2026, 8, 30)));
    const previous = iranianWeekRange(new Date(Date.UTC(2026, 8, 30)), -1);
    const dayDiff = (new Date(current.fromIso).getTime() - new Date(previous.fromIso).getTime()) / 86_400_000;
    expect(dayDiff).toBe(7);
  });
});

describe("فیلتر و گروه‌بندی هفتگی", () => {
  const orders = [
    order({ id: "w1", deviceId: "dev-press", createdAt: "2026-09-27", downtimeMinutes: 45, labourHours: 2, labourCost: 100, partsCost: 50 }),
    order({ id: "w2", deviceId: "dev-press", createdAt: "2026-09-28", downtimeMinutes: 30, status: "inProgress" }),
    order({ id: "w3", deviceId: "dev-motor", createdAt: "2026-09-29", labourHours: 1 }),
    order({ id: "w4", deviceId: "dev-press", createdAt: "2026-09-10" }), // خارج از بازه
  ];

  it("از بازه فیلتر می‌شود", () => {
    const ranged = filterOrdersInRange(orders, "2026-09-26", "2026-10-02");
    expect(ranged).toHaveLength(3);
  });

  it("دستگاه‌ها بر اساس تعداد کار مرتب می‌شوند و جمع درست است", () => {
    const groups = groupOrdersByDevice(filterOrdersInRange(orders, "2026-09-26", "2026-10-02"), () => "برچسب");
    expect(groups[0].deviceId).toBe("dev-press");
    expect(groups[0].totalCount).toBe(2);
    expect(groups[0].completedCount).toBe(1);
    expect(groups[0].totalDowntimeMinutes).toBe(75);
    expect(groups[0].totalLabourHours).toBe(2);
    expect(groups[0].totalRepairCost).toBe(150);
  });

  it("خلاصه‌ی هفته", () => {
    const summary = summarizeWeek(filterOrdersInRange(orders, "2026-09-26", "2026-10-02"));
    expect(summary.totalOrders).toBe(3);
    expect(summary.completedOrders).toBe(2);
    expect(summary.totalLabourHours).toBe(3);
  });
});

describe("خروجی CSV", () => {
  it("هدر و سطرها با نام فایل درست", () => {
    const groups = groupOrdersByDevice(
      filterOrdersInRange([order({ id: "w1" })], "2026-09-26", "2026-10-02"),
      () => "پرس ریمک",
    );
    const csv = buildWeeklyCsv(groups, (status) => status);
    expect(csv).toContain("دستگاه,عنوان اقدام");
    expect(csv).toContain("پرس ریمک");
    expect(weeklyReportFileName("2026-09-26")).toBe("tekarai-week-report-2026-09-26.csv");
  });
});
