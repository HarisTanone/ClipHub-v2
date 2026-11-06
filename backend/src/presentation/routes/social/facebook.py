"""Facebook OAuth flow - authorize, exchange, pages, connect, reconnect."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.presentation.routes.auth import get_current_user
from src.presentation.auth_deps import CurrentUser
from src.presentation.routes.social.helpers import repliz_get, repliz_post
from src.presentation.routes.social.accounts import register_account

facebook_router = APIRouter(prefix="/facebook", tags=["social-facebook"])


async def _resolve_page_token(page_id: str, token: str) -> str | None:
    """Fallback: if a user token was passed instead of page token, resolve it via /page."""
    try:
        pages_resp = await repliz_get("/public/account/facebook/page", params={"token": token})
        page_docs = pages_resp.get("docs", []) if isinstance(pages_resp, dict) else []
        matched = next((p for p in page_docs if str(p.get("id")) == str(page_id)), None)
        if matched and matched.get("token"):
            return matched["token"]
    except Exception:
        pass
    return None


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
    token = body.token
    try:
        result = await repliz_post(
            "/public/account/facebook/connect",
            json_body={"pageId": body.pageId, "token": token},
        )
    except HTTPException as exc:
        if exc.status_code == 403 and "page access token is required" in str(exc.detail):
            resolved = await _resolve_page_token(body.pageId, body.token)
            if resolved:
                result = await repliz_post(
                    "/public/account/facebook/connect",
                    json_body={"pageId": body.pageId, "token": resolved},
                )
            else:
                raise
        else:
            raise

    if result and "accountId" in result:
        await register_account(user.id, result["accountId"], "facebook")
    return result


@facebook_router.post("/reconnect/{account_id}")
async def facebook_reconnect(account_id: str, body: FacebookConnectRequest, _user=Depends(get_current_user)):
    """Reconnect an existing Facebook account with new token."""
    token = body.token
    try:
        return await repliz_post(
            f"/public/account/facebook/connect/{account_id}",
            json_body={"pageId": body.pageId, "token": token},
        )
    except HTTPException as exc:
        if exc.status_code == 403 and "page access token is required" in str(exc.detail):
            resolved = await _resolve_page_token(body.pageId, body.token)
            if resolved:
                return await repliz_post(
                    f"/public/account/facebook/connect/{account_id}",
                    json_body={"pageId": body.pageId, "token": resolved},
                )
            else:
                raise
        else:
            raise
