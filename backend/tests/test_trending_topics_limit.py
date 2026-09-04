import pytest
from unittest.mock import AsyncMock, patch
from src.infrastructure.hermes_trending_service import hermes_trending_service
from src.presentation.routes.video_generator import get_trending_topics_endpoint
from src.presentation.auth_deps import CurrentUser


@pytest.mark.asyncio
async def test_get_trending_topics_with_limit_and_count():
    mock_topics = [
        {
            "topic": "Trending Topic 1",
            "angle": "Tech angle",
            "hook": "Tahukah kamu?",
            "key_points": ["Point 1", "Point 2"],
            "recommended_cta": "Follow!",
            "search_keywords": ["keyword1"],
            "source": "Google Trends",
        }
    ]

    with patch.object(hermes_trending_service, "fetch_google_trends", new=AsyncMock(return_value=[{"title": "Trending 1"}])):
        with patch.object(hermes_trending_service, "fetch_youtube_trending", new=AsyncMock(return_value=[])):
            with patch.object(hermes_trending_service, "fetch_tiktok_trending", new=AsyncMock(return_value=[])):
                with patch.object(hermes_trending_service, "synthesize_trending_topics", new=AsyncMock(return_value=[])):
                    # Test calling with limit kwarg
                    res_limit = await hermes_trending_service.get_trending_topics(region="ID", limit=5, use_cache=False)
                    assert isinstance(res_limit, list)

                    # Test calling with count kwarg
                    res_count = await hermes_trending_service.get_trending_topics(region="ID", count=5, use_cache=False)
                    assert isinstance(res_count, list)


@pytest.mark.asyncio
async def test_trending_topics_endpoint():
    user = CurrentUser(1, "user@test.com", "user", [])
    mock_topics = [{"topic": "AI", "angle": "Tech", "hook": "Look"}]

    with patch.object(hermes_trending_service, "get_trending_topics", new=AsyncMock(return_value=mock_topics)) as mock_call:
        res = await get_trending_topics_endpoint(region="ID", limit=5, refresh=True, user=user)
        assert res["region"] == "ID"
        assert res["count"] == 1
        assert res["topics"] == mock_topics
        mock_call.assert_called_once_with(region="ID", count=5, limit=5, use_cache=False)
