import { defineConfig, devices } from "@playwright/test";

const e2ePort = Number(process.env.PLAYWRIGHT_PORT ?? 4174);
const e2eBaseUrl = `http://127.0.0.1:${e2ePort}`;

// Use Google Chrome / Edge already installed on the machine instead of
// downloading Playwright's bundled Chromium (some networks block the CDN).
// Set PLAYWRIGHT_CHANNEL=msedge to use Edge, or leave empty to use the
// bundled browser once it has been installed.
const browserChannel = process.env.PLAYWRIGHT_CHANNEL ?? "chrome";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL: e2eBaseUrl,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  webServer: {
    // Cross-platform: pass VITE_DEMO_MODE via `env` instead of inline shell
    // syntax (inline `VAR=value cmd` does not work on Windows shells).
    command: `npm run build && npm run preview -- --host 0.0.0.0 --port ${e2ePort}`,
    env: { VITE_DEMO_MODE: "true" },
    url: e2eBaseUrl,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], channel: browserChannel },
    },
    {
      name: "mobile",
      use: { ...devices["Pixel 5"], channel: browserChannel },
    },
  ],
});
