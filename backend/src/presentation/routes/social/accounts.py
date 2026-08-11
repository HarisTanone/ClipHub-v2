"""Generic account endpoints - list, count, get, remove."""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.presentation.routes.auth import get_current_user
from src.presentation.routes.social.helpers import repliz_get, repliz_delete

accounts_router = APIRouter(tags=["social-accounts"])


@accounts_router.get("/accounts")
async def list_accounts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    types: Optional[str] = Query(None, description="Comma-separated: facebook,instagram,tiktok,threads,youtube,linkedin"),
    search: Optional[str] = None,
    _user=Depends(get_current_user),
):
    """List connected social accounts."""
    params: dict = {"page": page, "limit": limit}
    if types:
        for i, t in enumerate(types.split(",")):
            params[f"types[{i}]"] = t.strip()
    if search:
        params["search"] = search
    return await repliz_get("/public/account", params=params)


@accounts_router.get("/accounts/count")
async def count_accounts(_user=Depends(get_current_user)):
    """Get account count breakdown per platform."""
    return await repliz_get("/public/account/count")


@accounts_router.get("/accounts/{account_id}")
async def get_account(account_id: str, _user=Depends(get_current_user)):
    """Get one account detail."""
    return await repliz_get(f"/public/account/{account_id}")


@accounts_router.get("/accounts/{account_id}/statistic")
async def get_account_statistic(account_id: str, _user=Depends(get_current_user)):
    """Get account engagement statistics."""
    return await repliz_get(f"/public/account/{account_id}/statistic")


@accounts_router.delete("/accounts/{account_id}")
async def remove_account(account_id: str, _user=Depends(get_current_user)):
    """Remove/disconnect an account."""
    await repliz_delete(f"/public/account/{account_id}")
    return {"success": True, "message": "Account removed"}
