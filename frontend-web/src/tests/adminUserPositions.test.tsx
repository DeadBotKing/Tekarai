import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

describe("users organizational positions", () => {
  beforeEach(() => { authenticate(["user.list", "organization.assignment.view"]); });
  afterEach(() => { vi.unstubAllGlobals(); sessionStore.clear(); });
  const mockData = (fail = false): void => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo) => {
      const url = String(input);
      if (url.includes("organization/assignments")) {
        if (fail) return new Response("{}", { status: 403 });
        return envelope({ items: [
          { id: "a1", userId: COLLEAGUE.id, positionName: "تکنسین برق", departmentName: "فنی", isPrimary: true, isActive: true },
          { id: "a2", userId: COLLEAGUE.id, positionName: "سرپرست شیفت", departmentName: "تولید", isPrimary: false, isActive: true },
          { id: "a3", userId: COLLEAGUE.id, positionName: "سمت قدیمی", departmentName: "فنی", isPrimary: false, isActive: false },
        ] });
      }
      if (url.includes("/users")) return envelope([userRow(ME, "active"), userRow(COLLEAGUE, "active")]);
      return envelope([]);
    }));
  };
  it("shows all active titles and departments, and marks unassigned users", async () => {
    mockData(); renderUsers();
    expect(await screen.findByText("تکنسین برق")).toBeInTheDocument();
    expect(screen.getByText("سرپرست شیفت")).toBeInTheDocument();
    expect(screen.queryByText("سمت قدیمی")).not.toBeInTheDocument();
    expect(screen.getByText("بدون انتساب")).toBeInTheDocument();
    expect(screen.getByText("سمت سازمانی")).toBeInTheDocument();
  });
  it("keeps users visible and distinguishes failed requests from no assignment", async () => {
    mockData(true); renderUsers();
    expect(await screen.findByRole("alert")).toHaveTextContent("دریافت سمت‌های سازمانی ناموفق بود");
    expect(await screen.findByText(COLLEAGUE.displayName)).toBeInTheDocument();
    expect(screen.queryByText("بدون انتساب")).not.toBeInTheDocument();
  });
});
