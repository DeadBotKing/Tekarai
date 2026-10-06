/**
 * A purchase requisition carries several parts.
 *
 * The API has always accepted `lines: [...]` with `min_length=1` and totalled
 * across them, but the form built exactly one line from a single `partId`, so
 * ordering three parts meant raising three separate requests. The "افزودن
 * قطعه" button next to the part picker did not add a line either — it opened
 * the warehouse part-registration dialog, which is what a user pressing it
 * actually reported running into.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
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
import { ProcurementPage } from "../pages/ProcurementPage";

const PARTS = [
  { id: "p1", code: "BRG-6205", name: "بلبرینگ", unit: "عدد", unitCost: 150000 },
  { id: "p2", code: "SEAL-22", name: "کاسه‌نمد", unit: "عدد", unitCost: 90000 },
  { id: "p3", code: "OIL-68", name: "روغن هیدرولیک", unit: "لیتر", unitCost: 420000 },
];

const envelope = (data: unknown): Response =>
  new Response(JSON.stringify({ success: true, data, errors: [], meta: {} }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

/** Captured bodies of every POST the page made. */
let posted: { url: string; body: Record<string, unknown> }[] = [];

const stubApi = (): void => {
  posted = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "POST") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
        posted.push({ url, body });
        if (url.includes("spare-parts")) {
          // The API echoes the stored part, which the form then selects.
          return Promise.resolve(
            envelope({
              id: "p-new",
              code: body.code,
              name: body.name,
              unit: body.unit ?? "عدد",
              unitCost: Number(body.unitCost ?? 0),
            }),
          );
        }
        return Promise.resolve(
          envelope({ id: "pr-new", number: "PR-NEW", status: "draft", total: 0 }),
        );
      }
      if (url.includes("spare-parts")) return Promise.resolve(envelope(PARTS));
      if (url.includes("procurement/dashboard")) return Promise.resolve(envelope({}));
      return Promise.resolve(envelope([]));
    }),
  );
};

const authenticate = (): void =>
  sessionStore.set({
    accessToken: "test-access",
    refreshToken: "test-refresh",
    user: {
      id: "u1",
      displayName: "Test User",
      email: "test@example.test",
      role: "Procurement",
      permissions: [
        "procurement.requisition.create",
        "procurement.requisition.view",
        "procurement.supplier.manage",
      ],
    },
  });

const openRequisitionForm = async (user: ReturnType<typeof userEvent.setup>): Promise<void> => {
  render(
    <AppProviders>
      <MemoryRouter>
        <ProcurementPage />
      </MemoryRouter>
    </AppProviders>,
  );
  await user.click(await screen.findByRole("button", { name: "درخواست خرید جدید" }));
  await screen.findByRole("dialog", { name: /درخواست خرید جدید/ });
};

/** Fill the composer row with a part and a quantity. */
const compose = async (
  user: ReturnType<typeof userEvent.setup>,
  partId: string,
  quantity: string,
  note?: string,
): Promise<void> => {
  await user.selectOptions(screen.getByLabelText(/قطعه انبار/), partId);
  const qty = screen.getByLabelText(/^تعداد/);
  await user.clear(qty);
  await user.type(qty, quantity);
  if (note !== undefined) await user.type(screen.getByLabelText(/توضیحات این قطعه/), note);
};

describe("purchase requisition with several parts", () => {
  beforeEach(() => {
    stubApi();
    authenticate();
  });

  it("adds each chosen part to the request as its own line", async () => {
    const user = userEvent.setup();
    await openRequisitionForm(user);

    await compose(user, "p1", "4");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));
    await compose(user, "p2", "2");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));

    const basket = screen.getByRole("table");
    expect(within(basket).getByText(/BRG-6205/)).toBeInTheDocument();
    expect(within(basket).getByText(/SEAL-22/)).toBeInTheDocument();
    // 4 × 150000 + 2 × 90000 = 780000
    expect(within(basket).getByText("۷۸۰٬۰۰۰")).toBeInTheDocument();
  });

  it("sends every line to the API, not just the last part picked", async () => {
    const user = userEvent.setup();
    await openRequisitionForm(user);

    await compose(user, "p1", "4");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));
    await compose(user, "p2", "2");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));
    await compose(user, "p3", "10");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));

    await user.click(screen.getByRole("button", { name: "ثبت درخواست" }));

    await waitFor(() => expect(posted).toHaveLength(1));
    const lines = posted[0].body.lines as { partId: string; quantity: number }[];
    expect(lines).toHaveLength(3);
    expect(lines.map((line) => line.partId)).toEqual(["p1", "p2", "p3"]);
    expect(lines.map((line) => line.quantity)).toEqual([4, 2, 10]);
  });

  it("merges a part chosen twice instead of writing a confusing duplicate row", async () => {
    const user = userEvent.setup();
    await openRequisitionForm(user);

    await compose(user, "p1", "4");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));
    await compose(user, "p1", "3");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));

    await user.click(screen.getByRole("button", { name: "ثبت درخواست" }));
    await waitFor(() => expect(posted).toHaveLength(1));
    const lines = posted[0].body.lines as { partId: string; quantity: number }[];
    expect(lines).toHaveLength(1);
    expect(lines[0].quantity).toBe(7);
  });

  it("still accepts a single-part request without pressing add first", async () => {
    const user = userEvent.setup();
    await openRequisitionForm(user);

    await compose(user, "p2", "5");
    await user.click(screen.getByRole("button", { name: "ثبت درخواست" }));

    await waitFor(() => expect(posted).toHaveLength(1));
    const lines = posted[0].body.lines as { partId: string; quantity: number }[];
    expect(lines).toHaveLength(1);
    expect(lines[0].partId).toBe("p2");
    expect(lines[0].quantity).toBe(5);
  });

  it("refuses an empty request instead of posting a requisition with no parts", async () => {
    const user = userEvent.setup();
    await openRequisitionForm(user);

    await user.click(screen.getByRole("button", { name: "ثبت درخواست" }));
    expect(await screen.findByText(/حداقل یک قطعه/)).toBeInTheDocument();
    expect(posted).toHaveLength(0);
  });

  it("removes a line the user changed their mind about", async () => {
    const user = userEvent.setup();
    await openRequisitionForm(user);

    await compose(user, "p1", "4");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));
    await compose(user, "p2", "2");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));

    await user.click(screen.getByRole("button", { name: /حذف بلبرینگ/ }));
    await user.click(screen.getByRole("button", { name: "ثبت درخواست" }));

    await waitFor(() => expect(posted).toHaveLength(1));
    const lines = posted[0].body.lines as { partId: string }[];
    expect(lines.map((line) => line.partId)).toEqual(["p2"]);
  });

  it("does not leave lines behind for the next requisition", async () => {
    const user = userEvent.setup();
    await openRequisitionForm(user);

    await compose(user, "p1", "4");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));
    await user.click(screen.getByRole("button", { name: "ثبت درخواست" }));
    await waitFor(() => expect(posted).toHaveLength(1));

    await user.click(await screen.findByRole("button", { name: "درخواست خرید جدید" }));
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows the amount of a requisition, which reports it as totalEstimated", async () => {
    // Orders and invoices expose `total`; a requisition exposes
    // `totalEstimated`, and the shared column only read the former.
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.includes("procurement/requisitions")) {
          return Promise.resolve(
            envelope([
              { id: "pr-1", number: "PR-0001", status: "submitted", totalEstimated: "4980000.00", lines: [] },
            ]),
          );
        }
        if (url.includes("spare-parts")) return Promise.resolve(envelope(PARTS));
        return Promise.resolve(envelope([]));
      }),
    );
    const user = userEvent.setup();
    render(
      <AppProviders>
        <MemoryRouter>
          <ProcurementPage />
        </MemoryRouter>
      </AppProviders>,
    );
    await user.click(await screen.findByRole("tab", { name: "درخواست\u200cها" }));
    expect(await screen.findByText("۴٬۹۸۰٬۰۰۰")).toBeInTheDocument();
  });

  it("offers «افزودن قطعه جدید» inside the part dropdown itself", async () => {
    const user = userEvent.setup();
    await openRequisitionForm(user);

    const picker = screen.getByLabelText(/قطعه انبار/);
    // The entry lives in the list, where someone looking for a missing part
    // actually looks, rather than as separate chrome beside it.
    expect(
      within(picker).getByRole("option", { name: /افزودن قطعه جدید/ }),
    ).toBeInTheDocument();

    expect(screen.queryByLabelText(/کد قطعه/)).not.toBeInTheDocument();
    await user.selectOptions(picker, "__addPart__");
    expect(screen.getByLabelText(/کد قطعه/)).toBeInTheDocument();
    // Still one window — the fields expanded in place.
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
  });

  it("types a part by hand, registers it, and uses it on the request", async () => {
    const user = userEvent.setup();
    await openRequisitionForm(user);

    await user.selectOptions(screen.getByLabelText(/قطعه انبار/), "__addPart__");
    await user.type(screen.getByLabelText(/کد قطعه/), "FLT-900");
    await user.type(screen.getByLabelText(/نام قطعه/), "فیلتر هوا");
    const cost = screen.getByLabelText(/^قیمت واحد/);
    await user.clear(cost);
    await user.type(cost, "250000");
    await user.click(screen.getByRole("button", { name: /ثبت قطعه و انتخاب آن/ }));

    // Registered in the warehouse...
    await waitFor(() => expect(posted.some((x) => x.url.includes("spare-parts"))).toBe(true));
    const partPost = posted.find((x) => x.url.includes("spare-parts"));
    expect(partPost?.body.code).toBe("FLT-900");

    // ...and the panel closed with the new part already selected.
    await waitFor(() => expect(screen.queryByLabelText(/کد قطعه/)).not.toBeInTheDocument());
    const qty = screen.getByLabelText(/^تعداد/);
    await user.clear(qty);
    await user.type(qty, "3");
    await user.click(screen.getByRole("button", { name: "ثبت درخواست" }));

    await waitFor(() => expect(posted.some((x) => x.url.includes("requisitions"))).toBe(true));
    const reqPost = posted.find((x) => x.url.includes("requisitions"));
    const lines = reqPost?.body.lines as { partCode: string; quantity: number }[];
    expect(lines).toHaveLength(1);
    expect(lines[0].partCode).toBe("FLT-900");
    expect(lines[0].quantity).toBe(3);
  });


  it("carries a note on the line it was typed for", async () => {
    const user = userEvent.setup();
    await openRequisitionForm(user);

    await compose(user, "p1", "4", "برای پمپ خط ۳");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));
    await compose(user, "p2", "2", "فوری");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));

    const basket = screen.getByRole("table");
    expect(within(basket).getByText("برای پمپ خط ۳")).toBeInTheDocument();
    expect(within(basket).getByText("فوری")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "ثبت درخواست" }));
    await waitFor(() => expect(posted).toHaveLength(1));
    const lines = posted[0].body.lines as { partId: string; note: string }[];
    // Each note stays attached to its own part, not to the request as a whole.
    expect(lines.find((line) => line.partId === "p1")?.note).toBe("برای پمپ خط ۳");
    expect(lines.find((line) => line.partId === "p2")?.note).toBe("فوری");
  });

  it("clears the note box after the line is added", async () => {
    const user = userEvent.setup();
    await openRequisitionForm(user);

    await compose(user, "p1", "2", "جنس استیل");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));
    // Otherwise the previous explanation silently follows the next part.
    expect(screen.getByLabelText(/توضیحات این قطعه/)).toHaveValue("");
  });

  it("keeps both notes when the same part is added twice", async () => {
    const user = userEvent.setup();
    await openRequisitionForm(user);

    await compose(user, "p1", "4", "برای پمپ");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));
    await compose(user, "p1", "3", "برای فن");
    await user.click(screen.getByRole("button", { name: /افزودن به درخواست/ }));

    await user.click(screen.getByRole("button", { name: "ثبت درخواست" }));
    await waitFor(() => expect(posted).toHaveLength(1));
    const lines = posted[0].body.lines as { quantity: number; note: string }[];
    expect(lines).toHaveLength(1);
    expect(lines[0].quantity).toBe(7);
    expect(lines[0].note).toBe("برای پمپ — برای فن");
  });

  it("shows each line and its note in the requisitions list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.includes("procurement/requisitions")) {
          return Promise.resolve(
            envelope([
              {
                id: "pr-1", number: "PR-0001", status: "submitted", totalEstimated: "600000.00",
                lines: [{ id: "l1", partId: "p1", partCode: "BRG-6205", partName: "بلبرینگ", unit: "عدد", quantity: 4, note: "برای پمپ خط ۳" }],
              },
            ]),
          );
        }
        if (url.includes("spare-parts")) return Promise.resolve(envelope(PARTS));
        return Promise.resolve(envelope([]));
      }),
    );
    const user = userEvent.setup();
    render(
      <AppProviders>
        <MemoryRouter>
          <ProcurementPage />
        </MemoryRouter>
      </AppProviders>,
    );
    await user.click(await screen.findByRole("tab", { name: "درخواست\u200cها" }));
    expect(await screen.findByText(/بلبرینگ × ۴/)).toBeInTheDocument();
    expect(screen.getByText("برای پمپ خط ۳")).toBeInTheDocument();
  });

  it("keeps everyday tabs in front and the rest behind «بیشتر»", async () => {
    const user = userEvent.setup();
    render(
      <AppProviders>
        <MemoryRouter>
          <ProcurementPage />
        </MemoryRouter>
      </AppProviders>,
    );

    expect(await screen.findByRole("tab", { name: /درخواست\u200cها/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "خریدشده" })).toBeInTheDocument();
    // Secondary destinations are not competing for attention up front.
    expect(screen.queryByRole("tab", { name: "برگشت کالا" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /بیشتر/ }));
    await user.click(screen.getByRole("menuitem", { name: "برگشت کالا" }));
    expect(screen.getByRole("button", { name: /برگشت کالا/ })).toBeInTheDocument();
  });

});
