import { expect, test } from "@playwright/test";

test.describe("Tekarai GUI smoke journeys", () => {
  test("logs in and loads the workspace dashboard", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
    await page.getByLabel(/tenant code/i).fill("platform");
    await page.getByLabel(/email or username/i).fill("platform-admin");
    await page.getByLabel(/password/i).fill("demo-password");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/app\/dashboard/);
    await expect(page.getByRole("heading", { name: /workspace overview/i })).toBeVisible();
    await expect(page.getByText(/active projects/i)).toBeVisible();
  });

  test("changes theme and language without losing tenant context", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByRole("heading", { name: /workspace overview/i })).toBeVisible();
    await page.getByRole("button", { name: /toggle theme/i }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.getByRole("button", { name: /change language/i }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", /en|fa|de/);
    await expect(page.getByRole("complementary").getByText(/nordic manufacturing group/i)).toBeVisible();
  });
});
