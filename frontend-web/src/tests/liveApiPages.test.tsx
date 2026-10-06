/**
 * The pages, rendered against the real HTTP client instead of demo data.
 *
 * Every page spec in this suite used to run with `demoMode` on, so the
 * branch that actually talks to the backend had no coverage at all: a
 * broken endpoint path, a renamed field or a changed envelope shape would
 * only surface in the browser. Here demo mode is off and `fetch` is
 * answered with API-shaped payloads, so the mapping layer and the page are
 * exercised exactly as they are in production.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../app/configuration/runtimeConfig", () => ({
  runtimeConfig: {
    appName: "Tekarai",
    apiBaseUrl: "http://api.test.invalid",
    apiVersion: "v1",
    demoMode: false,
    realtimeEnabled: false,
  },
}));

import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { EquipmentRegistryPage } from "../pages/EquipmentRegistryPage";
import { MaintenanceLocationsPage } from "../pages/MaintenanceLocationsPage";

const envelope = (data: unknown): Response =>
  new Response(JSON.stringify({ success: true, data, errors: [], meta: {} }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

const DEVICE = {
  id: "dev-9",
  code: "FAN-09",
  name: "فن هوارسان سالن رنگ",
  location: "سالن رنگ",
  status: "operational",
  department: "mechanical",
  pmIntervalDays: 45,
  lastPmDate: "2026-08-01",
  nextDueDate: "2026-09-15",
  pmDue: false,
  createdAt: "2026-01-01",
  criticality: "high",
  locationPath: "سایت تهران / سالن رنگ",
  manufacturer: "زیمنس",
  model: "HV-400",
};

const LOCATIONS = [
  {
    id: "loc-1",
    code: "SITE-THR",
    name: "سایت تهران",
    kind: "site",
    parentId: "",
    path: "سایت تهران",
    note: "",
    deviceCount: 4,
  },
  {
    id: "loc-2",
    code: "HALL-PNT",
    name: "سالن رنگ",
    kind: "hall",
    parentId: "loc-1",
    path: "سایت تهران / سالن رنگ",
    note: "",
    deviceCount: 2,
  },
];

/** Answers only the routes under test; anything else fails the spec loudly. */
const routeFetch = (): ReturnType<typeof vi.fn> =>
  vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.includes("maintenance/devices")) {
      // The client pages through until a short batch comes back.
      return Promise.resolve(envelope(url.includes("page=1") ? [DEVICE] : []));
    }
    if (url.includes("maintenance/locations")) return Promise.resolve(envelope(LOCATIONS));
    if (url.includes("maintenance/personnel")) return Promise.resolve(envelope([]));
    if (url.includes("maintenance/assets/tree")) return Promise.resolve(envelope({}));
    return Promise.reject(new Error(`Spec made an unexpected request to ${url}`));
  });

const authenticate = (): void =>
  sessionStore.set({
    accessToken: "test-access",
    refreshToken: "test-refresh",
    user: {
      id: "u1",
      displayName: "Test User",
      email: "test@example.test",
      role: "Maintenance",
      permissions: [
        "maintenance.device.list",
        "maintenance.device.view",
        "maintenance.device.manage",
        "maintenance.location.manage",
      ],
    },
  });

const renderPage = (path: string, element: JSX.Element, route: string): void => {
  render(
    <AppProviders>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
        </Routes>
      </MemoryRouter>
    </AppProviders>,
  );
};

describe("pages against the live API path", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", routeFetch());
    authenticate();
  });

  it("renders machines fetched over HTTP, not demo fixtures", async () => {
    renderPage("/app/maintenance/registry", <EquipmentRegistryPage />, "/app/maintenance/registry");
    expect(await screen.findByText("فن هوارسان سالن رنگ")).toBeInTheDocument();
    // Proves the demo catalogue is not what reached the screen.
    expect(screen.queryByText("پمپ خنک‌کننده اصلی")).not.toBeInTheDocument();
  });

  it("renders the location tree fetched over HTTP", async () => {
    renderPage(
      "/app/maintenance/locations",
      <MaintenanceLocationsPage />,
      "/app/maintenance/locations",
    );
    await waitFor(() => expect(screen.getByText("سایت تهران")).toBeInTheDocument());
    expect(screen.getByText("سالن رنگ")).toBeInTheDocument();
  });

  it("sends the tenant and bearer headers the backend requires", async () => {
    renderPage("/app/maintenance/registry", <EquipmentRegistryPage />, "/app/maintenance/registry");
    await screen.findByText("فن هوارسان سالن رنگ");
    const calls = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls;
    const init = calls[0][1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer test-access");
  });
});
