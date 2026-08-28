from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from character_vein_api import __version__
from character_vein_api.config import get_settings
from character_vein_api.logging import configure_logging
from character_vein_api.routers.assets import router as assets_router
from character_vein_api.routers.claims import router as claims_router
from character_vein_api.routers.contents import router as contents_router
from character_vein_api.routers.conversations import router as conversations_router
from character_vein_api.routers.glyph_images import router as glyph_images_router
from character_vein_api.routers.glyphs import router as glyphs_router
from character_vein_api.routers.health import router as health_router
from character_vein_api.routers.tasks import router as tasks_router

settings = get_settings()
configure_logging(settings.app_log_level)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(settings.web_origin).rstrip("/")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(assets_router, prefix=settings.api_v1_prefix)
app.include_router(tasks_router, prefix=settings.api_v1_prefix)
app.include_router(conversations_router, prefix=settings.api_v1_prefix)
app.include_router(claims_router, prefix=settings.api_v1_prefix)
app.include_router(contents_router, prefix=settings.api_v1_prefix)
app.include_router(glyphs_router, prefix=settings.api_v1_prefix)
app.include_router(glyph_images_router, prefix=settings.api_v1_prefix)
