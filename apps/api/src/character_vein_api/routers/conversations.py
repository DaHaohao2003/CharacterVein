from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from character_vein_api.conversation_service import ConversationService
from character_vein_api.database import get_session
from character_vein_api.models import TaskRecord
from character_vein_api.repositories import (
    ConversationRepository,
    CreativeArtifactRepository,
    TaskRepository,
)
from character_vein_api.schemas import (
    ConversationMessageRequest,
    ConversationMessageResponse,
    ConversationTurnResponse,
    CreativeArtifactResponse,
)

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
