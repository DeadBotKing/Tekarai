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
  allPermissions?: string[];
  featureFlag?: string;
  children?: NavigationItem[];
  badge?: number;
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
  { id: "assistant", label: "nav.intelligence", displayLabel: "دستیار هوشمند", icon: "sparkles", children: [
    { id: "localAssistant", label: "nav.intelligence", displayLabel: "دستیار هوشمند", icon: "sparkles", route: "/app/assistant", anyPermission: [PERMISSIONS.maintenanceDeviceView, PERMISSIONS.maintenanceWorkOrderView, PERMISSIONS.maintenanceDocumentView, PERMISSIONS.projectView, PERMISSIONS.taskView] },
  ] },
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
      // گزارش روزانه - جدید - برای همه فنی (کارشناس/سرپرست/رییس/مدیر) با تایید سرپرست/رییس همان واحد
      { id: "dailyReport", label: "گزارش روزانه" as TranslationKey, displayLabel: "گزارش روزانه", icon: "clipboard", route: "/app/daily-report", permission: PERMISSIONS.maintenanceWorkOrderCreate },
      { id: "maintenanceInspections", label: "nav.inspections", icon: "checkSquare", route: "/app/maintenance/inspections", permission: PERMISSIONS.maintenanceWorkOrderList },
      // فقط برای سرپرست/رییس/مدیر - مخفی برای کارشناس/پرسنل
      { id: "maintenancePmCalendar", label: "nav.pmCalendar", icon: "calendar", route: "/app/maintenance/pm-calendar", permission: PERMISSIONS.maintenanceDeviceManage , allPermissions: [PERMISSIONS.maintenanceWorkOrderList] },
      { id: "maintenanceWorkCalendar", label: "calendar.nav", icon: "clock", route: "/app/maintenance/work-calendar", permission: PERMISSIONS.maintenanceDeviceManage , allPermissions: [PERMISSIONS.maintenanceWorkOrderList] },
      { id: "maintenanceMeterReadings", label: "nav.meterReadings", icon: "activity", route: "/app/maintenance/meter-readings", permission: PERMISSIONS.maintenanceMeterView , allPermissions: [PERMISSIONS.maintenanceWorkOrderList] },
      { id: "safetyPermits", label: "nav.safetyPermits", icon: "shield", route: "/app/maintenance/permits", permission: PERMISSIONS.safetyPermitView },
      { id: "maintenanceOfflineQueue", label: "nav.offlineQueue", icon: "cloud", route: "/app/maintenance/offline-queue", permission: PERMISSIONS.maintenanceWorkOrderList },
    ],
  },
  {
    id: "equipment", label: "nav.section.equipment", icon: "cpu",
    children: [
      // فقط لیست تجهیزات - برای کارشناس فقط واحد خودش (فقط نمایش)
      { id: "maintenanceRegistry", label: "nav.equipment", icon: "cpu", route: "/app/maintenance/equipment", permission: PERMISSIONS.maintenanceDeviceList },
      // بقیه فقط برای سرپرست/رییس/مدیر (کارشناس نبیند)
      { id: "maintenanceAssetTree", label: "assets.tree.nav", icon: "layers", route: "/app/maintenance/asset-tree", permission: PERMISSIONS.maintenanceDeviceManage },
      { id: "maintenanceLocations", label: "nav.registryLocations", icon: "building", route: "/app/maintenance/locations", permission: PERMISSIONS.maintenanceDeviceManage },
      { id: "maintenancePersonnel", label: "nav.registryPersonnel", icon: "users", route: "/app/maintenance/personnel", permission: PERMISSIONS.maintenanceDeviceManage },
      { id: "maintenanceWarehouse", label: "nav.warehouse", icon: "layers", route: "/app/maintenance/warehouse", permission: PERMISSIONS.maintenanceInventoryView },
      { id: "maintenanceProcurement", label: "nav.procurement", icon: "briefcase", route: "/app/maintenance/procurement", permission: PERMISSIONS.procurementSupplierView },
    ],
  },
  {
    id: "production", label: "nav.reports" as TranslationKey, displayLabel: "تولید", icon: "target",
    // فقط مدیر تولید/برنامه‌ریزی و مدیران واحدها - مخفی برای کارشناس/پرسنل/سرپرست عادی
    permission: PERMISSIONS.productionView,
    children: [
      { id: "productionPlanning", label: "nav.reports" as TranslationKey, displayLabel: "داشبورد برنامه‌ریزی", icon: "chart", route: "/app/production/planning", permission: PERMISSIONS.productionView },
    ],
  },
  {
    id: "reports", label: "nav.section.reports", icon: "chart",
    // مخفی برای کارشناس/پرسنل - فقط سرپرست/رییس/مدیر
    permission: PERMISSIONS.maintenanceCostsView,
    children: [
      { id: "maintenanceDashboardDaily", label: "nav.dashDaily", icon: "chart", route: "/app/maintenance/dashboard", permission: PERMISSIONS.maintenanceCostsView, exact: true },
      { id: "maintenanceDashboardCalendar", label: "nav.dashCalendar", icon: "calendar", route: "/app/maintenance/dashboard/calendar", permission: PERMISSIONS.maintenanceCostsView },
      { id: "maintenanceDashboardPerformance", label: "nav.dashPerformance", icon: "activity", route: "/app/maintenance/dashboard/performance", permission: PERMISSIONS.maintenanceCostsView },
      { id: "maintenanceDashboardUser", label: "nav.dashUser", icon: "users", route: "/app/maintenance/dashboard/user", permission: PERMISSIONS.maintenanceCostsView },
      { id: "maintenanceFleet", label: "nav.registryFleet", icon: "chart", route: "/app/maintenance/fleet", permission: PERMISSIONS.maintenanceDeviceManage },
      { id: "maintenanceReports", label: "nav.maintenanceReports", icon: "chart", route: "/app/maintenance/reports", permission: PERMISSIONS.maintenanceCostsView , allPermissions: [PERMISSIONS.maintenanceDeviceList] },
      { id: "maintenanceWorkReport", label: "nav.workReport", icon: "download", route: "/app/maintenance/work-report", permission: PERMISSIONS.maintenanceCostsView , allPermissions: [PERMISSIONS.maintenanceDeviceList] },
      { id: "maintenancePerformanceReview", label: "review.nav", icon: "users", route: "/app/maintenance/performance-review", permission: PERMISSIONS.maintenanceCostsView },
    ],
  },
  {
    id: "administration", label: "nav.section.administration", icon: "shield",
    // مخفی برای کارشناس/پرسنل - فقط مدیر/رییس
    permission: PERMISSIONS.organizationDepartmentView,
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
