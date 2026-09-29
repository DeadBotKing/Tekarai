import { describe, expect, it } from "vitest";
import { seedDemoLedger, signedQuantity } from "../pages/SparePartsPage";
import type { SparePart } from "../shared/types/domain";

const part: SparePart = {
  id: "sp-1",
  code: "SAL-4021",
  name: "بلبرینگ 6204",
  unit: "عدد",
  quantityOnHand: 42,
  minimumStock: 20,
  unitCost: 185_000,
  lowStock: false,
  createdAt: "1405/05/12",
  updatedAt: "",
};

describe("signedQuantity — علامت از نوع تراکنش مشتق می‌شود", () => {
  it("رسید و برگشت همیشه مثبت", () => {
    expect(signedQuantity("RECEIPT", 5)).toBe(5);
    expect(signedQuantity("RECEIPT", -5)).toBe(5);
    expect(signedQuantity("RETURN", 3)).toBe(3);
  });
  it("حواله همیشه منفی", () => {
    expect(signedQuantity("ISSUE", 4)).toBe(-4);
    expect(signedQuantity("ISSUE", -4)).toBe(-4);
  });
  it("تعدیل علامت کاربر را نگه می‌دارد", () => {
    expect(signedQuantity("ADJUSTMENT", -2)).toBe(-2);
    expect(signedQuantity("ADJUSTMENT", 2)).toBe(2);
  });
});

describe("seedDemoLedger — دفتر نمایشی به موجودی فعلی می‌رسد", () => {
  it("مانده‌ی ردیف اخیر برابر موجودی قطعه است", () => {
    const rows = seedDemoLedger(part);
    expect(rows[0].balanceAfter).toBe(part.quantityOnHand);
    // زنجیره‌ی مانده: رسید + تعدیل = موجودی
    const [latest, first] = rows;
    expect(latest.balanceAfter).toBe(first.balanceAfter + latest.quantity);
  });
});
