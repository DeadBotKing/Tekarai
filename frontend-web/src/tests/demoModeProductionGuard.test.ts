/**
 * A production build must not be able to serve fixtures by accident.
 *
 * `demoLogin` accepts any password and returns `permissions: ["*"]`. Before
 * this guard, `VITE_DEMO_MODE=true` was enough to reach it from a production
 * bundle — one stray environment variable between a real deployment and one
 * that lets anybody in as platform administrator.
 *
 * The module reads `import.meta.env` once at import time, so each case needs a
 * fresh module registry.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const loadConfig = async (env: Record<string, unknown>) => {
  vi.resetModules();
  vi.stubGlobal("console", { ...console, error: vi.fn() });
  for (const [key, value] of Object.entries(env)) {
    vi.stubEnv(key as never, value as never);
  }
  return import("../app/configuration/runtimeConfig");
};

describe("demo mode in a production build", () => {
  beforeEach(() => vi.unstubAllEnvs());
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("is refused when only VITE_DEMO_MODE is set", async () => {
    const { runtimeConfig, demoModeRefusedInProduction } = await loadConfig({
      PROD: true,
      DEV: false,
      VITE_DEMO_MODE: "true",
    });
    expect(runtimeConfig.demoMode).toBe(false);
    expect(demoModeRefusedInProduction).toBe(true);
  });

  it("says so on the console rather than downgrading silently", async () => {
    await loadConfig({ PROD: true, DEV: false, VITE_DEMO_MODE: "true" });
    // Whoever deployed this asked for fixtures and is getting real data.
    expect(console.error).toHaveBeenCalledWith(
      expect.stringContaining("VITE_DEMO_MODE=true was ignored"),
    );
  });

  it("is allowed only with the explicit second flag", async () => {
    const { runtimeConfig, demoModeRefusedInProduction } = await loadConfig({
      PROD: true,
      DEV: false,
      VITE_DEMO_MODE: "true",
      VITE_ALLOW_DEMO_IN_PRODUCTION: "true",
    });
    expect(runtimeConfig.demoMode).toBe(true);
    expect(demoModeRefusedInProduction).toBe(false);
  });

  it("stays off in production when nothing is set", async () => {
    const { runtimeConfig } = await loadConfig({ PROD: true, DEV: false });
    expect(runtimeConfig.demoMode).toBe(false);
  });

  it("still works normally in a development build", async () => {
    const { runtimeConfig } = await loadConfig({
      PROD: false,
      DEV: true,
      VITE_DEMO_MODE: "true",
    });
    expect(runtimeConfig.demoMode).toBe(true);
  });

  it("can still be turned off explicitly in development", async () => {
    const { runtimeConfig } = await loadConfig({
      PROD: false,
      DEV: true,
      VITE_DEMO_MODE: "false",
    });
    expect(runtimeConfig.demoMode).toBe(false);
  });
});
