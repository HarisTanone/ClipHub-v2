"""Hook Optimizer — AI rewrite hook text to maximize scroll-stopping power.

Uses the configured 9router LLM to rewrite hook text into more viral format.
Techniques: curiosity gap, shock value, question format, number hook, challenge.
"""
import json
import logging
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)

OPTIMIZER_PROMPT = """Kamu adalah copywriter viral shorts/reels. Rewrite hook text berikut menjadi lebih SCROLL-STOPPING.

RULES:
- Maksimal 8 kata (pendek, punchy)
- Gunakan salah satu teknik: pertanyaan, shock, angka, tantangan, atau curiosity gap
- Bahasa Indonesia (sesuai input)
- JANGAN tambah emoji
- JANGAN ubah makna/topik
- Output HANYA 1 baris teks hook (tanpa penjelasan)

CONTOH REWRITE:
- "Cara Memperbaiki Kabel USB" → "Kabel Putus? 1 Trik Bikin Hidup Lagi!"
- "Tips Hemat Listrik di Rumah" → "Tagihan Listrik Turun 50%? Ini Rahasianya"
- "Review iPhone 15 Pro" → "iPhone 15 Pro: Worth It atau Buang Duit?"
- "Olahraga untuk Pemula" → "5 Menit Sehari, Badan Berubah Total"
- "Kenapa Kita Sering Lupa" → "Otak Kamu Sengaja Bikin Kamu Lupa!"

HOOK ASLI:
{hook_text}

REWRITE (1 baris saja):"""


class HookOptimizer:
    """Rewrite hooks using 9router for maximum viral potential."""

    def __init__(self):
        self._client = None

    def _init_client(self):
        """Initialize the configured 9router client."""
        if self._client:
            return
        try:
            if not settings.use_nine_router:
                return
            from src.infrastructure.nine_router_client import get_nine_router_client
            client = get_nine_router_client()
            if client.is_configured:
                self._client = client
        except Exception as e:
            logger.warning(f"hook_optimizer: failed to init client: {e}")

    def optimize_hooks(self, clips: list, max_clips: int = 10) -> dict[int, str]:
        """Rewrite hooks for multiple clips in one batch call.

        Args:
            clips: List of Clip objects with .rank and .hook
            max_clips: Max clips to optimize

        Returns:
            {rank: optimized_hook_text} dict
        """
        self._init_client()
        if not self._client:
            return {}

        # Build batch prompt
        hooks_to_optimize = []
        for clip in clips[:max_clips]:
            if clip.hook and len(clip.hook) > 5:
                hooks_to_optimize.append((clip.rank, clip.hook))

        if not hooks_to_optimize:
            return {}

        # Try batch approach (all hooks in one call)
        try:
            result = self._batch_optimize(hooks_to_optimize)
            if result:
                return result
        except Exception as e:
            logger.warning(f"hook_optimizer: batch failed: {e}")

        # Fallback: optimize individually
        results = {}
        for rank, hook in hooks_to_optimize[:5]:  # Limit individual calls
            try:
                optimized = self._optimize_single(hook)
                if optimized and len(optimized) > 3:
                    results[rank] = optimized
            except Exception:
                pass

        return results

    def _batch_optimize(self, hooks: list[tuple[int, str]]) -> Optional[dict[int, str]]:
        """Optimize all hooks in a single 9router call."""
        batch_prompt = """Kamu adalah copywriter viral shorts. Rewrite SEMUA hook berikut menjadi lebih SCROLL-STOPPING.

RULES:
- Maksimal 8 kata per hook
- Gunakan teknik: pertanyaan, shock, angka, tantangan, atau curiosity gap
- Bahasa Indonesia
- JANGAN tambah emoji
- Output JSON object dengan format: {"hooks": [{"rank": N, "hook": "..."}]}

HOOKS:
"""
        for rank, hook in hooks:
            batch_prompt += f"  {rank}. {hook}\n"

        batch_prompt += "\nOUTPUT (JSON object saja):"

        text = self._client.chat(
            model=settings.NINE_ROUTER_AI_LAYER_MODEL or settings.nine_router_model,
            messages=[{"role": "user", "content": batch_prompt}],
            temperature=0.3,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )

        if not text:
            return None

        # Parse JSON response
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                items = data.get("hooks", [])
            elif isinstance(data, list):
                items = data
            else:
                items = []
            return {
                item["rank"]: item["hook"]
                for item in items
                if isinstance(item, dict) and "rank" in item and "hook" in item
            }
        except (json.JSONDecodeError, KeyError):
            return None

    def _optimize_single(self, hook_text: str) -> Optional[str]:
        """Optimize a single hook."""
        prompt = OPTIMIZER_PROMPT.format(hook_text=hook_text)
        result = self._client.chat(
            model=settings.NINE_ROUTER_AI_LAYER_MODEL or settings.nine_router_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=120,
        )

        if result:
            result = result.strip().strip('"').strip("'")
            # Sanity check — not too long, not empty
            if 3 < len(result) < 100:
                return result
        return None
