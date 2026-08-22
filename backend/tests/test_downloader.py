import pytest
from src.infrastructure.downloader import extract_youtube_video_id, get_canonical_youtube_url, YouTubeDownloader


def test_extract_youtube_video_id_standard():
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=LLXkkvMXGsA") == "LLXkkvMXGsA"
    assert extract_youtube_video_id("https://youtu.be/LLXkkvMXGsA") == "LLXkkvMXGsA"
    assert extract_youtube_video_id("https://www.youtube.com/shorts/LLXkkvMXGsA") == "LLXkkvMXGsA"
    assert extract_youtube_video_id("https://youtube.com/embed/LLXkkvMXGsA") == "LLXkkvMXGsA"
    assert extract_youtube_video_id("LLXkkvMXGsA") == "LLXkkvMXGsA"


def test_extract_youtube_video_id_dirty_pasted_string():
    dirty = (
        "https://www.Oleh-oleh Cerita Dari Australia 57:44 Source "
        "https://www.youtube.com/watch?v=LLXkkvMXGsA Oleh-oleh Cerita Dari Australia "
        "Raditya Dika 57:44 530K views Gabung di membership Youtube Raditya Dika: "
        "https://www.youtube.com/channel/UC0rzsIrAxF4kCsALP6J2EsA/join Beli koleksi Stand Up Comedy Raditya Dika"
    )
    assert extract_youtube_video_id(dirty) == "LLXkkvMXGsA"
    assert get_canonical_youtube_url(dirty) == "https://www.youtube.com/watch?v=LLXkkvMXGsA"


@pytest.mark.asyncio
async def test_validate_url_dirty_string_validation():
    downloader = YouTubeDownloader()
    dirty = "Oleh-oleh Cerita Dari Australia https://www.youtube.com/watch?v=dQw4w9WgXcQ Raditya Dika"
    valid, title, duration = await downloader.validate_url(dirty)
    assert valid is True
    assert title != ""
    assert duration is not None
