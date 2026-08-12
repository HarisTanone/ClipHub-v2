"""Threads OAuth flow - authorize, connect, reconnect."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.presentation.routes.auth import get_current_user
from src.presentation.routes.social.helpers import repliz_get, repliz_post

threads_router = APIRouter(prefix="/threads", tags=["social-threads"])


@threads_router.get("/authorize")
async def threads_authorize(
    redirect: str = Query(..., description="Redirect URL after Threads auth"),
    _user=Depends(get_current_user),
):
    """Start Threads OAuth - returns the Threads authorization URL."""
    return await repliz_get("/public/account/threads/authorize", params={"redirect": redirect})


class ThreadsConnectRequest(BaseModel):
    code: str


@threads_router.post("/connect")
async def threads_connect(body: ThreadsConnectRequest, _user=Depends(get_current_user)):
    """Connect a Threads account to workspace."""
    return await repliz_post(
        "/public/account/threads/connect",
        json_body={"code": body.code},
    )


@threads_router.post("/reconnect/{account_id}")
async def threads_reconnect(account_id: str, body: ThreadsConnectRequest, _user=Depends(get_current_user)):
    """Reconnect an existing Threads account with new auth code."""
    return await repliz_post(
        f"/public/account/threads/connect/{account_id}",
        json_body={"code": body.code},
    )
