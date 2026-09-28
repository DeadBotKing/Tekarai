import { beforeEach, describe, expect, it } from "vitest";
import {
  activeReservedForPart,
  availableStock,
  reservationsForOrder,
} from "../features/maintenance/wave2";
import {
  closeReservation,
  listReservations,
  newId,
  saveReservation,
} from "../features/maintenance/wave2Store";

describe("رزرو قطعات (منطق)", () => {
  it("رزرو فعال بر اساس کد قطعه جمع می‌شود و وضعیت‌های بسته حساب نیستند", () => {
    const reservations = [
      { id: "1", orderId: "w1", partCode: "A", quantity: 3, status: "active" as const, at: "" },
      { id: "2", orderId: "w2", partCode: "A", quantity: 2, status: "consumed" as const, at: "" },
      { id: "3", orderId: "w3", partCode: "A", quantity: 1, status: "released" as const, at: "" },
      { id: "4", orderId: "w4", partCode: "B", quantity: 9, status: "active" as const, at: "" },
    ];
    expect(activeReservedForPart(reservations, "A")).toBe(3);
    expect(activeReservedForPart(reservations, "B")).toBe(9);
    expect(activeReservedForPart(reservations, "C")).toBe(0);
  });

  it("موجودی آزاد هرگز منفی نمی‌شود", () => {
    expect(availableStock(10, 3)).toBe(7);
    expect(availableStock(2, 5)).toBe(0);
    expect(availableStock(0, 0)).toBe(0);
  });

  it("فقط رزروهای فعال همان درخواست برمی‌گردد", () => {
    const reservations = [
      { id: "1", orderId: "w1", partCode: "A", quantity: 3, status: "active" as const, at: "" },
      { id: "2", orderId: "w1", partCode: "B", quantity: 1, status: "consumed" as const, at: "" },
      { id: "3", orderId: "w2", partCode: "C", quantity: 5, status: "active" as const, at: "" },
    ];
    expect(reservationsForOrder(reservations, "w1").map((r) => r.partCode)).toEqual(["A"]);
  });
});

describe("رزرو قطعات (ذخیره‌ی مرورگر)", () => {
  beforeEach(() => {
    try {
      localStorage.clear();
    } catch {
      /* محیط بدون localStorage */
    }
  });

  it("ثبت و سپس مصرف رزرو", () => {
    saveReservation({ id: newId("rsv"), orderId: "w9", partCode: "P1", quantity: 4, status: "active", at: "2026-09-24" });
    const saved = listReservations().find((reservation) => reservation.orderId === "w9")!;
    expect(saved.quantity).toBe(4);
    closeReservation(saved.id, "consumed");
    expect(listReservations().find((reservation) => reservation.id === saved.id)!.status).toBe("consumed");
  });

  it("آزادسازی رزرو", () => {
    saveReservation({ id: "fixed-id", orderId: "w1", partCode: "P2", quantity: 1, status: "active", at: "2026-09-24" });
    closeReservation("fixed-id", "released");
    expect(listReservations()[0].status).toBe("released");
  });
});
