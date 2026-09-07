import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useAuth } from "../auth/authContext";

export const PERMISSIONS = {
  dashboardView: "dashboard.view",
  projectView: "project.view",
  projectCreate: "project.create",
  projectUpdate: "project.update",
  taskView: "task.view",
  taskCreate: "task.create",
  documentView: "document.view",
  documentUpload: "document.upload",
  reportView: "report.view",
  intelligenceView: "projectIntelligence.view",
  intelligenceAnalyze: "projectIntelligence.analyze",
  notificationView: "notification.view",
  userManage: "user.manage",
  roleManage: "role.manage",
  tenantManage: "tenant.manage",
  auditView: "audit.view",
  settingsManage: "settings.manage",
} as const;

interface PermissionContextValue {
  permissions: string[];
  roles: string[];
  has: (permission: string | string[]) => boolean;
  hasAny: (permissions: string[]) => boolean;
}

const PermissionContext = createContext<PermissionContextValue | null>(null);

export function PermissionProvider({ children }: { children: ReactNode }): JSX.Element {
  const { session } = useAuth();
  const permissions = session?.user.permissions ?? [];
  const roles = session ? [session.user.role] : [];
  const value = useMemo<PermissionContextValue>(() => {
    const hasOne = (permission: string): boolean =>
      permissions.includes(permission) || permissions.includes("*");
    return {
      permissions,
      roles,
      has: (permission) => Array.isArray(permission) ? permission.every(hasOne) : hasOne(permission),
      hasAny: (required) => required.some(hasOne),
    };
  }, [permissions, roles]);
  return <PermissionContext.Provider value={value}>{children}</PermissionContext.Provider>;
}

export const usePermissions = (): PermissionContextValue => {
  const context = useContext(PermissionContext);
  if (!context) throw new Error("usePermissions must be used inside PermissionProvider");
  return context;
};
