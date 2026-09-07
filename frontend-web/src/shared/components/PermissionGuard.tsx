import type { ReactNode } from "react";
import { usePermissions } from "../../core/permissions/permissionContext";
import { useLocalization } from "../../core/localization/localizationContext";
import { Icon } from "./Icon";

export function PermissionGuard({ permission, children, fallback = "hide", label }: { permission: string | string[]; children: ReactNode; fallback?: "hide" | "denied" | ReactNode; label?: string }): JSX.Element | null {
  const { has } = usePermissions();
  const { t } = useLocalization();
  if (has(permission)) return <>{children}</>;
  if (fallback === "hide") return null;
  if (fallback === "denied") return <div className="permission-denied" role="status"><Icon name="lock" size={18} /><span>{label ?? t("error.forbiddenBody")}</span></div>;
  return <>{fallback}</>;
}
