from fastapi import APIRouter

from opvs.api import health, settings

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(settings.router)
