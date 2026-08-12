"""Social accounts routes package.

Each platform gets its own module (facebook.py, instagram.py, etc.)
Shared helpers live in helpers.py to avoid circular imports.
"""
from fastapi import APIRouter

from src.presentation.routes.social.accounts import accounts_router
from src.presentation.routes.social.facebook import facebook_router
from src.presentation.routes.social.tiktok import tiktok_router
from src.presentation.routes.social.instagram import instagram_router
from src.presentation.routes.social.threads import threads_router
from src.presentation.routes.social.youtube import youtube_router
from src.presentation.routes.social.linkedin import linkedin_router
from src.presentation.routes.social.schedule import schedule_router
from src.presentation.routes.social.publish import publish_router

router = APIRouter(prefix="/social", tags=["social"])
router.include_router(accounts_router)
router.include_router(facebook_router)
router.include_router(tiktok_router)
router.include_router(instagram_router)
router.include_router(threads_router)
router.include_router(youtube_router)
router.include_router(linkedin_router)
router.include_router(schedule_router)
router.include_router(publish_router)
