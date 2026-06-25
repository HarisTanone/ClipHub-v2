"""SHA-256 keyed filesystem cache with LRU eviction for Free Asset Fetcher."""

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.domain.entities import AssetResult

logger = logging.getLogger(__name__)


class AssetCache:
    """SHA-256 keyed filesystem cache with LRU eviction at configurable max size."""

    def __init__(self, cache_dir: str = "data/asset_cache", max_size_gb: float = 2.0):
        self._cache_dir = Path(cache_dir)
        self._max_size = int(max_size_gb * 1024 * 1024 * 1024)  # bytes
        self._evict_target = int(1.5 * 1024 * 1024 * 1024)  # 1.5 GB
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create cache directory structure on first use."""
        for category in ("footage", "icon", "motion_graphic", "reaction"):
            os.makedirs(self._cache_dir / category, exist_ok=True)

    def compute_key(self, keyword: str, category: str) -> str:
        """SHA-256(lowercase_keyword + category) → hex string."""
        raw = f"{keyword.lower()}{category}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, keyword: str, category: str) -> Optional[AssetResult]:
        """Check cache for an existing entry. Updates last_accessed on hit. Returns AssetResult or None."""
        key = self.compute_key(keyword, category)
        category_dir = self._cache_dir / category
        meta_path = category_dir / f"{key}.meta.json"

        if not meta_path.exists():
            return None

        try:
            meta = self._read_meta(meta_path)
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(f"[AssetCache] Corrupted meta at {meta_path}: {e}")
            return None

        # Resolve the cached asset file
        asset_ext = meta.get("asset_format", "")
        # Map format to file extension
        ext = self._format_to_extension(asset_ext)
        asset_path = category_dir / f"{key}{ext}"

        if not asset_path.exists():
            # Metadata exists but file is missing — clean up orphan
            logger.warning(f"[AssetCache] Orphaned meta (no asset file): {meta_path}")
            meta_path.unlink(missing_ok=True)
            return None

        # Update last_accessed timestamp
        meta["last_accessed"] = datetime.now(timezone.utc).isoformat()
        self._write_meta(meta_path, meta)

        return AssetResult(
            local_path=str(asset_path.resolve()),
            source_api=meta["source_api"],
            license_type=meta["license_type"],
            original_url=meta["original_url"],
            asset_format=meta["asset_format"],
            asset_id=meta.get("asset_id", ""),
            is_fallback=False,
            metadata=meta.get("metadata", {}),
        )

    def put(self, keyword: str, category: str, result: AssetResult) -> None:
        """Store asset file + sidecar .meta.json in cache. Updates result.local_path to cached location."""
        key = self.compute_key(keyword, category)
        category_dir = self._cache_dir / category
        os.makedirs(category_dir, exist_ok=True)

        ext = self._format_to_extension(result.asset_format)
        dest_path = category_dir / f"{key}{ext}"
        meta_path = category_dir / f"{key}.meta.json"

        # Copy file to cache (skip if source is already the cache path)
        source = Path(result.local_path)
        if source.exists() and source.resolve() != dest_path.resolve():
            shutil.copy2(str(source), str(dest_path))

        # Get file size
        file_size = dest_path.stat().st_size if dest_path.exists() else 0

        # Write sidecar metadata
        now_iso = datetime.now(timezone.utc).isoformat()
        meta = {
            "keyword": keyword,
            "category": category,
            "source_api": result.source_api,
            "license_type": result.license_type,
            "original_url": result.original_url,
            "asset_id": result.asset_id,
            "asset_format": result.asset_format,
            "fetched_at": now_iso,
            "last_accessed": now_iso,
            "file_size_bytes": file_size,
        }
        self._write_meta(meta_path, meta)

        # Update result to point to cached location
        result.local_path = str(dest_path.resolve())

        # Check if eviction is needed
        total = self.get_cache_size()
        if total > self._max_size:
            self.evict_lru()

        logger.debug(f"[AssetCache] PUT {category}/{key[:12]}… ({file_size} bytes)")

    def evict_lru(self) -> None:
        """Evict least-recently-used entries until cache is under evict_target (1.5GB)."""
        entries = self._collect_all_entries()
        if not entries:
            return

        # Sort by last_accessed ascending (oldest first)
        entries.sort(key=lambda e: e["last_accessed"])

        total_size = sum(e["file_size"] for e in entries)
        evicted_count = 0

        for entry in entries:
            if total_size <= self._evict_target:
                break

            # Delete asset file and meta file
            asset_path = Path(entry["asset_path"])
            meta_path = Path(entry["meta_path"])

            file_size = entry["file_size"]
            asset_path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)

            total_size -= file_size
            evicted_count += 1

        if evicted_count > 0:
            logger.info(f"[AssetCache] Evicted {evicted_count} entries. New size: {total_size / (1024**3):.2f} GB")

    def get_cache_size(self) -> int:
        """Sum all file sizes in cache directory (bytes). Excludes .meta.json files."""
        total = 0
        for path in self._cache_dir.rglob("*"):
            if path.is_file() and not path.name.endswith(".meta.json"):
                total += path.stat().st_size
        return total

    # ─── Private Helpers ──────────────────────────────────────────────────

    def _collect_all_entries(self) -> list[dict]:
        """Collect all cached entries with their metadata for eviction sorting."""
        entries = []
        for meta_path in self._cache_dir.rglob("*.meta.json"):
            try:
                meta = self._read_meta(meta_path)
                # Find the corresponding asset file
                key = meta_path.stem.replace(".meta", "")
                ext = self._format_to_extension(meta.get("asset_format", ""))
                asset_path = meta_path.parent / f"{key}{ext}"

                if not asset_path.exists():
                    # Orphan meta — clean up
                    meta_path.unlink(missing_ok=True)
                    continue

                entries.append({
                    "meta_path": str(meta_path),
                    "asset_path": str(asset_path),
                    "last_accessed": meta.get("last_accessed", "1970-01-01T00:00:00"),
                    "file_size": asset_path.stat().st_size,
                })
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[AssetCache] Error reading {meta_path}: {e}")
                continue
        return entries

    @staticmethod
    def _format_to_extension(asset_format: str) -> str:
        """Map asset_format to file extension."""
        mapping = {
            "video": ".mp4",
            "png": ".png",
            "svg": ".svg",
            "gif": ".gif",
            "lottie": ".json",
            "text": ".txt",
        }
        return mapping.get(asset_format, ".bin")

    @staticmethod
    def _read_meta(meta_path: Path) -> dict:
        """Read and parse a sidecar .meta.json file."""
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_meta(meta_path: Path, meta: dict) -> None:
        """Write sidecar .meta.json file atomically."""
        tmp_path = meta_path.with_suffix(".meta.json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        tmp_path.replace(meta_path)
