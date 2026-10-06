/**
 * Guards the line between demo fixtures and the real product.
 *
 * Demo mode is not a feature flag that changes a colour — it swaps the entire
 * backend for fixtures, including a login that accepts any password and hands
 * back `permissions: ["*"]`. Two things therefore have to hold:
 *
 * 1. a production build must not be able to turn it on by accident, and
 * 2. the `if (demoMode)` branches must stop spreading. There are 151 of them
 *    across 35 files today, each one a second implementation of a code path
 *    that can drift from the real one — and most of them untested, because
 *    the suite used to run in demo mode and only ever exercised the fake side.
 *
 * The ratchet below records today's count per file. It can go down; it cannot
 * go up, and no new file can start using the flag. New code uses the service
 * seam instead (`createDemoRegistryService()` / `createRegistryService(api)`),
 * which keeps the choice in one place and leaves the page with one code path.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

// Resolved from the project root so the scan does not depend on how the
// spec file itself was loaded.
const SOURCE_ROOT = resolve(process.cwd(), "src") + "/";

/**
 * Occurrences of `demoMode` per file, frozen at the moment the boundary was
 * documented. Lower a number when you delete a branch; never raise one.
 */
const BASELINE: Record<string, number> = {
  "app/configuration/runtimeConfig.ts": 4,
  // Prose, not a branch: the fixture module names the flag in its header
  // comment. Recorded rather than exempted, so the loophole stays visible.
  "features/demo/pageDemoFixtures.ts": 1,
  "core/auth/authContext.tsx": 2,
  "core/notifications/notificationContext.tsx": 2,
  "features/communication/useChatRealtime.ts": 1,
  "features/intelligence/intelligenceService.ts": 1,
  "features/maintenance/MaintenanceAttachments.tsx": 5,
  "features/maintenance/performanceReviewDemoData.ts": 1,
  "features/notifications/notificationService.ts": 3,
  "layouts/AppShell.tsx": 1,
  "pages/AccountPage.tsx": 2,
  "pages/AdministrationPage.tsx": 5,
  "pages/AssetHierarchyPage.tsx": 1,
  "pages/ChatPage.tsx": 5,
  "pages/DashboardPage.tsx": 7,
  "pages/DeviceProfilePage.tsx": 3,
  "pages/DocumentsPage.tsx": 5,
  "pages/EquipmentRegistryPage.tsx": 5,
  "pages/FleetAnalyticsPage.tsx": 1,
  "pages/LoginPage.tsx": 4,
  "pages/MaintenanceDashboardPage.tsx": 9,
  "pages/MaintenanceDevicesPage.tsx": 7,
  "pages/MaintenanceInspectionsPage.tsx": 2,
  "pages/MaintenanceLocationsPage.tsx": 1,
  "pages/MaintenancePersonnelPage.tsx": 1,
  "pages/MaintenancePmCalendarPage.tsx": 4,
  "pages/MaintenanceReportPage.tsx": 4,
  "pages/MaintenanceWorkReportPage.tsx": 3,
  "pages/PerformanceReviewPage.tsx": 1,
  "pages/ProcurementPage.tsx": 16,
  "pages/ProjectsPage.tsx": 2,
  "pages/SparePartsPage.tsx": 10,
  "pages/TasksPage.tsx": 3,
  "pages/WorkCalendarPage.tsx": 2,
  "pages/WorkOrdersPage.tsx": 27,
  "shared/components/DemoModeBanner.tsx": 1,
};

const sourceFiles = (directory: string, collected: string[] = []): string[] => {
  for (const entry of readdirSync(directory)) {
    const full = join(directory, entry);
    if (statSync(full).isDirectory()) {
      if (entry !== "tests") sourceFiles(full, collected);
      continue;
    }
    if (/\.tsx?$/.test(entry)) collected.push(full);
  }
  return collected;
};

const currentCounts = (): Record<string, number> => {
  const counts: Record<string, number> = {};
  for (const file of sourceFiles(SOURCE_ROOT)) {
    const occurrences = readFileSync(file, "utf8").split("demoMode").length - 1;
    if (occurrences > 0) {
      counts[file.slice(SOURCE_ROOT.length).replace(/\\/g, "/")] = occurrences;
    }
  }
  return counts;
};

describe("demo mode stays on its side of the line", () => {
  it("does not spread into new files", () => {
    const current = currentCounts();
    const newFiles = Object.keys(current).filter((file) => !(file in BASELINE));
    expect(
      newFiles,
      "This file now branches on demoMode. Use the service seam instead: pick " +
        "the demo or the live implementation once, and let the page call one " +
        "interface. See createRegistryService / createDemoRegistryService.",
    ).toEqual([]);
  });

  it("never gains more branches in a file that already has them", () => {
    const current = currentCounts();
    const grown = Object.entries(current)
      .filter(([file, count]) => file in BASELINE && count > BASELINE[file])
      .map(([file, count]) => `${file}: ${BASELINE[file]} → ${count}`);
    expect(grown, "Demo branching grew. It is only allowed to shrink.").toEqual([]);
  });

  it("reports progress when branches are removed", () => {
    // Not a failure — it asks whoever removed a branch to lower the number,
    // so the ratchet keeps holding at the new, better level.
    const current = currentCounts();
    const shrunk = Object.entries(BASELINE)
      .filter(([file, count]) => (current[file] ?? 0) < count)
      .map(([file, count]) => `${file}: ${count} → ${current[file] ?? 0}`);
    expect(shrunk, `Branches were removed — lower the BASELINE entries: ${shrunk.join(", ")}`).toEqual(
      [],
    );
  });
});
