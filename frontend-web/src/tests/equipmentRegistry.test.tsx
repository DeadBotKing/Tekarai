import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { apiEndpoints } from "../core/api/endpoints";
import type { ApiClient } from "../core/api/apiClient";
import {
  createRegistryService,
  toDeviceProfile,
  toPmPlan,
} from "../features/maintenance/registryService";
import { createDemoRegistryService } from "../features/maintenance/registryDemoData";
import { EquipmentRegistryPage } from "../pages/EquipmentRegistryPage";
import { DeviceProfilePage } from "../pages/DeviceProfilePage";
import { MaintenanceLocationsPage } from "../pages/MaintenanceLocationsPage";
import { MaintenancePersonnelPage } from "../pages/MaintenancePersonnelPage";
import { MAINTENANCE_DEPARTMENTS } from "../shared/types/domain";
import { translate } from "../core/localization/i18n";

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
        "maintenance.device.view",
        "maintenance.device.manage",
      ],
    },
  });

const renderPage = (path: string, element: JSX.Element, route: string): void => {
  render(
    <AppProviders>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
        </Routes>
      </MemoryRouter>
    </AppProviders>,
  );
};

describe("registry service wire mapping", () => {
  it("turns decimal strings from the API into numbers exactly once", () => {
    const profile = toDeviceProfile({
      device: {
        id: "d1",
        code: "PUMP-01",
        name: "پمپ",
        location: "",
        status: "operational",
        department: "mechanical",
        pmIntervalDays: 30,
        lastPmDate: "",
        nextDueDate: "",
        pmDue: false,
        createdAt: "2026-01-01",
        criticality: "critical",
        locationPath: "سایت / اتاق",
      },
      nameplate: { manufacturer: "گراندفوس", criticality: "critical", purchaseCost: "1850000000" },
      specifications: [{ id: "s1", label: "دبی", value: "120", unit: "m3/h", sortOrder: 0 }],
      pmPlans: [],
      pmExecutions: [],
      bom: [
        {
          id: "b1",
          partId: "p1",
          partCode: "BRG-6205",
          partName: "بلبرینگ",
          unit: "عدد",
          position: "سمت کوپلینگ",
          standardQuantity: "2.000",
          note: "",
          quantityOnHand: "12.000",
          minimumStock: "4.000",
          lowStock: false,
          usageCount: 3,
          usedQuantity: "6.000",
          lastUsedAt: "2026-08-14",
        },
      ],
      assignments: [
        {
          id: "a1",
          role: "responsible",
          personnelId: "per-1",
          personnelName: "رضا احمدی",
          unit: "مکانیک",
          fromDate: "2026-01-01",
          toDate: "",
          current: true,
        },
      ],
      location: null,
      locationPath: "سایت / اتاق",
      children: [],
      analytics: null,
      generatedAt: "2026-09-26",
    });

    expect(profile.bom[0].standardQuantity).toBe(2);
    expect(profile.bom[0].quantityOnHand).toBe(12);
    expect(profile.nameplate.purchaseCost).toBe("1850000000");
    expect(profile.device.criticality).toBe("critical");
    expect(profile.assignments[0].role).toBe("responsible");
  });

  it("keeps the seven PM disciplines addressable", () => {
    expect(MAINTENANCE_DEPARTMENTS).toHaveLength(7);
    MAINTENANCE_DEPARTMENTS.forEach((department) => {
      const label = translate("fa", `cmms.department.${department}` as "cmms.department.general");
      expect(label).not.toBe(`cmms.department.${department}`);
    });
    const plan = toPmPlan({
      id: "p1",
      deviceId: "d1",
      title: "بازرسی نشتی",
      discipline: "hydraulic",
      description: "",
      checklist: ["بازرسی شیلنگ"],
      frequencyEvery: 2,
      frequencyUnit: "month",
      periodDays: 60,
      estimatedMinutes: 45,
      responsibleName: "سارا نوری",
      lastExecutedOn: "2026-08-05",
      nextDueOn: "2026-10-04",
      overdue: false,
      active: true,
    });
    expect(plan.discipline).toBe("hydraulic");
    expect(plan.checklist).toEqual(["بازرسی شیلنگ"]);
  });

  it("calls the documented registry endpoints", async () => {
    const calls: { method: string; path: string }[] = [];
    const stub = {
      get: vi.fn(async (path: string) => {
        calls.push({ method: "GET", path });
        return [];
      }),
      post: vi.fn(async (path: string) => {
        calls.push({ method: "POST", path });
        return { id: "x", role: "technician" };
      }),
      put: vi.fn(async (path: string) => {
        calls.push({ method: "PUT", path });
        return [];
      }),
      patch: vi.fn(async (path: string) => {
        calls.push({ method: "PATCH", path });
        return {};
      }),
      delete: vi.fn(async (path: string) => {
        calls.push({ method: "DELETE", path });
        return null;
      }),
    } as unknown as ApiClient;

    const service = createRegistryService(stub);
    await service.listLocations();
    await service.listPmPlans("d1");
    await service.saveSpecifications("d1", [{ label: "دبی", value: "120" }]);
    await service.saveAssignments("d1", [{ role: "operator", personnelId: "per-1" }]);
    await service.removeBomItem("d1", "p1");
    await service.updateNameplate("d1", { manufacturer: "گراندفوس" });

    expect(calls).toEqual([
      { method: "GET", path: apiEndpoints.maintenance.locations },
      { method: "GET", path: apiEndpoints.maintenance.devicePmPlans("d1") },
      { method: "PUT", path: apiEndpoints.maintenance.deviceSpecifications("d1") },
      { method: "PUT", path: apiEndpoints.maintenance.deviceAssignments("d1") },
      { method: "DELETE", path: apiEndpoints.maintenance.deviceBomItem("d1", "p1") },
      { method: "PATCH", path: apiEndpoints.maintenance.deviceNameplate("d1") },
    ]);
  });
});

describe("offline registry store", () => {
  it("persists writes so the registry behaves like a database", async () => {
    const service = createDemoRegistryService();

    const location = await service.createLocation({ name: "سوله ۳", kind: "building" });
    expect((await service.listLocations()).some((item) => item.id === location.id)).toBe(true);

    const person = await service.createPersonnel({ fullName: "نیما سلیمی", specialty: "pneumatic" });
    expect((await service.listPersonnel()).some((item) => item.id === person.id)).toBe(true);

    const plan = await service.createPmPlan("dev-1", {
      title: "بازرسی فیلتر",
      discipline: "pneumatic",
      frequencyEvery: 1,
      frequencyUnit: "month",
    });
    expect((await service.listPmPlans("dev-1")).some((item) => item.id === plan.id)).toBe(true);

    await service.recordPmExecution(plan.id, { performedOn: "2026-09-20" });
    const profile = await service.getDeviceProfile("dev-1");
    expect(profile.pmPlans.find((item) => item.id === plan.id)?.lastExecutedOn).toBe("2026-09-20");
    expect(profile.pmExecutions[0].planId).toBe(plan.id);

    await service.deletePmPlan(plan.id);
    expect((await service.listPmPlans("dev-1")).some((item) => item.id === plan.id)).toBe(false);
  });

  it("stores the nameplate and reflects it on the device record", async () => {
    const service = createDemoRegistryService();
    await service.updateNameplate("dev-2", { manufacturer: "سازنده آزمایشی", criticality: "low" });
    const profile = await service.getDeviceProfile("dev-2");
    expect(profile.nameplate.manufacturer).toBe("سازنده آزمایشی");
    expect(profile.device.criticality).toBe("low");
  });
});

describe("registry pages", () => {
  it("lists every machine with its registry columns", async () => {
    authenticate();
    renderPage("/app/maintenance/registry", <EquipmentRegistryPage />, "/app/maintenance/registry");
    expect(await screen.findByText("پمپ خنک‌کننده اصلی")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /افزودن ماشین/ })).toBeInTheDocument();
    expect(screen.getAllByText("گراندفوس / NK 80-250").length).toBeGreaterThan(0);
  });

  it("opens the device file with all registry sections", async () => {
    authenticate();
    renderPage(
      "/app/maintenance/devices/dev-1/profile",
      <DeviceProfilePage />,
      "/app/maintenance/devices/:deviceId/profile",
    );
    expect(await screen.findByRole("tab", { name: /شناسنامه/ })).toBeInTheDocument();
    ["مشخصات فنی", "برنامه‌های PM", "قطعات", "محل استقرار و بهره‌بردار", "پرسنل نت", "شاخص‌ها و تحلیل"].forEach(
      (label) => {
        expect(screen.getByRole("tab", { name: new RegExp(label) })).toBeInTheDocument();
      },
    );
  });

  it("shows the location tree and the personnel directory", async () => {
    authenticate();
    renderPage(
      "/app/maintenance/locations",
      <MaintenanceLocationsPage />,
      "/app/maintenance/locations",
    );
    await waitFor(() => expect(screen.getByText("سایت اصفهان")).toBeInTheDocument());
    expect(screen.getByText("اتاق پمپ‌خانه")).toBeInTheDocument();

    renderPage(
      "/app/maintenance/personnel",
      <MaintenancePersonnelPage />,
      "/app/maintenance/personnel",
    );
    expect(await screen.findByText("رضا احمدی")).toBeInTheDocument();
    expect(screen.getByText("سارا نوری")).toBeInTheDocument();
  });
});
