import { expect, test, type Page } from "@playwright/test";

const appRoutes = [
  "/app/dashboard",
  "/app/projects",
  "/app/tasks",
  "/app/documents",
  "/app/organization/employees",
  "/app/organization/departments",
  "/app/devices",
  "/app/reports",
  "/app/intelligence",
  "/app/administration/users",
  "/app/administration/roles",
  "/app/administration/audit",
  "/app/notifications",
  "/app/settings",
] as const;

async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/app\/dashboard/);
}

test.describe("Tekarai GUI route and workflow coverage", () => {
  test("renders every protected application route", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === "mobile", "The desktop route matrix validates deep links; mobile shell coverage is covered by the mobile smoke journey.");
    await login(page);
    for (const route of appRoutes) {
      await page.goto(route);
      await expect(page).toHaveURL(new RegExp(`${route.replaceAll("/", "\\/")}$`));
      await expect(page.locator("main")).toBeVisible();
      await expect(page.locator(".page")).toBeVisible();
      await expect(page.locator("main").getByRole("heading").first()).toBeVisible();
    }
  });

  test("exercises dashboard, project, task, upload and settings controls", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === "mobile", "The workflow checks use the full desktop action surface; mobile layout is covered by the smoke journey.");
    await login(page);

    await page.getByRole("button", { name: /customize/i }).click();
    await expect(page.getByRole("button", { name: /remove widget/i }).first()).toBeVisible();
    await page.getByRole("button", { name: /remove widget/i }).first().click();
    await page.getByRole("button", { name: /done customizing/i }).first().click();

    await page.goto("/app/projects");
    await page.getByRole("button", { name: /new project/i }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByLabel(/^project name/i).fill("E2E delivery project");
    await page.getByRole("dialog").getByRole("button", { name: /save/i }).click();
    await expect(page.getByText("E2E delivery project")).toBeVisible();

    await page.goto("/app/tasks");
    await page.getByRole("button", { name: /new task/i }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByLabel(/task name/i).fill("E2E task");
    await page.getByRole("dialog").getByRole("button", { name: /create task/i }).click();
    await expect(page.getByText("E2E task")).toBeVisible();

    await page.goto("/app/documents");
    await page.getByRole("button", { name: /upload document/i }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.locator("input[type=file]").setInputFiles({ name: "e2e-note.txt", mimeType: "text/plain", buffer: Buffer.from("Tekarai") });
    await expect(page.getByText("e2e-note.txt")).toBeVisible();
    await page.getByRole("dialog").getByRole("button", { name: /^close$/i }).last().click();

    await page.goto("/app/settings");
    await page.getByRole("button", { name: /^dark$/i }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.locator("select[aria-label='Change language']").selectOption("fa");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator("html")).toHaveAttribute("lang", "fa");
  });
});
