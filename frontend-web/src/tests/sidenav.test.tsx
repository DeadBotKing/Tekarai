/**
 * The MaintainX-style sidebar — the promises it makes to a factory user.
 *
 * A light rail on the start edge carries every section with a small-caps
 * label; the current page is a blue pill; sub-menus expand in place and
 * pre-open to reveal the active child; a click navigates. These tests pin
 * that contract so the navigation cannot quietly regress into something a
 * mouseless shift supervisor can't use.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
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

describe("the sidebar — سایدبار روشن", () => {
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

  /** The rail itself — queries scoped to it, because the breadcrumb in the
   *  topbar repeats the current section's name. */
  const rail = (): HTMLElement => {
    const element = document.querySelector(".sidenav");
    expect(element).not.toBeNull();
    return element as HTMLElement;
  };

  it("carries the brand, the tenant and every section on a light rail", () => {
    renderShell();
    expect(within(rail()).getByText("Tekarai")).toBeInTheDocument();
    // Sections wear small-caps labels; the maintenance section is there.
    expect(within(rail()).getByText("نگهداری و تعمیرات")).toBeInTheDocument();
    expect(within(rail()).getByText("محیط کار")).toBeInTheDocument();
    // The old dark menubar is gone.
    expect(document.querySelector(".menubar")).toBeNull();
  });

  it("expands a sub-menu in place and navigates on pick", async () => {
    renderShell();
    // «عملیات» is a parent inside the maintenance section.
    const ops = within(rail()).getByRole("button", { name: /عملیات/ });
    expect(ops).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(ops);
    expect(ops).toHaveAttribute("aria-expanded", "true");
    const orders = within(rail()).getByRole("link", { name: /درخواست‌های کار/ });
    expect(orders).toBeInTheDocument();

    await userEvent.click(orders);
    expect(await screen.findByTestId("page-orders")).toBeInTheDocument();
  });

  it("pre-opens the sub-menu that owns the current page and pills the page", () => {
    renderShell("/app/maintenance/work-orders");
    const nav = rail();
    const ops = within(nav).getByRole("button", { name: /عملیات/ });
    expect(ops).toHaveAttribute("aria-expanded", "true");
    expect(ops.className).toContain("is-active");
    const orders = within(nav).getByRole("link", { name: /درخواست‌های کار/ });
    expect(orders.className).toContain("is-active");
  });

  it("pills the dashboard for a section with a single page", () => {
    renderShell("/app/dashboard");
    // Exact name: «داشبورد نگهداری» also lives in the rail.
    const dashboard = within(rail()).getByRole("link", { name: "داشبورد" });
    expect(dashboard.className).toContain("is-active");
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
    const nav = rail();
    expect(within(nav).queryByText("نگهداری و تعمیرات")).not.toBeInTheDocument();
    // «پروژه‌ها» is permission-gated (project.view/task.view withheld): its
    // group label and item share the name, so both must be gone together.
    expect(within(nav).queryAllByText("پروژه‌ها")).toHaveLength(0);
    // «مدیریت» stays — settings and one's own account belong to everyone.
    expect(within(nav).getByText("مدیریت")).toBeInTheDocument();
    // The dashboard itself stays reachable.
    expect(within(nav).getByRole("link", { name: "داشبورد" })).toBeInTheDocument();
  });

  it("closes an expanded sub-menu on a second click", async () => {
    renderShell();
    const ops = within(rail()).getByRole("button", { name: /عملیات/ });
    await userEvent.click(ops);
    expect(ops).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(ops);
    await waitFor(() => expect(ops).toHaveAttribute("aria-expanded", "false"));
  });
});
