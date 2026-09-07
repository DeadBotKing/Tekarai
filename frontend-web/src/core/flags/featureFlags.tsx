import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useTenant } from "../tenant/tenantContext";
import { usePermissions } from "../permissions/permissionContext";

export interface FeatureFlag {
  enabled: boolean;
  tenantIds?: string[];
  roles?: string[];
  rolloutPercentage?: number;
}

export const featureFlagConfig: Record<string, FeatureFlag> = {
  dashboardCustomization: { enabled: true },
  projectIntelligence: { enabled: true, tenantIds: ["tenant-nordic", "tenant-atlas", "tenant-demo"] },
  realtimeNotifications: { enabled: false },
  advancedReports: { enabled: true, roles: ["Platform Administrator", "Workspace Manager"] },
  documentUpload: { enabled: true },
};

interface FeatureFlagContextValue {
  isEnabled: (flagName: string) => boolean;
}

const FeatureFlagContext = createContext<FeatureFlagContextValue | null>(null);

export function FeatureFlagProvider({ children }: { children: ReactNode }): JSX.Element {
  const { selectedTenant } = useTenant();
  const { roles } = usePermissions();
  const value = useMemo(() => ({
    isEnabled: (flagName: string): boolean => {
      const flag = featureFlagConfig[flagName];
      if (!flag?.enabled) return false;
      if (flag.tenantIds && !flag.tenantIds.includes(selectedTenant.id)) return false;
      if (flag.roles && !flag.roles.some((role) => roles.includes(role))) return false;
      if (typeof flag.rolloutPercentage === "number") {
        const bucket = [...`${flagName}:${selectedTenant.id}`].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 100;
        if (bucket >= flag.rolloutPercentage) return false;
      }
      return true;
    },
  }), [roles, selectedTenant.id]);
  return <FeatureFlagContext.Provider value={value}>{children}</FeatureFlagContext.Provider>;
}

export const useFeatureFlags = (): FeatureFlagContextValue => {
  const context = useContext(FeatureFlagContext);
  if (!context) throw new Error("useFeatureFlags must be used inside FeatureFlagProvider");
  return context;
};
