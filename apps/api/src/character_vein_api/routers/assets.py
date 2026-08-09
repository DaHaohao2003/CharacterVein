from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from character_vein_api.asset_service import AssetService
from character_vein_api.config import get_settings
from character_vein_api.database import get_session
from character_vein_api.repositories import AssetRepository
from character_vein_api.schemas import AssetResponse

router = APIRouter(prefix="/assets", tags=["assets"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    session: SessionDependency, file: Annotated[UploadFile, File()]
) -> AssetResponse:
    settings = get_settings()
    read_limit = max(settings.asset_max_image_bytes, settings.asset_max_document_bytes) + 1
    try:
        record = await AssetService(AssetRepository(session)).upload(
            file.filename or "upload",
            file.content_type or "application/octet-stream",
            await file.read(read_limit),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return AssetResponse.from_record(record)


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: str, session: SessionDependency) -> AssetResponse:
    record = await AssetRepository(session).get(asset_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="上传材料不存在")
    return AssetResponse.from_record(record)
