/**
 * ثبت سرویس‌ورکر.
 *
 * Three rules, each learned the hard way:
 *
 * 1. **Never register in dev.** A service worker that caches a Vite dev
 *    bundle makes every later code change invisible, and the developer
 *    spends an afternoon debugging a file the browser refuses to re-fetch.
 * 2. **Never let registration failure break the app.** Private mode, an
 *    insecure origin, or an enterprise policy can all refuse it; offline
 *    support is an enhancement, not a prerequisite.
 * 3. **Take over immediately on update.** A technician who force-quits the
 *    app after an update must not get the old bundle; `skipWaiting` plus a
 *    one-shot reload keeps them on the version the office thinks they have.
 * 4. **Name the caches after the build.** The `?v=` carries this build's id
 *    into the worker, which uses it for its cache names. A new release
 *    therefore installs a new worker and drops the previous caches by
 *    itself — no constant to remember to bump.
 */

const buildId = typeof __APP_BUILD_ID__ === "string" ? __APP_BUILD_ID__ : "dev";
const SERVICE_WORKER_URL = `/serviceWorker.js?v=${encodeURIComponent(buildId)}`;

export interface RegisterOptions {
  /** Defaults to `import.meta.env.PROD`. */
  enabled?: boolean;
  onUpdate?: () => void;
}

export function registerServiceWorker(options: RegisterOptions = {}): void {
  const enabled = options.enabled ?? import.meta.env.PROD;
  if (!enabled) return;
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register(SERVICE_WORKER_URL, { scope: "/" })
      .then((registration) => {
        registration.addEventListener("updatefound", () => {
          const installing = registration.installing;
          if (!installing) return;
          installing.addEventListener("statechange", () => {
            if (installing.state === "installed" && navigator.serviceWorker.controller) {
              options.onUpdate?.();
              installing.postMessage({ type: "skipWaiting" });
            }
          });
        });
      })
      .catch(() => {
        /* offline support is optional — never block startup */
      });

    let reloading = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (reloading) return;
      reloading = true;
      window.location.reload();
    });
  });
}

/**
 * Drop cached API responses. Called on logout and tenant switch so a shared
 * phone never shows the previous user's work orders.
 */
export function clearCachedApiResponses(): void {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  navigator.serviceWorker.controller?.postMessage({ type: "clearApiCache" });
}
