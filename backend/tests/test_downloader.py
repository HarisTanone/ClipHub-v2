import asyncio
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


@pytest.mark.asyncio
async def test_vidkraken_client_initialization(monkeypatch):
    from src.infrastructure.vidkraken_client import VidKrakenClient
    from src.config import settings
    monkeypatch.setattr(settings, "VIDKRAKEN_ENABLED", True)
    client = VidKrakenClient()
    assert client.is_enabled is True
    assert client.api_key == "ce1bcba1-b808-470f-987c-072ca2d35488"
    assert "vidkraken.com" in client.base_url


@pytest.mark.asyncio
async def test_vidkraken_download_video_mocked(monkeypatch, tmp_path):
    from src.infrastructure.vidkraken_client import VidKrakenClient
    from src.config import settings
    monkeypatch.setattr(settings, "VIDKRAKEN_ENABLED", True)
    client = VidKrakenClient()
    output_file = str(tmp_path / "test_vid.mp4")

    # Mock enqueue, poll, and stream_download
    enqueue_calls = []

    async def mock_enqueue(url, fmt="1080"):
        enqueue_calls.append(fmt)
        return {"jobId": "test_job_123", "status": "IN_QUEUE"}

    async def mock_poll(job_id, timeout=None, poll_interval=2.0):
        return {
            "jobId": job_id,
            "status": "COMPLETED",
            "downloadUrl": "https://proxy.vidkraken.com/media/test.mp4",
            "format": "1080",
        }

    async def mock_stream(download_url, out_path, timeout=300.0):
        with open(out_path, "wb") as f:
            f.write(b"\x00" * 1024)
        return True

    monkeypatch.setattr(client, "enqueue_download", mock_enqueue)
    monkeypatch.setattr(client, "poll_job", mock_poll)
    monkeypatch.setattr(client, "stream_download_file", mock_stream)

    success = await client.download_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_file)
    assert success is True
    assert enqueue_calls == ["1080"]


@pytest.mark.asyncio
async def test_vidkraken_fallback_to_720_on_1080_fail(monkeypatch, tmp_path):
    from src.infrastructure.vidkraken_client import VidKrakenClient
    from src.config import settings
    monkeypatch.setattr(settings, "VIDKRAKEN_ENABLED", True)
    client = VidKrakenClient()
    output_file = str(tmp_path / "test_vid.mp4")

    enqueue_calls = []

    async def mock_enqueue(url, fmt="1080"):
        enqueue_calls.append(fmt)
        if fmt == "1080":
            raise RuntimeError("1080 format unavailable on VidKraken")
        return {"jobId": "test_job_720", "status": "IN_QUEUE"}

    async def mock_poll(job_id, timeout=None, poll_interval=2.0):
        return {
            "jobId": job_id,
            "status": "COMPLETED",
            "downloadUrl": "https://proxy.vidkraken.com/media/test720.mp4",
            "format": "720",
        }

    async def mock_stream(download_url, out_path, timeout=300.0):
        with open(out_path, "wb") as f:
            f.write(b"\x00" * 1024)
        return True

    monkeypatch.setattr(client, "enqueue_download", mock_enqueue)
    monkeypatch.setattr(client, "poll_job", mock_poll)
    monkeypatch.setattr(client, "stream_download_file", mock_stream)

    success = await client.download_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_file)
    assert success is True
    assert enqueue_calls == ["1080", "720"]


@pytest.mark.asyncio
async def test_multi_engine_fallback_to_pytubefix(monkeypatch, tmp_path):
    downloader = YouTubeDownloader()
    output_file = str(tmp_path / "test_hd.mp4")

    # Mock yt-dlp to fail
    monkeypatch.setattr(downloader, "_download_via_ytdlp", lambda *a, **kw: asyncio.sleep(0, result=False))

    # Mock pytubefix to succeed with valid HD file
    from src.infrastructure.pytubefix_downloader import PytubefixDownloader
    async def mock_pytube_download(self, url, out_path):
        with open(out_path, "wb") as f:
            f.write(b"\x00" * 2048)
        return True

    monkeypatch.setattr(PytubefixDownloader, "download_video", mock_pytube_download)
    # Mock validate_media_file to return 1080p
    monkeypatch.setattr(downloader, "_validate_media_file", lambda p: asyncio.sleep(0, result=1080))

    success = await downloader.download_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_file)
    assert success is True


@pytest.mark.asyncio
async def test_multi_engine_fallback_to_cobalt_on_pytube_fail(monkeypatch, tmp_path):
    downloader = YouTubeDownloader()
    output_file = str(tmp_path / "test_cobalt_hd.mp4")

    # Mock yt-dlp & pytubefix to fail
    monkeypatch.setattr(downloader, "_download_via_ytdlp", lambda *a, **kw: asyncio.sleep(0, result=False))
    from src.infrastructure.pytubefix_downloader import PytubefixDownloader
    monkeypatch.setattr(PytubefixDownloader, "download_video", lambda self, u, o: asyncio.sleep(0, result=False))

    # Mock Cobalt to succeed
    from src.infrastructure.cobalt_client import CobaltClient
    async def mock_cobalt_download(self, url, out_path):
        with open(out_path, "wb") as f:
            f.write(b"\x00" * 4096)
        return True

    monkeypatch.setattr(CobaltClient, "download_video", mock_cobalt_download)
    # Mock validate_media_file to return 720p
    monkeypatch.setattr(downloader, "_validate_media_file", lambda p: asyncio.sleep(0, result=720))

    success = await downloader.download_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_file)
    assert success is True


@pytest.mark.asyncio
async def test_multi_engine_rejects_sub_hd_video(monkeypatch, tmp_path):
    downloader = YouTubeDownloader()
    output_file = str(tmp_path / "test_sub_hd.mp4")

    # Mock yt-dlp to write a 360p file
    async def mock_ytdlp_360p(url, out_path):
        with open(out_path, "wb") as f:
            f.write(b"\x00" * 1024)
        return True

    monkeypatch.setattr(downloader, "_download_via_ytdlp", mock_ytdlp_360p)
    # Mock validate_media_file to return 360p
    monkeypatch.setattr(downloader, "_validate_media_file", lambda p: asyncio.sleep(0, result=360))

    # Pytubefix & Cobalt also fail
    from src.infrastructure.pytubefix_downloader import PytubefixDownloader
    from src.infrastructure.cobalt_client import CobaltClient
    monkeypatch.setattr(PytubefixDownloader, "download_video", lambda self, u, o: asyncio.sleep(0, result=False))
    monkeypatch.setattr(CobaltClient, "download_video", lambda self, u, o: asyncio.sleep(0, result=False))

    with pytest.raises(RuntimeError, match="Gagal mengunduh video YouTube dalam format HD"):
        await downloader.download_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ", output_file)


