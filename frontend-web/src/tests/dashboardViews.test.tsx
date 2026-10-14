/**
 * The maintenance-dashboard family (v0.15.0): one page, four dashboards
 * reachable from the side navigation — daily control, calendar,
 * performance and the user's own desk (v0.15.1 moved the switcher from
 * the page header into the sidenav, under «داشبورد نگهداری»). These
 * tests pin the two behaviours the brief called out by name: the
 * calendar's department rail filters the requests shown on the grid,
 * and the user dashboard shows the signed-in user's own work.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { MaintenanceDashboardPage } from "../pages/MaintenanceDashboardPage";

const renderDashboard = (path: string): void => {
  render(
    <AppProviders>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/app/maintenance/dashboard" element={<MaintenanceDashboardPage />} />
          <Route path="/app/maintenance/dashboard/:view" element={<MaintenanceDashboardPage />} />
        </Routes>
      </MemoryRouter>
    </AppProviders>,
  );
};

describe("the maintenance dashboard family", () => {
  beforeEach(() => {
    sessionStore.set({
      accessToken: "test-access",
      refreshToken: "test-refresh",
      user: {
        id: "u-1",
        // A name that exists in the demo fixtures, so the user dashboard
        // has data to show without any clicking.
        displayName: "رضا احمدی",
        email: "reza@tekarai.local",
        role: "Technician",
        permissions: ["*"],
      },
    });
  });

  it("renders the calendar dashboard with its department rail", async () => {
    renderDashboard("/app/maintenance/dashboard/calendar");
    // The Jalali month grid announces itself with its month label.
    await waitFor(() => expect(screen.getByRole("grid")).toBeInTheDocument());
    // The department rail sits beside the calendar with all five units.
    expect(screen.getByText("دپارتمان‌ها")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /برق/ })).toBeInTheDocument();
  });

  it("the department rail filters the requests shown on the calendar", async () => {
    renderDashboard("/app/maintenance/dashboard/calendar");
    await waitFor(() => expect(screen.getByRole("grid")).toBeInTheDocument());
    // Demo month (شهریور) holds 4 requests: 2 mechanical, 1 electrical, 1 facilities.
    const countAll = screen.getByText("درخواست‌های این ماه:", { exact: false });
    expect(countAll.textContent).toContain("۴");

    // Keep only the electrical department on the rail.
    await userEvent.click(screen.getByRole("button", { name: /برق/ }));
    const countElectrical = screen.getByText("درخواست‌های این ماه:", { exact: false });
    expect(countElectrical.textContent).toContain("۱");

    // «همه» brings everything back.
    await userEvent.click(screen.getByRole("button", { name: /^همه/ }));
    expect(screen.getByText("درخواست‌های این ماه:", { exact: false }).textContent).toContain("۴");
  });

  it("clicking a calendar day lists that day's requests", async () => {
    renderDashboard("/app/maintenance/dashboard/calendar");
    await waitFor(() => expect(screen.getByRole("grid")).toBeInTheDocument());
    // The demo fixtures include «تعویض باتری ژنراتور» (electrical, 2026-09-20).
    // Its coloured dot sits inside that day's cell.
    const dot = screen.getByTitle("تعویض باتری ژنراتور");
    const cell = dot.closest(".dash-cal__cell") as HTMLElement;
    expect(cell).not.toBeNull();
    await userEvent.click(cell);
    // The day panel opens with its close button and the request itself.
    expect(screen.getByRole("button", { name: "بستن" })).toBeInTheDocument();
    expect(screen.getByText("تعویض باتری ژنراتور")).toBeInTheDocument();
  });

  it("the user dashboard shows the signed-in user's own desk", async () => {
    renderDashboard("/app/maintenance/dashboard/user");
    // رضا احمدی is assigned two demo work orders.
    expect(screen.getByText("میز کار رضا احمدی")).toBeInTheDocument();
    expect(screen.getByText("کارهای واگذارشده به من")).toBeInTheDocument();
    expect(screen.getByText("صدای غیرعادی از یاتاقان پمپ")).toBeInTheDocument();
    expect(screen.getByText("بازرسی فشار مخزن هوا")).toBeInTheDocument();
    // A work order assigned to somebody else never appears.
    expect(screen.queryByText("کالیبراسیون دوره‌ای محور Z")).not.toBeInTheDocument();
  });

  it("the performance dashboard shows the trend widgets, not the daily alerts", async () => {
    renderDashboard("/app/maintenance/dashboard/performance");
    expect(await screen.findByText("روند درخواست‌ها در طول زمان")).toBeInTheDocument();
    expect(screen.getByText("روند میانگین زمان رفع عیب")).toBeInTheDocument();
    // The daily-control widgets stay on the daily view.
    expect(screen.queryByText("درخواست‌های باز به تفکیک وضعیت")).not.toBeInTheDocument();
  });

  it("the daily control dashboard keeps the current-state widgets", async () => {
    renderDashboard("/app/maintenance/dashboard");
    expect(await screen.findByText("درخواست‌های باز به تفکیک وضعیت")).toBeInTheDocument();
    expect(screen.queryByText("روند درخواست‌ها در طول زمان")).not.toBeInTheDocument();
  });
});
