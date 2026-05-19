from fastapi import APIRouter
from app.api.v1.endpoints import chat, health
from app.api.v1.endpoints import theme

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(chat.router)
router.include_router(theme.router)