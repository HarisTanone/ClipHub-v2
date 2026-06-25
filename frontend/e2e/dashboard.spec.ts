import { test, expect } from "@playwright/test";

const EMAIL = "admin@autocliper.com";
const PASSWORD = "Admin@2024!Secure";

async function login(page: any) {
  await page.goto("/login");
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL("/", { timeout: 8000 });
}

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("displays stat pills", async ({ page }) => {
    await expect(page.getByText("Active", { exact: true })).toBeVisible();
    await expect(page.getByText("Done", { exact: true })).toBeVisible();
    await expect(page.getByText("Failed", { exact: true })).toBeVisible();
    await expect(page.getByText("Total", { exact: true })).toBeVisible();
  });

  test("displays jobs table", async ({ page }) => {
    await expect(page.locator("h2", { hasText: "Jobs" })).toBeVisible({ timeout: 8000 });
    await expect(page.locator("text=Source")).toBeVisible({ timeout: 5000 });
  });

  test("has New Job button that navigates", async ({ page }) => {
    await page.click("text=New Job");
    await expect(page).toHaveURL("/jobs/new");
  });

  test("sidebar navigation works", async ({ page }) => {
    await page.click('a[href="/settings"]');
    await expect(page).toHaveURL("/settings");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

    await page.click('a[href="/"]');
    await expect(page).toHaveURL("/");
  });
});
