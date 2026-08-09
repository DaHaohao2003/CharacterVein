from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from character_vein_api import __version__
from character_vein_api.config import get_settings

router = APIRouter(tags=["system"])
settings = get_settings()


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.app_env,
    )
