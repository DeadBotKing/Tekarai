/**
 * ارجاع پله‌به‌پله — the referral ladder, at the screen.
 *
 * These tests pin the promises the backend makes, as the user meets them:
 * the button appears on an open order and disappears on a closed one, the
 * person is picked by the server (the screen never asks for a name or a
 * UUID), the note travels along, and the person the order landed on is
 * said out loud — a referral nobody can see is a referral nobody made.
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
import { WorkOrdersPage } from "../pages/WorkOrdersPage";

const ORDER_DTO = {
  id: "wo-1",
  tenantId: "t-1",
  deviceId: "dev-1",
  title: "پمپ خط دو نشتی می‌کند",
  description: "",
  orderType: "corrective",
  priority: "normal",
  status: "submitted",
  department: "general",
  requestedByName: "اکبری",
  assignedToName: "",
  orgDepartmentId: "dept-eng",
  requestedByUserId: "user-operator",
  assignedToUserId: "",
  resolutionNote: "",
  createdAt: "2026-10-10T08:00:00Z",
  closedAt: "",
  slaDueAt: "",
  overdue: false,
  failureType: "",
  failedComponent: "",
  failureSymptom: "",
  rootCause: "",
  actionTaken: "",
  repeatFailure: false,
  failureReportedAt: "",
  repairStartedAt: "",
  repairFinishedAt: "",
  returnedToServiceAt: "",
  downtimeMinutes: 0,
  labourHours: "0",
  labourCost: "0",
  partsCost: "0",
};

interface StubOptions {
  order?: Record<string, unknown>;
  /** What the escalate endpoint answers; defaults to «رضا تکنسین». */
  escalateResponse?: Record<string, unknown>;
  escalateStatus?: number;
}

/** The server's answer to a successful referral: the order, now held. */
const PROMOTED = {
  status: "assigned",
  assignedToName: "رضا تکنسین",
  assignedToUserId: "user-tech",
};

const stubApi = (options: StubOptions = {}): { posts: { url: string; body: unknown }[] } => {
  const posts: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "POST" && url.includes("/escalate")) {
        posts.push({ url, body: init?.body ? JSON.parse(String(init.body)) : {} });
        const merged = {
          ...ORDER_DTO,
          ...options.order,
          ...PROMOTED,
          ...(options.escalateResponse ?? {}),
        };
        return Promise.resolve(
          new Response(JSON.stringify({ success: true, data: merged, meta: {}, errors: [] }), {
            status: options.escalateStatus ?? 200,
            headers: { "content-type": "application/json" },
          }),
        );
      }
      if (method !== "GET") {
        return Promise.resolve(
          new Response(JSON.stringify({ success: true, data: { ok: true }, meta: {}, errors: [] }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      }
      if (url.includes("maintenance/work-orders")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              success: true,
              data: [{ ...ORDER_DTO, ...options.order }],
              meta: {},
              errors: [],
            }),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        );
      }
      // The notification poller and the sibling lists expect a bare list.
      return Promise.resolve(
        new Response(JSON.stringify({ success: true, data: [], meta: {}, errors: [] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    }),
  );
  return { posts };
};

const signIn = (permissions: string[]): void =>
  sessionStore.set({
    accessToken: "test-access",
    refreshToken: "test-refresh",
    user: {
      id: "user-operator",
      displayName: "اکبری",
      email: "operator@example.test",
      role: "Operator",
      permissions,
    },
  });

const ESCALATE_PERMISSIONS = [
  "maintenance.workorder.list",
  "maintenance.workorder.view",
  "maintenance.workorder.escalate",
];

const renderPage = (): void => {
  render(
    <AppProviders>
      <MemoryRouter>
        <WorkOrdersPage />
      </MemoryRouter>
    </AppProviders>,
  );
};

const openDetail = async (): Promise<void> => {
  // The list lands from the network a moment after mount — wait for the
  // row rather than demanding it synchronously.
  const title = await screen.findByRole("button", { name: /پمپ خط دو نشتی می‌کند/ });
  await userEvent.click(title);
};

describe("work order escalation — ارجاع پله‌به‌پله", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    signIn(ESCALATE_PERMISSIONS);
  });

  it("offers ارجاع به بالا on an open order and posts only a note", async () => {
    const { posts } = stubApi();
    renderPage();
    await openDetail();

    await userEvent.click(screen.getByRole("button", { name: "ارجاع به بالا" }));
    // The screen asks for nothing but a note — the person is the server's
    // decision, read from the org chart, never typed here.
    const modal = screen.getByRole("dialog");
    expect(within(modal).getByText(/تأیید نهایی همچنان با مدیر واحد است/)).toBeInTheDocument();
    await userEvent.type(within(modal).getByLabelText("توضیح (اختیاری)"), "نیاز به تأیید بالاتر");
    await userEvent.click(within(modal).getByRole("button", { name: "ارجاع به بالا" }));

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].url).toContain("maintenance/work-orders/wo-1/escalate");
    expect(posts[0].body).toEqual({ note: "نیاز به تأیید بالاتر" });
    // The person the order landed on is said out loud. The toast renders
    // twice (visible + aria-live region), so ask for all of them.
    expect((await screen.findAllByText(/به رضا تکنسین ارجاع شد/)).length).toBeGreaterThan(0);
  });

  it("says who holds the order after the referral", async () => {
    stubApi({
      escalateResponse: {
        status: "assigned",
        assignedToName: "رضا تکنسین",
        assignedToUserId: "user-tech",
      },
    });
    renderPage();
    await openDetail();
    await userEvent.click(screen.getByRole("button", { name: "ارجاع به بالا" }));
    await userEvent.click(screen.getByRole("button", { name: "ارجاع به بالا" }));
    await waitFor(() =>
      expect(screen.getAllByText(/به رضا تکنسین ارجاع شد/).length).toBeGreaterThan(0),
    );
  });

  it("does not offer referral on an order awaiting approval", async () => {
    stubApi({ order: { status: "pendingApproval" } });
    renderPage();
    await openDetail();
    expect(screen.queryByRole("button", { name: "ارجاع به بالا" })).not.toBeInTheDocument();
  });

  it("hides the button from someone without the escalate permission", async () => {
    signIn(["maintenance.workorder.list", "maintenance.workorder.view"]);
    stubApi();
    renderPage();
    await openDetail();
    expect(screen.queryByRole("button", { name: "ارجاع به بالا" })).not.toBeInTheDocument();
  });

  it("keeps the work-order board and exposes all workflow statuses in one scrollable view", async () => {
    stubApi({ order: { overdue: true, slaDueAt: "2026-10-12T08:00:00Z" } });
    renderPage();

    await userEvent.click(await screen.findByRole("tab", { name: /برد|Board/ }));
    expect(screen.getByRole("heading", { name: "در انتظار تأیید" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "لغوشده" })).toBeInTheDocument();
    expect(screen.getByText("تأخیر")).toBeInTheDocument();
    expect(screen.getByText("مهلت SLA")).toBeInTheDocument();
  });

  it("provides section shortcuts for the real activity log without inventing comments", async () => {
    stubApi();
    renderPage();
    await openDetail();

    const activityShortcut = screen.getByRole("button", { name: "رویدادهای ثبت‌شده" });
    await userEvent.click(activityShortcut);
    expect(activityShortcut).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("تاریخچه و گردش کار")).toBeInTheDocument();
  });

  it("shows the server's Persian refusal when there is nobody above", async () => {
    stubApi({
      escalateStatus: 422,
      escalateResponse: {},
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        const method = (init?.method ?? "GET").toUpperCase();
        if (method === "POST" && url.includes("/escalate")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                success: false,
                data: null,
                errors: [
                  {
                    code: "SYS_VALIDATION_FAILED",
                    message: "فردی با رده بالاتر از شما در این واحد یافت نشد؛ درخواست نزد شما می‌ماند.",
                  },
                ],
                meta: {},
              }),
              { status: 422, headers: { "content-type": "application/json" } },
            ),
          );
        }
        if (method === "GET" && url.includes("maintenance/work-orders")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                success: true,
                data: [{ ...ORDER_DTO }],
                meta: {},
                errors: [],
              }),
              { status: 200, headers: { "content-type": "application/json" } },
            ),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify({ success: true, data: [], meta: {}, errors: [] }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      }),
    );
    renderPage();
    await openDetail();
    await userEvent.click(screen.getByRole("button", { name: "ارجاع به بالا" }));
    await userEvent.click(screen.getByRole("button", { name: "ارجاع به بالا" }));
    expect(
      (await screen.findAllByText(/فردی با رده بالاتر از شما در این واحد یافت نشد/)).length,
    ).toBeGreaterThan(0);
  });
});
