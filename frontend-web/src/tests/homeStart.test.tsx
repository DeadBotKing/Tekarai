/**
 * The simple home page (v0.17.0) — the first screen a newcomer sees.
 *
 * A first-time user should never have to wonder where to start. These
 * tests pin the promises the home page makes: a greeting that knows who
 * you are, four big cards for the everyday tasks, a three-step guide
 * that leads to the first real action, a today strip fed by real data,
 * and a quiet way down to the full analytics dashboard.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { HomeStartPage } from "../pages/HomeStartPage";
import { demoWorkOrders } from "../features/maintenance/maintenanceDemoData";

const authenticate = (): void =>
  sessionStore.set({
    accessToken: "test-access",
    refreshToken: "test-refresh",
    user: {
      id: "u1",
      displayName: "مریم کریمی",
      email: "test@example.test",
      role: "Maintenance",
      permissions: [
        "dashboard.view",
        "maintenance.workorder.list",
        "maintenance.workorder.create",
        "maintenance.device.list",
      ],
    },
  });

const renderHome = (): void => {
  render(
    <AppProviders>
      <MemoryRouter initialEntries={["/app/dashboard"]}>
        <Routes>
          <Route path="/app/dashboard" element={<HomeStartPage />} />
          <Route
            path="/app/maintenance/work-orders"
            element={<div data-testid="page-orders">صفحه درخواست‌ها</div>}
          />
        </Routes>
      </MemoryRouter>
    </AppProviders>,
  );
};

describe("the simple home page", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ success: true, data: [], meta: {}, errors: [] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    authenticate();
  });

  it("greets the signed-in user by their first name and names today", () => {
    renderHome();
    expect(screen.getByText(/سلام مریم/)).toBeInTheDocument();
    // The date line is spoken in words, not a raw timestamp.
    expect(screen.getByText(/امروز .* است\./u)).toBeInTheDocument();
  });

  it("offers the four everyday tasks as cards", () => {
    renderHome();
    // The card's accessible name folds in its caption, so assert on the
    // card titles themselves — four big targets, in the brief's order.
    const cards = document.querySelectorAll(".home-card");
    const titles = [...cards].map((card) => card.querySelector("strong")?.textContent ?? "");
    expect(titles).toEqual([
      "ثبت درخواست تعمیر",
      "کارهای من",
      "تقویم نگهداری",
      "تجهیزات",
    ]);
  });

  it("leads a first-time user through three steps, the first one actionable", async () => {
    renderHome();
    expect(screen.getByText("شروع سریع در سه قدم")).toBeInTheDocument();
    // Step one navigates straight into the work-orders page (create form).
    await userEvent.click(screen.getByText("اولین درخواست تعمیر را ثبت کنید"));
    expect(await screen.findByTestId("page-orders")).toBeInTheDocument();
  });

  it("counts today's open work from the data, not from thin air", () => {
    renderHome();
    const open = demoWorkOrders.filter(
      (order) => order.status !== "completed" && order.status !== "cancelled",
    ).length;
    // Persian digits on screen.
    const persianOpen = String(open).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
    expect(document.querySelector(".home-today__cell strong")?.textContent).toBe(persianOpen);
    expect(screen.getByText("درخواست‌های باز")).toBeInTheDocument();
    expect(screen.getByText("کارهای باز من")).toBeInTheDocument();
    expect(screen.getByText("تجهیزات ثبت‌شده")).toBeInTheDocument();
  });

  it("surfaces the highest-priority open requests in the calm work queue", () => {
    renderHome();
    const queue = document.querySelector(".home-queue__list");
    expect(queue).toBeInTheDocument();
    expect(queue?.textContent).toContain("تعویض باتری ژنراتور");
    expect(queue?.textContent).toContain("صدای غیرعادی از یاتاقان پمپ");
  });

  it("the work-orders page opens its create form when home sends ?create=1", async () => {
    const { WorkOrdersPage } = await import("../pages/WorkOrdersPage");
    render(
      <AppProviders>
        <MemoryRouter initialEntries={["/app/maintenance/work-orders?create=1"]}>
          <Routes>
            <Route path="/app/maintenance/work-orders" element={<WorkOrdersPage />} />
          </Routes>
        </MemoryRouter>
      </AppProviders>,
    );
    // The create modal announces itself with its documented title.
    expect(await screen.findByText("ثبت درخواست کار جدید")).toBeInTheDocument();
  });

  it("keeps a quiet door to the full analytics dashboard", () => {
    renderHome();
    expect(
      screen.getByRole("button", { name: /داشبورد کامل پروژه‌ها و فعالیت‌ها/ }),
    ).toBeInTheDocument();
  });
});
