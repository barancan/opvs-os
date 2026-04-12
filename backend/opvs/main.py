import asyncio
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from opvs.api.router import api_router
from opvs.config import settings
from opvs.database import init_db
from opvs.websocket import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    from alembic.config import Config

    from alembic import command

    alembic_cfg = Config("backend/alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    alembic_cfg.set_main_option("script_location", "backend/alembic")
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")

    from opvs.database import AsyncSessionLocal
    from opvs.services.project_service import (
        _create_project_workspace,
        _ensure_global_memory_structure,
        ensure_default_project,
        list_projects,
    )
    from opvs.services.settings_service import get_setting

    async with AsyncSessionLocal() as db:
        workspace_setting = await get_setting(db, "workspace_path")
        wp = str(workspace_setting.value) if workspace_setting else settings.workspace_path
        await ensure_default_project(db, workspace_path=wp)

        # Backfill memory structure for existing projects (idempotent)
        _ensure_global_memory_structure(wp)
        existing_projects = await list_projects(db)
        for project in existing_projects:
            _create_project_workspace(wp, project.slug)

    yield


app = FastAPI(title="opvs OS", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)

try:
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
except Exception:
    logger.warning("frontend/dist not found — static file serving disabled")
