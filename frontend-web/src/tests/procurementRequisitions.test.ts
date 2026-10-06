import { describe, expect, it } from "vitest";
import {
  statusLabel,
  statusTone,
  waitingLabel,
} from "../features/procurement/requisitionPresentation";

describe("purchase document status labels", () => {
  it("translates the requisition vocabulary, including the new terminal state", () => {
    expect(statusLabel("submitted")).toBe("ارسال‌شده");
    expect(statusLabel("ordered")).toBe("سفارش داده شد");
    expect(statusLabel("purchased")).toBe("خریدشده");
  });

  it("translates the purchase-order vocabulary", () => {
    expect(statusLabel("partiallyReceived")).toBe("تحویل جزئی");
    expect(statusLabel("received")).toBe("تحویل‌شده");
  });

  it("falls back to the raw value instead of rendering an empty cell", () => {
    expect(statusLabel("somethingNew")).toBe("somethingNew");
  });

  it("reads a completed purchase as success, not as work in progress", () => {
    expect(statusTone("purchased")).toBe("success");
    expect(statusTone("cancelled")).toBe("danger");
    expect(statusTone("submitted")).toBe("warning");
  });
});

describe("how long a purchase request has been waiting", () => {
  it("calls out a stale request", () => {
    expect(
      waitingLabel({ status: "submitted", submittedAt: "2026-01-01T00:00:00Z", daysWaiting: 9, isStale: true }),
    ).toBe("9 روز معطل");
  });

  it("states the wait plainly while still inside the threshold", () => {
    expect(
      waitingLabel({ status: "submitted", submittedAt: "2026-01-01T00:00:00Z", daysWaiting: 3, isStale: false }),
    ).toBe("3 روز");
  });

  it("does not pretend an unsubmitted draft is being worked on", () => {
    // "0 روز" would read as "in progress since today"; nobody has been
    // asked to buy anything yet.
    expect(waitingLabel({ status: "draft", submittedAt: null })).toBe("ارسال نشده");
  });
});
