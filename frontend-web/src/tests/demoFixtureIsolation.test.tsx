/**
 * With VITE_DEMO_MODE=false, no fabricated record may reach the screen.
 *
 * This is the test the boundary actually needs. The production guard proves
 * the flag cannot be flipped by accident, and the build firewall proves the
 * fixtures are not linked in — but neither proves that a page, asked to
 * render with demo mode off, keeps its hands off the fake data. Pages did
 * exactly that: `MaintenanceDashboardPage` seeded its state from `demoParts`,
 * `ProcurementPage` from `demoSuppliers`, and a failed request fell back to
 * invented rows.
 *
 * So: render every page that imports a fixture, with demo mode off and the
 * network refusing, and assert that none of the fixtures' signature strings
 * appear. A failure here means a user could be shown invented data and
 * believe it.
 */

import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../app/configuration/runtimeConfig", () => ({
  runtimeConfig: {
    appName: "Tekarai",
    apiBaseUrl: "http://api.test.invalid",
    apiVersion: "v1",
    demoMode: false,
    realtimeEnabled: false,
  },
  demoModeRefusedInProduction: false,
}));

import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";

/**
 * Strings that exist nowhere but in the fixtures. If one of these is on the
 * screen, it was fabricated.
 */
const FABRICATED = [
  "گراندفوس",
  "رضا احمدی",
  "پمپ خنک‌کننده اصلی",
  "تأمین‌کننده نمونه",
  "راهبر نمایشی",
  "قطعه نمونه",
  "بلبرینگ 6204",
  "تسمه V118",
  "سیل مکانیکی 45mm",
  "مدیر سکو",
  "demo@tekarai.local",
  "demo.admin",
];

const renderPage = async (Page: () => JSX.Element) => {
  const view = render(
    <MemoryRouter>
      <AppProviders>
        <Page />
      </AppProviders>
    </MemoryRouter>,
  );
  // Let the mounted effects fire and their rejected requests settle.
  await waitFor(() => expect(document.body).toBeTruthy());
  await new Promise((resolve) => setTimeout(resolve, 0));
  return view;
};

const assertNothingFabricated = (): void => {
  const text = document.body.textContent ?? "";
  const leaked = FABRICATED.filter((needle) => text.includes(needle));
  expect(
    leaked,
    `demo fixture content rendered with demoMode=false: ${leaked.join(", ")}`,
  ).toEqual([]);
};

describe("no demo fixture is consumed when VITE_DEMO_MODE=false", () => {
  beforeEach(() => {
    sessionStore.set({
      accessToken: "test-access",
      refreshToken: "test-refresh",
      user: {
        id: "u-1",
        displayName: "کاربر واقعی",
        email: "real@example.com",
        role: "Platform Administrator",
        permissions: ["*"],
      },
    });
    // Every request fails. A page that survives this by inventing data is
    // precisely the bug under test.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("network unavailable"))),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStore.clear();
    vi.clearAllMocks();
  });

  const pages: Array<[string, () => Promise<{ [k: string]: unknown }>, string]> = [
    ["SparePartsPage", () => import("../pages/SparePartsPage"), "SparePartsPage"],
    ["ProcurementPage", () => import("../pages/ProcurementPage"), "ProcurementPage"],
    ["AccountPage", () => import("../pages/AccountPage"), "AccountPage"],
    ["AdministrationPage", () => import("../pages/AdministrationPage"), "AdministrationPage"],
    ["MaintenanceDashboardPage", () => import("../pages/MaintenanceDashboardPage"), "MaintenanceDashboardPage"],
    ["MaintenanceDevicesPage", () => import("../pages/MaintenanceDevicesPage"), "MaintenanceDevicesPage"],
    ["WorkOrdersPage", () => import("../pages/WorkOrdersPage"), "WorkOrdersPage"],
    ["DashboardPage", () => import("../pages/DashboardPage"), "DashboardPage"],
    ["TasksPage", () => import("../pages/TasksPage"), "TasksPage"],
    ["ProjectsPage", () => import("../pages/ProjectsPage"), "ProjectsPage"],
    ["DocumentsPage", () => import("../pages/DocumentsPage"), "DocumentsPage"],
    ["MaintenanceLocationsPage", () => import("../pages/MaintenanceLocationsPage"), "MaintenanceLocationsPage"],
    ["MaintenancePersonnelPage", () => import("../pages/MaintenancePersonnelPage"), "MaintenancePersonnelPage"],
    ["EquipmentRegistryPage", () => import("../pages/EquipmentRegistryPage"), "EquipmentRegistryPage"],
    ["AssetHierarchyPage", () => import("../pages/AssetHierarchyPage"), "AssetHierarchyPage"],
    ["FleetAnalyticsPage", () => import("../pages/FleetAnalyticsPage"), "FleetAnalyticsPage"],
    ["MaintenanceInspectionsPage", () => import("../pages/MaintenanceInspectionsPage"), "default"],
    ["PerformanceReviewPage", () => import("../pages/PerformanceReviewPage"), "PerformanceReviewPage"],
    ["WorkCalendarPage", () => import("../pages/WorkCalendarPage"), "WorkCalendarPage"],
    ["MaintenancePmCalendarPage", () => import("../pages/MaintenancePmCalendarPage"), "MaintenancePmCalendarPage"],
  ];

  for (const [label, importer, exportName] of pages) {
    it(`${label} renders no fabricated record`, async () => {
      const module = await importer();
      const Page = module[exportName] as () => JSX.Element;
      // A renamed or newly default-exported page must break this test rather
      // than quietly stop being checked.
      expect(Page, `${label} does not export "${exportName}"`).toBeTypeOf("function");
      await renderPage(Page);
      assertNothingFabricated();
    });
  }
});

describe("the fixtures themselves still hold data", () => {
  it("so the test above is proving absence, not an empty module", async () => {
    const { demoParts } = await import("../features/demo/pageDemoFixtures");
    expect(demoParts.length).toBeGreaterThan(0);
    expect(demoParts.some((part) => part.name === "بلبرینگ 6204")).toBe(true);
  });
});
