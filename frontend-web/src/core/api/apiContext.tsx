import { createContext, useContext, useMemo, type ReactNode } from "react";
import { runtimeConfig } from "../../app/configuration/runtimeConfig";
import { ApiClient, type ApiClientConfig } from "./apiClient";
import { sessionStore } from "../auth/sessionStore";
import { useTenant } from "../tenant/tenantContext";

const ApiContext = createContext<ApiClient | null>(null);

export function ApiProvider({ children }: { children: ReactNode }): JSX.Element {
  const tenant = useTenant();
  const client = useMemo(() => {
    const config: ApiClientConfig = {
      baseUrl: runtimeConfig.apiBaseUrl,
      apiVersion: runtimeConfig.apiVersion,
      defaultTimeoutMs: 12_000,
      defaultRetries: 2,
    };
    return new ApiClient(config, {
      getAccessToken: () => sessionStore.get()?.accessToken ?? null,
      getRefreshToken: () => sessionStore.get()?.refreshToken ?? null,
      setTokens: (tokens) => sessionStore.updateTokens(tokens),
      clearTokens: () => sessionStore.clear(),
      getTenantId: () => tenant.selectedTenant?.id ?? null,
    });
  }, [tenant.selectedTenant?.id]);
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>;
}

export const useApiClient = (): ApiClient => {
  const context = useContext(ApiContext);
  if (!context) throw new Error("useApiClient must be used inside ApiProvider");
  return context;
};
