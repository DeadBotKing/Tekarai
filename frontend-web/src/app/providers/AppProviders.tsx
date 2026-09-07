import type { ReactNode } from "react";
import { ErrorBoundary } from "../../core/errors/errorBoundary";
import { ApiProvider } from "../../core/api/apiContext";
import { AuthProvider } from "../../core/auth/authContext";
import { FeatureFlagProvider } from "../../core/flags/featureFlags";
import { LocalizationProvider } from "../../core/localization/localizationContext";
import { NotificationProvider } from "../../core/notifications/notificationContext";
import { PermissionProvider } from "../../core/permissions/permissionContext";
import { TenantProvider } from "../../core/tenant/tenantContext";
import { ThemeProvider } from "../../core/theme/themeContext";

export function AppProviders({ children }: { children: ReactNode }): JSX.Element {
  return (
    <ErrorBoundary>
      <LocalizationProvider>
        <ThemeProvider>
          <TenantProvider>
            <ApiProvider>
              <AuthProvider>
                <PermissionProvider>
                  <FeatureFlagProvider>
                    <NotificationProvider>{children}</NotificationProvider>
                  </FeatureFlagProvider>
                </PermissionProvider>
              </AuthProvider>
            </ApiProvider>
          </TenantProvider>
        </ThemeProvider>
      </LocalizationProvider>
    </ErrorBoundary>
  );
}
