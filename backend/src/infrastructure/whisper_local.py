"""WhisperLocal — Local transcription with whisper.cpp or faster-whisper fallback."""
import asyncio
import json
import logging
import os
import re
import subprocess
from typing import Optional

from src.config import settings
from src.domain.interfaces import IWhisperLocal

logger = logging.getLogger(__name__)


class WhisperLocal(IWhisperLocal):
    def __init__(self):
        self.model_path = settings.WHISPER_MODEL_PATH
        self.whisper_binary = self._find_binary()
        self.n_threads = settings.WHISPER_THREADS
        self._subprocess_env = self._build_subprocess_env()
        self._faster_whisper_model = None
        self._use_faster_whisper = not self._is_binary_working()

        if self._use_faster_whisper:
            logger.info("whisper_backend: faster-whisper (Python)")
        else:
            logger.info(f"whisper_backend: whisper.cpp ({self.whisper_binary})")

    def _build_subprocess_env(self) -> dict:
        """Build environment dict with DYLD_LIBRARY_PATH for whisper.cpp shared libs.

        The whisper-cli binary may have incorrect @rpath if built at a different
        location. We resolve all lib directories from the binary's parent path.
        """
        env = os.environ.copy()
        if not self.whisper_binary:
            return env

        # Derive library paths from the binary location
        # Binary: .../whisper.cpp/build/bin/whisper-cli
        # Libs:   .../whisper.cpp/build/src/libwhisper.*.dylib
        #         .../whisper.cpp/build/ggml/src/libggml.*.dylib
        build_dir = os.path.dirname(os.path.dirname(self.whisper_binary))  # .../build
        lib_paths = [
            os.path.join(build_dir, "src"),
            os.path.join(build_dir, "ggml", "src"),
            os.path.join(build_dir, "ggml", "src", "ggml-blas"),
            os.path.join(build_dir, "ggml", "src", "ggml-metal"),
        ]
        # Filter to paths that actually exist
        valid_paths = [p for p in lib_paths if os.path.isdir(p)]
        if valid_paths:
            existing = env.get("DYLD_LIBRARY_PATH", "")
            new_path = ":".join(valid_paths)
            env["DYLD_LIBRARY_PATH"] = f"{new_path}:{existing}" if existing else new_path

        return env

    def _is_binary_working(self) -> bool:
        """Check if whisper.cpp binary actually works."""
        if not self.whisper_binary or not os.path.exists(self.whisper_binary):
            return False
        try:
            r = subprocess.run(
                [self.whisper_binary, "--help"],
                capture_output=True, timeout=5,
                env=self._subprocess_env,
            )
            return r.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def _find_binary(self) -> str:
        """Auto-detect whisper.cpp binary."""
        candidates = [
            settings.WHISPER_BINARY_PATH,
            "./whisper.cpp/build/bin/whisper-cli",
            "./whisper.cpp/build/bin/main",
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return ""

    async def transcribe_clip(self, audio_path: str) -> list[dict]:
        """Transcribe single clip audio → segments with word-level timestamps."""
        loop = asyncio.get_event_loop()
        if self._use_faster_whisper:
            # Add timeout to prevent hanging on large clips
            try:
                return await asyncio.wait_for(
                    loop.run_in_executor(None, self._transcribe_faster_whisper, audio_path),
                    timeout=300  # 5 minute max per clip
                )
            except asyncio.TimeoutError:
                logger.error(f"faster_whisper_timeout: {audio_path} exceeded 300s")
                return []
        return await loop.run_in_executor(None, self._transcribe_sync, audio_path)

    def _transcribe_faster_whisper(self, audio_path: str) -> list[dict]:
        """Transcribe using faster-whisper Python library."""
        try:
            from faster_whisper import WhisperModel

            if self._faster_whisper_model is None:
                model_size = settings.WHISPER_MODEL_SIZE
                logger.info(f"Loading faster-whisper model: {model_size}")
                self._faster_whisper_model = WhisperModel(
                    model_size, device="cpu", compute_type="float32",
                    num_workers=1, cpu_threads=settings.WHISPER_THREADS
                )

            # Convert to WAV 16kHz mono (required for reliable transcription)
            wav_path = audio_path.rsplit(".", 1)[0] + "_whisper.wav"
            convert_cmd = [
                "ffmpeg", "-y", "-i", audio_path,
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                wav_path
            ]
            result = subprocess.run(convert_cmd, capture_output=True, timeout=120)
            if result.returncode != 0 or not os.path.exists(wav_path):
                logger.error(f"WAV conversion failed: {result.stderr.decode()[:200]}")
                return []

            try:
                segs, info = self._faster_whisper_model.transcribe(
                    wav_path, word_timestamps=True, language="id"
                )

                segments = []
                for seg in segs:
                    words = []
                    for w in (seg.words or []):
                        word_text = w.word.strip()
                        if word_text:
                            words.append({
                                "word": word_text,
                                "start": round(w.start, 3),
                                "end": round(w.end, 3),
                            })

                    if words:
                        segments.append({
                            "start": round(seg.start, 2),
                            "end": round(seg.end, 2),
                            "text": seg.text.strip(),
                            "words": words,
                        })

                logger.info(f"faster_whisper_done: {len(segments)} segments, lang={info.language}")
                return segments
            finally:
                # Cleanup WAV file
                if os.path.exists(wav_path):
                    os.remove(wav_path)

        except ImportError:
            logger.error("faster-whisper not installed, cannot transcribe")
            return []
        except Exception as e:
            logger.error(f"faster_whisper_error: {e}")
            return []

    def _transcribe_sync(self, audio_path: str) -> list[dict]:
        """Synchronous whisper.cpp transcription."""
        # Convert to WAV 16kHz mono if needed
        wav_path = audio_path.rsplit(".", 1)[0] + "_16k.wav"
        self._convert_to_wav(audio_path, wav_path)

        try:
            output_base = wav_path.rsplit(".", 1)[0]
            json_path = f"{output_base}.json"

            # Run whisper.cpp (whisper-cli)
            cmd = [
                self.whisper_binary,
                "-m", self.model_path,
                "-f", wav_path,
                "-t", str(self.n_threads),
                "-oj",       # Output JSON
                "-ojf",      # Full JSON (includes tokens/words)
                "-of", output_base,
                "--language", "auto",
            ]

            # GPU flag for production (CUDA)
            if settings.WHISPER_USE_GPU:
                cmd.append("--gpu")

            logger.info(f"Running whisper.cpp: {os.path.basename(audio_path)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                env=self._subprocess_env,
            )

            if result.returncode != 0:
                logger.error(f"Whisper gagal: {result.stderr[:300]}")
                return []

            if not os.path.exists(json_path):
                logger.error(f"Whisper JSON output tidak ditemukan: {json_path}")
                return []

            # Parse whisper.cpp JSON output (may have trailing comma issue)
            with open(json_path) as f:
                content = f.read()

            whisper_output = self._safe_parse_json(content)
            if not whisper_output:
                logger.error("Gagal parse Whisper JSON output")
                return []

            segments = self._parse_whisper_json(whisper_output)

            # Cleanup temp files
            self._cleanup(wav_path, json_path)

            return segments

        except subprocess.TimeoutExpired:
            logger.error("Whisper timeout")
            self._cleanup(wav_path)
            return []
        except Exception as e:
            logger.error(f"Whisper error: {e}")
            self._cleanup(wav_path)
            return []

    def _safe_parse_json(self, content: str) -> Optional[dict]:
        """Parse JSON with tolerance for trailing commas."""
        # Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Fix trailing commas: ,\n] or ,\n}
        import re as re_mod
        fixed = re_mod.sub(r',(\s*[}\]])', r'\1', content)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # Try extracting just the transcription array
        try:
            idx = content.find('"transcription"')
            if idx > 0:
                # Wrap in minimal object
                arr_start = content.find('[', idx)
                if arr_start > 0:
                    # Find matching bracket
                    bracket_count = 0
                    for i in range(arr_start, len(content)):
                        if content[i] == '[':
                            bracket_count += 1
                        elif content[i] == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                arr_str = content[arr_start:i+1]
                                arr_fixed = re_mod.sub(r',(\s*[}\]])', r'\1', arr_str)
                                arr = json.loads(arr_fixed)
                                return {"transcription": arr}
                                break
        except (json.JSONDecodeError, ValueError):
            pass

        return None

    def _convert_to_wav(self, input_path: str, output_path: str) -> None:
        """Convert audio to WAV 16kHz mono for whisper.cpp."""
        if os.path.exists(output_path):
            return
        os.makedirs(settings.WAV_DIR, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    def _parse_whisper_json(self, whisper_output: dict) -> list[dict]:
        """Parse whisper.cpp JSON → [{start, end, text, words: [{word, start, end}]}]."""
        raw_segments = whisper_output.get("transcription", [])
        if not raw_segments and isinstance(whisper_output, list):
            raw_segments = whisper_output

        segments = []
        for seg in raw_segments:
            text = seg.get("text", "").strip()
            if not text:
                continue

            # whisper-cli format: offsets.from/to in milliseconds
            offsets = seg.get("offsets", {})
            start = offsets.get("from", 0) / 1000.0
            end = offsets.get("to", 0) / 1000.0

            # Parse tokens into words
            words = []
            if "tokens" in seg:
                current_word = None
                for token in seg["tokens"]:
                    token_text = token.get("text", "")
                    if self._should_skip_token(token_text):
                        continue

                    t_offsets = token.get("offsets", {})
                    t_start = t_offsets.get("from", 0) / 1000.0
                    t_end = t_offsets.get("to", 0) / 1000.0

                    # New word starts with space or is first token
                    if token_text.startswith(" ") or not current_word:
                        if current_word and current_word["word"].strip():
                            words.append(current_word)
                        current_word = {
                            "word": token_text.strip(),
                            "start": round(t_start, 2),
                            "end": round(t_end, 2),
                        }
                    else:
                        if current_word:
                            current_word["word"] += token_text
                            current_word["end"] = round(t_end, 2)

                if current_word and current_word["word"].strip():
                    words.append(current_word)

            segments.append({
                "start": round(start, 2),
                "end": round(end, 2),
                "text": text,
                "words": words,
            })

        return segments

    def _should_skip_token(self, text: str) -> bool:
        """Skip special tokens."""
        if not text or not text.strip():
            return True
        skip_patterns = [
            r"\[_TT_\d+\]",
            r"\[_BEG_\]",
            r"\[_END_\]",
            r"\[_SOT_\]",
            r"\[_EOT_\]",
            r"<\|\d+\.\d+\|>",
            r"\[BLANK_AUDIO\]",
        ]
        for pattern in skip_patterns:
            if re.match(pattern, text.strip()):
                return True
        return False

    def _cleanup(self, *paths: str) -> None:
        """Remove temp files."""
        for path in paths:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
