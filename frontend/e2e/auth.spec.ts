import { test, expect } from "@playwright/test";

const EMAIL = "admin@autocliper.com";
const PASSWORD = "Admin@2024!Secure";

test.describe("Auth Flow", () => {
  test("redirects to /login when not authenticated", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });

  test("shows login page with form", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("h1")).toContainText("AutoCliper");
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test("shows error on invalid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="email"]', "wrong@email.com");
    await page.fill('input[type="password"]', "wrongpassword");
    await page.click('button[type="submit"]');
    await expect(page.locator("text=Invalid email or password")).toBeVisible({ timeout: 5000 });
  });

  test("logs in successfully and redirects to dashboard", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="email"]', EMAIL);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL("/", { timeout: 8000 });
    // Dashboard shows Jobs table (loads async)
    await expect(page.locator("text=Jobs").first()).toBeVisible({ timeout: 8000 });
  });

  test("persists session on reload", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="email"]', EMAIL);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL("/", { timeout: 8000 });

    await page.reload();
    await expect(page).toHaveURL("/");
    await expect(page.locator("text=Jobs").first()).toBeVisible({ timeout: 8000 });
  });

  test("logout clears session", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[type="email"]', EMAIL);
    await page.fill('input[type="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL("/", { timeout: 8000 });

    await page.click('button[title="Logout"]');
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 });
  });
});
