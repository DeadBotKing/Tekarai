/**
 * The stock→purchase loop on screen.
 *
 * The panel's job is to make the arithmetic auditable: a buyer must be able
 * to see *why* the system wants 28 of something before pressing the button
 * that creates purchase documents. These tests pin the numbers that appear,
 * the permission gate on the button, and the behaviour after applying —
 * which is the part most likely to go quietly wrong, because the correct
 * answer afterwards is an empty table.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../app/configuration/runtimeConfig", () => ({
  runtimeConfig: {
    appName: "Tekarai",
    apiBaseUrl: "http://api.test.invalid",
    apiVersion: "v1",
    demoMode: false,
    realtimeEnabled: false,
  },
}));

import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { ReplenishmentPanel } from "../features/procurement/ReplenishmentPanel";

const SUGGESTIONS = [
  {
    partId: "p1",
    partCode: "BRG-6205",
    partName: "بلبرینگ",
    unit: "عدد",
    quantityOnHand: "2.000",
    minimumStock: "10.000",
    onOrderQuantity: "0",
    netAvailable: "2.000",
    suggestedQuantity: "28.000",
    estimatedUnitCost: "150000",
    estimatedTotal: "4200000.00",
    urgency: "high",
    reason: "موجودی خالص ۲ عدد / حداقل ۱۰ عدد",
    supplierId: "s1",
    supplierName: "پخش فنی تهران",
    leadTimeDays: 5,
  },
  {
    partId: "p2",
    partCode: "SEAL-22",
    partName: "کاسه‌نمد",
    unit: "عدد",
    quantityOnHand: "0",
    minimumStock: "5.000",
    onOrderQuantity: "3.000",
    netAvailable: "3.000",
    suggestedQuantity: "7.000",
    estimatedUnitCost: "90000",
    estimatedTotal: "630000.00",
    urgency: "critical",
    reason: "موجودی قابل‌استفاده صفر است",
    supplierId: null,
    supplierName: "",
    leadTimeDays: 0,
  },
];

const envelope = (data: unknown, meta: unknown = {}): Response =>
  new Response(JSON.stringify({ success: true, data, errors: [], meta }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

let posted: string[] = [];
let getCount = 0;

const stubApi = (options: { afterApply?: unknown[]; failGet?: boolean } = {}): void => {
  posted = [];
  getCount = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "POST") {
        posted.push(url);
        return Promise.resolve(
          envelope({
            createdRequisitions: ["PR-AAA111"],
            createdRequisitionIds: ["r1"],
            lineCount: 2,
            estimatedTotal: "4830000.00",
          }),
        );
      }
      getCount += 1;
      if (options.failGet) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              success: false,
              data: null,
              errors: [{ code: "SRV", message: "سرویس در دسترس نیست." }],
              meta: {},
            }),
            { status: 500, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      // The second GET is the reload after applying.
      if (getCount > 1 && options.afterApply) return Promise.resolve(envelope(options.afterApply));
      return Promise.resolve(envelope(SUGGESTIONS));
    }),
  );
};

const authenticate = (permissions: string[]): void =>
  sessionStore.set({
    accessToken: "test-access",
    refreshToken: "test-refresh",
    user: {
      id: "u1",
      displayName: "Test User",
      email: "test@example.test",
      role: "Procurement",
      permissions,
    },
  });

const renderPanel = (): void => {
  render(
    <AppProviders>
      <MemoryRouter>
        <ReplenishmentPanel />
      </MemoryRouter>
    </AppProviders>,
  );
};

describe("replenishment panel", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    authenticate(["procurement.requisition.create", "procurement.supplier.view"]);
  });

  it("shows every suggested part", async () => {
    stubApi();
    renderPanel();
    expect(await screen.findByText("BRG-6205")).toBeTruthy();
    expect(screen.getByText("SEAL-22")).toBeTruthy();
  });

  it("shows the arithmetic behind the number, not just the number", async () => {
    // A buyer who cannot see on-hand, inbound and net has no way to judge
    // whether the suggestion is sane, and will not trust it.
    stubApi();
    renderPanel();
    const row = (await screen.findByText("SEAL-22")).closest("tr");
    expect(row).toBeTruthy();
    // Read the cells positionally: a fuzzy text search matches digits
    // inside the money column too and proves nothing.
    const text = Array.from((row as HTMLElement).querySelectorAll("td")).map((cell) =>
      (cell.textContent ?? "").trim(),
    );
    // قطعه | فوریت | موجودی | حداقل | در راه | خالص | پیشنهاد | تأمین‌کننده | مبلغ
    expect(text).toContain("۰"); // on hand
    expect(text).toContain("۵"); // minimum
    expect(text).toContain("۳"); // already on order — the suppressing term
    expect(text.some((cell) => cell.includes("۷") && cell.includes("عدد"))).toBe(true);
  });

  it("marks urgency so a stockout is visually distinct", async () => {
    stubApi();
    renderPanel();
    expect(await screen.findByText("بحرانی")).toBeTruthy();
    expect(screen.getByText("بالا")).toBeTruthy();
  });

  it("says so plainly when a part has no supplier on file", async () => {
    stubApi();
    renderPanel();
    expect(await screen.findByText("تعیین‌نشده")).toBeTruthy();
  });

  it("totals the estimated spend", async () => {
    stubApi();
    renderPanel();
    // 4,200,000 + 630,000
    expect(await screen.findByText("۴٬۸۳۰٬۰۰۰")).toBeTruthy();
  });

  it("creates the requisitions and reports their numbers", async () => {
    const user = userEvent.setup();
    stubApi({ afterApply: [] });
    renderPanel();
    await user.click(await screen.findByRole("button", { name: /ساخت درخواست/ }));
    await waitFor(() => expect(posted.length).toBe(1));
    expect(posted[0]).toContain("procurement/replenishment");
    expect(await screen.findByText(/PR-AAA111/)).toBeTruthy();
  });

  it("re-reads after applying, so the cleared shortfall is visible", async () => {
    // The drafts it just created count as stock on order, so the honest
    // view afterwards is an empty list. Leaving the old rows on screen
    // would invite the user to press the button a second time.
    const user = userEvent.setup();
    stubApi({ afterApply: [] });
    renderPanel();
    await user.click(await screen.findByRole("button", { name: /ساخت درخواست/ }));
    expect(await screen.findByText("همه‌چیز بالای حداقل است")).toBeTruthy();
  });

  it("hides the create button from users who cannot raise requisitions", async () => {
    authenticate(["procurement.supplier.view"]);
    stubApi();
    renderPanel();
    expect(await screen.findByText("BRG-6205")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /ساخت درخواست/ })).toBeNull();
  });

  it("shows an empty state rather than a blank card when nothing is short", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(envelope([]))));
    renderPanel();
    expect(await screen.findByText("همه‌چیز بالای حداقل است")).toBeTruthy();
  });

  it("surfaces a failed load instead of pretending stock is healthy", async () => {
    // The dangerous failure mode: an error rendered as "nothing to order"
    // tells the warehouse everything is fine when nobody actually looked.
    stubApi({ failGet: true });
    renderPanel();
    await waitFor(() => expect(screen.queryByText("همه‌چیز بالای حداقل است")).toBeNull());
    expect(await screen.findByText("خطا")).toBeTruthy();
  });
});
