import { describe, expect, it, beforeEach } from "vitest";
import {
  FAILURE_TREE,
  buildDeviceTree,
  buildInspectionWorkOrderDraft,
  buildReorderSuggestions,
  failedTemplateItems,
  findFailureLabel,
  formatFailureNote,
  isSlaBreached,
  slaBreachedOrders,
  type InspectionTemplate,
} from "../features/maintenance/wave1";
import {
  deleteInspectionTemplate,
  listInspectionTemplates,
  newTemplateId,
  saveInspectionTemplate,
} from "../features/maintenance/inspectionsStore";

const device = (id: string, location: string, department = "") => ({
  id,
  code: id.toUpperCase(),
  name: `دستگاه ${id}`,
  location,
  department,
});

describe("درخت تجهیزات (buildDeviceTree)", () => {
  it("گروه‌بندی سلسله‌مراتبی بر اساس locationPath و شمارنده‌ی درخواست‌های باز", () => {
    const devices = [
      { ...device("d1", "", ""), locationPath: "کارخانه ۱/سالن A/خط ۱" },
      { ...device("d2", "", ""), locationPath: "کارخانه ۱/سالن A/خط ۱" },
      { ...device("d3", "", ""), locationPath: "کارخانه ۱/سالن B" },
      { ...device("d4", "بدون مکان") },
    ];
    const orders = [
      { id: "w1", deviceId: "d1", status: "inProgress" },
      { id: "w2", deviceId: "d3", status: "completed" }, // بسته — شمرده نشود
      { id: "w3", deviceId: "d4", status: "pendingApproval" },
    ];
    const tree = buildDeviceTree(devices, orders);
    const plant = tree.find((node) => node.label === "کارخانه ۱")!;
    expect(plant.children.map((c) => c.label)).toEqual(["سالن A", "سالن B"]);
    const hallA = plant.children[0];
    expect(hallA.children[0].devices.map((d) => d.id)).toEqual(["d1", "d2"]);
    expect(plant.openWorkOrders).toBe(1); // فقط w1
    const other = tree.find((node) => node.label === "بدون مکان")!;
    expect(other.openWorkOrders).toBe(1); // w3
  });

  it("دستگاه بدون مکان در گره «سایر» نمی‌نشیند اگر department داشته باشد", () => {
    const tree = buildDeviceTree([device("a1", "", "تولید")], []);
    expect(tree[0].label).toBe("تولید");
  });
});

describe("کد و علت خرابی (RCA)", () => {
  it("درخت شامل پنج دسته‌ی اصلی با علت‌های استاندارد است", () => {
    expect(FAILURE_TREE).toHaveLength(5);
    expect(FAILURE_TREE.every((c) => c.reasons.length >= 2)).toBe(true);
  });

  it("برچسب دسته/علت و قالب‌بندی یادداشت تأیید", () => {
    expect(findFailureLabel("mec", "mec-bearing")).toBe("مکانیکی / خرابی بلبرینگ یا بوش");
    const note = formatFailureNote("ele", "ele-power", "  قطعه تعویض شد. ");
    expect(note).toContain("کد/علت خرابی: [برق و الکترونیک / نوسان یا قطع برق]");
    expect(note).toContain("قطعه تعویض شد.");
  });

  it("بدون کد انتخابی، یادداشت خام برمی‌گردد", () => {
    expect(formatFailureNote("", "", "تست")).toBe("تست");
  });
});

describe("نقطه‌ی سفارش قطعات", () => {
  const parts = [
    { code: "SAL-1", name: "بلبرینگ", unit: "عدد", quantityOnHand: 2, minimumStock: 5 },
    { code: "SAL-2", name: "روغن", unit: "لیتر", quantityOnHand: 30, minimumStock: 10 },
    { code: "SAL-3", name: "فیلتر", unit: "عدد", quantityOnHand: 0, minimumStock: 3 },
  ];

  it("فقط قطعات زیر حداقل، با فرمول دو برابر حداقل منها موجودی", () => {
    const suggestions = buildReorderSuggestions(parts);
    expect(suggestions.map((s) => s.partCode)).toEqual(["SAL-1", "SAL-3"]); // کمبود مساوی، بر اساس کد قطعه مرتب
    expect(suggestions.find((s) => s.partCode === "SAL-1")!.suggestedOrder).toBe(8);
    expect(suggestions.find((s) => s.partCode === "SAL-3")!.suggestedOrder).toBe(6);
  });

  it("بدون کمبود → لیست خالی", () => {
    expect(buildReorderSuggestions([{ code: "X", name: "x", unit: "عدد", quantityOnHand: 9, minimumStock: 3 }])).toEqual([]);
  });
});

describe("SLA و عقب‌ماندگی", () => {
  const now = new Date("2026-09-27T12:00:00Z");
  const openLate = { id: "o1", deviceId: "d", status: "assigned", slaDueAt: "2026-09-20T00:00:00Z" };
  const openOnTime = { id: "o2", deviceId: "d", status: "routed", slaDueAt: "2099-01-01T00:00:00Z" };
  const closedLate = { id: "o3", deviceId: "d", status: "completed", slaDueAt: "2020-01-01T00:00:00Z" };
  const noDue = { id: "o4", deviceId: "d", status: "submitted" };

  it("فقط درخواست‌های باز و پاس‌هریکیکی‌از SLA شمرده می‌شوند", () => {
    expect(isSlaBreached(openLate, now)).toBe(true);
    expect(isSlaBreached(openOnTime, now)).toBe(false);
    expect(isSlaBreached(closedLate, now)).toBe(false);
    expect(isSlaBreached(noDue, now)).toBe(false);
  });

  it("فیلتر لیستی", () => {
    expect(slaBreachedOrders([openLate, openOnTime, closedLate, noDue], now).map((o) => o.id)).toEqual(["o1"]);
  });
});

describe("چک‌لیست بازرسی", () => {
  const template: InspectionTemplate = {
    id: "t1",
    title: "بازرسی هفتگی",
    deviceCode: "",
    items: [
      { id: "i1", text: "صدا" },
      { id: "i2", text: "روغن" },
      { id: "i3", text: "دما" },
      { id: "i4", text: "پیچ" },
    ],
  };

  it("موارد نامقبول تشخیص داده می‌شوند", () => {
    const run = [
      { itemId: "i1", ok: true },
      { itemId: "i2", ok: false },
      { itemId: "i3", ok: false },
      { itemId: "i4", ok: true },
    ];
    expect(failedTemplateItems(template, run).map((i) => i.id)).toEqual(["i2", "i3"]);
  });

  it("پیش‌نویس دستور کار: سه یا بیشتر fail → اولویت بالا و فهرست موارد در متن", () => {
    const failed = template.items.slice(0, 3);
    const draft = buildInspectionWorkOrderDraft(
      { id: "dev-9", code: "PRT-9", name: "پمپ" },
      template,
      failed,
    );
    expect(draft.deviceId).toBe("dev-9");
    expect(draft.priority).toBe("high");
    expect(draft.title).toContain("بازرسی هفتگی");
    expect(draft.description).toContain("• صدا");
    expect(draft.description).toContain("• دما");
  });

  it("یک fail → اولویت عادی", () => {
    const draft = buildInspectionWorkOrderDraft({ id: "d", code: "c", name: "n" }, template, [template.items[0]]);
    expect(draft.priority).toBe("normal");
  });
});

describe("انبارچه‌ی قالب‌های بازرسی (localStorage)", () => {
  beforeEach(() => localStorage.clear());

  it("ذخیره/خواندن/حذف قالب‌ها", () => {
    const initial = listInspectionTemplates();
    expect(initial.length).toBeGreaterThan(0); // داده‌ی نمونه
    const tpl = { id: newTemplateId(), title: "تست جدید", deviceCode: "DEV-1", items: [{ id: "i1", text: "مورد ۱" }] };
    saveInspectionTemplate(tpl);
    expect(listInspectionTemplates().some((t) => t.title === "تست جدید")).toBe(true);
    deleteInspectionTemplate(tpl.id);
    expect(listInspectionTemplates().some((t) => t.id === tpl.id)).toBe(false);
  });
});
