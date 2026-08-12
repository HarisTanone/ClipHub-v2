"""LinkedIn OAuth flow - authorize, exchange, organizations, connect, reconnect."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.presentation.routes.auth import get_current_user
from src.presentation.auth_deps import CurrentUser
from src.presentation.routes.social.helpers import repliz_get, repliz_post
from src.presentation.routes.social.accounts import register_account

linkedin_router = APIRouter(prefix="/linkedin", tags=["social-linkedin"])


@linkedin_router.get("/authorize")
async def linkedin_authorize(
    redirect: str = Query(..., description="Redirect URL after LinkedIn auth"),
    _user=Depends(get_current_user),
):
    """Start LinkedIn OAuth - returns the LinkedIn authorization URL."""
    return await repliz_get("/public/account/linkedin/authorize", params={"redirect": redirect})


class LinkedInExchangeRequest(BaseModel):
    code: str


@linkedin_router.post("/exchange")
async def linkedin_exchange(body: LinkedInExchangeRequest, _user=Depends(get_current_user)):
    """Exchange LinkedIn OAuth code for access token."""
    return await repliz_post("/public/account/linkedin/exchange", json_body={"code": body.code})


@linkedin_router.get("/organizations")
async def linkedin_organizations(
    token: str = Query(..., description="Access token from exchange"),
    _user=Depends(get_current_user),
):
    """Get list of LinkedIn organizations available to connect."""
    return await repliz_get("/public/account/linkedin/organization", params={"token": token})


class LinkedInConnectRequest(BaseModel):
    organizationId: str
    token: str


@linkedin_router.post("/connect")
async def linkedin_connect(body: LinkedInConnectRequest, user: CurrentUser = Depends(get_current_user)):
    """Connect a LinkedIn organization to workspace."""
    result = await repliz_post(
        "/public/account/linkedin/connect",
        json_body={"organizationId": body.organizationId, "token": body.token},
    )
    if result and "accountId" in result:
        await register_account(user.id, result["accountId"], "linkedin")
    return result


@linkedin_router.post("/reconnect/{account_id}")
async def linkedin_reconnect(account_id: str, body: LinkedInConnectRequest, _user=Depends(get_current_user)):
    """Reconnect an existing LinkedIn account with new token."""
    return await repliz_post(
        f"/public/account/linkedin/connect/{account_id}",
        json_body={"organizationId": body.organizationId, "token": body.token},
    )
