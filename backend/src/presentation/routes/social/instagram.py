"""Instagram OAuth flow - authorize, connect, reconnect."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.presentation.routes.auth import get_current_user
from src.presentation.auth_deps import CurrentUser
from src.presentation.routes.social.helpers import repliz_get, repliz_post
from src.presentation.routes.social.accounts import register_account

instagram_router = APIRouter(prefix="/instagram", tags=["social-instagram"])


@instagram_router.get("/authorize")
async def instagram_authorize(
    redirect: str = Query(..., description="Redirect URL after Instagram auth"),
    _user=Depends(get_current_user),
):
    """Start Instagram OAuth - returns the Instagram authorization URL."""
    return await repliz_get("/public/account/instagram/authorize", params={"redirect": redirect})


class InstagramConnectRequest(BaseModel):
    code: str


@instagram_router.post("/connect")
async def instagram_connect(body: InstagramConnectRequest, user: CurrentUser = Depends(get_current_user)):
    """Connect an Instagram account to workspace."""
    result = await repliz_post(
        "/public/account/instagram/connect",
        json_body={"code": body.code},
    )
    if result and "accountId" in result:
        await register_account(user.id, result["accountId"], "instagram")
    return result


@instagram_router.post("/reconnect/{account_id}")
async def instagram_reconnect(account_id: str, body: InstagramConnectRequest, _user=Depends(get_current_user)):
    """Reconnect an existing Instagram account with new auth code."""
    return await repliz_post(
        f"/public/account/instagram/connect/{account_id}",
        json_body={"code": body.code},
    )
