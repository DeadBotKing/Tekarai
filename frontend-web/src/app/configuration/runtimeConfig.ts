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

/**
 * Demo mode replaces the backend with fixtures — including `demoLogin`, which
 * accepts any credentials and returns `permissions: ["*"]`. That is fine for a
 * sales demo and catastrophic in production, and until now a single stray
 * `VITE_DEMO_MODE=true` (a leftover .env, a mistyped CI variable) was all it
 * took to turn a real deployment into one that lets anyone in as platform
 * administrator.
 *
 * A production build therefore ignores `VITE_DEMO_MODE` on its own. Enabling
 * it there takes a second, deliberately awkward variable, so it cannot happen
 * by accident — and when it does happen the app says so, loudly and
 * permanently, in the UI.
 */
const isProductionBuild = import.meta.env.PROD;
const demoRequested = envValue("VITE_DEMO_MODE", isProductionBuild ? "false" : "true") === "true";
const demoAllowedInProduction =
  envValue("VITE_ALLOW_DEMO_IN_PRODUCTION", "false") === "true";

export const demoModeRefusedInProduction =
  demoRequested && isProductionBuild && !demoAllowedInProduction;

if (demoModeRefusedInProduction) {
  // Not a silent downgrade: whoever deployed this asked for fake data and is
  // getting real data instead, and needs to know which one they are looking at.
  console.error(
    "[Tekarai] VITE_DEMO_MODE=true was ignored: demo fixtures, including a login " +
      "that accepts any password, must never back a production build. Set " +
      "VITE_ALLOW_DEMO_IN_PRODUCTION=true as well if this really is a demo deployment.",
  );
}

export const runtimeConfig: RuntimeConfig = {
  appName: envValue("VITE_APP_NAME", "Tekarai"),
  apiBaseUrl: envValue("VITE_API_BASE_URL", ""),
  apiVersion: envValue("VITE_API_VERSION", "v1"),
  demoMode: demoRequested && (!isProductionBuild || demoAllowedInProduction),
  realtimeEnabled: envValue("VITE_REALTIME_ENABLED", "false") === "true",
};
