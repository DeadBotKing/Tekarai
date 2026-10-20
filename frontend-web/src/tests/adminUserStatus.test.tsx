/**
 * The users table's suspend / reactivate lever (v0.17.1).
 *
 * The endpoint has existed in the domain since Phase 07 — the 8-state
 * machine, the §19 policy — but nothing HTTP ever reached it and no
 * button ever offered it. These tests pin the page side of the contract:
 * an admin sees the lever on other people's rows, never on their own,
 * and a click really PATCHes `users/{id}/status` and flips the badge.
 * Rendered against the real HTTP client (demo mode off), like the
 * liveApiPages suite.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
import { AdministrationPage } from "../pages/AdministrationPage";

const envelope = (data: unknown): Response =>
  new Response(JSON.stringify({ success: true, data, errors: [], meta: {} }), {
    status: 200,
    headers: { "content-Type": "application/json" },
  });

const ME = { id: "u-admin", displayName: "مدیر آزمون" };
const COLLEAGUE = { id: "u-2", displayName: "همکار آزمون" };

const userRow = (base: { id: string; displayName: string }, status: string) => ({
  id: base.id,
  username: base.id,
  email: `${base.id}@tekarai.local`,
  displayName: base.displayName,
  status,
  createdAt: "2026-10-01T10:00:00Z",
});

const authenticate = (permissions: string[]): void =>
  sessionStore.set({
    accessToken: "test-access",
    refreshToken: "test-refresh",
    user: {
      id: ME.id,
      displayName: ME.displayName,
      email: "admin@tekarai.local",
      role: "Admin",
      permissions,
    },
  });

const renderUsers = (): void => {
  render(
    <AppProviders>
      <MemoryRouter initialEntries={["/app/administration/users"]}>
        <Routes>
          <Route path="/app/administration/:section" element={<AdministrationPage />} />
        </Routes>
      </MemoryRouter>
    </AppProviders>,
  );
};

describe("the users table suspend lever", () => {
  let calls: Array<{ url: string; method: string; body: string }>;

  beforeEach(() => {
    vi.unstubAllGlobals();
    calls = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        calls.push({ url, method, body: String(init?.body ?? "") });
        if (url.includes("/users/u-2/status")) {
          return envelope(userRow(COLLEAGUE, "suspended"));
        }
        if (url.includes("/users")) {
          return envelope([userRow(ME, "active"), userRow(COLLEAGUE, "active")]);
        }
        return envelope([]);
      }),
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);
    authenticate([
      "user.list",
      "user.create",
      "user.suspend",
      "role.list",
      "audit.view",
      "dashboard.view",
    ]);
  });

  it("shows the suspend lever on other people's rows but never on one's own", async () => {
    renderUsers();
    await waitFor(() => expect(screen.getByText("همکار آزمون")).toBeInTheDocument());
    // The colleague carries the lever…
    expect(screen.getByRole("button", { name: "تعلیق" })).toBeInTheDocument();
    // …and the admin's own row shows a dash instead — the backend would
    // refuse a self-suspension anyway; the row simply never offers it.
    const ownRow = screen.getByText("مدیر آزمون").closest("tr");
    expect(ownRow).not.toBeNull();
    expect(ownRow?.querySelector("button")).toBeNull();
  });

  it("a confirmed click PATCHes the status endpoint and flips the badge", async () => {
    renderUsers();
    await waitFor(() => expect(screen.getByText("همکار آزمون")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "تعلیق" }));

    await waitFor(() => {
      const patch = calls.find((call) => call.method === "PATCH");
      expect(patch).toBeDefined();
      expect(patch?.url).toContain("/users/u-2/status");
      expect(patch?.body).toContain('"suspended"');
    });
    // The confirm dialog spoke the colleague's name before acting.
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("همکار آزمون"));
    // The badge reflects the suspended state, not "archived" as before.
    await waitFor(() => expect(screen.getByText("تعلیق‌شده")).toBeInTheDocument());
  });

  it("hides the lever entirely without the user.suspend permission", async () => {
    authenticate(["user.list", "user.create", "role.list", "audit.view", "dashboard.view"]);
    renderUsers();
    await waitFor(() => expect(screen.getByText("همکار آزمون")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "تعلیق" })).not.toBeInTheDocument();
  });
});
