/**
 * The eMaint-style top menubar — the promises it makes to a factory user.
 *
 * Every section of the app lives in a dropdown off one dark strip; a
 * section with a single page is an honest link, not a dropdown of one;
 * a click opens (nothing hover-only), Escape closes, and picking an item
 * navigates. These tests pin that contract so the navigation cannot
 * quietly regress into something a mouseless shift supervisor can't use.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
import { AppShell } from "../layouts/AppShell";

const ALL = [
  "dashboard.view",
  "project.view",
  "task.view",
  "maintenance.document.view",
  "maintenance.workorder.list",
  "maintenance.inventory.view",
  "procurement.supplier.view",
  "safety.permit.view",
  "organization.department.view",
  "maintenance.device.list",
  "maintenance.meter.view",
  "communication.chat.use",
  "intelligence.view",
  "user.list",
  "role.list",
  "audit.view",
];

const envelope = (data: unknown): Response =>
  new Response(JSON.stringify({ success: true, data, meta: {}, errors: [] }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });

const renderShell = (initialRoute = "/app/dashboard"): void => {
  render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <AppProviders>
        <Routes>
          <Route path="/app" element={<AppShell />}>
            <Route path="dashboard" element={<div data-testid="page-dashboard">صفحه داشبورد</div>} />
            <Route path="maintenance/work-orders" element={<div data-testid="page-orders">صفحه درخواست‌ها</div>} />
          </Route>
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
};

describe("the top menubar — نوار منوی بالایی", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    // The notification poller mounted by AppProviders expects a list.
    vi.stubGlobal("fetch", vi.fn(async () => envelope([])));
    sessionStore.set({
      accessToken: "test-access",
      refreshToken: "test-refresh",
      user: {
        id: "u1",
        displayName: "کاربر آزمون",
        email: "test@example.test",
        role: "Admin",
        permissions: ALL,
      },
    });
  });

  it("keeps every section in dropdowns on the top strip", async () => {
    renderShell();
    // The dark strip carries the brand and the sections as menus.
    expect(screen.getByText("Tekarai")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /نگهداری و تعمیرات/ })).toHaveAttribute(
      "aria-haspopup",
      "menu",
    );
    // The old vertical sidebar is gone.
    expect(document.querySelector(".sidebar")).toBeNull();
  });

  it("opens a section's pages on click and navigates on pick", async () => {
    renderShell();
    await userEvent.click(screen.getByRole("button", { name: /نگهداری و تعمیرات/ }));

    // Direct pages and titled sub-sections are all in one panel.
    const panel = screen.getByRole("menu", { name: /نگهداری و تعمیرات/ });
    expect(panel).toBeInTheDocument();
    expect(screen.getByText("عملیات")).toBeInTheDocument();
    const orders = screen.getByRole("menuitem", { name: /درخواست‌های کار/ });
    expect(orders).toBeInTheDocument();

    await userEvent.click(orders);
    expect(await screen.findByTestId("page-orders")).toBeInTheDocument();
    // Picking a page closes the menu behind the navigation.
    await waitFor(() =>
      expect(screen.queryByRole("menu", { name: /نگهداری و تعمیرات/ })).not.toBeInTheDocument(),
    );
  });

  it("marks the section that owns the current page", () => {
    renderShell("/app/maintenance/work-orders");
    const trigger = screen.getByRole("button", { name: /نگهداری و تعمیرات/ });
    expect(trigger.className).toContain("is-active");
  });

  it("closes on Escape and on an outside click", async () => {
    renderShell();
    const trigger = screen.getByRole("button", { name: /نگهداری و تعمیرات/ });
    await userEvent.click(trigger);
    expect(screen.getByRole("menu", { name: /نگهداری و تعمیرات/ })).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu", { name: /نگهداری و تعمیرات/ })).not.toBeInTheDocument();

    await userEvent.click(trigger);
    await userEvent.click(document.body);
    await waitFor(() =>
      expect(screen.queryByRole("menu", { name: /نگهداری و تعمیرات/ })).not.toBeInTheDocument(),
    );
  });

  it("hides sections the signed-in user has no permission for", () => {
    sessionStore.set({
      accessToken: "test-access",
      refreshToken: "test-refresh",
      user: {
        id: "u1",
        displayName: "کاربر محدود",
        email: "limited@example.test",
        role: "Member",
        permissions: ["dashboard.view"],
      },
    });
    renderShell();
    expect(screen.queryByRole("button", { name: /نگهداری و تعمیرات/ })).not.toBeInTheDocument();
    // «مدیریت» stays — settings and one's own account belong to everyone —
    // but its admin-only pages must not be offered.
    const admin = screen.getByRole("button", { name: /مدیریت/ });
    expect(admin).toBeInTheDocument();
    // The dashboard itself stays reachable.
    expect(screen.getByRole("link", { name: /داشبورد/ })).toBeInTheDocument();
  });
});
