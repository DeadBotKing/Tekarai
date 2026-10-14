/**
 * The personnel ↔ account link (v0.16.0): a workforce person can be
 * connected to the account they sign in with, picked by name from a
 * search box — never a typed UUID. The directory shows the linked
 * account as a badge, and saving carries the id through.
 *
 * These tests run against the demo registry service (vitest runs with
 * VITE_DEMO_MODE=true), whose fixture directory has رضا احمدی and
 * حسین محمدی already linked.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { MaintenancePersonnelPage } from "../pages/MaintenancePersonnelPage";

const authenticate = (): void =>
  sessionStore.set({
    accessToken: "test-access",
    refreshToken: "test-refresh",
    user: {
      id: "u1",
      displayName: "Test User",
      email: "test@example.test",
      role: "Maintenance",
      permissions: [
        "maintenance.device.list",
        "maintenance.device.manage",
        "maintenance.workorder.list",
      ],
    },
  });

const renderPage = (): void => {
  render(
    <AppProviders>
      <MemoryRouter initialEntries={["/app/maintenance/personnel"]}>
        <Routes>
          <Route path="/app/maintenance/personnel" element={<MaintenancePersonnelPage />} />
        </Routes>
      </MemoryRouter>
    </AppProviders>,
  );
};

describe("the personnel ↔ account link", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    // The notification poller mounted by AppProviders expects a list.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ success: true, data: [], meta: {}, errors: [] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    authenticate();
  });

  it("shows the linked account as a badge on the directory", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("MT-101")).toBeInTheDocument());
    // رضا احمدی is linked to his account: the name cell and the badge both
    // carry it, so the directory shows the person twice — once per role.
    expect(screen.getAllByText("رضا احمدی").length).toBeGreaterThanOrEqual(2);
    // حسین محمدی too…
    expect(screen.getAllByText("حسین محمدی").length).toBeGreaterThanOrEqual(2);
    // …while an unlinked person shows the empty marker, not a badge.
    expect(screen.getAllByText("سارا نوری").length).toBe(1);
  });

  it("picks an account by name and carries the link through a save", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("MT-101")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "افزودن پرسنل" }));
    await userEvent.type(screen.getByLabelText(/نام و نام خانوادگی/), "کاربر آزمون");
    await userEvent.type(screen.getByLabelText("کد پرسنلی"), "MT-900");

    // Type a name into the account picker and wait for the fixture
    // directory to answer (the picker debounces at 200ms).
    const picker = screen.getByPlaceholderText("جستجوی نام / نام کاربری…");
    await userEvent.type(picker, "مریم");
    const option = await screen.findByRole("option", { name: /مریم کریمی/ });
    await userEvent.click(option);

    await userEvent.click(screen.getByRole("button", { name: "ذخیره" }));
    await waitFor(() => expect(screen.getByText("MT-900")).toBeInTheDocument());
    // The new row carries the linked account as a badge.
    expect(screen.getAllByText("مریم کریمی").length).toBeGreaterThanOrEqual(2);
  });
});
