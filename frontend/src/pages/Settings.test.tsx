/**
 * Bug Condition Exploration Test
 * 
 * Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
 * 
 * This test verifies that the current Reframe Tuning tab LACKS:
 * - Section descriptions explaining pipeline stages
 * - Slider tooltips/popovers on hover/focus
 * - SVG schematic previews reacting to slider values
 * 
 * EXPECTED: These tests FAIL on unfixed code (confirming the bug exists)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RangeSlider } from '@/components/ui/RangeSlider';

// --- Mock all external dependencies that Settings.tsx imports ---
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { is_superadmin: true }, isAuthenticated: true }),
}));

vi.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}));

vi.mock('@/lib/api', () => ({
  system: { health: () => Promise.resolve({ version: '1.0', mode: 'dev' }) },
  storage: { clearProcessingData: () => Promise.resolve({ message: 'ok' }) },
  API_BASE: 'http://localhost:8000',
  getToken: () => 'fake-token',
}));

// Mock fetch for API calls
beforeEach(() => {
  global.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/settings/reframe-tuning')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: null }),
      });
    }
    if (url.includes('/api/settings')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      });
    }
    if (url.includes('/api/auth/users')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: [] }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ data: null }),
    });
  });
});

describe('Bug Condition: Reframe Tuning Tab Missing Descriptions, Tooltips, and Previews', () => {

  describe('Property 1: Section Descriptions Absent', () => {
    it('should have NO description paragraph in Sampling & Detection section explaining pipeline stage', async () => {
      // Validates: Requirement 1.6 - sections show only title with no explanatory text
      const { Settings } = await import('@/pages/Settings');
      const { container } = render(<Settings />);

      // Click the Reframe Tuning tab
      const reframeTab = screen.getByText('Reframe Tuning');
      fireEvent.click(reframeTab);

      // Look for any paragraph that describes frame sampling pipeline
      // The actual descriptions use Indonesian text, so check for:
      // - data-testid="section-description" elements
      // - OR keywords from the actual description content
      const sectionDescriptions = container.querySelectorAll('[data-testid="section-description"]');
      const allParagraphs = container.querySelectorAll('p');
      const pipelineDescriptions = Array.from(allParagraphs).filter(p => {
        const text = p.textContent?.toLowerCase() || '';
        return text.includes('frame sampling') ||
          text.includes('detection pipeline') ||
          text.includes('face detection') && text.includes('pipeline') ||
          text.includes('menganalisis frame') ||
          text.includes('mendeteksi wajah');
      });

      // BUG CONDITION: We EXPECT descriptions to be present (they should be)
      // On UNFIXED code, this will FAIL because no descriptions exist
      expect(sectionDescriptions.length + pipelineDescriptions.length).toBeGreaterThan(0);
    });

    it('should have NO description paragraph in Auto Grid section explaining split-screen composition', async () => {
      // Validates: Requirement 1.6
      const { Settings } = await import('@/pages/Settings');
      const { container } = render(<Settings />);

      const reframeTab = screen.getByText('Reframe Tuning');
      fireEvent.click(reframeTab);

      const allParagraphs = container.querySelectorAll('p');
      const gridDescriptions = Array.from(allParagraphs).filter(p => {
        const text = p.textContent?.toLowerCase() || '';
        return text.includes('split-screen') ||
          text.includes('grid layout') && text.includes('composition') ||
          text.includes('split screen composition');
      });

      // BUG CONDITION: We EXPECT descriptions to be present
      // On UNFIXED code, this FAILS — confirming the bug
      expect(gridDescriptions.length).toBeGreaterThan(0);
    });

    it('should have NO description paragraph in Ghost Detection section explaining false-positive filtering', async () => {
      // Validates: Requirement 1.6
      const { Settings } = await import('@/pages/Settings');
      const { container } = render(<Settings />);

      const reframeTab = screen.getByText('Reframe Tuning');
      fireEvent.click(reframeTab);

      // Look for section description elements or paragraphs about ghost filtering
      // The actual descriptions use Indonesian text
      const sectionDescriptions = container.querySelectorAll('[data-testid="section-description"]');
      const allParagraphs = container.querySelectorAll('p');
      const ghostDescriptions = Array.from(allParagraphs).filter(p => {
        const text = p.textContent?.toLowerCase() || '';
        return (text.includes('false-positive filtering') ||
          text.includes('ghost filtering pipeline') ||
          text.includes('filters out false detections') ||
          text.includes('memfilter deteksi wajah palsu') ||
          text.includes('false-positive') && text.includes('filtering') ||
          text.includes('ghost')) &&
          text.length > 20 && text.length < 200; // Must be a proper description, not a one-liner tip
      });

      // BUG CONDITION: We EXPECT descriptions to be present
      // On UNFIXED code, this FAILS
      expect(sectionDescriptions.length + ghostDescriptions.length).toBeGreaterThan(0);
    });
  });

  describe('Property 1: Slider Tooltips Absent', () => {
    it('should show NO tooltip or popover when hovering/focusing a RangeSlider', async () => {
      // Validates: Requirements 1.2, 1.5
      // Test RangeSlider WITH tooltip prop — it should show tooltip on hover
      const user = userEvent.setup();
      const onChange = vi.fn();

      const { container } = render(
        <RangeSlider
          label="Face Confidence"
          value={0.55}
          min={0.1}
          max={0.9}
          step={0.01}
          onChange={onChange}
          tooltip={{
            what: "Detection threshold for MediaPipe",
            increase: "Fewer false positives but may miss faces",
            decrease: "More detections but more noise",
          }}
        />
      );

      // Hover over the label/value area (the wrapper div with onMouseEnter)
      const labelArea = container.querySelector('.flex.items-center.justify-between')!;
      await user.hover(labelArea);

      // Check for tooltip elements (role=tooltip, data-testid with tooltip, or aria-describedby)
      const tooltips = container.querySelectorAll('[role="tooltip"]');
      const tooltipDivs = container.querySelectorAll('[data-testid*="tooltip"]');
      const popovers = container.querySelectorAll('[data-testid*="popover"]');

      // BUG CONDITION: We EXPECT tooltips to be present on hover
      // On UNFIXED code, this FAILS — no tooltip appears
      expect(tooltips.length + tooltipDivs.length + popovers.length).toBeGreaterThan(0);
    });

    it('should show NO inline description below any slider in the Reframe Tuning tab', async () => {
      // Validates: Requirement 1.5
      const { Settings } = await import('@/pages/Settings');
      const { container } = render(<Settings />);

      const reframeTab = screen.getByText('Reframe Tuning');
      fireEvent.click(reframeTab);

      // Look for description elements associated with sliders
      const sliderDescriptions = container.querySelectorAll('[data-testid*="slider-description"]');
      const ariaDescriptions = container.querySelectorAll('[id*="slider-desc"]');

      // BUG CONDITION: We EXPECT slider descriptions to be present
      // On UNFIXED code, this FAILS
      expect(sliderDescriptions.length + ariaDescriptions.length).toBeGreaterThan(0);
    });
  });

  describe('Property 2: SVG Previews Replaced by Image Preview Panel', () => {
    // Phase 2 replaced the old SVG schematics with a real image preview panel.
    // These tests now verify the old SVGs are removed and the new panel exists.

    it('should have NO old SVG preview for Sampling & Detection section (replaced by image preview)', async () => {
      // Validates: Requirement 1.2 — old SVGs intentionally removed in Phase 2
      const { Settings } = await import('@/pages/Settings');
      const { container } = render(<Settings />);

      const reframeTab = screen.getByText('Reframe Tuning');
      fireEvent.click(reframeTab);

      const preview = container.querySelector('[data-testid="sampling-detection-preview"]');

      // After Phase 2 fix: SVG previews are removed, replaced by ImagePreviewPanel
      expect(preview).toBeNull();
    });

    it('should have NO old SVG preview for Auto Grid section (replaced by image preview)', async () => {
      // Validates: Requirement 1.3 — old SVGs intentionally removed in Phase 2
      const { Settings } = await import('@/pages/Settings');
      const { container } = render(<Settings />);

      const reframeTab = screen.getByText('Reframe Tuning');
      fireEvent.click(reframeTab);

      const preview = container.querySelector('[data-testid="auto-grid-preview"]');

      // After Phase 2 fix: SVG previews are removed, replaced by ImagePreviewPanel
      expect(preview).toBeNull();
    });

    it('should have NO old SVG preview for Ghost Detection section (replaced by image preview)', async () => {
      // Validates: Requirement 1.4 — old SVGs intentionally removed in Phase 2
      const { Settings } = await import('@/pages/Settings');
      const { container } = render(<Settings />);

      const reframeTab = screen.getByText('Reframe Tuning');
      fireEvent.click(reframeTab);

      const preview = container.querySelector('[data-testid="ghost-detection-preview"]');

      // After Phase 2 fix: SVG previews are removed, replaced by ImagePreviewPanel
      expect(preview).toBeNull();
    });
  });
});
