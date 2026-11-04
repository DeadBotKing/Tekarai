import { describe, expect, it } from "vitest";
import { navigationConfig, flattenNavigation } from "../app/configuration/navigation";
import { PERMISSIONS } from "../core/permissions/permissionContext";

describe("daily-work navigation order", () => {
  it("keeps home first and projects/tasks at the end", () => {
    expect(navigationConfig.map((item) => item.id)).toEqual([
      "workspace", "maintenance", "records", "communication", "administration", "intelligence", "delivery",
    ]);
    expect(navigationConfig.at(-1)?.children?.map((item) => item.id)).toEqual(["projects", "tasks"]);
  });

  it("puts daily operations before dashboards, assets and supporting work", () => {
    const maintenance = navigationConfig.find((item) => item.id === "maintenance");
    expect(maintenance?.children?.map((item) => item.id)).toEqual([
      "maintenanceOps", "maintenanceDashboard", "maintenanceAssets", "safetyPermits",
      "maintenanceWarehouse", "maintenanceProcurement", "maintenanceInsights",
    ]);
    expect(maintenance?.children?.[0].children?.[0].id).toBe("maintenanceWorkOrders");
  });

  it("preserves merged people/access visibility and separate roles", () => {
    const flat = flattenNavigation(navigationConfig);
    expect(flat.find((item) => item.id === "users")).toMatchObject({
      route: "/app/administration/users",
      anyPermission: [PERMISSIONS.userList, PERMISSIONS.organizationDepartmentView],
    });
    expect(flat.find((item) => item.id === "roles")?.route).toBe("/app/administration/roles");
    expect(flat.find((item) => item.id === "maintenanceWorkOrders")?.permission).toBe(PERMISSIONS.maintenanceWorkOrderList);
    expect(new Set(flat.map((item) => item.id)).size).toBe(flat.length);
  });
});
