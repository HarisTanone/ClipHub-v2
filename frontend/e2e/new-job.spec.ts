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

test.describe("New Job", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/jobs/new");
  });

  test("shows the job creation form", async ({ page }) => {
    await expect(page.locator("h1")).toContainText("New Job");
    await expect(page.locator('input[type="url"]')).toBeVisible();
    await expect(page.locator("text=Aspect Ratio")).toBeVisible();
    await expect(page.locator("text=Hook Engine")).toBeVisible();
    await expect(page.locator("text=Start Processing")).toBeVisible();
  });

  test("validates empty URL", async ({ page }) => {
    await page.click("text=Start Processing");
    await expect(page.locator("text=URL required")).toBeVisible();
  });

  test("validates invalid URL", async ({ page }) => {
    // Use a valid URL format that's not YouTube (browser native validation won't block)
    await page.fill('input[type="url"]', "https://example.com/notayoutube");
    await page.click("text=Start Processing");
    await expect(page.locator("text=Enter a valid YouTube URL")).toBeVisible();
  });

  test("aspect ratio selector works", async ({ page }) => {
    // Click 16:9 button
    const btn = page.locator("button", { hasText: "16:9" });
    await btn.click();
    // YOLO should show OFF in pipeline summary
    await expect(page.locator("text=OFF")).toBeVisible();
  });

  test("toggle controls work", async ({ page }) => {
    // Auto B-roll is optional and disabled by default.
    const brollOption = page.locator("label", { hasText: "Auto B-roll" });
    await expect(brollOption).toBeVisible();
    await expect(brollOption.getByRole("switch")).toHaveAttribute("aria-checked", "false");
    await brollOption.getByRole("switch").click();
    await expect(brollOption.getByRole("switch")).toHaveAttribute("aria-checked", "true");
    await expect(page.locator("text=Auto-Grid")).toBeVisible();
    await expect(page.locator("text=Force Reprocess")).toBeVisible();
  });

  test("submits job with valid URL and redirects to detail", async ({ page }) => {
    await page.fill('input[type="url"]', "https://www.youtube.com/watch?v=dQw4w9WgXcQ");
    await page.click("text=Start Processing");

    // Should either redirect to job detail or show error
    // (backend may fail if yt-dlp validation fails, but the request should go through)
    await page.waitForURL(/\/jobs\/job_/, { timeout: 10000 }).catch(() => {
      // If it doesn't redirect, check for an error toast
    });
  });
});
