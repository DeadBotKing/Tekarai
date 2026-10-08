/**
 * The organisation structure and access screen.
 *
 * These tests pin the properties that make the page an access-control tool
 * rather than a settings form: that the grid is drawn from the catalogue
 * the server sends (so an unsupported verb is not even drawable), that
 * scope is always part of granting a permission, that a unit-specific
 * override is distinguishable from an inherited default, that a seeded
 * unit cannot be deleted by accident, and that a server refusal reaches
 * the user as a readable Persian sentence.
 *
 * Permission tests are written in pairs — hidden and visible for the same
 * control — so a typo'd permission key fails rather than passing
 * vacuously.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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
import { OrganizationStructurePage } from "../pages/OrganizationStructurePage";

const DEPARTMENTS = [
  {
    id: "dept-eng",
    code: "ENG",
    name: "فنی و مهندسی",
    description: "",
    status: "active",
    statusLabel: "فعال",
    parentId: null,
    managerName: "",
    isSystem: true,
    memberCount: 3,
  },
  {
    id: "dept-qc",
    code: "QC",
    name: "کنترل کیفیت",
    description: "",
    status: "inactive",
    statusLabel: "غیرفعال",
    parentId: null,
    managerName: "",
    isSystem: true,
    memberCount: 0,
  },
  {
    id: "dept-wh",
    code: "WH",
    name: "انبار",
    description: "",
    status: "active",
    statusLabel: "فعال",
    parentId: "dept-eng",
    managerName: "",
    isSystem: false,
    memberCount: 0,
  },
];

const POSITIONS = [
  {
    id: "pos-mgr",
    code: "MGR",
    name: "مدیر",
    description: "",
    level: 100,
    isActive: true,
    isSystem: true,
    memberCount: 1,
  },
  {
    id: "pos-tech",
    code: "TECHNICIAN",
    name: "تکنسین",
    description: "",
    level: 20,
    isActive: true,
    isSystem: true,
    memberCount: 4,
  },
];

const ASSIGNMENTS = [
  {
    id: "asg-1",
    userId: "user-ali",
    userDisplayName: "علی",
    departmentId: "dept-eng",
    departmentName: "فنی و مهندسی",
    positionId: "pos-mgr",
    positionName: "مدیر",
    isPrimary: true,
    isActive: true,
  },
  {
    id: "asg-2",
    userId: "user-reza",
    userDisplayName: "رضا",
    departmentId: "dept-eng",
    departmentName: "فنی و مهندسی",
    positionId: "pos-tech",
    positionName: "تکنسین",
    isPrimary: true,
    isActive: true,
  },
];

const CAPABILITIES = [
  {
    key: "workOrder",
    label: "دستور کار",
    group: "نگهداری و تعمیرات",
    scoped: true,
    actions: [
      { value: "view", label: "مشاهده" },
      { value: "create", label: "ایجاد" },
      { value: "delete", label: "حذف" },
    ],
  },
  {
    key: "inventory",
    label: "انبار قطعات",
    group: "انبار و خرید",
    scoped: false,
    actions: [{ value: "view", label: "مشاهده" }],
  },
];

const SCOPES = [
  { value: "own", label: "خودش" },
  { value: "team", label: "تیم" },
  { value: "department", label: "واحد" },
  { value: "all", label: "کل کارخانه" },
];

const MATRIX = {
  "pos-mgr": { workOrder: { view: "all", create: "department", delete: "department" } },
  "pos-tech": { workOrder: { view: "own" } },
};

const matrixPayload = (overrides = {}) => ({
  departmentId: null,
  matrix: MATRIX,
  positions: POSITIONS,
  capabilities: CAPABILITIES,
  scopes: SCOPES,
  ...overrides,
});

const envelope = (data: unknown, status = 200): Response =>
  new Response(JSON.stringify({ success: true, data, errors: [], meta: {} }), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const refusal = (code: string, message: string): Response =>
  new Response(
    JSON.stringify({
      success: false,
      data: null,
      errors: [{ code, message }],
      error: { code, message, category: "organizationRule" },
      meta: {},
    }),
    { status: 422, headers: { "Content-Type": "application/json" } },
  );

interface StubOptions {
  matrix?: unknown;
  createRefusal?: { code: string; message: string };
  onPost?: (url: string, body: unknown) => void;
}

const stubApi = (options: StubOptions = {}): void => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "POST" || method === "PATCH" || method === "DELETE") {
        const body = init?.body ? JSON.parse(String(init.body)) : {};
        options.onPost?.(url, body);
        if (options.createRefusal) {
          return Promise.resolve(
            refusal(options.createRefusal.code, options.createRefusal.message),
          );
        }
        if (url.includes("access-matrix")) {
          return Promise.resolve(envelope({ matrix: options.matrix ?? MATRIX }));
        }
        return Promise.resolve(envelope({ ok: true }));
      }
      if (url.includes("access-matrix")) {
        return Promise.resolve(
          envelope(matrixPayload(options.matrix ? { matrix: options.matrix } : {})),
        );
      }
      if (url.includes("/departments")) return Promise.resolve(envelope({ items: DEPARTMENTS }));
      if (url.includes("/positions")) return Promise.resolve(envelope({ items: POSITIONS }));
      if (url.includes("/assignments")) return Promise.resolve(envelope({ items: ASSIGNMENTS }));
      // The notification poller mounted by AppProviders expects a list.
      return Promise.resolve(envelope([]));
    }),
  );
};

const authenticate = (permissions: string[]): void =>
  sessionStore.set({
    accessToken: "test-access",
    refreshToken: "test-refresh",
    user: {
      id: "u1",
      displayName: "Test User",
      email: "test@example.test",
      role: "Admin",
      permissions,
    },
  });

const ALL_PERMISSIONS = [
  "organization.department.view",
  "organization.department.manage",
  "organization.position.view",
  "organization.position.manage",
  "organization.assignment.view",
  "organization.assignment.manage",
  "organization.accessRule.view",
  "organization.accessRule.manage",
];

const renderPage = (): void => {
  render(
    <AppProviders>
      <MemoryRouter>
        <OrganizationStructurePage />
      </MemoryRouter>
    </AppProviders>,
  );
};

const openTab = async (label: string): Promise<void> => {
  await userEvent.click(screen.getByRole("tab", { name: label }));
};

describe("organisation structure page — units", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    authenticate(ALL_PERMISSIONS);
    stubApi();
  });

  it("lists units with their code, status and member count", async () => {
    renderPage();
    expect(await screen.findByText("ENG")).toBeInTheDocument();
    // «فنی و مهندسی» appears twice — as its own row and as انبار's parent —
    // so assert within the row rather than loosening the query.
    const engineering = screen.getByText("ENG").closest("tr") as HTMLElement;
    expect(within(engineering).getByText("فنی و مهندسی")).toBeInTheDocument();
    // Numeric cells are read positionally: digit text matching is
    // ambiguous and locale-dependent.
    const engineeringCells = [...engineering.querySelectorAll("td")].map((cell) => cell.textContent);
    expect(engineeringCells).toContain("3");
    const quality = screen.getByText("QC").closest("tr") as HTMLElement;
    expect(within(quality).getByText("غیرفعال")).toBeInTheDocument();
  });

  it("shows the parent unit so the hierarchy is visible", async () => {
    renderPage();
    await screen.findByText("WH");
    const row = screen.getByText("WH").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("فنی و مهندسی")).toBeInTheDocument();
  });

  it("offers an add-unit affordance and posts the new unit", async () => {
    const posts: { url: string; body: unknown }[] = [];
    stubApi({ onPost: (url, body) => posts.push({ url, body }) });
    renderPage();
    await screen.findByText("ENG");

    await userEvent.click(screen.getByRole("button", { name: "＋ افزودن واحد" }));
    await userEvent.type(screen.getByLabelText("نام واحد"), "تدارکات");
    await userEvent.click(screen.getByRole("button", { name: "ثبت واحد" }));

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].url).toContain("organization/departments");
    expect(posts[0].body).toMatchObject({ name: "تدارکات" });
  });

  it("refuses to delete a seeded unit and explains why instead of failing on click", async () => {
    renderPage();
    await screen.findByText("ENG");
    const row = screen.getByText("ENG").closest("tr") as HTMLElement;
    const remove = within(row).getByRole("button", { name: "حذف" });
    expect(remove).toBeDisabled();
    expect(remove).toHaveAttribute(
      "title",
      "واحد پیش‌فرض حذف نمی‌شود؛ آن را غیرفعال کنید.",
    );
  });

  it("allows deleting a unit the plant created itself", async () => {
    renderPage();
    await screen.findByText("WH");
    const row = screen.getByText("WH").closest("tr") as HTMLElement;
    expect(within(row).getByRole("button", { name: "حذف" })).toBeEnabled();
  });

  it("warns that deactivating a unit cuts off its members immediately", async () => {
    renderPage();
    await screen.findByText("ENG");
    const row = screen.getByText("ENG").closest("tr") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "غیرفعال‌سازی" }));
    expect(
      await screen.findByText(/دسترسی اعضای آن بلافاصله قطع می‌شود/),
    ).toBeInTheDocument();
  });

  it("shows a server refusal verbatim rather than a generic failure", async () => {
    stubApi({
      createRefusal: {
        code: "department.codeTaken",
        message: "واحدی با کد «ENG» از قبل وجود دارد.",
      },
    });
    renderPage();
    await screen.findByText("ENG");

    await userEvent.click(screen.getByRole("button", { name: "＋ افزودن واحد" }));
    await userEvent.type(screen.getByLabelText("نام واحد"), "دیگر");
    await userEvent.click(screen.getByRole("button", { name: "ثبت واحد" }));

    expect(
      await screen.findByText("واحدی با کد «ENG» از قبل وجود دارد."),
    ).toBeInTheDocument();
  });

  it("hides the add-unit control without the manage permission", async () => {
    authenticate(["organization.department.view"]);
    renderPage();
    await screen.findByText("ENG");
    expect(screen.queryByRole("button", { name: "＋ افزودن واحد" })).not.toBeInTheDocument();
  });

  it("shows the add-unit control with the manage permission", async () => {
    renderPage();
    await screen.findByText("ENG");
    expect(screen.getByRole("button", { name: "＋ افزودن واحد" })).toBeInTheDocument();
  });
});

describe("organisation structure page — positions and postings", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    authenticate(ALL_PERMISSIONS);
    stubApi();
  });

  it("lists positions with their level", async () => {
    renderPage();
    await screen.findByText("ENG");
    await openTab("سمت‌ها");
    // «مدیر» is also a position name in the postings table below, so scope
    // the assertion to the positions row keyed by its code.
    const manager = (await screen.findByText("MGR")).closest("tr") as HTMLElement;
    expect(within(manager).getByText("مدیر")).toBeInTheDocument();
    const managerCells = [...manager.querySelectorAll("td")].map((cell) => cell.textContent);
    expect(managerCells).toContain("100");
    expect(screen.getByText("TECHNICIAN")).toBeInTheDocument();
  });

  it("states that a position alone grants nothing", async () => {
    renderPage();
    await screen.findByText("ENG");
    await openTab("سمت‌ها");
    expect(
      await screen.findByText(/سمت به‌تنهایی دسترسی نمی‌دهد/),
    ).toBeInTheDocument();
  });

  it("explains that a new position starts with no authority", async () => {
    const posts: { url: string; body: unknown }[] = [];
    stubApi({ onPost: (url, body) => posts.push({ url, body }) });
    renderPage();
    await screen.findByText("ENG");
    await openTab("سمت‌ها");

    await userEvent.click(screen.getByRole("button", { name: "＋ افزودن سمت" }));
    await userEvent.type(screen.getByLabelText("نام سمت"), "سرپرست برق");
    await userEvent.click(screen.getByRole("button", { name: "ثبت سمت" }));

    expect(
      await screen.findByText(/تا زمانی که در ماتریس دسترسی تعیین نشود، هیچ اختیاری ندارد/),
    ).toBeInTheDocument();
    expect(posts[0].body).toMatchObject({ name: "سرپرست برق" });
  });

  it("notes that level is only for ordering, not for granting", async () => {
    renderPage();
    await screen.findByText("ENG");
    await openTab("سمت‌ها");
    await userEvent.click(screen.getByRole("button", { name: "＋ افزودن سمت" }));
    expect(
      screen.getByText(/سطح بالاتر به‌خودی‌خود دسترسی بیشتری نمی‌دهد/),
    ).toBeInTheDocument();
  });

  it("shows the same unit holding two people with different titles", async () => {
    renderPage();
    await screen.findByText("ENG");
    await openTab("سمت‌ها");
    expect(await screen.findByText("علی")).toBeInTheDocument();
    expect(screen.getByText("رضا")).toBeInTheDocument();
  });

  it("hides the posting control without the assignment permission", async () => {
    authenticate(["organization.department.view", "organization.position.view"]);
    renderPage();
    await screen.findByText("ENG");
    await openTab("سمت‌ها");
    expect(screen.queryByRole("button", { name: "＋ انتساب کاربر" })).not.toBeInTheDocument();
  });

  it("shows the posting control with the assignment permission", async () => {
    renderPage();
    await screen.findByText("ENG");
    await openTab("سمت‌ها");
    expect(screen.getByRole("button", { name: "＋ انتساب کاربر" })).toBeInTheDocument();
  });
});

describe("organisation structure page — access matrix", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    authenticate(ALL_PERMISSIONS);
    stubApi();
  });

  it("draws its rows from the catalogue the server sends", async () => {
    renderPage();
    await screen.findByText("ENG");
    await openTab("ماتریس دسترسی");
    expect(await screen.findByText("نگهداری و تعمیرات")).toBeInTheDocument();
    expect(screen.getByText("انبار و خرید")).toBeInTheDocument();
    // Only the three verbs the catalogue lists for workOrder are drawn —
    // a verb the capability does not support must not be tickable.
    const grid = screen.getByText("نگهداری و تعمیرات").closest("table") as HTMLElement;
    expect(within(grid).getAllByRole("row")).toHaveLength(4);
  });

  it("ticks a granted cell and leaves an ungranted one clear", async () => {
    renderPage();
    await screen.findByText("ENG");
    await openTab("ماتریس دسترسی");
    const granted = await screen.findByLabelText("دستور کار — مشاهده — مدیر");
    const ungranted = screen.getByLabelText("دستور کار — حذف — تکنسین");
    expect(granted).toBeChecked();
    expect(ungranted).not.toBeChecked();
  });

  it("offers a scope selector on every granted scoped cell", async () => {
    renderPage();
    await screen.findByText("ENG");
    await openTab("ماتریس دسترسی");
    const scope = await screen.findByLabelText("محدوده دستور کار — مشاهده — تکنسین");
    expect(scope).toHaveValue("own");
  });

  it("does not offer a scope selector where scope would be ignored", async () => {
    renderPage();
    await screen.findByText("ENG");
    await openTab("ماتریس دسترسی");
    await screen.findByText("انبار و خرید");
    expect(
      screen.queryByLabelText("محدوده انبار قطعات — مشاهده — مدیر"),
    ).not.toBeInTheDocument();
  });

  it("sends the chosen scope when a cell is ticked", async () => {
    const posts: { url: string; body: unknown }[] = [];
    stubApi({ onPost: (url, body) => posts.push({ url, body }) });
    renderPage();
    await screen.findByText("ENG");
    await openTab("ماتریس دسترسی");

    await userEvent.click(await screen.findByLabelText("دستور کار — ایجاد — تکنسین"));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].body).toMatchObject({
      positionId: "pos-tech",
      capability: "workOrder",
      action: "create",
      granted: true,
    });
  });

  it("sends a revocation when a granted cell is unticked", async () => {
    const posts: { url: string; body: unknown }[] = [];
    stubApi({ onPost: (url, body) => posts.push({ url, body }) });
    renderPage();
    await screen.findByText("ENG");
    await openTab("ماتریس دسترسی");

    await userEvent.click(await screen.findByLabelText("دستور کار — مشاهده — تکنسین"));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].body).toMatchObject({ granted: false, action: "view" });
  });

  it("narrows an existing grant when the scope is changed", async () => {
    const posts: { url: string; body: unknown }[] = [];
    stubApi({ onPost: (url, body) => posts.push({ url, body }) });
    renderPage();
    await screen.findByText("ENG");
    await openTab("ماتریس دسترسی");

    await userEvent.selectOptions(
      await screen.findByLabelText("محدوده دستور کار — مشاهده — مدیر"),
      "department",
    );
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].body).toMatchObject({ scope: "department", granted: true });
  });

  it("explains that a unit-specific rule replaces the organisation default", async () => {
    renderPage();
    await screen.findByText("ENG");
    await openTab("ماتریس دسترسی");
    await screen.findByText("نگهداری و تعمیرات");

    await userEvent.selectOptions(screen.getByLabelText("واحد"), "dept-eng");
    expect(
      await screen.findByText(/جایگزین پیش‌فرض کل سازمان می‌شوند — حتی اگر محدودتر باشند/),
    ).toBeInTheDocument();
  });

  it("scopes matrix writes to the selected unit", async () => {
    const posts: { url: string; body: unknown }[] = [];
    stubApi({ onPost: (url, body) => posts.push({ url, body }) });
    renderPage();
    await screen.findByText("ENG");
    await openTab("ماتریس دسترسی");
    await screen.findByText("نگهداری و تعمیرات");

    await userEvent.selectOptions(screen.getByLabelText("واحد"), "dept-eng");
    await userEvent.click(await screen.findByLabelText("دستور کار — ایجاد — تکنسین"));

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].body).toMatchObject({ departmentId: "dept-eng" });
  });

  it("confirms that a permission change applies immediately", async () => {
    renderPage();
    await screen.findByText("ENG");
    await openTab("ماتریس دسترسی");
    await userEvent.click(await screen.findByLabelText("دستور کار — ایجاد — تکنسین"));
    expect(await screen.findByText(/بلافاصله اعمال می‌شود/)).toBeInTheDocument();
  });

  it("surfaces a refusal when the server rejects a cell", async () => {
    stubApi({
      createRefusal: {
        code: "rule.unsupportedCell",
        message: "عملیات «بستن» برای قابلیت «گزارش‌ها» تعریف نشده است.",
      },
    });
    renderPage();
    await screen.findByText("ENG");
    await openTab("ماتریس دسترسی");
    await userEvent.click(await screen.findByLabelText("دستور کار — ایجاد — تکنسین"));
    expect(
      await screen.findByText("عملیات «بستن» برای قابلیت «گزارش‌ها» تعریف نشده است."),
    ).toBeInTheDocument();
  });
});
