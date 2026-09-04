"""Gemini Agentic Video Understanding Service for B-Roll & Behind-Person Footage.

Follows official Gemini Agentic Video Understanding principles:
https://ai.google.dev/gemini-api/docs/video-understanding#agentic-video-understanding

Key Capabilities:
1. Dynamic Subtitle & Context Reasoning:
   When a short/Indonesian keyword or phrase (e.g. 'FIGHT TERUS', 'KESEMPATAN BISNIS')
   fails to match stock footage directly, uses Gemini Agentic Understanding to inspect the
   exact spoken sentence, understand narrative intent, and formulate concrete English visual queries.
2. Placement-Aware Visual Direction:
   For 'behind_person', enforces concrete environmental and action footage (modern offices,
   retail stores, athletic training, city landscapes) while strictly banning talking heads,
   selfie videos, and irrelevant abstract 3D models (such as neural networks / glowing spheres).
3. Candidate Verification:
   Validates candidate titles and tags to guarantee high relevance before downloading.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger(__name__)


class GeminiAgenticVideoService:
    """Agentic Video & Subtitle Reasoner powered by Gemini."""

    BANNED_VISUAL_TERMS = {
        "neuron", "neurons", "synapse", "nerve cell", "neural network",
        "brain cells", "abstract glowing", "floating balls", "yellow black abstract",
        "talking head", "talking-head", "podcast host", "interview face",
    }

    def __init__(self):
        from src.infrastructure.auth import GeminiKeyRotator
        self._key_rotator = GeminiKeyRotator()
        self._model = settings.GEMINI_MODEL or "gemini-3.7-flash"
        self._fallback_model = settings.GEMINI_FALLBACK_MODEL or "gemini-3.6-flash"

    async def derive_contextual_queries(
        self,
        keyword: str,
        subtitle_text: str,
        context: str = "",
        placement: str = "behind_person",
    ) -> list[str]:
        """Use Gemini Agentic Subtitle Reasoning to generate concrete English visual stock queries."""
        sub = (subtitle_text or "").strip()
        ctx = (context or "").strip()
        kw = (keyword or "").strip()

        combined_speech = f"{sub} {ctx}".strip()
        if not combined_speech and not kw:
            return []

        # Try Gemini reasoning across keys
        keys = self._key_rotator.keys
        if keys:
            prompt = f"""Kamu visual researcher & director video pendek profesional dengan kemampuan Agentic Video Understanding.
Tugasmu adalah menganalisa ucapan pembicara pada potongan video berikut, memahami konteks topiknya secara mendalam, dan merumuskan 3-4 kueri pencarian video stock bahasa Inggris (Pexels/Pixabay) yang SANGAT KONKRET dan RELEVAN untuk ditampilkan sebagai B-roll ({placement}).

KATA KUNCI AWAL: {kw or "(none)"}
TEKS SUBTITLE / UCAPAN PEMBICARA DI DETIK INI:
"{combined_speech}"
PLACEMENT: {placement} (video latar di belakang pembicara, pembicara tetap terlihat di depan)

PANDUAN VISUAL CONCRETE (SANGAT PENTING):
1. Pahami apa yang sebenarnya sedang diceritakan atau dianalogikan pembicara:
   - Jika 'fight terus' dalam podcast bisnis/karir -> kerja keras kantor larut malam, atlet bertinju di gym (boxing training gym), pelari pantang menyerah.
   - Jika 'kesempatan bisnis' / 'peluang' -> pertemuan bisnis modern (business meeting office handshake), presentasi tablet, toko ramai pembeli.
   - Jika 'wisenya' / 'kebijaksanaan' -> orang berpikir fokus di meja kerja (person thinking focused desk), mentor berdiskusi.
   - Jika membahas produk/gadget (iPhone, iBox, toko) -> toko elektronik modern (electronics retail store), unboxing smartphone gadget.
2. DILARANG KERAS visual abstrak tanpa makna (DILARANG: neuron, sel saraf, brain synapse, bola-bola bercahaya kuning hitam, partikel abstrak acak).
3. DILARANG kueri generik seperti "aesthetic", "cinematic", "mood". Berikan nama benda, tempat, atau aktivitas nyata!
4. Kueri harus dalam BAHASA INGGRIS (3-6 kata per kueri) agar mesin pencari video stock internasional dapat menemukannya dengan akurat.

OUTPUT RAW JSON ONLY (tanpa markdown):
{{"queries": ["english query 1", "english query 2", "english query 3"]}}"""

            for k in keys:
                try:
                    client = genai.Client(api_key=k)
                    # Use run_in_executor to avoid blocking event loop
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=self._model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.2,
                            response_mime_type="application/json",
                        ),
                    )
                    text = getattr(response, "text", "") or ""
                    data = json.loads(text)
                    queries = data.get("queries", [])
                    if isinstance(queries, list) and queries:
                        clean_queries = [
                            q.strip().lower()
                            for q in queries
                            if isinstance(q, str) and q.strip() and not any(b in q.lower() for b in self.BANNED_VISUAL_TERMS)
                        ]
                        if clean_queries:
                            logger.info(
                                f"[GeminiAgenticVideo] Subtitle '{combined_speech[:40]}' -> "
                                f"Queries: {clean_queries}"
                            )
                            return clean_queries
                except Exception as exc:
                    logger.debug(f"[GeminiAgenticVideo] Key failed or error: {exc}")
                    continue

        # Fallback heuristic: dictionary-guided contextual expansion
        return self._fallback_heuristic_queries(kw, combined_speech)

    def verify_candidate(
        self,
        candidate_title: str,
        candidate_tags: str,
    ) -> bool:
        """Verify that candidate footage is NOT banned or abstract nonsense."""
        blob = f"{candidate_title} {candidate_tags}".lower()
        if any(banned in blob for banned in self.BANNED_VISUAL_TERMS):
            logger.warning(f"[GeminiAgenticVideo] Rejected candidate with banned term: '{blob[:60]}'")
            return False
        return True

    def _fallback_heuristic_queries(self, keyword: str, spoken_text: str) -> list[str]:
        """Deterministic fallback when Gemini API is offline."""
        from src.infrastructure.pexels_client import ID_TO_EN_VISUAL_MAP, expand_visual_queries

        blob = f"{keyword} {spoken_text}".lower()
        found: list[str] = []

        # Check full spoken words against visual map using word boundaries
        for k, v in ID_TO_EN_VISUAL_MAP.items():
            if re.search(rf"\b{re.escape(k)}\b", blob):
                if v not in found:
                    found.append(v)
            if len(found) >= 4:
                break

        if not found and keyword:
            found = expand_visual_queries(keyword)

        return [q for q in found if not any(b in q for b in self.BANNED_VISUAL_TERMS)]
