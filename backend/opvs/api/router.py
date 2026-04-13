from fastapi import APIRouter

from opvs.api import (
    chat,
    health,
    jobs,
    killswitch,
    notifications,
    personas,
    projects,
    sessions,
    settings,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(settings.router)
api_router.include_router(notifications.router)
api_router.include_router(chat.router)
api_router.include_router(killswitch.router)
api_router.include_router(projects.router)
api_router.include_router(jobs.router)
api_router.include_router(personas.router)
api_router.include_router(sessions.router)
