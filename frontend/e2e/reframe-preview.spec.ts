import { test, expect } from '@playwright/test';

const EMAIL = "admin@autocliper.com";
const PASSWORD = "YourSecurePassword123!";
const BASE_URL = "http://100.64.5.96:3001";

async function login(page: any) {
  await page.goto(`${BASE_URL}/login`);
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);

  await Promise.all([
    page.waitForResponse((r: any) => r.url().includes("/api/auth/login") && r.status() === 200),
    page.click('button[type="submit"]'),
  ]);

  await page.waitForURL(/\/$/, { timeout: 8000 });
}

test.describe('Reframe Tuning Preview - Live Update Verification', () => {
  test('upload image and verify overlay changes on slider adjustment', async ({ page }) => {
    test.setTimeout(120000); // 2 minutes

    // 1. Login and navigate to settings
    await login(page);
    await page.goto(`${BASE_URL}/settings`);
    await page.waitForLoadState('networkidle');

    // 2. Click Reframe Tuning tab
    await page.click('button:has-text("Reframe Tuning")');
    await page.waitForTimeout(500);

    // 3. Upload image
    const imagePath = '/Users/macbookairm1/Downloads/test-img.png';
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(imagePath);
    await page.waitForTimeout(1500);

    // 4. Verify image is displayed
    const img = page.locator('img[alt="Preview frame"]');
    await expect(img).toBeVisible({ timeout: 5000 });

    // 5. Verify crop overlay SVG exists
    const overlay = page.locator('[data-testid="crop-overlay"]');
    await expect(overlay).toBeVisible({ timeout: 5000 });

    // 6. Get overlay SVG content helper
    const getOverlayContent = async () => {
      return await overlay.innerHTML();
    };

    const initialContent = await getOverlayContent();
    console.log('✅ Initial overlay rendered. Testing slider changes...\n');

    // 7. Results tracking
    const results: { slider: string; changed: boolean; section: string }[] = [];

    // Helper: find slider by label text and adjust value using JavaScript
    const testSlider = async (label: string, targetValue: number, section: string) => {
      const beforeContent = await getOverlayContent();

      // Find the label, then get the range input within the same parent container
      const labelEl = page.locator(`label:has-text("${label}")`).first();

      if (await labelEl.count() === 0) {
        console.log(`  ⚠️ Slider "${label}" not found`);
        results.push({ slider: label, changed: false, section });
        return;
      }

      // The RangeSlider structure: div.space-y-1.5 > div(label+value) + input[type=range]
      // Navigate from label to its parent's parent (the .space-y-1.5 container)
      const container = labelEl.locator('..').locator('..');
      const rangeInput = container.locator('input[type="range"]');

      if (await rangeInput.count() === 0) {
        console.log(`  ⚠️ Range input for "${label}" not found`);
        results.push({ slider: label, changed: false, section });
        return;
      }

      // Set value using JavaScript to properly trigger React onChange
      await rangeInput.evaluate((el: HTMLInputElement, val: number) => {
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, 'value'
        )!.set!;
        nativeInputValueSetter.call(el, val.toString());
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }, targetValue);

      await page.waitForTimeout(300);

      const afterContent = await getOverlayContent();
      const changed = beforeContent !== afterContent;

      results.push({ slider: label, changed, section });
      console.log(`  ${changed ? '✅' : '❌'} ${label} → ${targetValue} ${changed ? '(overlay CHANGED)' : '(NO change)'}`);
    };

    // --- Sampling & Detection ---
    console.log('\n📐 Sampling & Detection:');
    await testSlider('Sample Interval (sec)', 0.8, 'Sampling & Detection');
    await testSlider('Max Samples', 200, 'Sampling & Detection');
    await testSlider('Face Confidence', 0.3, 'Sampling & Detection');
    await testSlider('Min Face Size Ratio', 0.25, 'Sampling & Detection');
    await testSlider('Max Face Size Ratio', 0.60, 'Sampling & Detection');
    // These have longer labels
    await testSlider('Min Separation Ratio', 0.40, 'Sampling & Detection');
    await testSlider('Min Coexist Ratio', 0.60, 'Sampling & Detection');

    // --- Auto Grid ---
    console.log('\n🔲 Auto Grid:');
    await testSlider('Dominance Single Crop', 0.60, 'Auto Grid');
    await testSlider('Grid Base Zoom', 1.35, 'Auto Grid');
    await testSlider('Grid Max Zoom', 2.5, 'Auto Grid');
    await testSlider('Grid Face Margin', 0.50, 'Auto Grid');
    await testSlider('Grid Enter Samples', 8, 'Auto Grid');
    await testSlider('Grid Exit Samples', 4, 'Auto Grid');
    await testSlider('Min Grid Segment', 2.0, 'Auto Grid');

    // --- Ghost Detection ---
    console.log('\n👻 Ghost Detection:');
    await testSlider('Min Face Area (px)', 10000, 'Ghost Detection');
    await testSlider('Min Area Ratio to Max', 0.45, 'Ghost Detection');
    await testSlider('Min Frame Ratio', 0.35, 'Ghost Detection');
    await testSlider('Ghost IoU Threshold', 0.45, 'Ghost Detection');
    await testSlider('Ghost Center Dist Ratio', 0.20, 'Ghost Detection');
    await testSlider('Ghost Center Dist Broad', 0.40, 'Ghost Detection');
    await testSlider('Min Pair Size Ratio', 0.35, 'Ghost Detection');

    // 8. Test aspect ratio buttons
    console.log('\n📏 Aspect Ratio:');
    const before16_9 = await getOverlayContent();
    const btn16_9 = page.locator('button:has-text("16:9")');
    if (await btn16_9.count() > 0) {
      await btn16_9.click();
      await page.waitForTimeout(500);
    }
    const after16_9 = await getOverlayContent();
    const ratio16_9Changed = before16_9 !== after16_9;
    console.log(`  ${ratio16_9Changed ? '✅' : '❌'} 16:9 ${ratio16_9Changed ? '(overlay CHANGED)' : '(NO change)'}`);

    const before1_1 = await getOverlayContent();
    const btn1_1 = page.locator('button:has-text("1:1")');
    if (await btn1_1.count() > 0) {
      await btn1_1.click();
      await page.waitForTimeout(500);
    }
    const after1_1 = await getOverlayContent();
    const ratio1_1Changed = before1_1 !== after1_1;
    console.log(`  ${ratio1_1Changed ? '✅' : '❌'} 1:1 ${ratio1_1Changed ? '(overlay CHANGED)' : '(NO change)'}`);

    const before9_16 = await getOverlayContent();
    const btn9_16 = page.locator('button:has-text("9:16")');
    if (await btn9_16.count() > 0) {
      await btn9_16.click();
      await page.waitForTimeout(500);
    }
    const after9_16 = await getOverlayContent();
    const ratio9_16Changed = before9_16 !== after9_16;
    console.log(`  ${ratio9_16Changed ? '✅' : '❌'} 9:16 ${ratio9_16Changed ? '(overlay CHANGED)' : '(NO change)'}`);

    // 9. Summary
    console.log('\n' + '═'.repeat(60));
    console.log('📊 SUMMARY');
    console.log('═'.repeat(60));

    const changedCount = results.filter(r => r.changed).length;
    const totalCount = results.length;
    console.log(`\n  Sliders: ${changedCount}/${totalCount} caused overlay changes`);
    console.log(`  Aspect ratios: 16:9=${ratio16_9Changed ? '✅' : '❌'}, 1:1=${ratio1_1Changed ? '✅' : '❌'}, 9:16=${ratio9_16Changed ? '✅' : '❌'}`);

    // Group by section
    const sections = ['Sampling & Detection', 'Auto Grid', 'Ghost Detection'];
    for (const section of sections) {
      const sectionResults = results.filter(r => r.section === section);
      const sectionChanged = sectionResults.filter(r => r.changed).length;
      console.log(`\n  ${section}: ${sectionChanged}/${sectionResults.length} working`);

      const notWorking = sectionResults.filter(r => !r.changed);
      if (notWorking.length > 0) {
        notWorking.forEach(r => console.log(`    ❌ ${r.slider}`));
      }
    }

    const notChanged = results.filter(r => !r.changed);
    if (notChanged.length > 0) {
      console.log(`\n⚠️  Sliders that did NOT cause overlay change (${notChanged.length}):`);
      notChanged.forEach(r => console.log(`   - [${r.section}] ${r.slider}`));
    }

    console.log('\n' + '═'.repeat(60));

    // Take a screenshot for reference
    await page.screenshot({ path: '/Users/macbookairm1/Downloads/reframe-preview-test.png', fullPage: false });
    console.log('\n📸 Screenshot saved to /Users/macbookairm1/Downloads/reframe-preview-test.png');

    // Assert that at least some sliders work (the ones that affect the overlay geometry)
    // Based on CropOverlay.tsx: dominance_single_crop, grid_base_zoom, grid_max_zoom, 
    // grid_face_margin, min_face_area_px, min_area_ratio_to_max directly affect SVG output
    expect(changedCount).toBeGreaterThan(0);
  });
});
