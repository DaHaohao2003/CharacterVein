import asyncio
import re
from typing import Annotated, cast

import boto3  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from character_vein_api.config import get_settings
from character_vein_api.database import get_session
from character_vein_api.repositories import GlyphImageRepository
from character_vein_api.schemas import GlyphImageSearchResult
from character_vein_providers import DeterministicEmbeddingProvider

router = APIRouter(prefix="/glyph-images", tags=["glyph image RAG"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]
SAFE_CODEPOINT = re.compile(r"U\+[0-9A-F]{4,6}")
SAFE_SCRIPT = re.compile(r"[JBGSLKC]")
SAFE_FILENAME = re.compile(r"[A-Za-z0-9._-]+\.(?:jpg|jpeg|png)", re.IGNORECASE)


@router.get("/search", response_model=list[GlyphImageSearchResult])
async def search_glyph_images(
    session: SessionDependency,
    query: str = Query(min_length=1, max_length=200),
    character: str | None = Query(default=None, min_length=1, max_length=1),
    script_code: str | None = Query(default=None, pattern=r"^[JBGSLKC]$"),
    limit: int = Query(default=12, ge=1, le=200),
) -> list[GlyphImageSearchResult]:
    vector = (await DeterministicEmbeddingProvider().embed([query]))[0]
    rows = await GlyphImageRepository(session).search(
        vector, character=character, script_code=script_code, limit=limit
    )
    return [GlyphImageSearchResult.from_record(record, score) for record, score in rows]


@router.get("/{codepoint}/{script_code}/{filename}")
async def get_glyph_image(
    codepoint: str,
    script_code: str,
    filename: str,
    session: SessionDependency,
) -> Response:
    if not (
        SAFE_CODEPOINT.fullmatch(codepoint)
        and SAFE_SCRIPT.fullmatch(script_code)
        and SAFE_FILENAME.fullmatch(filename)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="字形图片不存在")
    record = await GlyphImageRepository(session).get(f"{codepoint}/{script_code}/{filename}")
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="字形图片不存在")

    settings = get_settings()

    def read_object() -> bytes:
        client = boto3.client(
            "s3",
            endpoint_url=str(settings.s3_endpoint_url),
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )
        response = client.get_object(Bucket=settings.s3_bucket, Key=record.storage_key)
        try:
            return cast(bytes, response["Body"].read())
        finally:
            response["Body"].close()

    try:
        content = await asyncio.to_thread(read_object)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="字形对象存储暂不可用",
        ) from exc
    return Response(
        content=content,
        media_type=record.mime_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable", "ETag": record.sha256},
    )
