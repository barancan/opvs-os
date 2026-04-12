from fastapi import APIRouter

from opvs.api import chat, health, killswitch, notifications, settings

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(settings.router)
api_router.include_router(notifications.router)
api_router.include_router(chat.router)
api_router.include_router(killswitch.router)
