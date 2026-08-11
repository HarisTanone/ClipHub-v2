"""TikTok OAuth flow - authorize, connect, reconnect."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.presentation.routes.auth import get_current_user
from src.presentation.routes.social.helpers import repliz_get, repliz_post

tiktok_router = APIRouter(prefix="/tiktok", tags=["social-tiktok"])


@tiktok_router.get("/authorize")
async def tiktok_authorize(
    redirect: str = Query(..., description="Redirect URL after TikTok auth"),
    _user=Depends(get_current_user),
):
    """Start TikTok OAuth - returns the TikTok authorization URL."""
    return await repliz_get("/public/account/tiktok/authorize", params={"redirect": redirect})


class TikTokConnectRequest(BaseModel):
    code: str


@tiktok_router.post("/connect")
async def tiktok_connect(body: TikTokConnectRequest, _user=Depends(get_current_user)):
    """Connect a TikTok account to workspace."""
    return await repliz_post(
        "/public/account/tiktok/connect",
        json_body={"code": body.code},
    )


@tiktok_router.post("/reconnect/{account_id}")
async def tiktok_reconnect(account_id: str, body: TikTokConnectRequest, _user=Depends(get_current_user)):
    """Reconnect an existing TikTok account with new auth code."""
    return await repliz_post(
        f"/public/account/tiktok/connect/{account_id}",
        json_body={"code": body.code},
    )
