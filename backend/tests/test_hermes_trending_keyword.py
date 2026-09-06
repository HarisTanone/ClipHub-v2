"""Tests for Hermes Trending Radar custom keyword search across YouTube, Google Trends/News, TikTok, and Gemini AI."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from src.presentation.api import app
from src.infrastructure.auth import create_access_token
from src.infrastructure.hermes_trending_service import HermesTrendingService, hermes_trending_service, TrendingTopic


@pytest.fixture
def auth_token():
    return create_access_token(user_id=1, email="admin@autocliper.com", role="superadmin", permissions=["*"])


@pytest.mark.asyncio
async def test_hermes_trending_service_with_custom_keyword():
    """Verify that get_trending_topics forwards custom keyword and 4 filters to all source fetchers and synthesizer."""
    service = HermesTrendingService()

    fake_topic = TrendingTopic(
        topic="Mobil Listrik Murah Mengguncang Pasar",
        angle="Perang harga mobil listrik terbaru",
        hook="Mobil listrik seharga motor? Ini dia faktanya!",
        key_points=["Subsidi pemerintah", "Fitur canggih", "Baterai tahan lama"],
        recommended_cta="Komen pendapatmu di bawah!",
        search_keywords=["Mobil Listrik", "EV Indonesia", "Baterai"],
        source="AI Synthesis",
        traffic_estimate="Trending",
        region="ID",
        category="Otomotif",
        timeframe="24 jam terakhir",
        is_active=True,
        status="Aktif",
        recency="Baru saja",
    )

    with patch.object(service, "fetch_google_trends", new_callable=AsyncMock) as mock_gt:
        mock_gt.return_value = [{"title": "Berita Mobil Listrik", "source": "Google News", "is_active": True, "_pub_ts": 100}]
        with patch.object(service, "fetch_youtube_trending", new_callable=AsyncMock) as mock_yt:
            mock_yt.return_value = [{"title": "Review Mobil Listrik", "source": "YouTube Search", "is_active": True, "_pub_ts": 200}]
            with patch.object(service, "fetch_tiktok_trending", new_callable=AsyncMock) as mock_tt:
                mock_tt.return_value = [{"title": "Mobil Listrik FYP", "source": "TikTok", "is_active": True, "_pub_ts": 300}]
                with patch.object(service, "synthesize_trending_topics", new_callable=AsyncMock) as mock_synth:
                    mock_synth.return_value = [fake_topic]

                    results = await service.get_trending_topics(
                        region="ID",
                        count=3,
                        keyword="Mobil Listrik",
                        timeframe="24h",
                        active_only=True,
                        sort_by="recency",
                        use_cache=False,
                    )

                    assert len(results) == 1
                    assert results[0]["topic"] == "Mobil Listrik Murah Mengguncang Pasar"
                    assert results[0]["timeframe"] == "24 jam terakhir"
                    assert results[0]["is_active"] is True
                    assert results[0]["status"] == "Aktif"
                    assert results[0]["recency"] == "Baru saja"

                    # Verify 4 filters were propagated to all components
                    mock_gt.assert_called_once_with(region="ID", keyword="Mobil Listrik", timeframe="24h", sort_by="recency", active_only=True)
                    mock_yt.assert_called_once_with(region="ID", keyword="Mobil Listrik", timeframe="24h", sort_by="recency", active_only=True)
                    mock_tt.assert_called_once_with(region="ID", keyword="Mobil Listrik", timeframe="24h")
                    assert mock_synth.call_args[1]["keyword"] == "Mobil Listrik"
                    assert mock_synth.call_args[1]["timeframe"] == "24h"
                    assert mock_synth.call_args[1]["active_only"] is True
                    assert mock_synth.call_args[1]["sort_by"] == "recency"


@pytest.mark.asyncio
async def test_cache_separation_between_keywords():
    """Verify that different keywords and filters have isolated caches in HermesTrendingService."""
    service = HermesTrendingService()
    service._cache.clear()

    topic_ai = TrendingTopic(topic="Topik AI", angle="AI Angle", hook="AI Hook", timeframe="24 jam terakhir", is_active=True, status="Aktif", recency="Baru saja")
    topic_crypto = TrendingTopic(topic="Topik Kripto", angle="Crypto Angle", hook="Crypto Hook", timeframe="24 jam terakhir", is_active=True, status="Aktif", recency="Baru saja")

    with patch.object(service, "synthesize_trending_topics", new_callable=AsyncMock) as mock_synth:
        mock_synth.return_value = [topic_ai]
        with patch.object(service, "fetch_google_trends", return_value=[]):
            with patch.object(service, "fetch_youtube_trending", return_value=[]):
                with patch.object(service, "fetch_tiktok_trending", return_value=[]):
                    res_ai = await service.get_trending_topics(region="ID", count=3, keyword="AI", use_cache=True)
                    assert res_ai[0]["topic"] == "Topik AI"

                    mock_synth.return_value = [topic_crypto]
                    res_crypto = await service.get_trending_topics(region="ID", count=3, keyword="Crypto", use_cache=True)
                    assert res_crypto[0]["topic"] == "Topik Kripto"

                    # Cache key for AI should return cached AI, not crypto
                    cached_ai = await service.get_trending_topics(region="ID", count=3, keyword="AI", use_cache=True)
                    assert cached_ai[0]["topic"] == "Topik AI"
                    # synthesize_trending_topics should only have been called twice (once for AI, once for Crypto)
                    assert mock_synth.call_count == 2


@pytest.mark.asyncio
async def test_fetch_google_trends_news_rss_url_with_keyword():
    """Verify fetch_google_trends queries Google News search RSS with when:1d when timeframe='24h'."""
    service = HermesTrendingService()

    fake_xml = """<rss version="2.0"><channel>
        <item>
            <title>Kecerdasan Buatan Mengubah Dunia Kerja</title>
            <description>Berita seputar perkembangan AI terbaru.</description>
            <source>Kompas.com</source>
            <pubDate>Sun, 06 Sep 2026 04:00:00 GMT</pubDate>
        </item>
    </channel></rss>"""

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.text = fake_xml

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = fake_resp
        items = await service.fetch_google_trends(region="ID", keyword="Kecerdasan Buatan", timeframe="24h", sort_by="recency")
        assert len(items) == 1
        assert "Kecerdasan Buatan" in items[0]["title"]
        assert items[0]["timeframe"] == "24 jam terakhir"
        assert items[0]["status"] == "Aktif"
        # Check URL queried contains when:1d
        called_url = mock_get.call_args[0][0]
        assert "news.google.com/rss/search" in called_url
        assert "when" in called_url


@pytest.mark.asyncio
async def test_fetch_youtube_trending_search_with_keyword():
    """Verify fetch_youtube_trending invokes YouTube v3/search with order=date and publishedAfter for recency."""
    service = HermesTrendingService()

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "items": [{
            "id": {"videoId": "test_vid_123"},
            "snippet": {
                "title": "Tutorial Resep Rendang Daging Sapi Empuk",
                "channelTitle": "Chef Channel",
                "description": "Resep rahasia rendang lezat khas Padang.",
                "publishedAt": "2026-09-06T03:00:00Z",
            }
        }]
    }

    with patch("src.infrastructure.hermes_trending_service.settings.YOUTUBE_API_KEY", "fake_yt_key"):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = fake_resp
            items = await service.fetch_youtube_trending(
                region="ID",
                keyword="Resep Rendang",
                timeframe="24h",
                sort_by="recency",
            )
            assert len(items) == 1
            assert "Rendang" in items[0]["title"]
            called_url = mock_get.call_args[0][0]
            called_params = mock_get.call_args[1]["params"]
            assert "googleapis.com/youtube/v3/search" in called_url
            assert called_params.get("q") == "Resep Rendang"
            assert called_params.get("order") == "date"
            assert "publishedAfter" in called_params


@pytest.mark.asyncio
async def test_trending_topics_endpoint_with_keyword(auth_token):
    """Verify GET /api/video-generator/trending-topics accepts keyword & 4 filters and returns them in response."""
    fake_topics = [{
        "topic": "Revolusi Kecerdasan Buatan di 2026",
        "angle": "Teknologi baru yang wajib diketahui",
        "hook": "Apakah AI sudah melampaui manusia?",
        "key_points": ["Model AI", "Otomasi"],
        "recommended_cta": "Follow untuk info tech!",
        "search_keywords": ["AI", "Tech"],
        "source": "AI Synthesis",
        "traffic_estimate": "Viral",
        "region": "ID",
        "category": "Teknologi",
        "timeframe": "24 jam terakhir",
        "is_active": True,
        "status": "Aktif",
        "recency": "Baru saja",
    }]

    with patch.object(hermes_trending_service, "get_trending_topics", new_callable=AsyncMock) as mock_get_topics:
        mock_get_topics.return_value = fake_topics
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/video-generator/trending-topics?region=ID&limit=3&keyword=Teknologi%20AI&timeframe=24h&active_only=true&sort_by=recency",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["region"] == "ID"
            assert data["timeframe"] == "24h"
            assert data["active_only"] is True
            assert data["sort_by"] == "recency"
            assert data["keyword"] == "Teknologi AI"
            assert data["count"] == 1
            assert data["topics"][0]["topic"] == "Revolusi Kecerdasan Buatan di 2026"
            assert data["topics"][0]["timeframe"] == "24 jam terakhir"
            assert data["topics"][0]["is_active"] is True
            assert data["topics"][0]["status"] == "Aktif"
            assert data["topics"][0]["recency"] == "Baru saja"
            mock_get_topics.assert_called_once_with(
                region="ID",
                count=3,
                limit=3,
                use_cache=True,
                niche_focus="Teknologi AI",
                keyword="Teknologi AI",
                timeframe="24h",
                active_only=True,
                sort_by="recency",
            )


@pytest.mark.asyncio
async def test_trending_topics_mandatory_filters_defaults(auth_token):
    """Verify endpoint defaults adhere strictly to the 4 user-specified filters:
    1. country: Indonesia (ID)
    2. time frame: 24 jam terakhir (24h)
    3. Status tren: Tampilkan tren aktif saja (active_only=True)
    4. sort by: Menurut keterkinian (sort_by='recency')
    """
    with patch.object(hermes_trending_service, "get_trending_topics", new_callable=AsyncMock) as mock_get_topics:
        mock_get_topics.return_value = []
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/video-generator/trending-topics",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["region"] == "ID"
            assert data["timeframe"] == "24h"
            assert data["active_only"] is True
            assert data["sort_by"] == "recency"
            mock_get_topics.assert_called_once_with(
                region="ID",
                count=5,
                limit=5,
                use_cache=True,
                niche_focus="",
                keyword="",
                timeframe="24h",
                active_only=True,
                sort_by="recency",
            )
