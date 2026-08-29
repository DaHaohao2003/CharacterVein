import asyncio
from typing import Annotated, Literal, cast

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from character_vein_api.artifact_exports import (
    export_docx,
    export_html,
    export_pdf,
    export_pptx,
    export_txt,
)
from character_vein_api.config import get_settings
from character_vein_api.conversation_service import ConversationService
from character_vein_api.database import get_session
from character_vein_api.models import TaskRecord
from character_vein_api.repositories import (
    ConversationRepository,
    CreativeArtifactRepository,
    GlyphImageRepository,
    TaskRepository,
)
from character_vein_api.schemas import (
    ConversationMessageRequest,
    ConversationMessageResponse,
    ConversationTurnResponse,
    CreativeArtifactResponse,
)
from character_vein_domain import RichArtifactDocument

router = APIRouter(prefix="/tasks", tags=["conversation"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


async def _require_task(repository: TaskRepository, task_id: str) -> TaskRecord:
    task = await repository.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task


@router.get(
    "/{task_id}/conversation/messages",
    response_model=list[ConversationMessageResponse],
)
async def list_conversation_messages(
    task_id: str, session: SessionDependency
) -> list[ConversationMessageResponse]:
    task_repository = TaskRepository(session)
    await _require_task(task_repository, task_id)
    records = await ConversationRepository(session).list(task_id)
    return [ConversationMessageResponse.from_record(item) for item in records]


@router.post(
    "/{task_id}/conversation/messages",
    response_model=ConversationTurnResponse,
)
async def send_conversation_message(
    task_id: str,
    payload: ConversationMessageRequest,
    session: SessionDependency,
) -> ConversationTurnResponse:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    try:
        return await ConversationService(repository).respond(
            task,
            payload.content,
            active_artifact_id=payload.active_artifact_id,
            active_page_id=payload.active_page_id,
            active_block_id=payload.active_block_id,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{task_id}/creative-artifacts",
    response_model=list[CreativeArtifactResponse],
)
async def list_creative_artifacts(
    task_id: str, session: SessionDependency
) -> list[CreativeArtifactResponse]:
    task_repository = TaskRepository(session)
    await _require_task(task_repository, task_id)
    records = await CreativeArtifactRepository(session).list(task_id)
    return [CreativeArtifactResponse.from_record(item) for item in records]


@router.get(
    "/{task_id}/creative-artifacts/{artifact_id}",
    response_model=CreativeArtifactResponse,
)
async def get_creative_artifact(
    task_id: str,
    artifact_id: str,
    session: SessionDependency,
) -> CreativeArtifactResponse:
    task_repository = TaskRepository(session)
    await _require_task(task_repository, task_id)
    record = await CreativeArtifactRepository(session).get(task_id, artifact_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在")
    return CreativeArtifactResponse.from_record(record)


@router.get("/{task_id}/creative-artifacts/{artifact_id}/export.md")
async def export_creative_artifact(
    task_id: str,
    artifact_id: str,
    session: SessionDependency,
) -> Response:
    task_repository = TaskRepository(session)
    await _require_task(task_repository, task_id)
    record = await CreativeArtifactRepository(session).get(task_id, artifact_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在")
    return Response(
        content=record.content_markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="artifact-{record.id}.md"'},
    )


@router.get("/{task_id}/creative-artifacts/{artifact_id}/exports/{export_format}")
async def export_rich_creative_artifact(
    task_id: str,
    artifact_id: str,
    export_format: Literal["docx", "html", "txt", "pdf", "pptx"],
    session: SessionDependency,
) -> Response:
    task_repository = TaskRepository(session)
    await _require_task(task_repository, task_id)
    record = await CreativeArtifactRepository(session).get(task_id, artifact_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在")
    document = (
        RichArtifactDocument.model_validate(record.document_json)
        if record.document_json
        else CreativeArtifactResponse.from_record(record).rich_document
    )
    images = await _load_artifact_images(document, session)
    try:
        if export_format == "docx":
            content = export_docx(document, images)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif export_format == "html":
            content = export_html(document, images)
            media_type = "text/html; charset=utf-8"
        elif export_format == "txt":
            content = export_txt(document)
            media_type = "text/plain; charset=utf-8"
        elif export_format == "pdf":
            content = export_pdf(document, images)
            media_type = "application/pdf"
        else:
            content = export_pptx(document, images)
            media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    except (RuntimeError, BotoCoreError, ClientError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="character-vein-{record.id}.{export_format}"'
            )
        },
    )


async def _load_artifact_images(
    document: RichArtifactDocument,
    session: AsyncSession,
) -> dict[str, tuple[bytes, str]]:
    image_ids = list(
        dict.fromkeys(
            block.image_id
            for page in document.pages
            for block in page.blocks
            if block.image_id and block.source_kind == "glyph"
        )
    )
    if not image_ids:
        return {}
    repository = GlyphImageRepository(session)
    settings = get_settings()

    records = []
    for image_id in image_ids:
        record = await repository.get_compatible(image_id)
        if record is not None:
            records.append((image_id, record))

    async def load_one(image_id: str, storage_key: str, mime_type: str) -> tuple[str, bytes, str]:
        def read_object() -> bytes:
            client = boto3.client(
                "s3",
                endpoint_url=str(settings.s3_endpoint_url),
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name=settings.s3_region,
            )
            response = client.get_object(Bucket=settings.s3_bucket, Key=storage_key)
            try:
                return cast(bytes, response["Body"].read())
            finally:
                response["Body"].close()

        return image_id, await asyncio.to_thread(read_object), mime_type

    loaded = await asyncio.gather(
        *(load_one(image_id, record.storage_key, record.mime_type) for image_id, record in records)
    )
    return {image_id: (payload, mime_type) for image_id, payload, mime_type in loaded}
