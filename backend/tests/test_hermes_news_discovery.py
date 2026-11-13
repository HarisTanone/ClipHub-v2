"""Unit tests for Hermes Image Studio: multi-topic news discovery, the Always
Update queue, and the user_upload/design_clone background fix."""
import asyncio
import json
import os

import pytest
from PIL import Image


def _make_png(path: str, color=(10, 20, 30)) -> str:
    Image.new("RGB", (200, 300), color).save(path, format="PNG")
    return path


@pytest.mark.asyncio
async def test_discover_news_for_topics_dedupes_across_topics(monkeypatch):
    """Same headline surfacing under two different topic searches must only
    appear once, and already-seen URLs must be excluded."""
    from src.infrastructure.ai_image_studio_service import AIImageStudioService

    async def fake_fetch_google_trends(region="ID", keyword="", limit=3, **kwargs):
        if keyword == "ai":
            return [
                {"title": "Terobosan AI Baru Diluncurkan", "summary": "ringkasan a", "source": "Tech Daily", "url": "https://news.example/a"},
                {"title": "Startup AI Raih Pendanaan", "summary": "ringkasan b", "source": "Biz Daily", "url": "https://news.example/b"},
            ]
        return [
            # Duplicate of the first article's URL — must be filtered out.
            {"title": "Terobosan AI Baru Diluncurkan", "summary": "ringkasan a", "source": "Tech Daily", "url": "https://news.example/a"},
            {"title": "Serangan Siber Baru Terdeteksi", "summary": "ringkasan c", "source": "Sec Daily", "url": "https://news.example/c"},
        ]

    monkeypatch.setattr(
        "src.infrastructure.hermes_trending_service.hermes_trending_service.fetch_google_trends",
        fake_fetch_google_trends,
    )

    studio = AIImageStudioService()
    articles = await studio.discover_news_for_topics(["ai", "serangan siber"], exclude_urls={"https://news.example/b"})

    urls = [a["url"] for a in articles]
    assert urls.count("https://news.example/a") == 1  # deduped across topics
    assert "https://news.example/b" not in urls  # excluded via exclude_urls
    assert "https://news.example/c" in urls


@pytest.mark.asyncio
async def test_discover_news_for_topics_empty_topics_returns_empty(monkeypatch):
    from src.infrastructure.ai_image_studio_service import AIImageStudioService

    studio = AIImageStudioService()
    assert await studio.discover_news_for_topics([]) == []
    assert await studio.discover_news_for_topics(["   ", ""]) == []


def test_news_queue_dedup_and_atomic_claim_order():
    """enqueue_news_articles must dedup via UNIQUE(user_id, article_url), and
    _claim_next_queue_item must hand out the oldest pending item exactly once."""
    from src.infrastructure.ai_image_studio_service import ai_image_studio_service as svc
    from src.infrastructure.db_connection import get_dict_connection

    user_id = 991401
    articles = [
        {"topic": "t", "title": "Artikel Satu", "summary": "s1", "url": "https://q.example/1", "source": "Src"},
        {"topic": "t", "title": "Artikel Dua", "summary": "s2", "url": "https://q.example/2", "source": "Src"},
    ]
    try:
        inserted_first = svc.enqueue_news_articles(user_id, articles)
        inserted_again = svc.enqueue_news_articles(user_id, articles)
        assert inserted_first == 2
        assert inserted_again == 0  # fully deduped on re-discovery

        first_claim = svc._claim_next_queue_item(user_id)
        second_claim = svc._claim_next_queue_item(user_id)
        third_claim = svc._claim_next_queue_item(user_id)

        assert first_claim["article_title"] == "Artikel Satu"
        assert second_claim["article_title"] == "Artikel Dua"
        assert third_claim is None  # nothing left pending

        svc._finish_queue_item(first_claim["id"], status="done", run_id=42)
        svc._finish_queue_item(second_claim["id"], status="failed", error="boom")

        queue = svc.get_news_queue(user_id)
        statuses = {q["article_title"]: (q["status"], q["run_id"], q["error_message"]) for q in queue}
        assert statuses["Artikel Satu"] == ("done", 42, None)
        assert statuses["Artikel Dua"][0] == "failed"
        assert statuses["Artikel Dua"][2] == "boom"
    finally:
        conn = get_dict_connection()
        conn.execute("DELETE FROM ai_image_news_queue WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_render_image_item_uses_custom_base_image_without_network(monkeypatch, tmp_path):
    """When a custom_base_image is supplied (user_upload background), no AI/stock
    network call should happen — this is the exact bug being fixed."""
    from src.infrastructure.ai_image_studio_service import AIImageStudioService
    from src.infrastructure.ai_image_typography import TypographyContent

    studio = AIImageStudioService()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("Should not call AI/stock image generation when a custom background is supplied")

    monkeypatch.setattr(studio, "generate_gemini_image", fail_if_called)
    monkeypatch.setattr(studio, "search_stock_photo", fail_if_called)
    monkeypatch.setattr(studio._minio, "upload_clip", lambda *a, **k: None)

    custom_img = Image.new("RGB", (400, 600), (200, 50, 50))
    content = TypographyContent(headline="Halo Dunia", template="minimal_quote", aspect_ratio="9:16")

    local_path, _public_url = await studio.render_image_item(
        topic="apa saja",
        prompt="tidak dipakai",
        content=content,
        background_source="user_upload",
        custom_base_image=custom_img,
    )
    assert os.path.exists(local_path)
    os.remove(local_path)


@pytest.mark.asyncio
async def test_execute_generation_session_wires_custom_background_path(monkeypatch, tmp_path):
    """custom_background_path must actually reach render_image_item as a loaded
    image for background_source=user_upload — this was previously dropped."""
    from src.infrastructure.ai_image_studio_service import ai_image_studio_service as svc
    from src.infrastructure.db_connection import get_dict_connection

    upload_path = _make_png(str(tmp_path / "upload.png"))

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("Should not fall back to AI/stock background when a custom upload path is given")

    monkeypatch.setattr(svc, "generate_gemini_image", fail_if_called)
    monkeypatch.setattr(svc, "search_stock_photo", fail_if_called)
    monkeypatch.setattr(svc._minio, "upload_clip", lambda *a, **k: None)

    user_id = 991402
    try:
        result = await svc.execute_generation_session(
            user_id=user_id,
            topic="Topik Uji",
            session_name="Pytest Upload Session",
            image_count=1,
            background_source="user_upload",
            custom_background_path=upload_path,
            quote_headline="Judul Uji Coba",
            quote_body="Isi uji coba",
            quote_author="Pytest",
            trigger_source="pytest",
        )
        assert result["success"] is True
    finally:
        conn = get_dict_connection()
        cur = conn.execute("SELECT local_paths FROM ai_image_runs WHERE user_id = ?", (user_id,))
        for row in cur.fetchall():
            for p in json.loads(row["local_paths"] or "[]"):
                if os.path.exists(p):
                    os.remove(p)
        conn.execute("DELETE FROM ai_image_runs WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()


@pytest.mark.asyncio
async def test_content_mode_news_falls_back_to_quote_when_no_article_found(monkeypatch):
    """If content_mode='news' but discovery returns nothing for the topic, the
    run must still succeed as a quote (graceful degrade), not fail outright."""
    from src.infrastructure.ai_image_studio_service import ai_image_studio_service as svc
    from src.infrastructure.db_connection import get_dict_connection

    async def empty_discovery(*args, **kwargs):
        return []

    monkeypatch.setattr(svc, "discover_news_for_topics", empty_discovery)
    monkeypatch.setattr(svc, "generate_gemini_image", lambda *a, **k: asyncio.sleep(0, result=Image.new("RGB", (10, 10))))
    monkeypatch.setattr(svc._minio, "upload_clip", lambda *a, **k: None)

    user_id = 991403
    try:
        result = await svc.execute_generation_session(
            user_id=user_id,
            topic="Topik Tanpa Berita",
            content_mode="news",
            trigger_source="pytest",
        )
        assert result["success"] is True
        assert result["content_mode"] == "quote"
        assert result["source_url"] is None
    finally:
        conn = get_dict_connection()
        cur = conn.execute("SELECT local_paths FROM ai_image_runs WHERE user_id = ?", (user_id,))
        for row in cur.fetchall():
            for p in json.loads(row["local_paths"] or "[]"):
                if os.path.exists(p):
                    os.remove(p)
        conn.execute("DELETE FROM ai_image_runs WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
