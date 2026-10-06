import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/tests/setup.ts",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    css: true,
    restoreMocks: true,
    clearMocks: true,
    // The unit suite must be hermetic. Without this, Vite loads the
    // developer's .env file and VITE_DEMO_MODE=false sent the page specs
    // at a real backend, so `npm test` passed or failed depending on
    // whether a server happened to be running locally. Specs that need
    // the live-API path mock this module instead (see liveApiPages.test.tsx).
    env: {
      VITE_DEMO_MODE: "true",
      VITE_API_BASE_URL: "http://api.test.invalid",
      VITE_REALTIME_ENABLED: "false",
    },
  },
});
