/* eslint-disable no-restricted-globals */
/**
 * سرویس‌ورکر تکارای — the app shell, cached.
 *
 * Hand-written rather than generated, because the generated kind
 * (Workbox/vite-plugin-pwa) precaches a manifest produced at build time and
 * this project builds with plain Vite. The strategies here are chosen per
 * request class, which matters more than precision precaching:
 *
 * | request                      | strategy                                   |
 * |------------------------------|--------------------------------------------|
 * | navigation (`/app/...`)      | network-first → cached shell → offline page |
 * | hashed assets (`/assets/*`)  | cache-first (immutable by content hash)     |
 * | icons, fonts, manifest       | stale-while-revalidate                      |
 * | allow-listed maintenance GET | network-first → cached copy (offline read)  |
 * | every mutation (POST/…)      | never cached, never queued here             |
 *
 * **Mutations are deliberately not handled by the service worker.** Background
 * Sync is unavailable on iOS and gives no per-item verdict; our queue lives in
 * IndexedDB and replays through `/maintenance/sync`, which returns
 * applied/duplicate/rejected/failed per operation. Two queues would fight.
 *
 * Authenticated API responses are cached under a *separate* cache that the app
 * clears on logout and on tenant switch (`postMessage({type:"clearApiCache"})`),
 * so a shared phone cannot leak one user's work orders to the next.
 */

const VERSION = "v1";
const SHELL_CACHE = `tekarai-shell-${VERSION}`;
const ASSET_CACHE = `tekarai-assets-${VERSION}`;
const API_CACHE = `tekarai-api-${VERSION}`;
const OFFLINE_URL = "/offline.html";

const SHELL_URLS = [
  "/",
  "/index.html",
  OFFLINE_URL,
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

/** GET endpoints a technician must be able to read with no signal. */
const CACHEABLE_API = [
  /\/api\/v\d+\/maintenance\/work-orders(\/|\?|$)/,
  /\/api\/v\d+\/maintenance\/devices(\/|\?|$)/,
  /\/api\/v\d+\/maintenance\/spare-parts(\/|\?|$)/,
  /\/api\/v\d+\/maintenance\/locations(\/|\?|$)/,
  /\/api\/v\d+\/maintenance\/personnel(\/|\?|$)/,
  /\/api\/v\d+\/me$/,
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_URLS))
      // A missing optional file must not block activation of the whole worker.
      .catch(() => undefined)
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name.startsWith("tekarai-") && !name.endsWith(VERSION))
            .map((name) => caches.delete(name)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type === "clearApiCache") {
    event.waitUntil(caches.delete(API_CACHE));
  }
  if (data.type === "skipWaiting") {
    self.skipWaiting();
  }
});

const isApiCacheable = (url) =>
  CACHEABLE_API.some((pattern) => pattern.test(url.pathname + url.search));

async function networkFirst(request, cacheName, fallback) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response && response.status === 200 && response.type !== "opaque") {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (fallback) {
      const shell = await caches.open(SHELL_CACHE);
      const offline = await shell.match(fallback);
      if (offline) return offline;
    }
    throw error;
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response && response.status === 200) cache.put(request, response.clone());
  return response;
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then((response) => {
      if (response && response.status === 200) cache.put(request, response.clone());
      return response;
    })
    .catch(() => cached);
  return cached || network;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Full page loads: keep the SPA reachable offline.
  if (request.mode === "navigate") {
    event.respondWith(
      networkFirst(request, SHELL_CACHE, OFFLINE_URL).catch(async () => {
        const cache = await caches.open(SHELL_CACHE);
        return (
          (await cache.match("/index.html")) ||
          (await cache.match(OFFLINE_URL)) ||
          Response.error()
        );
      }),
    );
    return;
  }

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(cacheFirst(request, ASSET_CACHE));
    return;
  }

  if (
    url.pathname.startsWith("/icons/") ||
    url.pathname.startsWith("/fonts/") ||
    url.pathname === "/manifest.webmanifest"
  ) {
    event.respondWith(staleWhileRevalidate(request, ASSET_CACHE));
    return;
  }

  if (url.pathname.includes("/api/") && isApiCacheable(url)) {
    event.respondWith(networkFirst(request, API_CACHE));
  }
});
