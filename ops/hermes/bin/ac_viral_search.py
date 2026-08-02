"""
AutoCliper Tool: Cari Video YouTube Viral
Dipanggil oleh Hermes toolset autocliper_viral_search.

Menggunakan ClipScout API untuk mencari video YouTube viral/trending.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import httpx

# Load .env dari HERMES_HOME
_hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
_env_file = os.path.join(_hermes_home, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

CLIPSCOUT_API_URL = os.environ.get(
    "CLIPSCOUT_API_URL", "https://www.clipscout.app/api/search"
)
CLIPSCOUT_TIMEOUT = int(os.environ.get("CLIPSCOUT_TIMEOUT", "15"))


def search_viral(query: str, limit: int = 5, language: str = "") -> list[dict]:
    """Cari video viral via ClipScout API."""
    params = {
        "q": query,
        "limit": min(limit, 10),
        "sources": "youtube_cc,youtube_protected",
    }
    if language:
        params["lang"] = language

    try:
        resp = httpx.get(CLIPSCOUT_API_URL, params=params, timeout=CLIPSCOUT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or data.get("items") or []
        return results[:limit]
    except httpx.HTTPStatusError as e:
        return [{"error": f"ClipScout API error {e.response.status_code}: {e.response.text[:200]}"}]
    except Exception as e:
        # Fallback: cari via yt-dlp jika ClipScout tidak tersedia
        return _fallback_ytdlp_search(query, limit, language)


def _fallback_ytdlp_search(query: str, limit: int, language: str) -> list[dict]:
    """Fallback: gunakan yt-dlp untuk search YouTube."""
    try:
        import subprocess
        search_query = f"ytsearch{limit}:{query}"
        if language:
            search_query = f"ytsearch{limit}:{query} {language}"

        result = subprocess.run(
            [
                "yt-dlp",
                "--dump-json",
                "--no-playlist",
                "--flat-playlist",
                search_query,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return [{"error": f"yt-dlp search gagal: {result.stderr[:200]}"}]

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                videos.append({
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "url": f"https://www.youtube.com/watch?v={item.get('id', '')}",
                    "channel": item.get("channel") or item.get("uploader", ""),
                    "duration": item.get("duration"),
                    "view_count": item.get("view_count"),
                    "source": "youtube_search",
                })
            except json.JSONDecodeError:
                continue
        return videos
    except Exception as e:
        return [{"error": f"Fallback search gagal: {e}"}]


def format_results(results: list[dict]) -> str:
    """Format hasil pencarian untuk output ke Hermes."""
    if not results:
        return "Tidak ada hasil ditemukan."

    if len(results) == 1 and "error" in results[0]:
        return f"Error: {results[0]['error']}"

    lines = [f"Ditemukan {len(results)} video:\n"]
    for i, video in enumerate(results, 1):
        url = video.get("url") or video.get("webpage_url") or ""
        if not url and video.get("id"):
            url = f"https://www.youtube.com/watch?v={video['id']}"

        title = video.get("title", "Untitled")
        channel = video.get("channel") or video.get("uploader") or video.get("channel_title", "")
        duration = video.get("duration")
        views = video.get("view_count") or video.get("views")
        virality = video.get("virality_score") or video.get("score")

        duration_str = ""
        if duration:
            m, s = divmod(int(duration), 60)
            duration_str = f" | {m}:{s:02d}"

        views_str = ""
        if views:
            if views >= 1_000_000:
                views_str = f" | {views/1_000_000:.1f}M views"
            elif views >= 1_000:
                views_str = f" | {views/1_000:.0f}K views"
            else:
                views_str = f" | {views} views"

        virality_str = f" | Virality: {virality:.1f}" if virality else ""

        lines.append(f"{i}. {title}")
        lines.append(f"   Channel: {channel}{duration_str}{views_str}{virality_str}")
        lines.append(f"   URL: {url}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Cari video YouTube viral")
    parser.add_argument("--query", required=True, help="Keyword pencarian")
    parser.add_argument("--limit", type=int, default=5, help="Jumlah hasil")
    parser.add_argument("--language", default="", help="Filter bahasa (id/en)")
    args = parser.parse_args()

    results = search_viral(args.query, args.limit, args.language)
    print(format_results(results))

    # Output JSON ke stderr untuk Hermes tool response metadata
    print(json.dumps({"count": len(results), "results": results}), file=sys.stderr)


if __name__ == "__main__":
    main()
