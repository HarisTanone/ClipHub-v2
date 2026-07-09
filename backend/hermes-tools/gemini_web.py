"""Gemini Web Automation via Playwright + Real Chrome.

Uses a persistent Chrome profile (pre-authenticated) to send prompts
to gemini.google.com and extract JSON responses.

Usage:
    python gemini_web.py --prompt "Your prompt here"
    python gemini_web.py --prompt-file /path/to/prompt.txt
    python gemini_web.py --video-url "https://youtube.com/..." --duration 120 --max-clips 5
"""
import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────
CHROME_PROFILE = os.environ.get(
    "CHROME_PROFILE", str(Path.home() / ".hermes" / "chrome-profile")
)
CHROME_EXECUTABLE = os.environ.get(
    "CHROME_EXECUTABLE", "/usr/bin/google-chrome-stable"
)
DISPLAY_ENV = os.environ.get("DISPLAY", ":99")
GEMINI_URL = "https://gemini.google.com/app"
MAX_WAIT_RESPONSE = 300            # Gemini video analysis can take 3-5 min
STABLE_CHECK_ITERATIONS = 4        # consecutive stable checks before done
STABLE_CHECK_INTERVAL = 3          # seconds between stability checks
INITIAL_RESPONSE_DELAY = 8         # seconds before first response read


# ─── Helpers ──────────────────────────────────────────────────────────────────


def ensure_display() -> None:
    """Ensure Xvfb virtual display is running (Linux only)."""
    if sys.platform != "linux":
        return
    os.environ["DISPLAY"] = DISPLAY_ENV
    try:
        r = subprocess.run(
            ["xdpyinfo", "-display", DISPLAY_ENV],
            capture_output=True,
            check=False,
        )
        if r.returncode == 0:
            return
    except FileNotFoundError:
        pass

    logger.info(f"Starting Xvfb on {DISPLAY_ENV}...")
    try:
        subprocess.Popen(
            ["Xvfb", DISPLAY_ENV, "-screen", "0", "1920x1080x24"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
    except FileNotFoundError:
        logger.warning("Xvfb not found. Assuming external display is available.")


def extract_json_from_response(raw_text: str) -> dict:
    """Extract JSON object/array from Gemini response (handles markdown fences)."""
    if not raw_text or not raw_text.strip():
        raise ValueError("Empty response from Gemini")

    text = raw_text.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    fence_match = re.search(r"```(?:json|JSON)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Direct parse
    try:
        parsed = json.loads(text)
        return _as_dict(parsed)
    except json.JSONDecodeError:
        pass

    # Locate outermost JSON object/array
    start_obj = text.find("{")
    start_arr = text.find("[")

    if start_obj == -1 and start_arr == -1:
        raise ValueError(f"No JSON found in response: {text[:300]}")

    # Prefer the earliest valid delimiter
    if start_obj == -1:
        start_idx, open_ch, close_ch = start_arr, "[", "]"
    elif start_arr == -1:
        start_idx, open_ch, close_ch = start_obj, "{", "}"
    elif start_obj < start_arr:
        start_idx, open_ch, close_ch = start_obj, "{", "}"
    else:
        start_idx, open_ch, close_ch = start_arr, "[", "]"

    end_idx = text.rfind(close_ch) + 1
    if end_idx <= start_idx:
        raise ValueError(f"Malformed JSON boundaries: {text[:300]}")

    json_str = text[start_idx:end_idx]
    # Remove trailing commas before closing brackets
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
    # Strip JS-style comments
    json_str = re.sub(r"//.*?$", "", json_str, flags=re.MULTILINE)
    json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)

    try:
        return _as_dict(json.loads(json_str))
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON decode failed: {e}\nExtracted: {json_str[:300]}")


def _as_dict(parsed: Any) -> dict:
    """Normalize parsed JSON into a dict (wraps top-level arrays)."""
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        return {"items": parsed}
    raise ValueError(f"Unexpected JSON root type: {type(parsed).__name__}")


# ─── Gemini Web Class ─────────────────────────────────────────────────────────


class GeminiWeb:
    """Automates Gemini Web via Playwright with real Chrome."""

    INPUT_SELECTORS = [
        'rich-textarea div.ql-editor[contenteditable="true"]',
        'div.ql-editor[contenteditable="true"]',
        '[contenteditable="true"][aria-label="Enter a prompt for Gemini"]',
        '.text-input-field [contenteditable="true"]',
        '[contenteditable="true"][aria-label*="rompt"]',
        'div[contenteditable="true"]',
    ]

    SEND_BUTTON_SELECTORS = [
        'button[aria-label="Send message"]',
        'button[aria-label*="Send"]',
        'button.send-button',
        'rich-textarea button[type="submit"]',
    ]

    STOP_BUTTON_SELECTORS = [
        'button[aria-label="Stop responding"]',
        'button[aria-label*="Stop"]',
        'button[data-test-id="stop-button"]',
    ]

    NEW_CHAT_SELECTORS = [
        'button[aria-label="New chat"]',
        'a[aria-label="New chat"]',
        'button:has-text("New chat")',
        '[data-test-id="new-chat-button"]',
    ]

    # Prefer MODEL-specific selectors so we never read back our own prompt.
    RESPONSE_SELECTORS = [
        "model-response message-content",
        "model-response .model-response-text",
        ".model-response-text",
        ".response-container message-content",
        "message-content",
    ]

    CONSENT_BUTTON_SELECTORS = [
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        'button:has-text("Agree")',
        'button:has-text("Got it")',
        'button:has-text("OK")',
    ]

    def __init__(self, headless: bool = False):
        self._pw = None
        self.context = None
        self.page = None
        self._headless = headless

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch Chrome with persistent profile."""
        from playwright.sync_api import sync_playwright

        ensure_display()
        self._pw = sync_playwright().start()

        exec_path = CHROME_EXECUTABLE
        if exec_path and not Path(exec_path).exists():
            logger.warning(
                f"Chrome executable not found at {exec_path}; "
                "using Playwright's bundled Chromium."
            )
            exec_path = None

        launch_kwargs: dict = dict(
            user_data_dir=CHROME_PROFILE,
            headless=self._headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-extensions",
                "--start-maximized",
            ],
            viewport={"width": 1920, "height": 1080},
            timeout=60000,
        )
        if exec_path:
            launch_kwargs["executable_path"] = exec_path

        self.context = self._pw.chromium.launch_persistent_context(**launch_kwargs)
        self.page = (
            self.context.pages[0]
            if self.context.pages
            else self.context.new_page()
        )
        logger.info("Browser started with persistent profile")

    def close(self) -> None:
        """Shutdown browser."""
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        logger.info("Browser closed")

    def __enter__(self) -> "GeminiWeb":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ── navigation ────────────────────────────────────────────────────────────

    def open_gemini(self, retries: int = 2) -> bool:
        """Navigate to Gemini and verify login status."""
        last_err: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                self.page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=60000)
                self._dismiss_consent_dialogs()
                self.page.wait_for_timeout(5000)

                if "accounts.google.com" in self.page.url:
                    raise RuntimeError(
                        "Session expired — re-login needed via VNC. "
                        "Run the Chrome profile login flow again."
                    )

                page_text = self.page.inner_text("body", timeout=10000)
                low = page_text.lower()
                if "unusual traffic" in low or "captcha" in low:
                    raise RuntimeError("Captcha/block detected — solve via VNC.")

                logger.info(f"Gemini loaded: {self.page.url}")
                return True
            except Exception as e:
                last_err = e
                logger.warning(f"open_gemini attempt {attempt} failed: {e}")
                time.sleep(3)
        raise RuntimeError(f"Failed to open Gemini: {last_err}")

    def _dismiss_consent_dialogs(self) -> None:
        """Try to dismiss cookie/consent dialogs."""
        for sel in self.CONSENT_BUTTON_SELECTORS:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    self.page.wait_for_timeout(800)
                    logger.info(f"Dismissed consent dialog: {sel}")
            except Exception:
                continue

    # ── prompting ─────────────────────────────────────────────────────────────

    def send_prompt(self, prompt: str, max_retries: int = 2) -> str:
        """Send prompt to Gemini and return the response text."""
        if not prompt or not prompt.strip():
            raise ValueError("Empty prompt")

        last_err: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Sending prompt (attempt {attempt}, {len(prompt)} chars)...")
                self.page.wait_for_timeout(2000)

                existing = self._count_existing_responses()
                logger.info(f"Existing response elements: {existing}")

                if not self._fill_input(prompt):
                    raise RuntimeError("Failed to fill input field")
                if not self._click_send():
                    raise RuntimeError("Failed to send prompt")

                return self._wait_for_response(existing)
            except Exception as e:
                last_err = e
                logger.warning(f"send_prompt attempt {attempt} failed: {e}")
                try:
                    self.new_chat()
                except Exception:
                    pass
                time.sleep(3)

        raise RuntimeError(f"send_prompt failed after {max_retries} attempts: {last_err}")

    def _find_input(self):
        for sel in self.INPUT_SELECTORS:
            try:
                el = self.page.wait_for_selector(sel, timeout=5000)
                if el:
                    logger.info(f"Found input: {sel}")
                    return el
            except Exception:
                continue
        return None

    def _fill_input(self, prompt: str) -> bool:
        """Fill chat input. Returns True if verified."""
        input_el = self._find_input()
        if not input_el:
            return False

        try:
            input_el.click()
            self.page.wait_for_timeout(400)
        except Exception as e:
            logger.warning(f"Input click failed: {e}")

        # Method 1: execCommand insertText (works great with Quill)
        inserted = False
        try:
            inserted = bool(
                self.page.evaluate(
                    """(text) => {
                        const el = document.querySelector(
                            'rich-textarea div.ql-editor[contenteditable="true"]'
                        ) || document.querySelector('div.ql-editor[contenteditable="true"]');
                        if (!el) return false;
                        el.focus();
                        el.textContent = '';
                        document.execCommand('selectAll', false, null);
                        document.execCommand('delete', false, null);
                        document.execCommand('insertText', false, text);
                        return (el.textContent || '').length > 0;
                    }""",
                    prompt,
                )
            )
        except Exception as e:
            logger.debug(f"execCommand insertText failed: {e}")

        # Method 2: keyboard typing in chunks
        if not inserted:
            try:
                logger.info("Using keyboard typing fallback")
                input_el.click()
                self.page.wait_for_timeout(200)
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Delete")
                chunk = 200
                for i in range(0, len(prompt), chunk):
                    self.page.keyboard.type(prompt[i:i + chunk], delay=5)
                inserted = True
            except Exception as e:
                logger.error(f"Keyboard typing failed: {e}")
                return False

        # Verify
        self.page.wait_for_timeout(500)
        try:
            current = self.page.evaluate(
                """() => {
                    const el = document.querySelector(
                        'rich-textarea div.ql-editor[contenteditable="true"]'
                    ) || document.querySelector('div.ql-editor[contenteditable="true"]');
                    return el ? (el.textContent || '') : '';
                }"""
            )
            if current and len(current.strip()) >= min(50, len(prompt) * 0.5):
                logger.info(f"Input filled ({len(current)} chars)")
                return True
            logger.warning(
                f"Input verification weak: got {len(current)} chars, expected ~{len(prompt)}"
            )
            return len(current.strip()) > 0
        except Exception:
            return True

    def _click_send(self) -> bool:
        """Click send button. Returns True on success."""
        self.page.wait_for_timeout(500)
        for sel in self.SEND_BUTTON_SELECTORS:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible() and btn.is_enabled():
                    btn.click(force=True)
                    logger.info(f"Prompt sent via button: {sel}")
                    return True
            except Exception:
                continue
        # Fallback: Enter
        try:
            self.page.keyboard.press("Enter")
            logger.info("Prompt sent via Enter (fallback)")
            return True
        except Exception as e:
            logger.error(f"All send methods failed: {e}")
            return False

    # ── response handling ─────────────────────────────────────────────────────

    def _count_existing_responses(self) -> int:
        for sel in self.RESPONSE_SELECTORS:
            try:
                els = self.page.query_selector_all(sel)
                if els:
                    return len(els)
            except Exception:
                continue
        return 0

    def _is_still_generating(self) -> bool:
        for sel in self.STOP_BUTTON_SELECTORS:
            try:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    return True
            except Exception:
                continue
        return False

    def _wait_for_response(self, skip_count: int = 0) -> str:
        logger.info("Waiting for response...")
        self.page.wait_for_timeout(INITIAL_RESPONSE_DELAY * 1000)

        last_text = ""
        last_len = 0
        stable = 0
        empty_wait = 0
        t0 = time.time()

        while time.time() - t0 < MAX_WAIT_RESPONSE:
            text = self._get_new_response(skip_count)

            if not text:
                empty_wait += 1
                if empty_wait > 10:
                    logger.warning("No response text detected after long wait")
                    break
            else:
                empty_wait = 0

            same_text = text == last_text
            same_len = abs(len(text) - last_len) < 5
            generating = self._is_still_generating()

            if text and same_text and same_len and not generating:
                stable += 1
                if stable >= STABLE_CHECK_ITERATIONS:
                    elapsed = time.time() - t0
                    logger.info(f"Response complete ({len(text)} chars, {elapsed:.1f}s)")
                    return text
            else:
                stable = 0

            last_text = text
            last_len = len(text)
            self.page.wait_for_timeout(STABLE_CHECK_INTERVAL * 1000)

        logger.warning(
            f"Response wait ended after {time.time() - t0:.1f}s (stable={stable})"
        )
        return last_text or ""

    def _get_new_response(self, skip_count: int = 0) -> str:
        """Extract text from elements appearing AFTER the prompt was sent."""
        for sel in self.RESPONSE_SELECTORS:
            try:
                els = self.page.query_selector_all(sel)
                new_els = els[skip_count:]
                if not new_els:
                    continue
                target = new_els[-1]
                try:
                    text = target.inner_text(timeout=3000)
                except Exception:
                    text = target.text_content() or ""
                if text and text.strip():
                    cleaned = self._clean_response_text(text)
                    if cleaned:
                        return cleaned
            except Exception:
                continue
        return ""

    @staticmethod
    def _clean_response_text(text: str) -> str:
        """Strip common UI artifacts (action-button labels)."""
        if not text:
            return ""
        noise = [
            r"\bCopy\b", r"\bGood response\b", r"\bBad response\b",
            r"\bListen\b", r"\bShare\b", r"\bMore\b", r"\bDouble check\b",
            r"\bExport\b", r"\bEdit\b", r"\bRegenerate\b", r"\bRelated sites\b",
            r"\bShow more\b", r"\bShow less\b",
        ]
        out = text
        for pat in noise:
            out = re.sub(pat, "", out)
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out.strip()

    # ── chat control ──────────────────────────────────────────────────────────

    def new_chat(self) -> None:
        """Start a fresh chat. Prefers clicking the 'New chat' button."""
        for sel in self.NEW_CHAT_SELECTORS:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    self.page.wait_for_timeout(3000)
                    logger.info("Started new chat via button")
                    return
            except Exception:
                continue
        try:
            self.page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_timeout(3000)
            logger.info("Started new chat via navigation")
        except Exception as e:
            logger.warning(f"new_chat navigation failed: {e}")


# ─── Prompt Builders ──────────────────────────────────────────────────────────


def build_phase1_prompt(video_url: str, duration: float, max_clips: int) -> str:
    """Phase 1: Video analysis — clip selection + creative direction."""
    return (
        "Kamu adalah AI analis video viral profesional. "
        "Tonton video ini dan analisis secara mendalam.\n\n"
        f"VIDEO URL: {video_url}\n"
        f"DURASI VIDEO: {duration:.1f} detik\n"
        f"TARGET: Temukan maksimal {max_clips} momen PALING VIRAL "
        "(durasi MINIMUM 45 detik, biarkan cerita SELESAI UTUH).\n\n"
        "=== TUGAS 1: CLIP SELECTION ===\n"
        "Identifikasi momen yang:\n"
        "- Punya kekuatan emosional tinggi\n"
        "- Bisa berdiri sendiri tanpa konteks tambahan\n"
        "- Memicu komentar/share\n"
        "- Punya struktur cerita utuh\n\n"
        "ATURAN:\n"
        "- Klip TIDAK BOLEH OVERLAP\n"
        "- start = awal kalimat baru\n"
        "- end = setelah kalimat selesai (+1 detik toleransi)\n"
        "- Skor 1-100 berdasarkan potensi viral\n\n"
        "=== TUGAS 2: CREATIVE DIRECTION ===\n"
        "Tentukan visual identity: primary_color (hex), secondary_color (hex), "
        "background_accent (hex gelap), "
        "typography_mood (bold_impact/elegant_minimal/playful/dramatic), "
        "energy_level (high/medium/chill), "
        "transition_style (fast_cuts/smooth/kinetic), "
        "music_mood (energetic/chill/dramatic/suspense), "
        "hook_animation (fade_scale/slide_up/glitch/typewriter)\n\n"
        "=== TUGAS 3: HOOKS ===\n"
        "Untuk setiap clip: hook maks 60 karakter, bahasa sama dengan video, "
        "brutal & bikin penasaran (open loop).\n\n"
        "OUTPUT FORMAT - RAW JSON SAJA (tanpa markdown, tanpa penjelasan):\n"
        '{"clips": [{"rank": 1, "score": 85, "start": 10.5, "end": 65.2, '
        '"hook": "hook text", "reason": "alasan singkat", '
        '"content_type": "storytelling", "speaker_energy": "high"}], '
        '"creative_direction": {"primary_color": "#hex", '
        '"secondary_color": "#hex", "background_accent": "#hex", '
        '"typography_mood": "bold_impact", "energy_level": "high", '
        '"transition_style": "fast_cuts", "music_mood": "energetic", '
        '"hook_animation": "fade_scale"}}'
    )


def build_phase2_prompt(clips: list, duration: float) -> str:
    """Phase 2: Hook refinement + b-roll suggestions."""
    clips_lines = []
    for c in clips:
        clips_lines.append(
            f"  Clip {c['rank']}: [{c['start']:.1f}s-{c['end']:.1f}s] "
            f"score={c.get('score', 0)}, hook=\"{c.get('hook', '')}\""
        )
    clips_ctx = "\n".join(clips_lines)

    return (
        "Kamu adalah copywriter viral dan motion graphics director.\n\n"
        f"Video berdurasi {duration:.0f} detik. Clips terpilih:\n"
        f"{clips_ctx}\n\n"
        "=== TUGAS 1: HOOK REFINEMENT ===\n"
        "Buat hook LEBIH BAIK + hook_alt untuk setiap clip (maks 60 char).\n\n"
        "=== TUGAS 2: B-ROLL PLACEMENT ===\n"
        "Untuk setiap clip, 1-2 momen b-roll:\n"
        "- at_time: offset dalam clip (detik dari awal clip)\n"
        "- keyword: UPPERCASE maks 20 char\n"
        "- template: word_pop_typography / line_reveal_typography / "
        "particle_text_burst\n"
        "- duration: 1.5 - 3.0 detik\n"
        "- visual_category: footage / icon / motion_graphic / reaction\n\n"
        "OUTPUT - RAW JSON SAJA:\n"
        '{"clips": [{"rank": 1, "hook": "refined hook", '
        '"hook_alt": "alternative"}], '
        '"broll_suggestions": {"1": [{"at_time": 5.0, '
        '"keyword": "KEYWORD", "template": "word_pop_typography", '
        '"duration": 2.0, "visual_category": "footage"}]}}'
    )


# ─── High-Level Functions ─────────────────────────────────────────────────────


def analyze_video(video_url: str, duration: float, max_clips: int = 5) -> dict:
    """Full 2-phase video analysis via Gemini Web."""
    with GeminiWeb() as g:
        g.open_gemini()

        # Phase 1
        logger.info("=== PHASE 1: Video Analysis ===")
        prompt1 = build_phase1_prompt(video_url, duration, max_clips)
        raw1 = g.send_prompt(prompt1)
        logger.debug(f"Phase 1 raw response (head): {raw1[:500]!r}")
        result = extract_json_from_response(raw1)

        if "clips" not in result or not result["clips"]:
            raise RuntimeError(
                f"Phase 1 failed: no clips in response. Raw head: {raw1[:300]!r}"
            )
        logger.info(f"Phase 1 complete: {len(result['clips'])} clips")

        # Phase 2 in a new chat
        g.new_chat()
        g.page.wait_for_timeout(3000)

        logger.info("=== PHASE 2: Creative Enrichment ===")
        prompt2 = build_phase2_prompt(result["clips"], duration)
        raw2 = g.send_prompt(prompt2)
        logger.debug(f"Phase 2 raw response (head): {raw2[:500]!r}")

        try:
            res2 = extract_json_from_response(raw2)
        except Exception as e:
            logger.warning(f"Phase 2 JSON parse failed (non-critical): {e}")
            res2 = {}

        # Merge phase-2 hooks (rank-first, position-fallback)
        if isinstance(res2.get("clips"), list):
            by_rank = {
                c.get("rank"): c
                for c in res2["clips"]
                if isinstance(c, dict) and c.get("rank") is not None
            }
            rank_values = list(by_rank.values())
            for idx, clip in enumerate(result["clips"], start=1):
                rank = clip.get("rank", idx)
                ec = by_rank.get(rank)
                if ec is None and rank_values and idx - 1 < len(rank_values):
                    ec = rank_values[idx - 1]
                if ec:
                    if ec.get("hook"):
                        clip["hook"] = ec["hook"]
                    if ec.get("hook_alt"):
                        clip["hook_alt"] = ec["hook_alt"]

        result["broll_suggestions"] = res2.get("broll_suggestions", {})
        if result["broll_suggestions"]:
            logger.info("Phase 2 complete (with b-roll suggestions)")
        else:
            logger.warning("Phase 2 produced no b-roll suggestions")

        return result


def send_raw_prompt(prompt: str) -> dict:
    """Send arbitrary prompt to Gemini, return parsed JSON."""
    with GeminiWeb() as g:
        g.open_gemini()
        raw = g.send_prompt(prompt)
        return extract_json_from_response(raw)


# ─── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini Web Automation")
    parser.add_argument("--prompt", help="Raw prompt to send")
    parser.add_argument("--prompt-file", help="File containing prompt")
    parser.add_argument("--video-url", help="YouTube URL for video analysis")
    parser.add_argument("--duration", type=float, help="Video duration (seconds)")
    parser.add_argument("--max-clips", type=int, default=5, help="Max clips")
    parser.add_argument("-o", "--output", help="Output JSON file")
    parser.add_argument(
        "--raw-output",
        help="File to dump raw Gemini response text (for debugging)",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        if args.video_url:
            if not args.duration:
                parser.error("--duration required with --video-url")
            result = analyze_video(args.video_url, args.duration, args.max_clips)
        elif args.prompt:
            result = send_raw_prompt(args.prompt)
        elif args.prompt_file:
            prompt = Path(args.prompt_file).read_text(encoding="utf-8")
            result = send_raw_prompt(prompt)
        else:
            parser.error("Provide --prompt, --prompt-file, or --video-url")
    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=args.verbose)
        sys.exit(1)

    output_str = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(output_str, encoding="utf-8")
        logger.info(f"Result saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()