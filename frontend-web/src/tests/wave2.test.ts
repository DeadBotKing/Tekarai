import { beforeEach, describe, expect, it } from "vitest";
import {
  activeReservedForPart,
  availableStock,
  buildProformas,
  isMeterAlarmed,
  latestReading,
  nextDocumentVersion,
  priceChanged,
  usagePmDue,
  usagePmRemaining,
  type MeterReading,
  type ReorderLike,
  type Supplier,
} from "../features/maintenance/wave2";
import {
  closeReservation,
  getDocumentMeta,
  getMeterConfig,
  listMeterReadings,
  listReservations,
  listSuppliers,
  newId,
  saveDocumentMeta,
  saveMeterConfig,
  saveReservation,
  saveSupplier,
  setPartSupplier,
  getPartSupplierMap,
} from "../features/maintenance/wave2Store";

describe("کنتورها و PM مصرفی", () => {
  const hours: MeterReading[] = [
    { id: "a", deviceId: "d1", kind: "hours", value: 300, at: "2026-09-01T00:00:00Z", note: "" },
    { id: "b", deviceId: "d1", kind: "hours", value: 850, at: "2026-09-20T00:00:00Z", note: "" },
    { id: "c", deviceId: "d1", kind: "vibration", value: 8.4, at: "2026-09-21T00:00:00Z", note: "" },
  ];

  it("آخرین قرائت هر نوع جداست", () => {
    expect(latestReading(hours, "d1", "hours")!.value).toBe(850);
    expect(latestReading(hours, "d1", "temperature")).toBeUndefined();
  });

  it("داده‌ی بالاتر از آستانه → هشدار", () => {
    expect(isMeterAlarmed(latestReading(hours, "d1", "vibration"))).toBe(true); // 8.4 ≥ 7.1
    expect(isMeterAlarmed(latestReading(hours, "d1", "hours"))).toBe(false); // بدون آستانه
  });

  it("PM مصرفی با گذر از بازه فعال می‌شود و باقیمانده محاسبه می‌شود", () => {
    expect(usagePmDue(850, 100, 500)).toBe(true); // 750 < 500? خیر → true
    expect(usagePmDue(600, 100, 500)).toBe(true);
    expect(usagePmDue(550, 100, 500)).toBe(false);
    expect(usagePmDue(undefined, 100, 500)).toBe(false);
    expect(usagePmRemaining(550, 100, 500)).toBe(50);
  });
});

describe("تأمین‌کننده و پیش‌فاکتور", () => {
  const suppliers: Record<string, Supplier> = {
    s1: { id: "s1", name: "قطعه‌باران", phone: "", email: "" },
  };
  const lines: ReorderLike[] = [
    { partCode: "A", partName: "بلبرینگ", unit: "عدد", suggestedOrder: 10, unitCost: 1000, supplierId: "s1" },
    { partCode: "B", partName: "روغن", unit: "لیتر", suggestedOrder: 5, unitCost: 2000 },
  ];

  it("تغییر قیمت تشخیص داده می‌شود", () => {
    expect(priceChanged(100, 120)).toBe(true);
    expect(priceChanged(100, 100)).toBe(false);
  });

  it("پیش‌فاکتور به تفکیک تأمین‌کننده با جمع صحیح", () => {
    const proformas = buildProformas(lines, suppliers);
    expect(proformas).toHaveLength(2);
    const named = proformas.find((p) => p.supplierName === "قطعه‌باران")!;
    expect(named.lines[0].lineTotal).toBe(10_000);
    expect(named.grandTotal).toBe(10_000);
    const anon = proformas.find((p) => p.supplierName === "بدون تأمین‌کننده")!;
    expect(anon.grandTotal).toBe(10_000);
  });
});

describe("نسخه‌بندی اسناد", () => {
  it("نسخه‌ی اول و افزایش نسخه", () => {
    const first = nextDocumentVersion(undefined, { at: "2026-09-24", sizeLabel: "12 KB", note: "انتشار" });
    expect(first.currentVersion).toBe(1);
    const second = nextDocumentVersion({ ...first, documentId: "doc-1" }, { at: "2026-09-25", sizeLabel: "13 KB", note: "بازبینی" });
    expect(second.currentVersion).toBe(2);
    expect(second.history.map((h) => h.note)).toEqual(["انتشار", "بازبینی"]);
  });
});

describe("رزرو قطعات", () => {
  it("موجودی آزاد = دسترس منها رزرو فعال", () => {
    const reservations = [
      { id: "1", orderId: "w1", partCode: "A", quantity: 3, status: "active" as const, at: "" },
      { id: "2", orderId: "w2", partCode: "A", quantity: 2, status: "consumed" as const, at: "" },
    ];
    expect(activeReservedForPart(reservations, "A")).toBe(3);
    expect(availableStock(10, 3)).toBe(7);
    expect(availableStock(2, 5)).toBe(0);
  });
});

describe("ذخیره‌ی مرورگر (stores)", () => {
  beforeEach(() => { try { localStorage.clear(); } catch { /* node */ } });

  it("تأمین‌کننده + پیوند قطعه", () => {
    saveSupplier({ id: "s9", name: "تست قطعات", phone: "1", email: "" });
    expect(listSuppliers().some((s) => s.name === "تست قطعات")).toBe(true);
    setPartSupplier("SAL-9", "s9");
    expect(getPartSupplierMap()["SAL-9"]).toBe("s9");
  });

  it("تنظیمات PM مصرفی گردش کامل", () => {
    const config = getMeterConfig("dev-x");
    expect(config.intervalHours).toBe(500);
    saveMeterConfig({ deviceId: "dev-x", lastPmHoursAt: 120, intervalHours: 300 });
    expect(getMeterConfig("dev-x").intervalHours).toBe(300);
  });

  it("رزرو و سپس مصرف آن", () => {
    saveReservation({ id: newId("r"), orderId: "w9", partCode: "P1", quantity: 4, status: "active", at: "2026-09-24" });
    const rsv = listReservations().find((r) => r.orderId === "w9")!;
    closeReservation(rsv.id, "consumed");
    expect(listReservations().find((r) => r.id === rsv.id)!.status).toBe("consumed");
  });

  it("نسخه‌ی سند ذخیره و بازخوانی", () => {
    saveDocumentMeta({ documentId: "doc-9", currentVersion: 2, deviceCode: "DEV-2", history: [] });
    expect(getDocumentMeta("doc-9")!.currentVersion).toBe(2);
    expect(getDocumentMeta("doc-9")!.deviceCode).toBe("DEV-2");
  });

  it("خواندن کنتورها با قرائت جدید", () => {
    const before = listMeterReadings("dev-1").length;
    // فقط مرجع منطقی — seed demo دست کم شامل dev-1 است
    expect(before).toBeGreaterThanOrEqual(1);
  });
});
