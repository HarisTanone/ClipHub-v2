"""BatchHighlightProcessor — batches multiple clips into single Gemini highlight request."""
import logging
import re
from typing import Any, Callable, Awaitable, Dict, List, Optional

logger = logging.getLogger(__name__)


class BatchHighlightProcessor:
    """Batches multiple clips into single Gemini highlight request."""
    MAX_BATCH_SIZE = 5

    def __init__(self, gemini_call: Optional[Callable[..., Awaitable[str]]] = None):
        self._gemini_call = gemini_call

    async def process_batch(self, clips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Send batched prompt, parse per-clip results, fallback individually on failure.
        
        Args:
            clips: List of clip data dicts with at least 'index' and 'transcript' keys.
        Returns:
            List of highlight results per clip.
        """
        if not clips:
            return []
        if not self._gemini_call:
            logger.warning("batch_no_gemini_call")
            return [{} for _ in clips]

        # Split into batches of MAX_BATCH_SIZE
        results: List[Dict[str, Any]] = [{}] * len(clips)
        
        for batch_start in range(0, len(clips), self.MAX_BATCH_SIZE):
            batch = clips[batch_start:batch_start + self.MAX_BATCH_SIZE]
            batch_indices = list(range(batch_start, batch_start + len(batch)))
            
            # Try batch request
            batch_results = await self._process_single_batch(batch)
            
            if batch_results is None:
                # Total failure — fallback to individual
                logger.warning("batch_total_failure", extra={"batch_size": len(batch), "fallback": "individual"})
                for i, clip in enumerate(batch):
                    individual = await self._process_individual(clip)
                    results[batch_indices[i]] = individual or {}
            else:
                # Accept partial results, reprocess missing
                for i, clip in enumerate(batch):
                    if i < len(batch_results) and batch_results[i]:
                        results[batch_indices[i]] = batch_results[i]
                    else:
                        logger.info("batch_missing_clip", extra={"clip_index": batch_indices[i]})
                        individual = await self._process_individual(clip)
                        results[batch_indices[i]] = individual or {}

        return results

    async def _process_single_batch(self, batch: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Send batch prompt to Gemini, parse response."""
        prompt = self._build_batch_prompt(batch)
        
        try:
            response = await self._gemini_call(prompt)
            logger.info("batch_request_sent", extra={"batch_size": len(batch), "response_len": len(response)})
            parsed = self._parse_batch_response(response, len(batch))
            return parsed
        except Exception as e:
            logger.error("batch_request_failed", extra={"error": str(e)})
            return None

    async def _process_individual(self, clip: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process single clip (fallback)."""
        prompt = f"[CLIP_1]\n{clip.get('transcript', '')}\n[/CLIP_1]"
        try:
            response = await self._gemini_call(prompt)
            parsed = self._parse_batch_response(response, 1)
            return parsed[0] if parsed else None
        except Exception as e:
            logger.error("individual_request_failed", extra={"error": str(e)})
            return None

    def _build_batch_prompt(self, batch: List[Dict[str, Any]]) -> str:
        """Build prompt with indexed [CLIP_N] delimiters."""
        parts = []
        for i, clip in enumerate(batch, 1):
            parts.append(f"[CLIP_{i}]\n{clip.get('transcript', '')}\n[/CLIP_{i}]")
        return "\n\n".join(parts)

    def _parse_batch_response(self, response: str, expected_count: int) -> List[Dict[str, Any]]:
        """Parse per-clip results from [CLIP_N] delimited response."""
        results: List[Dict[str, Any]] = []
        
        for i in range(1, expected_count + 1):
            pattern = rf"\[CLIP_{i}\](.*?)\[/CLIP_{i}\]"
            match = re.search(pattern, response, re.DOTALL)
            if match:
                content = match.group(1).strip()
                results.append({"highlight": content, "index": i})
            else:
                results.append({})
        
        return results
