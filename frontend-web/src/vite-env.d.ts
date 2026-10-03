/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_NAME?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_API_VERSION?: string;
  readonly VITE_DEMO_MODE?: string;
  readonly VITE_REALTIME_ENABLED?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Injected by vite.config.ts; names the service worker's caches. */
declare const __APP_BUILD_ID__: string;
