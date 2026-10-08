/**
 * The permit screen.
 *
 * These tests pin the things that make the page a safety control rather
 * than a form: that the outstanding blockers are shown all at once, that
 * the approve button is unavailable until the permit is actually ready,
 * that a server-side safety refusal reaches the user as a readable Persian
 * sentence instead of disappearing, and that the approve/close controls
 * are gated on permissions a technician does not hold.
 *
 * The permission tests are written so a typo'd permission key fails rather
 * than passing vacuously: each asserts both the hidden and the visible
 * case for the same control.
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
import { SafetyPermitsPage, formatDuration, validitySummary } from "../pages/SafetyPermitsPage";

const OPTIONS = {
  statuses: [
    { value: "draft", label: "پیش‌نویس" },
    { value: "active", label: "در حال اجرا" },
  ],
  types: [
    { value: "general", label: "عمومی", requiresIsolation: false, maxValidityHours: 24 },
    { value: "electrical", label: "کار برقی", requiresIsolation: true, maxValidityHours: 24 },
  ],
  riskLevels: [
    { value: "low", label: "کم" },
    { value: "high", label: "زیاد" },
  ],
  energyTypes: [{ value: "electrical", label: "الکتریکی" }],
};

const validity = (overrides = {}) => ({
  hasStarted: true,
  isExpired: false,
  isWithinWindow: true,
  minutesUntilStart: 0,
  minutesRemaining: 180,
  isExpiringSoon: false,
  isOverdueWithWorkInProgress: false,
  ...overrides,
});

const SUMMARY = {
  id: "permit-1",
  number: "PTW-20261007-001",
  permitType: "electrical",
  permitTypeLabel: "کار برقی",
  status: "submitted",
  statusLabel: "ارسال‌شده",
  title: "تعویض کنتاکتور",
  riskLevel: "high",
  riskLabel: "زیاد",
  locationName: "سالن ۲",
  requesterName: "تکنسین احمدی",
  performerName: "",
  approverName: "",
  validFrom: "2026-10-07T06:00:00Z",
  validTo: "2026-10-07T14:00:00Z",
  requiresIsolation: true,
  validity: validity(),
};

const DETAIL = {
  ...SUMMARY,
  description: "",
  maxValidityHours: 24,
  rejectionReason: "",
  suspensionReason: "",
  closureNote: "",
  readiness: {
    isReadyToIssue: false,
    blockers: ["نقطه جداسازی تأیید نشده: ISO-1", "اقدام احتیاطی تأییدنشده: قطع برق"],
  },
  precautions: [
    {
      id: "prec-1",
      code: "deEnergised",
      text: "قطع برق",
      isMandatory: true,
      confirmed: false,
      confirmedByName: "",
      confirmedAt: null,
    },
  ],
  isolations: [
    {
      id: "iso-1",
      pointCode: "ISO-1",
      description: "کلید اصلی",
      energyType: "electrical",
      energyLabel: "الکتریکی",
      isolationMethod: "قفل",
      lockTag: "LK-1",
      appliedByName: "تکنسین احمدی",
      verifiedByName: "",
      removedByName: "",
      isApplied: true,
      isVerified: false,
      isRemoved: false,
    },
  ],
  events: [
    {
      id: "ev-1",
      action: "created",
      toStatus: "draft",
      toStatusLabel: "پیش‌نویس",
      actorName: "تکنسین احمدی",
      note: "",
      occurredAt: "2026-10-07T05:00:00Z",
    },
  ],
};

const COMPLETED_DETAIL = {
  ...DETAIL,
  status: "completed",
  statusLabel: "پایان‌یافته",
  readiness: { isReadyToIssue: true, blockers: [] },
};

const envelope = (data: unknown, status = 200): Response =>
  new Response(JSON.stringify({ success: true, data, errors: [], meta: {} }), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const refusal = (code: string, message: string): Response =>
  new Response(
    JSON.stringify({
      success: false,
      data: null,
      errors: [{ code, message }],
      error: { code, message, category: "safetyRule" },
      meta: {},
    }),
    { status: 422, headers: { "Content-Type": "application/json" } },
  );

interface StubOptions {
  detail?: unknown;
  items?: unknown[];
  approveRefusal?: { code: string; message: string };
}

const stubApi = (options: StubOptions = {}): void => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "POST" && url.endsWith("/approve")) {
        if (options.approveRefusal) {
          return Promise.resolve(
            refusal(options.approveRefusal.code, options.approveRefusal.message),
          );
        }
        return Promise.resolve(envelope(options.detail ?? DETAIL));
      }
      if (method === "POST") return Promise.resolve(envelope(options.detail ?? DETAIL));
      if (/\/permits\/[^/]+$/.test(url) && !url.endsWith("/permits")) {
        return Promise.resolve(envelope(options.detail ?? DETAIL));
      }
      return Promise.resolve(
        envelope({ items: options.items ?? [SUMMARY], options: OPTIONS }),
      );
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
      role: "Safety",
      permissions,
    },
  });

const ALL_PERMISSIONS = [
  "safety.permit.view",
  "safety.permit.request",
  "safety.permit.approve",
  "safety.permit.isolate",
  "safety.permit.close",
];

const renderPage = (): void => {
  render(
    <AppProviders>
      <MemoryRouter>
        <SafetyPermitsPage />
      </MemoryRouter>
    </AppProviders>,
  );
};

describe("permit to work page", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    authenticate(ALL_PERMISSIONS);
    stubApi();
  });

  it("lists permits with their status and remaining validity", async () => {
    renderPage();
    expect(await screen.findByText("PTW-20261007-001")).toBeInTheDocument();
    expect(screen.getByText("تعویض کنتاکتور")).toBeInTheDocument();
    expect(screen.getByText("ارسال‌شده")).toBeInTheDocument();
  });

  it("shows every outstanding blocker at once rather than one at a time", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "مشاهده" }));
    expect(await screen.findByText(/نقطه جداسازی تأیید نشده: ISO-1/)).toBeInTheDocument();
    expect(screen.getByText(/اقدام احتیاطی تأییدنشده: قطع برق/)).toBeInTheDocument();
  });

  it("disables approval while the permit is not ready to issue", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "مشاهده" }));
    const approve = await screen.findByRole("button", { name: "تأیید و صدور" });
    expect(approve).toBeDisabled();
  });

  it("enables approval once the server says the permit is ready", async () => {
    stubApi({
      detail: { ...DETAIL, readiness: { isReadyToIssue: true, blockers: [] } },
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "مشاهده" }));
    expect(await screen.findByRole("button", { name: "تأیید و صدور" })).toBeEnabled();
  });

  it("surfaces a server-side safety refusal as a readable message", async () => {
    // The UI's disabled state is a courtesy; the real guard is the server,
    // and its refusal has to reach the user instead of vanishing.
    stubApi({
      detail: { ...DETAIL, readiness: { isReadyToIssue: true, blockers: [] } },
      approveRefusal: {
        code: "permit.approval.selfApproval",
        message: "درخواست‌کننده نمی‌تواند مجوز خودش را تأیید کند.",
      },
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "مشاهده" }));
    await userEvent.click(await screen.findByRole("button", { name: "تأیید و صدور" }));
    await waitFor(() =>
      expect(
        screen.getByText(/درخواست‌کننده نمی‌تواند مجوز خودش را تأیید کند/),
      ).toBeInTheDocument(),
    );
  });

  it("shows the isolation register with applied and verified as separate facts", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "مشاهده" }));
    expect(await screen.findByText("ISO-1")).toBeInTheDocument();
    const row = screen.getByText("ISO-1").closest("tr");
    expect(row).not.toBeNull();
    const cells = row!.querySelectorAll("td");
    // applied by someone, verified by nobody yet — the two-person rule is
    // mid-flight, and the table must show that rather than one "done" tick.
    expect(cells[2].textContent).toContain("تکنسین احمدی");
    expect(cells[3].textContent).toBe("—");
  });

  it("offers isolation verification but not authorisation to a technician", async () => {
    authenticate(["safety.permit.view", "safety.permit.request", "safety.permit.isolate"]);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "مشاهده" }));
    expect(await screen.findByRole("button", { name: "تأیید جداسازی" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "تأیید و صدور" })).not.toBeInTheDocument();
  });

  it("hides isolation controls from someone who may only look", async () => {
    authenticate(["safety.permit.view"]);
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "مشاهده" }));
    await screen.findByText("ISO-1");
    expect(screen.queryByRole("button", { name: "تأیید جداسازی" })).not.toBeInTheDocument();
  });

  it("offers approval to a supervisor", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "مشاهده" }));
    expect(await screen.findByRole("button", { name: "تأیید و صدور" })).toBeInTheDocument();
  });

  it("hides the close button from anyone without the close permission", async () => {
    authenticate(["safety.permit.view", "safety.permit.request"]);
    stubApi({ detail: COMPLETED_DETAIL });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "مشاهده" }));
    await screen.findByText(/سوابق مجوز/);
    expect(
      screen.queryByRole("button", { name: "بستن مجوز و تحویل تجهیز" }),
    ).not.toBeInTheDocument();
  });

  it("offers the close button to someone who holds it", async () => {
    // The paired half of the test above: without this, a typo in the
    // permission key would hide the button from everyone and the negative
    // assertion would still pass.
    authenticate(ALL_PERMISSIONS);
    stubApi({ detail: COMPLETED_DETAIL });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "مشاهده" }));
    expect(
      await screen.findByRole("button", { name: "بستن مجوز و تحویل تجهیز" }),
    ).toBeInTheDocument();
  });

  it("calls out permits that are overdue with work still in progress", async () => {
    stubApi({
      items: [
        {
          ...SUMMARY,
          status: "active",
          statusLabel: "در حال اجرا",
          validity: validity({
            isExpired: true,
            isWithinWindow: false,
            minutesRemaining: 0,
            isOverdueWithWorkInProgress: true,
          }),
        },
      ],
    });
    renderPage();
    expect(
      await screen.findByText(/کار در جریان با مجوز منقضی‌شده/),
    ).toBeInTheDocument();
  });

  it("shows the audit trail on the permit itself", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "مشاهده" }));
    expect(await screen.findByText(/سوابق مجوز/)).toBeInTheDocument();
  });

  it("shows an error state instead of inventing permits when the API fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              success: false,
              data: null,
              errors: [{ code: "SRV", message: "سرویس در دسترس نیست." }],
              meta: {},
            }),
            { status: 500, headers: { "Content-Type": "application/json" } },
          ),
        ),
      ),
    );
    renderPage();
    expect(await screen.findByText("خطا در دریافت اطلاعات")).toBeInTheDocument();
  });
});

describe("permit validity formatting", () => {
  it("reads hours and minutes the way a person says them", () => {
    expect(formatDuration(195)).toBe("۳ ساعت و ۱۵ دقیقه");
    expect(formatDuration(120)).toBe("۲ ساعت");
    expect(formatDuration(45)).toBe("۴۵ دقیقه");
    expect(formatDuration(0)).toBe("۰ دقیقه");
  });

  it("ranks overdue-with-work-in-progress above a plain expiry", () => {
    const overdue = validitySummary(
      validity({ isExpired: true, isOverdueWithWorkInProgress: true }),
    );
    expect(overdue.tone).toBe("danger");
    expect(overdue.text).toContain("کار در جریان");

    const expired = validitySummary(validity({ isExpired: true }));
    expect(expired.text).toBe("اعتبار به پایان رسیده");
  });

  it("warns while there is still time to extend in an orderly way", () => {
    const soon = validitySummary(validity({ minutesRemaining: 30, isExpiringSoon: true }));
    expect(soon.tone).toBe("warning");
    expect(soon.text).toContain("تا پایان اعتبار");
  });

  it("counts down to the start of a permit that has not opened yet", () => {
    const pending = validitySummary(validity({ hasStarted: false, minutesUntilStart: 90 }));
    expect(pending.text).toContain("تا شروع اعتبار");
  });
});
