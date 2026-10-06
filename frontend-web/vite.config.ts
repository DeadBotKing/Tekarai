import { readFileSync } from "node:fs";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import {
  demoFixtureFirewall,
  fixturesAllowedFor,
} from "./vite/demoFixtureFirewall";

const { version } = JSON.parse(readFileSync("./package.json", "utf-8")) as {
  version: string;
};

/**
 * Identifies this build to the service worker, which names its caches after
 * it. Without a per-build id the shell cache is immortal: ship a fix, and
 * phones that already installed the app keep serving the old bundle until
 * someone remembers to bump a constant by hand.
 */
const buildId = `${version}-${Date.now().toString(36)}`;

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const allowFixtures = fixturesAllowedFor(mode, { ...env, ...process.env });

  if (!allowFixtures) {
    // Stated out loud: a build without fixtures is the safe default, but it
    // is also the build where a leftover demo branch renders nothing.
    console.info("[tekarai] demo fixtures excluded from this build");
  }

  return {
    plugins: [react(), demoFixtureFirewall({ allowFixtures })],
    define: {
      __APP_BUILD_ID__: JSON.stringify(buildId),
    },
    server: {
      host: "0.0.0.0",
      allowedHosts: true,
      port: 4173,
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
        },
        "/ws": {
          target: "ws://127.0.0.1:8000",
          ws: true,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: "0.0.0.0",
      allowedHosts: true,
      port: 4173,
    },
    build: {
      sourcemap: true,
      target: "es2022",
    },
  };
});
