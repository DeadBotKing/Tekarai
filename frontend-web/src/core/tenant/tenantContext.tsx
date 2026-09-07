import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export interface Tenant {
  id: string;
  code: string;
  name: string;
  industry: string;
  plan: string;
  status: "active" | "suspended";
  members: number;
}

export const demoTenants: Tenant[] = [
  {
    id: "tenant-nordic",
    code: "nordic",
    name: "Nordic Manufacturing Group",
    industry: "Industrial operations",
    plan: "Enterprise",
    status: "active",
    members: 248,
  },
  {
    id: "tenant-atlas",
    code: "atlas",
    name: "Atlas Engineering GmbH",
    industry: "Engineering services",
    plan: "Scale",
    status: "active",
    members: 86,
  },
  {
    id: "tenant-demo",
    code: "platform",
    name: "Tekarai Platform",
    industry: "Enterprise operations",
    plan: "Platform",
    status: "active",
    members: 42,
  },
];

interface TenantContextValue {
  tenants: Tenant[];
  selectedTenant: Tenant;
  selectTenant: (tenantId: string) => void;
}

const TENANT_KEY = "tekarai.gui.tenant.v1";
const TenantContext = createContext<TenantContextValue | null>(null);

const initialTenant = (): Tenant => {
  try {
    const storedId = localStorage.getItem(TENANT_KEY);
    return demoTenants.find((tenant) => tenant.id === storedId) ?? demoTenants[0];
  } catch {
    return demoTenants[0];
  }
};

export function TenantProvider({ children }: { children: ReactNode }): JSX.Element {
  const [selectedTenant, setSelectedTenant] = useState<Tenant>(initialTenant);
  const selectTenant = (tenantId: string): void => {
    const next = demoTenants.find((tenant) => tenant.id === tenantId);
    if (!next || next.status !== "active") return;
    setSelectedTenant(next);
    try {
      localStorage.setItem(TENANT_KEY, next.id);
    } catch {
      // Tenant context remains in memory when storage is restricted.
    }
  };
  const value = useMemo(() => ({ tenants: demoTenants, selectedTenant, selectTenant }), [selectedTenant]);
  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export const useTenant = (): TenantContextValue => {
  const context = useContext(TenantContext);
  if (!context) throw new Error("useTenant must be used inside TenantProvider");
  return context;
};
