"""Facebook OAuth flow - authorize, exchange, pages, connect, reconnect."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.presentation.routes.auth import get_current_user
from src.presentation.auth_deps import CurrentUser
from src.presentation.routes.social.helpers import repliz_get, repliz_post
from src.presentation.routes.social.accounts import register_account

facebook_router = APIRouter(prefix="/facebook", tags=["social-facebook"])


@facebook_router.get("/authorize")
async def facebook_authorize(
    redirect: str = Query(..., description="Redirect URL after Facebook auth"),
    _user=Depends(get_current_user),
):
    """Start Facebook OAuth - returns the Facebook authorization URL."""
    return await repliz_get("/public/account/facebook/authorize", params={"redirect": redirect})


class FacebookExchangeRequest(BaseModel):
    code: str


@facebook_router.post("/exchange")
async def facebook_exchange(body: FacebookExchangeRequest, _user=Depends(get_current_user)):
    """Exchange Facebook OAuth code for access token."""
    return await repliz_post("/public/account/facebook/exchange", json_body={"code": body.code})


@facebook_router.get("/pages")
async def facebook_pages(
    token: str = Query(..., description="Access token from exchange"),
    _user=Depends(get_current_user),
):
    """Get list of Facebook pages available to connect."""
    return await repliz_get("/public/account/facebook/page", params={"token": token})


class FacebookConnectRequest(BaseModel):
    pageId: str
    token: str


@facebook_router.post("/connect")
async def facebook_connect(body: FacebookConnectRequest, user: CurrentUser = Depends(get_current_user)):
    """Connect a Facebook page to workspace."""
    result = await repliz_post(
        "/public/account/facebook/connect",
        json_body={"pageId": body.pageId, "token": body.token},
    )
    if result and "accountId" in result:
        await register_account(user.id, result["accountId"], "facebook")
    return result


@facebook_router.post("/reconnect/{account_id}")
async def facebook_reconnect(account_id: str, body: FacebookConnectRequest, _user=Depends(get_current_user)):
    """Reconnect an existing Facebook account with new token."""
    return await repliz_post(
        f"/public/account/facebook/connect/{account_id}",
        json_body={"pageId": body.pageId, "token": body.token},
    )
