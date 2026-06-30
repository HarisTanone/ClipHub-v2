# QA Testing — All Flow Breakdown Report

**Run Date**: 2025-07-15  
**Runner**: `cd backend && python -m tests.test_qa_all_flows`  
**Result**: **26 PASSED | 0 FAILED | 0 SKIPPED**

---

## Executive Summary

All 26 test scenarios across 5 pipeline modules passed successfully. The pipeline handles normal operations, edge cases, and error conditions gracefully. No crashes or unhandled exceptions detected.

---

## A. LLM Analysis (Groq) — 7 Tests

| # | Scenario | Result | Detail |
|---|----------|--------|--------|
| A1 | Normal 5-min video (20 segments, 3 clips) | PASS | Got 3 clips |
| A2 | Long 30-min video (200 segments, 5 clips) | PASS | Got 5 clips |
| A3 | Very short 30s video (3 segments) | PASS | Got 2 clips (graceful even if video too short) |
| A4 | Single segment video | PASS | No crash |
| A5 | Empty transcript (0 segments) | PASS | No crash |
| A6 | Unicode/special characters (emoji, Thai, HTML entities) | PASS | Got 2 clips |
| A7 | Overlapping timestamps | PASS | No crash |

**Observations**:
- Groq LLM (llama-3.3-70b-versatile) handles all edge cases without crashing
- For very short/single segment videos, the LLM sometimes returns non-standard JSON keys (`clip` instead of `clips`) — the parser handles this gracefully
- Unicode and special characters do not cause JSON parsing failures
- The `_analyze_with_groq` method's truncation logic (first+last 40%) works for 200-segment transcripts

---

## B. Segment ID System — 5 Tests

| # | Scenario | Result | Detail |
|---|----------|--------|--------|
| B1 | Segment map built correctly | PASS | Map has 3 entries with correct IDs |
| B2 | Transcript format includes IDs | PASS | Format: `[S0000 \| 00:00] text` |
| B3 | Valid ID resolution | PASS | S0001.start=5.5, S0002.end=20.0 |
| B4 | Invalid ID handling | PASS | `S9999` correctly not found in map |
| B5 | Fallback to raw timestamps | PASS | When IDs invalid, falls back to float timestamps |

**Observations**:
- Segment ID system (S0000-S9999) correctly maps transcript segments to timestamps
- The fallback mechanism ensures clips can still be extracted even if LLM returns invalid IDs
- Format is deterministic: `[S{idx:04d} | MM:SS] text`

---

## C. Subtitle Timing — 5 Tests

| # | Scenario | Result | Detail |
|---|----------|--------|--------|
| C1 | Words during hook period filtered | PASS | 2 words remain (words with start >= 3.0) |
| C2 | Safety fallback (all words in hook period) | PASS | All 3 words restored when 100% filtered |
| C3 | Empty words array | PASS | No crash, empty result |
| C4 | Word at start=0.0 | PASS | Correctly filtered by hook |
| C5 | Word at exactly hook boundary (start=3.0) | PASS | Passes through (>= comparison) |

**Observations**:
- Hook duration filtering uses `>=` comparison: words at exactly `hook_dur` pass through
- Safety fallback prevents empty subtitle render when all words fall within hook period
- The boundary behavior (start=3.0 with hook_dur=3.0) passes — this is correct since `3.0 >= 3.0` is true

---

## D. YOLO Reframe Logic — 6 Tests

| # | Scenario | Result | Detail |
|---|----------|--------|--------|
| D1 | No persons detected | PASS | Triggers center crop fallback |
| D2 | Single person static (near center) | PASS | Range: 0px — static crop |
| D3 | Single person moving (1000px travel) | PASS | Range: 221px — smooth pan |
| D4 | Multiple speakers (2 persons) | PASS | Multi ratio: 1.00 — triggers autogrid logic |
| D5 | Target 16:9 | PASS | Skips YOLO entirely (passthrough) |
| D6 | Target 1:1 | PASS | Center crop, no YOLO |

**Observations**:
- EMA smoothing (alpha=0.08) with deadzone (30px) works correctly:
  - Person within deadzone: zero crop movement
  - Person moving significantly: smooth 221px pan over 20 frames
- Multi-speaker detection threshold (0.7) correctly identifies 2-person scenarios
- Aspect ratio routing correctly skips YOLO for non-9:16 targets

---

## E. Remotion Input Path — 3 Tests

| # | Scenario | Result | Detail |
|---|----------|--------|--------|
| E1 | Reframed clip exists | PASS | Prefers `clip_01_reframed.mp4` |
| E2 | Hooked clip exists (but ignored) | PASS | Never uses `clip_01_hooked.mp4` |
| E3 | Only base clip exists | PASS | Falls back to `clip_01.mp4` |

**Observations**:
- Path priority is strictly: `reframed > base` (never hooked)
- The `_hooked.mp4` file is NEVER used as Remotion input — this prevents double-hook rendering
- Fallback chain works correctly when reframed file doesn't exist

---

## Issues Found

### No Critical Issues

All tests pass. The pipeline handles edge cases gracefully.

### Minor Observations (Non-blocking)

1. **A4/A5/A7**: Groq LLM sometimes returns `{"clip": {...}}` (singular) instead of `{"clips": [...]}` for degenerate inputs. The parser handles this but logs a warning. This is expected LLM behavior for unusual inputs.

2. **D2 Test Design Note**: The static person test requires the person to be within the deadzone (30px) of the starting smooth position. If the person is far from center initially, EMA will still converge — this is correct behavior (initial acquisition pan).

---

## Recommendations

1. **Consider adding A8 (Bad API Key)**: Currently skipped in CI. Could add a dedicated test with an intentionally invalid key to verify the error handling path returns a clear error message.

2. **Subtitle timing edge case**: The `>=` boundary at hook_dur means words starting exactly at hook end render immediately. If visual overlap with hook animation is undesirable, consider `>` (strict greater than) instead.

3. **YOLO initial acquisition**: When a person is detected far from center on first frame, the EMA will create a slow pan to acquire them. For very short clips (<5s), this could mean the person isn't centered until midway. Consider a faster initial alpha for the first few frames.

4. **Groq degenerate input handling**: For empty/single-segment transcripts, consider returning early (before API call) to save Groq API credits on inputs that can't produce valid 45-90s clips.

---

## Test File Location

```
backend/tests/test_qa_all_flows.py
```

Run command:
```bash
cd backend && python -m tests.test_qa_all_flows
# OR
cd backend && ./venv/bin/python tests/test_qa_all_flows.py
```
