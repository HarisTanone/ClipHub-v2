import { test, expect } from "@playwright/test";

const EMAIL = "admin@autocliper.com";
const PASSWORD = "Admin@2024!Secure";

async function login(page: any) {
  await page.goto("/login");
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);

  const [response] = await Promise.all([
    page.waitForResponse((r: any) => r.url().includes("/api/auth/login") && r.status() === 200),
    page.click('button[type="submit"]'),
  ]);

  await expect(page).toHaveURL("/", { timeout: 8000 });
}

test.describe("Settings Page", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/settings");
  });

  test("displays settings form", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await expect(page.locator("text=Pipeline Defaults")).toBeVisible();
    await expect(page.locator("text=Whisper Transcription")).toBeVisible();
  });

  test("shows backend connection status", async ({ page }) => {
    await expect(page.locator("text=Backend Connected")).toBeVisible({ timeout: 8000 });
  });

  test("save button works", async ({ page }) => {
    await page.click("text=Save Settings");
    await expect(page.locator("text=Settings saved")).toBeVisible({ timeout: 3000 });
  });
});
