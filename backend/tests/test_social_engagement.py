import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.presentation.api import app
from src.presentation.routes.auth import get_current_user
from src.presentation.auth_deps import CurrentUser, require_superadmin

# Mock current user
class MockUser:
    id = 1
    email = "admin@example.com"
    full_name = "Admin User"
    role = "superadmin"
    is_superadmin = True

@pytest.fixture
def client():
    app.dependency_overrides[require_superadmin()] = lambda: MockUser()
    app.dependency_overrides[get_current_user] = lambda: MockUser()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_engagement_rules_lifecycle(client):
    # 1. Create rule
    payload = {
        "name": "TikTok Auto Comment Trio",
        "targetAccountId": "acc_target_a",
        "targetAccountName": "Akun A Target",
        "targetMode": "latest",
        "specificContentId": "",
        "isActive": True,
        "delayMinutes": 5,
        "commenters": [
            {
                "accountId": "acc_bot_b",
                "accountName": "Akun B",
                "persona": "Reaksi takjub dan penasaran"
            },
            {
                "accountId": "acc_bot_c",
                "accountName": "Akun C",
                "persona": "Pertanyaan santai relate sehari-hari"
            }
        ]
    }
    res = client.post("/api/social/engagement/rules", json=payload)
    assert res.status_code == 200
    rule_id = res.json()["id"]
    assert rule_id > 0

    # 2. List rules
    res = client.get("/api/social/engagement/rules")
    assert res.status_code == 200
    rules = res.json()
    assert any(r["id"] == rule_id for r in rules)
    matched = next(r for r in rules if r["id"] == rule_id)
    assert matched["delayMinutes"] == 5
    assert len(matched["commenters"]) == 2

    # 3. Toggle rule
    res = client.patch(f"/api/social/engagement/rules/{rule_id}/toggle", json={"isActive": False})
    assert res.status_code == 200
    assert res.json()["isActive"] is False

    # 4. Update rule
    payload["name"] = "TikTok Updated"
    payload["delayMinutes"] = 3
    res = client.put(f"/api/social/engagement/rules/{rule_id}", json=payload)
    assert res.status_code == 200

    # 5. Delete rule
    res = client.delete(f"/api/social/engagement/rules/{rule_id}")
    assert res.status_code == 200

def test_generate_comment_preview(client):
    with patch("src.presentation.routes.social.engagement.route_chat", return_value="jujurly valid bgt nih kontennya 😭"):
        payload = {
            "metadata": {
                "title": "Tutorial Masak Kilat",
                "description": "Cara masak nasi goreng enak dalam 5 menit",
                "topic": "Cooking"
            },
            "commenters": [
                {
                    "accountId": "acc_b",
                    "accountName": "Akun B",
                    "roleCategory": "pro",
                    "persona": "Reaksi antusias setuju"
                },
                {
                    "accountId": "acc_c",
                    "accountName": "Akun C",
                    "roleCategory": "contra",
                    "persona": "Agak skeptis"
                },
                {
                    "accountId": "acc_d",
                    "accountName": "Akun D",
                    "roleCategory": "hate",
                    "persona": "Julid sarkas"
                }
            ]
        }
        res = client.post("/api/social/engagement/generate-preview", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert len(data["previews"]) == 3
        assert data["previews"][0]["roleCategory"] == "pro"
        assert data["previews"][1]["roleCategory"] == "contra"
        assert data["previews"][2]["roleCategory"] == "hate"
        assert "jujurly valid bgt" in data["previews"][0]["comment"]

def test_trigger_engagement_with_staggered_delay(client):
    mock_content_list = {
        "docs": [
            {
                "id": "content_tt_123",
                "title": "Video Terkini",
                "description": "Deskripsi video",
                "topic": "Vlog"
            }
        ]
    }

    with patch("src.presentation.routes.social.engagement.repliz_get", new_callable=AsyncMock) as mock_get, \
         patch("src.presentation.routes.social.engagement.repliz_post", new_callable=AsyncMock) as mock_post, \
         patch("src.presentation.routes.social.engagement.route_chat", return_value="Keren parah nih! 🔥"):

        mock_get.return_value = mock_content_list
        mock_post.return_value = {"commentId": "repliz_comm_999"}

        payload = {
            "targetAccountId": "acc_target_a",
            "targetMode": "latest",
            "delayMinutes": 0,  # 0 for fast test execution
            "commenters": [
                {
                    "accountId": "acc_bot_b",
                    "accountName": "Akun B",
                    "persona": "Reaksi positif"
                },
                {
                    "accountId": "acc_bot_c",
                    "accountName": "Akun C",
                    "persona": "Reaksi lucu"
                }
            ]
        }

        res = client.post("/api/social/engagement/trigger", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["totalPosts"] == 1
        assert data["totalCommenters"] == 2
        task_id = data["tasks"][0]["taskId"]

        # Check tasks endpoint
        res = client.get("/api/social/engagement/tasks")
        assert res.status_code == 200
        tasks = res.json()
        assert any(t["id"] == task_id for t in tasks)
