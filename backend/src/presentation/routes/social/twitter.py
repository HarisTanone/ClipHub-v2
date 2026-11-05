"""Twitter (X) OAuth flow via Repliz API - authorize, connect, reconnect."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.presentation.routes.auth import get_current_user
from src.presentation.auth_deps import CurrentUser
from src.presentation.routes.social.helpers import repliz_get, repliz_post
from src.presentation.routes.social.accounts import register_account

logger = logging.getLogger(__name__)

twitter_router = APIRouter(prefix="/twitter", tags=["social-twitter"])


@twitter_router.get("/authorize")
async def twitter_authorize(
    redirect: str = Query(..., description="Redirect URL after X/Twitter auth"),
    _user=Depends(get_current_user),
):
    """Start Twitter/X OAuth - returns the authorization URL from Repliz."""
    return await repliz_get("/public/account/twitter/authorize", params={"redirect": redirect})


class TwitterConnectRequest(BaseModel):
    code: str


@twitter_router.post("/connect")
async def twitter_connect(body: TwitterConnectRequest, user: CurrentUser = Depends(get_current_user)):
    """Connect a Twitter/X account to workspace."""
    result = await repliz_post(
        "/public/account/twitter/connect",
        json_body={"code": body.code},
    )
    if result and ("accountId" in result or "id" in result or "_id" in result):
        acc_id = result.get("accountId") or result.get("id") or result.get("_id")
        await register_account(user.id, acc_id, "twitter")
    return result


@twitter_router.post("/reconnect/{account_id}")
async def twitter_reconnect(account_id: str, body: TwitterConnectRequest, _user=Depends(get_current_user)):
    """Reconnect an existing Twitter/X account with new auth code."""
    return await repliz_post(
        f"/public/account/twitter/connect/{account_id}",
        json_body={"code": body.code},
    )

