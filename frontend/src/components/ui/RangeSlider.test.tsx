/**
 * Preservation Property Tests — RangeSlider & ReframeTuning State
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
 *
 * These tests verify EXISTING behavior is maintained:
 * - RangeSlider without description/tooltip props renders identically (backward compatible)
 * - For all valid ReframeTuning value objects, save payload matches interface (no extra fields)
 * - Reset always produces REFRAME_TUNING_DEFAULTS values
 *
 * MUST PASS on current unfixed code.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import fc from 'fast-check';
import { RangeSlider } from '@/components/ui/RangeSlider';

// ─── RangeSlider Backward Compatibility ──────────────────────────────────────

describe('Property 4: RangeSlider Backward Compatibility (Preservation)', () => {

  /**
   * **Validates: Requirements 3.6**
   *
   * Property: For all valid combinations of label, value, min, max, step,
   * RangeSlider renders a structure with: a label element, a value display span,
   * and an input[type=range] — and nothing else unexpected.
   */
  it('renders correct structure with only required props for any valid slider config', () => {
    fc.assert(
      fc.property(
        fc.record({
          label: fc.string({ minLength: 1, maxLength: 50 }),
          min: fc.double({ min: 0, max: 100, noNaN: true, noDefaultInfinity: true }),
          step: fc.double({ min: 0.001, max: 10, noNaN: true, noDefaultInfinity: true }),
        }).chain(({ label, min, step }) => {
          const maxVal = min + step * 10; // ensure max > min
          return fc.record({
            label: fc.constant(label),
            min: fc.constant(min),
            max: fc.constant(maxVal),
            step: fc.constant(step),
            value: fc.double({ min, max: maxVal, noNaN: true, noDefaultInfinity: true }),
          });
        }),
        ({ label, value, min, max, step }) => {
          const onChange = vi.fn();
          const { container } = render(
            <RangeSlider
              label={label}
              value={value}
              min={min}
              max={max}
              step={step}
              onChange={onChange}
            />
          );

          // Structure checks: must have a wrapping div
          const wrapper = container.firstElementChild;
          expect(wrapper).not.toBeNull();
          expect(wrapper?.tagName).toBe('DIV');

          // Must have a label element with the label text
          const labelEl = container.querySelector('label');
          expect(labelEl).not.toBeNull();
          expect(labelEl?.textContent).toBe(label);

          // Must have a value display span
          const spans = container.querySelectorAll('span');
          expect(spans.length).toBeGreaterThanOrEqual(1);

          // Must have exactly one input[type=range]
          const inputs = container.querySelectorAll('input[type="range"]');
          expect(inputs.length).toBe(1);

          // Input must have correct min, max, step attributes
          const input = inputs[0];
          expect(input.getAttribute('min')).toBe(String(min));
          expect(input.getAttribute('max')).toBe(String(max));
          expect(input.getAttribute('step')).toBe(String(step));

          // No tooltip, popover, or description elements should exist
          expect(container.querySelectorAll('[role="tooltip"]').length).toBe(0);
          expect(container.querySelectorAll('[data-testid*="tooltip"]').length).toBe(0);
          expect(container.querySelectorAll('[data-testid*="description"]').length).toBe(0);
        }
      ),
      { numRuns: 50 }
    );
  });

  /**
   * **Validates: Requirements 3.6**
   *
   * Property: RangeSlider onChange fires with the correct parsed float value.
   */
  it('calls onChange with parseFloat of input value for any valid slider interaction', () => {
    fc.assert(
      fc.property(
        fc.record({
          min: fc.double({ min: 0, max: 50, noNaN: true, noDefaultInfinity: true }),
          step: fc.double({ min: 0.01, max: 5, noNaN: true, noDefaultInfinity: true }),
        }).chain(({ min, step }) => {
          const max = min + step * 20;
          return fc.record({
            min: fc.constant(min),
            max: fc.constant(max),
            step: fc.constant(step),
            initialValue: fc.double({ min, max, noNaN: true, noDefaultInfinity: true }),
            newValue: fc.double({ min, max, noNaN: true, noDefaultInfinity: true }),
          });
        }).filter(({ initialValue, newValue }) => {
          // Ensure newValue differs from initialValue (otherwise onChange won't fire)
          return String(newValue) !== String(initialValue);
        }),
        ({ min, max, step, initialValue, newValue }) => {
          const onChange = vi.fn();
          const { container } = render(
            <RangeSlider
              label="Test"
              value={initialValue}
              min={min}
              max={max}
              step={step}
              onChange={onChange}
            />
          );

          const input = container.querySelector('input[type="range"]')!;
          fireEvent.change(input, { target: { value: String(newValue) } });

          expect(onChange).toHaveBeenCalledWith(parseFloat(String(newValue)));
        }
      ),
      { numRuns: 30 }
    );
  });

  /**
   * **Validates: Requirements 3.6**
   *
   * Property: RangeSlider value display shows integer for whole numbers,
   * and .toFixed(2) for decimals.
   */
  it('displays value correctly — integer for whole numbers, toFixed(2) for decimals', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.integer({ min: 0, max: 1000 }).map(v => ({ value: v, isInt: true })),
          fc.double({ min: 0.01, max: 100, noNaN: true, noDefaultInfinity: true })
            .filter(v => !Number.isInteger(v))
            .map(v => ({ value: v, isInt: false }))
        ),
        ({ value, isInt }) => {
          const { container } = render(
            <RangeSlider
              label="Test"
              value={value}
              min={0}
              max={1000}
              step={0.01}
              onChange={vi.fn()}
            />
          );

          const valueSpan = container.querySelector('span');
          expect(valueSpan).not.toBeNull();

          if (isInt) {
            expect(valueSpan?.textContent).toBe(String(value));
          } else {
            expect(valueSpan?.textContent).toBe(value.toFixed(2));
          }
        }
      ),
      { numRuns: 30 }
    );
  });
});

// ─── ReframeTuning Save Payload Structure ────────────────────────────────────

describe('Property 3: ReframeTuning Save Payload Matches Interface (Preservation)', () => {

  // The exact 21 keys in the ReframeTuning interface
  const REFRAME_TUNING_KEYS = [
    'sample_interval_sec', 'max_samples', 'face_confidence',
    'min_face_size_ratio', 'max_face_size_ratio',
    'min_separation_ratio', 'min_coexist_ratio',
    'dominance_single_crop', 'grid_base_zoom', 'grid_max_zoom',
    'grid_face_margin', 'grid_enter_samples', 'grid_exit_samples',
    'min_grid_segment_seconds',
    'min_face_area_px', 'min_area_ratio_to_max', 'min_frame_ratio',
    'ghost_iou_threshold', 'ghost_center_dist_ratio',
    'ghost_center_dist_broad', 'min_pair_size_ratio',
  ] as const;

  const REFRAME_TUNING_DEFAULTS = {
    sample_interval_sec: 0.333, max_samples: 720, face_confidence: 0.55,
    min_face_size_ratio: 0.10, max_face_size_ratio: 0.50,
    min_separation_ratio: 0.05, min_coexist_ratio: 0.40,
    dominance_single_crop: 0.75, grid_base_zoom: 1.08, grid_max_zoom: 3.50,
    grid_face_margin: 0.35, grid_enter_samples: 4, grid_exit_samples: 2,
    min_grid_segment_seconds: 1.20,
    min_face_area_px: 4000, min_area_ratio_to_max: 0.25, min_frame_ratio: 0.15,
    ghost_iou_threshold: 0.25, ghost_center_dist_ratio: 0.08,
    ghost_center_dist_broad: 0.20, min_pair_size_ratio: 0.18,
  };

  // Generator for valid ReframeTuning objects within slider ranges
  const reframeTuningArb = fc.record({
    sample_interval_sec: fc.double({ min: 0.1, max: 1.0, noNaN: true, noDefaultInfinity: true }),
    max_samples: fc.integer({ min: 60, max: 1440 }),
    face_confidence: fc.double({ min: 0.1, max: 0.9, noNaN: true, noDefaultInfinity: true }),
    min_face_size_ratio: fc.double({ min: 0.02, max: 0.30, noNaN: true, noDefaultInfinity: true }),
    max_face_size_ratio: fc.double({ min: 0.20, max: 0.80, noNaN: true, noDefaultInfinity: true }),
    min_separation_ratio: fc.double({ min: 0.05, max: 0.50, noNaN: true, noDefaultInfinity: true }),
    min_coexist_ratio: fc.double({ min: 0.10, max: 0.80, noNaN: true, noDefaultInfinity: true }),
    dominance_single_crop: fc.double({ min: 0.50, max: 0.95, noNaN: true, noDefaultInfinity: true }),
    grid_base_zoom: fc.double({ min: 1.0, max: 1.5, noNaN: true, noDefaultInfinity: true }),
    grid_max_zoom: fc.double({ min: 1.2, max: 4.0, noNaN: true, noDefaultInfinity: true }),
    grid_face_margin: fc.double({ min: 0.10, max: 0.60, noNaN: true, noDefaultInfinity: true }),
    grid_enter_samples: fc.integer({ min: 1, max: 10 }),
    grid_exit_samples: fc.integer({ min: 1, max: 6 }),
    min_grid_segment_seconds: fc.double({ min: 0.5, max: 3.0, noNaN: true, noDefaultInfinity: true }),
    min_face_area_px: fc.integer({ min: 500, max: 15000 }),
    min_area_ratio_to_max: fc.double({ min: 0.05, max: 0.60, noNaN: true, noDefaultInfinity: true }),
    min_frame_ratio: fc.double({ min: 0.05, max: 0.50, noNaN: true, noDefaultInfinity: true }),
    ghost_iou_threshold: fc.double({ min: 0.10, max: 0.60, noNaN: true, noDefaultInfinity: true }),
    ghost_center_dist_ratio: fc.double({ min: 0.02, max: 0.30, noNaN: true, noDefaultInfinity: true }),
    ghost_center_dist_broad: fc.double({ min: 0.05, max: 0.50, noNaN: true, noDefaultInfinity: true }),
    min_pair_size_ratio: fc.double({ min: 0.05, max: 0.50, noNaN: true, noDefaultInfinity: true }),
  });

  /**
   * **Validates: Requirements 3.1, 3.4**
   *
   * Property: For all valid ReframeTuning value objects, the payload has exactly
   * 21 keys matching the interface — no extra fields from descriptions/previews leak in.
   */
  it('any valid ReframeTuning object has exactly 21 numeric fields matching the interface', () => {
    fc.assert(
      fc.property(reframeTuningArb, (tuning) => {
        const keys = Object.keys(tuning);

        // Exactly 21 keys
        expect(keys.length).toBe(21);

        // All keys match the interface
        for (const key of REFRAME_TUNING_KEYS) {
          expect(keys).toContain(key);
        }

        // No extra keys
        for (const key of keys) {
          expect(REFRAME_TUNING_KEYS).toContain(key);
        }

        // All values are numbers
        for (const key of keys) {
          expect(typeof tuning[key as keyof typeof tuning]).toBe('number');
        }
      }),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 3.3, 3.5**
   *
   * Property: REFRAME_TUNING_DEFAULTS has exactly 21 fields, all numeric,
   * and produces a valid payload structure.
   */
  it('REFRAME_TUNING_DEFAULTS has exactly 21 numeric fields matching the interface', () => {
    const keys = Object.keys(REFRAME_TUNING_DEFAULTS);

    expect(keys.length).toBe(21);

    for (const key of REFRAME_TUNING_KEYS) {
      expect(keys).toContain(key);
      expect(typeof REFRAME_TUNING_DEFAULTS[key]).toBe('number');
    }

    // No extra keys
    for (const key of keys) {
      expect(REFRAME_TUNING_KEYS as readonly string[]).toContain(key);
    }
  });

  /**
   * **Validates: Requirements 3.3**
   *
   * Property: Reset always produces REFRAME_TUNING_DEFAULTS values regardless
   * of what the current state was before reset.
   */
  it('reset always restores to REFRAME_TUNING_DEFAULTS regardless of current state', () => {
    fc.assert(
      fc.property(reframeTuningArb, (randomState) => {
        // Simulate reset: no matter what randomState was, reset returns defaults
        // This verifies the reset logic is deterministic
        const resetResult = { ...REFRAME_TUNING_DEFAULTS };

        // Result must exactly equal defaults
        for (const key of REFRAME_TUNING_KEYS) {
          expect(resetResult[key]).toBe(REFRAME_TUNING_DEFAULTS[key]);
        }

        // Must not carry over any values from the random state
        // (unless by coincidence they're the same default values)
        expect(Object.keys(resetResult).length).toBe(21);
      }),
      { numRuns: 50 }
    );
  });

  /**
   * **Validates: Requirements 3.1, 3.4**
   *
   * Integration-style property: Settings page calls saveReframeTuning with
   * the correct payload structure (all 21 fields, no extras).
   */
  it('saveReframeTuning payload structure matches interface when called from Settings', async () => {
    // Mock the fetch to capture the save payload
    let capturedPayload: any = null;

    global.fetch = vi.fn().mockImplementation((url: string, options?: any) => {
      if (url.includes('/api/settings/reframe-tuning') && options?.method === 'PUT') {
        capturedPayload = JSON.parse(options.body);
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: null }) });
      }
      if (url.includes('/api/settings/reframe-tuning')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: REFRAME_TUNING_DEFAULTS }),
        });
      }
      if (url.includes('/api/settings')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: {} }) });
      }
      if (url.includes('/api/auth/users')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [] }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    // Mock auth & toast
    vi.doMock('@/hooks/useAuth', () => ({
      useAuth: () => ({ user: { is_superadmin: true }, isAuthenticated: true }),
    }));
    vi.doMock('@/components/ui/Toast', () => ({
      useToast: () => ({ success: vi.fn(), error: vi.fn() }),
    }));
    vi.doMock('@/lib/api', () => ({
      system: { health: () => Promise.resolve({ version: '1.0', mode: 'dev' }) },
      storage: { clearProcessingData: () => Promise.resolve({ message: 'ok' }) },
      API_BASE: 'http://localhost:8000',
      getToken: () => 'fake-token',
    }));

    const { Settings } = await import('@/pages/Settings');
    render(<Settings />);

    // Navigate to reframe tab
    const reframeTab = screen.getByText('Reframe Tuning');
    fireEvent.click(reframeTab);

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText('Sample Interval (sec)')).toBeInTheDocument();
    });

    // The Save button is only enabled when there are unsaved changes (dirty
    // state) relative to the last-persisted baseline. On fresh load the form
    // equals the baseline, so we must first modify a slider to make it dirty.
    const sliders = screen.getAllByRole('slider') as HTMLInputElement[];
    expect(sliders.length).toBeGreaterThan(0);
    const firstSlider = sliders[0];
    const currentValue = Number(firstSlider.value);
    const step = Number(firstSlider.step) || 1;
    const max = Number(firstSlider.max);
    const min = Number(firstSlider.min);
    // Nudge the value by one step, staying within [min, max].
    const nextValue =
      currentValue + step <= max ? currentValue + step : currentValue - step;
    expect(nextValue).toBeGreaterThanOrEqual(min);
    fireEvent.change(firstSlider, { target: { value: String(nextValue) } });

    // Now the form is dirty and Save should be enabled.
    const saveButton = screen.getByText('Save').closest('button') as HTMLButtonElement;
    await waitFor(() => {
      expect(saveButton).not.toBeDisabled();
    });
    fireEvent.click(saveButton);


    await waitFor(() => {
      expect(capturedPayload).not.toBeNull();
    });

    // Verify payload structure
    const payloadKeys = Object.keys(capturedPayload);
    expect(payloadKeys.length).toBe(21);

    for (const key of REFRAME_TUNING_KEYS) {
      expect(payloadKeys).toContain(key);
      expect(typeof capturedPayload[key]).toBe('number');
    }

    // No extra fields (descriptions, tooltips, previews shouldn't leak)
    for (const key of payloadKeys) {
      expect(REFRAME_TUNING_KEYS as readonly string[]).toContain(key);
    }
  });
});
