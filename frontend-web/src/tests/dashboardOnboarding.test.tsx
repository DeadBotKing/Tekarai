/** First-visit help and the permission-aware overview map on /app/dashboard. */

import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../app/configuration/runtimeConfig", () => ({
  runtimeConfig: {
    appName: "Tekarai",
    apiBaseUrl: "http://api.test.invalid",
    apiVersion: "v1",
    demoMode: false,
    realtimeEnabled: false,
  },
}));

vi.mock("../core/offline/offlineContext", () => ({
  OfflineProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
  useOptionalOffline: () => null,
}));

import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { AppShell } from "../layouts/AppShell";
import { DashboardPage } from "../pages/DashboardPage";

const envelope = (data: unknown): Response => new Response(
  JSON.stringify({ success: true, data, meta: {}, errors: [] }),
  { status: 200, headers: { "content-type": "application/json" } },
);

const renderDashboard = () => render(
  <MemoryRouter initialEntries={["/app/dashboard"]}>
    <AppProviders>
      <Routes>
        <Route path="/app" element={<AppShell />}>
          <Route path="dashboard" element={<DashboardPage />} />
        </Route>
      </Routes>
    </AppProviders>
  </MemoryRouter>,
);

const user = {
  id: "dashboard-onboarding-user",
  displayName: "کاربر تازه‌وارد",
  email: "first.visit@example.test",
  role: "Member",
  permissions: [PERMISSIONS.dashboardView, PERMISSIONS.projectView, PERMISSIONS.taskView],
};

beforeEach(() => {
  window.localStorage.clear();
  sessionStore.set({ accessToken: "test-access", refreshToken: "test-refresh", user });
  // Empty live responses keep this test focused on navigation, not fixtures.
  vi.stubGlobal("fetch", vi.fn(async () => envelope([])));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStore.clear();
  window.localStorage.clear();
});

describe("dashboard first-visit experience", () => {
  it("shows the start guide and only links to areas permitted for this user", async () => {
    const visitor = userEvent.setup();
    renderDashboard();

    expect(screen.getByRole("heading", { name: "نمایی روشن از فضای کاری شما" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "هر چیز را کجا پیدا کنم؟" })).toBeInTheDocument();

    const areaSection = screen.getByRole("heading", { name: "هر چیز را کجا پیدا کنم؟" }).closest("section");
    expect(areaSection).not.toBeNull();
    const area = within(areaSection as HTMLElement);
    const expandMap = area.getByRole("button", { name: "نمایش نقشهٔ فضای کاری" });
    expect(expandMap).toHaveAttribute("aria-expanded", "false");
    expect(area.queryByRole("link", { name: "پروژه‌ها" })).not.toBeInTheDocument();

    // The onboarding CTA reveals the permission-filtered workspace map.
    await visitor.click(screen.getByRole("button", { name: "دیدن بخش‌ها" }));
    expect(area.getByRole("button", { name: "پنهان کردن نقشهٔ فضای کاری" })).toHaveAttribute("aria-expanded", "true");
    expect(area.getByRole("link", { name: "پروژه‌ها" })).toHaveAttribute("href", "/app/projects");
    expect(area.getByRole("link", { name: "وظایف" })).toHaveAttribute("href", "/app/tasks");
    expect(area.queryByRole("link", { name: /درخواست‌های کار/ })).not.toBeInTheDocument();
    expect(area.queryByRole("link", { name: /تدارکات/ })).not.toBeInTheDocument();
    expect(area.queryByRole("link", { name: /هوشمندی/ })).not.toBeInTheDocument();

    // The onboarding CTA still opens the existing GuideDrawer in AppShell.
    await visitor.click(screen.getByRole("button", { name: "باز کردن راهنما" }));
    const guide = await screen.findByRole("dialog");
    expect(guide).toBeInTheDocument();
    await visitor.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("keeps inaccessible areas hidden when the map is opened for a limited user", async () => {
    const visitor = userEvent.setup();
    act(() => sessionStore.set({
      accessToken: "test-access",
      refreshToken: "test-refresh",
      user: { ...user, id: "dashboard-limited-user", permissions: [PERMISSIONS.dashboardView] },
    }));
    renderDashboard();

    const startStep = screen.getByRole("heading", { name: "وارد یک بخش کاری شوید" }).closest("li");
    expect(startStep).not.toBeNull();
    const step = within(startStep as HTMLElement);
    expect(step.getByText("از نقشهٔ پایین، یکی از بخش‌های در دسترس خود را انتخاب کنید.")).toBeInTheDocument();
    expect(step.queryByRole("link", { name: "دیدن بخش‌ها" })).not.toBeInTheDocument();
    expect(step.queryByRole("link", { name: "ورود به فضای کاری" })).not.toBeInTheDocument();

    const map = within(screen.getByRole("heading", { name: "هر چیز را کجا پیدا کنم؟" }).closest("section") as HTMLElement);
    expect(map.getByRole("button", { name: "نمایش نقشهٔ فضای کاری" })).toHaveAttribute("aria-expanded", "false");
    await visitor.click(step.getByRole("button", { name: "دیدن بخش‌ها" }));
    const collapseMap = map.getByRole("button", { name: "پنهان کردن نقشهٔ فضای کاری" });
    expect(collapseMap).toHaveAttribute("aria-expanded", "true");
    expect(map.queryByRole("link", { name: "پروژه‌ها" })).not.toBeInTheDocument();
    expect(map.queryByRole("link", { name: "وظایف" })).not.toBeInTheDocument();
    await visitor.click(collapseMap);
    expect(map.getByRole("button", { name: "نمایش نقشهٔ فضای کاری" })).toHaveAttribute("aria-expanded", "false");
  });

  it("remembers dismissal per user and tenant, with a way to restore the guide", async () => {
    const visitor = userEvent.setup();
    const firstVisit = renderDashboard();
    expect(screen.getByRole("heading", { name: "نمایی روشن از فضای کاری شما" })).toBeInTheDocument();

    await visitor.click(screen.getByRole("button", { name: "پنهان کردن راهنمای شروع" }));
    expect(screen.getByText("راهنمای شروع پنهان شد")).toBeInTheDocument();
    expect(window.localStorage.getItem("tekarai.dashboard.onboarding.v1:tenant-nordic:dashboard-onboarding-user")).toBe("dismissed");

    firstVisit.unmount();
    renderDashboard();
    expect(screen.queryByRole("heading", { name: "نمایی روشن از فضای کاری شما" })).not.toBeInTheDocument();
    await visitor.click(screen.getByRole("button", { name: "نمایش راهنمای شروع" }));
    expect(screen.getByRole("heading", { name: "نمایی روشن از فضای کاری شما" })).toBeInTheDocument();
  });
});
