"""
AutoCliper Tool: Cari Video YouTube Viral
Dipanggil oleh Hermes toolset autocliper_viral_search.

Mencari video YouTube viral/trending langsung via yt-dlp search.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

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

# Timeout untuk yt-dlp search (detik)
YTDLP_TIMEOUT = int(os.environ.get("YTDLP_SEARCH_TIMEOUT", "45"))


def search_viral(query: str, limit: int = 5, language: str = "") -> list[dict]:
    """Cari video viral di YouTube via yt-dlp search."""
    search_query = f"ytsearch{limit}:{query}"
    if language:
        search_query = f"ytsearch{limit}:{query} {language}"

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--dump-json",
                "--no-playlist",
                "--flat-playlist",
                "--no-warnings",
                search_query,
            ],
            capture_output=True,
            text=True,
            timeout=YTDLP_TIMEOUT,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()[:300]
            return [{"error": f"yt-dlp search gagal: {stderr}"}]

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                videos.append({
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "url": item.get("url") or f"https://www.youtube.com/watch?v={item.get('id', '')}",
                    "channel": item.get("channel") or item.get("uploader", ""),
                    "duration": item.get("duration"),
                    "view_count": item.get("view_count"),
                    "like_count": item.get("like_count"),
                    "upload_date": item.get("upload_date"),
                    "description": (item.get("description") or "")[:150],
                    "source": "youtube",
                })
            except json.JSONDecodeError:
                continue

        # Sort by view_count descending (most viral first)
        videos.sort(key=lambda v: v.get("view_count") or 0, reverse=True)
        return videos[:limit]

    except FileNotFoundError:
        return [{"error": "yt-dlp tidak terinstall. Install: pip install yt-dlp"}]
    except subprocess.TimeoutExpired:
        return [{"error": f"Search timeout setelah {YTDLP_TIMEOUT}s — coba kurangi limit"}]
    except Exception as e:
        return [{"error": f"Search gagal: {e}"}]


def format_results(results: list[dict]) -> str:
    """Format hasil pencarian untuk output ke Hermes/Telegram."""
    if not results:
        return "Tidak ada hasil ditemukan."

    if len(results) == 1 and "error" in results[0]:
        return f"[ERROR] {results[0]['error']}"

    lines = [f"Ditemukan {len(results)} video:\n"]
    for i, video in enumerate(results, 1):
        url = video.get("url", "")
        if not url and video.get("id"):
            url = f"https://www.youtube.com/watch?v={video['id']}"

        title = video.get("title", "Untitled")
        channel = video.get("channel", "")
        duration = video.get("duration")
        views = video.get("view_count")

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

        lines.append(f"{i}. {title}")
        lines.append(f"   Channel: {channel}{duration_str}{views_str}")
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
