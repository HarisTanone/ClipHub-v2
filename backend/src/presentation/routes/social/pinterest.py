"""Pinterest OAuth flow & board addon via Repliz API - authorize, connect, reconnect, boards."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.presentation.routes.auth import get_current_user
from src.presentation.auth_deps import CurrentUser
from src.presentation.routes.social.helpers import repliz_get, repliz_post
from src.presentation.routes.social.accounts import register_account

logger = logging.getLogger(__name__)

pinterest_router = APIRouter(prefix="/pinterest", tags=["social-pinterest"])


@pinterest_router.get("/authorize")
async def pinterest_authorize(
    redirect: str = Query(..., description="Redirect URL after Pinterest auth"),
    _user=Depends(get_current_user),
):
    """Start Pinterest OAuth - returns the authorization URL from Repliz."""
    return await repliz_get("/public/account/pinterest/authorize", params={"redirect": redirect})


class PinterestConnectRequest(BaseModel):
    code: str


@pinterest_router.post("/connect")
async def pinterest_connect(body: PinterestConnectRequest, user: CurrentUser = Depends(get_current_user)):
    """Connect a Pinterest account to workspace."""
    result = await repliz_post(
        "/public/account/pinterest/connect",
        json_body={"code": body.code},
    )
    if result and ("accountId" in result or "id" in result or "_id" in result):
        acc_id = result.get("accountId") or result.get("id") or result.get("_id")
        await register_account(user.id, acc_id, "pinterest")
    return result


@pinterest_router.post("/reconnect/{account_id}")
async def pinterest_reconnect(account_id: str, body: PinterestConnectRequest, _user=Depends(get_current_user)):
    """Reconnect an existing Pinterest account with new auth code."""
    return await repliz_post(
        f"/public/account/pinterest/connect/{account_id}",
        json_body={"code": body.code},
    )


@pinterest_router.get("/boards")
async def pinterest_boards(
    account_id: str = Query(..., description="Connected Pinterest account ID"),
    _user=Depends(get_current_user),
):
    """Fetch Pinterest boards for a connected Pinterest account."""
    return await repliz_get("/public/addon/pinterest/board", params={"accountId": account_id})

