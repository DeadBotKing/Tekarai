import { PERMISSIONS } from "../../core/permissions/permissionContext";
import type { TranslationKey } from "../../core/localization/i18n";
import type { IconName } from "../../shared/components/Icon";

export interface NavigationItem {
  displayLabel?: string;
  id: string;
  label: TranslationKey;
  icon: IconName;
  route?: string;
  permission?: string;
  anyPermission?: string[];
  /** Ancestor permissions retained when flattening the display hierarchy. */
  allPermissions?: string[];
  featureFlag?: string;
  children?: NavigationItem[];
  badge?: number;
  /** Match the route exactly (no prefix) — for a view that owns the bare
   *  route while its siblings live under it, e.g. the daily dashboard. */
  exact?: boolean;
}

export const navigationConfig: NavigationItem[] = [
  {
    id: "workspace", label: "nav.workspace", icon: "home",
    children: [
      { id: "dashboard", label: "nav.home", icon: "home", route: "/app/dashboard", exact: true },
    ],
  },
  {
    id: "records", label: "nav.records", icon: "file",
    children: [
      { id: "documents", label: "nav.documents", icon: "file", route: "/app/documents", permission: PERMISSIONS.maintenanceDocumentView },
    ],
  },
  {
    id: "communication", label: "nav.chat", icon: "message",
    children: [
      { id: "chat", label: "nav.chat", icon: "message", route: "/app/chat" },
    ],
  },
  {
    id: "operations", label: "nav.section.operations", icon: "checkSquare",
    children: [
      { id: "maintenanceWorkOrders", label: "nav.workOrders", icon: "checkSquare", route: "/app/maintenance/work-orders", permission: PERMISSIONS.maintenanceWorkOrderList },
      { id: "maintenanceInspections", label: "nav.inspections", icon: "checkSquare", route: "/app/maintenance/inspections", permission: PERMISSIONS.maintenanceWorkOrderList },
      { id: "maintenancePmCalendar", label: "nav.pmCalendar", icon: "calendar", route: "/app/maintenance/pm-calendar", permission: PERMISSIONS.maintenanceDeviceList , allPermissions: [PERMISSIONS.maintenanceWorkOrderList] },
      { id: "maintenanceWorkCalendar", label: "calendar.nav", icon: "clock", route: "/app/maintenance/work-calendar", permission: PERMISSIONS.maintenanceDeviceList , allPermissions: [PERMISSIONS.maintenanceWorkOrderList] },
      { id: "maintenanceMeterReadings", label: "nav.meterReadings", icon: "activity", route: "/app/maintenance/meter-readings", permission: PERMISSIONS.maintenanceMeterView , allPermissions: [PERMISSIONS.maintenanceWorkOrderList] },
      { id: "safetyPermits", label: "nav.safetyPermits", icon: "shield", route: "/app/maintenance/permits", permission: PERMISSIONS.safetyPermitView },
      { id: "maintenanceOfflineQueue", label: "nav.offlineQueue", icon: "cloud", route: "/app/maintenance/offline-queue", permission: PERMISSIONS.maintenanceWorkOrderList },
    ],
  },
  {
    id: "equipment", label: "nav.section.equipment", icon: "cpu",
    children: [
      { id: "maintenanceRegistry", label: "nav.equipment", icon: "cpu", route: "/app/maintenance/equipment", permission: PERMISSIONS.maintenanceDeviceList },
      { id: "maintenanceAssetTree", label: "assets.tree.nav", icon: "layers", route: "/app/maintenance/asset-tree", permission: PERMISSIONS.maintenanceDeviceList },
      { id: "maintenanceLocations", label: "nav.registryLocations", icon: "building", route: "/app/maintenance/locations", permission: PERMISSIONS.maintenanceDeviceList },
      { id: "maintenancePersonnel", label: "nav.registryPersonnel", icon: "users", route: "/app/maintenance/personnel", permission: PERMISSIONS.maintenanceDeviceList },
      { id: "maintenanceWarehouse", label: "nav.warehouse", icon: "layers", route: "/app/maintenance/warehouse", permission: PERMISSIONS.maintenanceInventoryView },
      { id: "maintenanceProcurement", label: "nav.procurement", icon: "briefcase", route: "/app/maintenance/procurement", permission: PERMISSIONS.procurementSupplierView },
    ],
  },
  {
    id: "reports", label: "nav.section.reports", icon: "chart",
    children: [
      { id: "maintenanceDashboardDaily", label: "nav.dashDaily", icon: "chart", route: "/app/maintenance/dashboard", permission: PERMISSIONS.maintenanceWorkOrderList, exact: true },
      { id: "maintenanceDashboardCalendar", label: "nav.dashCalendar", icon: "calendar", route: "/app/maintenance/dashboard/calendar", permission: PERMISSIONS.maintenanceWorkOrderList },
      { id: "maintenanceDashboardPerformance", label: "nav.dashPerformance", icon: "activity", route: "/app/maintenance/dashboard/performance", permission: PERMISSIONS.maintenanceWorkOrderList },
      { id: "maintenanceDashboardUser", label: "nav.dashUser", icon: "users", route: "/app/maintenance/dashboard/user", permission: PERMISSIONS.maintenanceWorkOrderList },
      { id: "maintenanceFleet", label: "nav.registryFleet", icon: "chart", route: "/app/maintenance/fleet", permission: PERMISSIONS.maintenanceDeviceList },
      { id: "maintenanceReports", label: "nav.maintenanceReports", icon: "chart", route: "/app/maintenance/reports", permission: PERMISSIONS.maintenanceWorkOrderList , allPermissions: [PERMISSIONS.maintenanceDeviceList] },
      { id: "maintenanceWorkReport", label: "nav.workReport", icon: "download", route: "/app/maintenance/work-report", permission: PERMISSIONS.maintenanceWorkOrderList , allPermissions: [PERMISSIONS.maintenanceDeviceList] },
      { id: "maintenancePerformanceReview", label: "review.nav", icon: "users", route: "/app/maintenance/performance-review", permission: PERMISSIONS.maintenanceDeviceList , allPermissions: [PERMISSIONS.maintenanceWorkOrderList] },
    ],
  },
  {
    id: "administration", label: "nav.section.administration", icon: "shield",
    children: [
      { id: "users", label: "nav.users", icon: "users", route: "/app/administration/users", anyPermission: [PERMISSIONS.userList, PERMISSIONS.organizationDepartmentView] },
      { id: "roles", label: "nav.roles", icon: "key", route: "/app/administration/roles", permission: PERMISSIONS.roleList },
      { id: "settings", label: "nav.settings", icon: "settings", route: "/app/settings" },
      { id: "account", label: "nav.account", icon: "user", route: "/app/account" },
      { id: "audit", label: "nav.audit", icon: "activity", route: "/app/administration/audit", permission: PERMISSIONS.auditView },
    ],
  },
  {
    id: "intelligence", label: "nav.intelligence", icon: "sparkles", featureFlag: "projectIntelligence",
    children: [
      { id: "projectIntelligence", label: "nav.projectIntelligence", icon: "sparkles", route: "/app/intelligence", permission: PERMISSIONS.intelligenceView },
      { id: "insights", label: "nav.insights", icon: "lightbulb", route: "/app/intelligence#insights", permission: PERMISSIONS.intelligenceView },
    ],
  },
  {
    id: "delivery", label: "nav.section.delivery", icon: "briefcase",
    children: [
      { id: "projects", label: "nav.projects", icon: "folder", route: "/app/projects", permission: PERMISSIONS.projectView },
      { id: "tasks", label: "nav.tasks", icon: "checkSquare", route: "/app/tasks", permission: PERMISSIONS.taskView },
    ],
  },
];

export const flattenNavigation = (items: NavigationItem[]): NavigationItem[] => items.flatMap((item) => [item, ...(item.children ? flattenNavigation(item.children) : [])]);
