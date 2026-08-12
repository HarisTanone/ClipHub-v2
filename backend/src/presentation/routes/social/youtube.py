"""YouTube OAuth flow - authorize, exchange, channels, connect, reconnect."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.presentation.routes.auth import get_current_user
from src.presentation.routes.social.helpers import repliz_get, repliz_post

youtube_router = APIRouter(prefix="/youtube", tags=["social-youtube"])


@youtube_router.get("/authorize")
async def youtube_authorize(
    redirect: str = Query(..., description="Redirect URL after Google auth"),
    _user=Depends(get_current_user),
):
    """Start YouTube OAuth - returns the Google authorization URL."""
    return await repliz_get("/public/account/youtube/authorize", params={"redirect": redirect})


class YouTubeExchangeRequest(BaseModel):
    code: str


@youtube_router.post("/exchange")
async def youtube_exchange(body: YouTubeExchangeRequest, _user=Depends(get_current_user)):
    """Exchange YouTube OAuth code for access token."""
    return await repliz_post("/public/account/youtube/exchange", json_body={"code": body.code})


@youtube_router.get("/channels")
async def youtube_channels(
    token: str = Query(..., description="Access token from exchange"),
    _user=Depends(get_current_user),
):
    """Get list of YouTube channels available to connect."""
    return await repliz_get("/public/account/youtube/channel", params={"token": token})


class YouTubeConnectRequest(BaseModel):
    channelId: str
    token: str


@youtube_router.post("/connect")
async def youtube_connect(body: YouTubeConnectRequest, _user=Depends(get_current_user)):
    """Connect a YouTube channel to workspace."""
    return await repliz_post(
        "/public/account/youtube/connect",
        json_body={"channelId": body.channelId, "token": body.token},
    )


@youtube_router.post("/reconnect/{account_id}")
async def youtube_reconnect(account_id: str, body: YouTubeConnectRequest, _user=Depends(get_current_user)):
    """Reconnect an existing YouTube account with new token."""
    return await repliz_post(
        f"/public/account/youtube/connect/{account_id}",
        json_body={"channelId": body.channelId, "token": body.token},
    )
