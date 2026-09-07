import { PERMISSIONS } from "../../core/permissions/permissionContext";
import type { TranslationKey } from "../../core/localization/i18n";
import type { IconName } from "../../shared/components/Icon";

export interface NavigationItem {
  id: string;
  label: TranslationKey;
  icon: IconName;
  route?: string;
  permission?: string;
  featureFlag?: string;
  children?: NavigationItem[];
  badge?: number;
}

export const navigationConfig: NavigationItem[] = [
  {
    id: "workspace",
    label: "nav.workspace",
    icon: "grid",
    children: [
      { id: "dashboard", label: "nav.dashboard", icon: "home", route: "/app/dashboard", permission: PERMISSIONS.dashboardView },
    ],
  },
  {
    id: "organization",
    label: "nav.organization",
    icon: "building",
    children: [
      { id: "employees", label: "nav.employees", icon: "users", route: "/app/organization/employees", permission: PERMISSIONS.userManage },
      { id: "departments", label: "nav.departments", icon: "layers", route: "/app/organization/departments", permission: PERMISSIONS.userManage },
    ],
  },
  {
    id: "delivery",
    label: "nav.projects",
    icon: "briefcase",
    children: [
      { id: "projects", label: "nav.projects", icon: "folder", route: "/app/projects", permission: PERMISSIONS.projectView },
      { id: "tasks", label: "nav.tasks", icon: "checkSquare", route: "/app/tasks", permission: PERMISSIONS.taskView },
    ],
  },
  {
    id: "records",
    label: "nav.documents",
    icon: "file",
    children: [
      { id: "documents", label: "nav.documents", icon: "file", route: "/app/documents", permission: PERMISSIONS.documentView },
      { id: "devices", label: "nav.devices", icon: "cpu", route: "/app/devices", permission: PERMISSIONS.projectView },
    ],
  },
  {
    id: "reporting",
    label: "nav.reports",
    icon: "chart",
    children: [
      { id: "reports", label: "nav.reports", icon: "chart", route: "/app/reports", permission: PERMISSIONS.reportView },
    ],
  },
  {
    id: "intelligence",
    label: "nav.intelligence",
    icon: "sparkles",
    featureFlag: "projectIntelligence",
    children: [
      { id: "projectIntelligence", label: "nav.projectIntelligence", icon: "sparkles", route: "/app/intelligence", permission: PERMISSIONS.intelligenceView },
      { id: "insights", label: "nav.insights", icon: "lightbulb", route: "/app/intelligence#insights", permission: PERMISSIONS.intelligenceView },
    ],
  },
  {
    id: "administration",
    label: "nav.administration",
    icon: "shield",
    children: [
      { id: "users", label: "nav.users", icon: "users", route: "/app/administration/users", permission: PERMISSIONS.userManage },
      { id: "roles", label: "nav.roles", icon: "key", route: "/app/administration/roles", permission: PERMISSIONS.roleManage },
      { id: "settings", label: "nav.settings", icon: "settings", route: "/app/settings", permission: PERMISSIONS.settingsManage },
      { id: "audit", label: "nav.audit", icon: "activity", route: "/app/administration/audit", permission: PERMISSIONS.auditView },
    ],
  },
];

export const flattenNavigation = (items: NavigationItem[]): NavigationItem[] => items.flatMap((item) => [item, ...(item.children ? flattenNavigation(item.children) : [])]);
