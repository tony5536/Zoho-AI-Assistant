from fastapi import APIRouter

from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.health import router as health_router


def create_api_router() -> APIRouter:
    api = APIRouter()
    api.include_router(health_router, tags=["health"])
    api.include_router(chat_router, prefix="/chat", tags=["chat"])
    api.include_router(auth_router, prefix="/auth", tags=["auth"])
    return api
