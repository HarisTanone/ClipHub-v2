"""Social accounts routes package.

Each platform gets its own module (facebook.py, instagram.py, etc.)
Shared helpers live in helpers.py to avoid circular imports.
"""
from fastapi import APIRouter

from src.presentation.routes.social.accounts import accounts_router
from src.presentation.routes.social.facebook import facebook_router
from src.presentation.routes.social.schedule import schedule_router

router = APIRouter(prefix="/social", tags=["social"])
router.include_router(accounts_router)
router.include_router(facebook_router)
router.include_router(schedule_router)
