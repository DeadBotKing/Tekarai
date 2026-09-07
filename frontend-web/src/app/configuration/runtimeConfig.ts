export interface RuntimeConfig {
  appName: string;
  apiBaseUrl: string;
  apiVersion: string;
  demoMode: boolean;
  realtimeEnabled: boolean;
}

const envValue = (key: keyof ImportMetaEnv, fallback: string): string => {
  const value = import.meta.env[key];
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
};

export const runtimeConfig: RuntimeConfig = {
  appName: envValue("VITE_APP_NAME", "Tekarai"),
  apiBaseUrl: envValue("VITE_API_BASE_URL", ""),
  apiVersion: envValue("VITE_API_VERSION", "v1"),
  demoMode: envValue("VITE_DEMO_MODE", import.meta.env.DEV ? "true" : "false") === "true",
  realtimeEnabled: envValue("VITE_REALTIME_ENABLED", "false") === "true",
};
