"""Generic account endpoints - list, count, get, remove.

Filters accounts by user ownership. Superadmin can see all.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, delete

from src.presentation.routes.auth import get_current_user
from src.presentation.auth_deps import CurrentUser
from src.presentation.routes.social.helpers import repliz_get, repliz_delete
from src.infrastructure.database import async_session, SocialAccountModel
from src.infrastructure.db_connection import get_dict_connection

accounts_router = APIRouter(tags=["social-accounts"])


async def _get_user_account_ids(user: CurrentUser) -> list[str]:
    """Get account IDs owned by this user. Superadmin gets all."""
    if user.is_superadmin:
        return []  # empty = no filter (show all)
    async with async_session() as session:
        result = await session.execute(
            select(SocialAccountModel.account_id).where(SocialAccountModel.user_id == user.id)
        )
        return [row[0] for row in result.fetchall()]


async def _user_owns_account(user: CurrentUser, account_id: str) -> bool:
    """Check if user owns this account (or is superadmin)."""
    if user.is_superadmin:
        return True
    async with async_session() as session:
        result = await session.execute(
            select(SocialAccountModel.id).where(
                SocialAccountModel.user_id == user.id,
                SocialAccountModel.account_id == account_id,
            )
        )
        return result.first() is not None


async def register_account(user_id: int, account_id: str, platform: str, name: str = "") -> None:
    """Register a social account as owned by a user."""
    async with async_session() as session:
        # Check if already registered
        existing = await session.execute(
            select(SocialAccountModel).where(SocialAccountModel.account_id == account_id)
        )
        if existing.first():
            return  # already registered
        session.add(SocialAccountModel(
            user_id=user_id,
            account_id=account_id,
            platform=platform,
            name=name,
        ))
        await session.commit()


async def unregister_account(account_id: str) -> None:
    """Remove account ownership record."""
    async with async_session() as session:
        await session.execute(
            delete(SocialAccountModel).where(SocialAccountModel.account_id == account_id)
        )
        await session.commit()


@accounts_router.get("/accounts/users")
async def list_account_users(user: CurrentUser = Depends(get_current_user)):
    """List users that have connected social accounts (superadmin only)."""
    if not user.is_superadmin:
        return []
    try:
        conn = get_dict_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT u.id, u.email, u.full_name, COUNT(sa.id) as accounts_count
            FROM users u
            INNER JOIN social_accounts sa ON u.id = sa.user_id
            GROUP BY u.id
            ORDER BY u.full_name ASC, u.email ASC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


@accounts_router.get("/accounts")
async def list_accounts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    types: Optional[str] = Query(None, description="Comma-separated: facebook,instagram,tiktok,threads,youtube,linkedin"),
    search: Optional[str] = None,
    user_id: Optional[int] = Query(None, description="Filter by local user ID (superadmin only)"),
    user: CurrentUser = Depends(get_current_user),
):
    """List connected social accounts (filtered by user ownership)."""
    params: dict = {"page": page, "limit": limit}
    if types:
        for i, t in enumerate(types.split(",")):
            params[f"types[{i}]"] = t.strip()
    if search:
        params["search"] = search
    data = await repliz_get("/public/account", params=params)

    # Load account ownership mappings
    owner_map = {}
    try:
        conn = get_dict_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT sa.account_id, sa.user_id, sa.platform, sa.name, u.email, u.full_name
            FROM social_accounts sa
            LEFT JOIN users u ON sa.user_id = u.id
        """)
        for row in cur.fetchall():
            owner_map[row["account_id"]] = {
                "user_id": row["user_id"],
                "email": row["email"] or "",
                "full_name": row["full_name"] or "",
            }
        conn.close()
    except Exception:
        owner_map = {}

    docs = data.get("docs") or []

    # Attach owner metadata to each doc
    for acc in docs:
        acc_id = acc.get("_id") or acc.get("id") or ""
        acc["owner"] = owner_map.get(acc_id)

    # Filter by ownership unless superadmin
    if not user.is_superadmin:
        owned_ids = await _get_user_account_ids(user)
        docs = [acc for acc in docs if (acc.get("_id") or acc.get("id")) in owned_ids]
    elif user_id is not None:
        # Superadmin filtering by specific user
        docs = [acc for acc in docs if acc.get("owner") and acc["owner"].get("user_id") == user_id]

    data["docs"] = docs
    data["totalDocs"] = len(docs)
    return data


@accounts_router.get("/accounts/platforms-status")
async def get_platforms_status(user: CurrentUser = Depends(get_current_user)):
    """Get connection status and account breakdown for each social media platform."""
    from src.infrastructure.social_auto_post_service import social_auto_post_service
    status = await social_auto_post_service.get_platforms_status(user_id=None if user.is_superadmin else user.id)
    return status


@accounts_router.get("/accounts/count")
async def count_accounts(user: CurrentUser = Depends(get_current_user)):
    """Get account count breakdown per platform (filtered by user)."""
    if user.is_superadmin:
        return await repliz_get("/public/account/count")

    # For regular users, count from local DB
    async with async_session() as session:
        result = await session.execute(
            select(SocialAccountModel.platform).where(SocialAccountModel.user_id == user.id)
        )
        platforms = [row[0] for row in result.fetchall()]

    counts = {"total": len(platforms), "facebook": 0, "instagram": 0, "tiktok": 0, "threads": 0, "youtube": 0, "linkedin": 0}
    for p in platforms:
        if p in counts:
            counts[p] += 1
    return counts


@accounts_router.get("/accounts/{account_id}")
async def get_account(account_id: str, user: CurrentUser = Depends(get_current_user)):
    """Get one account detail (must be owned by user)."""
    if not await _user_owns_account(user, account_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    return await repliz_get(f"/public/account/{account_id}")


@accounts_router.get("/accounts/{account_id}/statistic")
async def get_account_statistic(account_id: str, user: CurrentUser = Depends(get_current_user)):
    """Get account engagement statistics (must be owned by user)."""
    if not await _user_owns_account(user, account_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    return await repliz_get(f"/public/account/{account_id}/statistic")


@accounts_router.delete("/accounts/{account_id}")
async def remove_account(account_id: str, user: CurrentUser = Depends(get_current_user)):
    """Remove/disconnect an account (must be owned by user)."""
    if not await _user_owns_account(user, account_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    await repliz_delete(f"/public/account/{account_id}")
    await unregister_account(account_id)
    return {"success": True, "message": "Account removed"}
