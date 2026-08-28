from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from character_vein_api.database import get_session
from character_vein_api.models import TaskRecord
from character_vein_api.repositories import TaskRepository
from character_vein_api.schemas import (
    ContentVersionResponse,
    ExportContentRequest,
    RegenerateContentRequest,
    UpdateContentRequest,
)
from character_vein_api.services import ContentService
from character_vein_domain import (
    AuditReport,
    CommunicationAsset,
    CulturalMotif,
    EvolutionPackage,
    GeneratedContent,
    TaskSpec,
)
from character_vein_exporters import (
    export_communication_package_html,
    export_communication_package_json,
    export_communication_package_markdown,
    export_html,
    export_json,
    export_markdown,
)

router = APIRouter(prefix="/tasks", tags=["contents"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


async def _require_task(repository: TaskRepository, task_id: str) -> TaskRecord:
    task = await repository.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task


@router.get("/{task_id}/contents", response_model=list[ContentVersionResponse])
async def list_contents(task_id: str, session: SessionDependency) -> list[ContentVersionResponse]:
    repository = TaskRepository(session)
    await _require_task(repository, task_id)
    records = await ContentService(repository).list_versions(task_id)
    return [ContentVersionResponse.from_record(record) for record in records]


@router.post("/{task_id}/regenerate", response_model=ContentVersionResponse)
async def regenerate_content(
    task_id: str, payload: RegenerateContentRequest, session: SessionDependency
) -> ContentVersionResponse:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    try:
        record = await ContentService(repository).regenerate(
            task,
            audience=payload.audience,
            duration_minutes=payload.duration_minutes,
            output_type=payload.output_type,
            interaction_count=payload.interaction_count,
            mode=payload.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ContentVersionResponse.from_record(record)


@router.put("/{task_id}/contents/{version}", response_model=ContentVersionResponse)
async def save_content_edit(
    task_id: str,
    version: int,
    payload: UpdateContentRequest,
    session: SessionDependency,
) -> ContentVersionResponse:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    if version != task.current_content_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="只能编辑当前内容版本；请先恢复目标版本",
        )
    try:
        record = await ContentService(repository).save_edit(
            task, payload.content, payload.change_summary
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ContentVersionResponse.from_record(record)


@router.post("/{task_id}/contents/{version}/activate", response_model=ContentVersionResponse)
async def activate_content_version(
    task_id: str, version: int, session: SessionDependency
) -> ContentVersionResponse:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    try:
        record = await ContentService(repository).activate(task, version)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ContentVersionResponse.from_record(record)


@router.post("/{task_id}/exports")
async def export_content(
    task_id: str, payload: ExportContentRequest, session: SessionDependency
) -> Response:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    if (
        task.generated_content is None
        or task.evolution_package is None
        or task.audit_report is None
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务尚未生成内容")
    content = GeneratedContent.model_validate(task.generated_content)
    evolution = EvolutionPackage.model_validate(task.evolution_package)
    filename = f"character-vein-{task.id}-v{task.current_content_version}"
    if payload.format == "markdown":
        body = export_markdown(content, evolution)
        media_type = "text/markdown; charset=utf-8"
        suffix = "md"
    elif payload.format == "html":
        body = export_html(content, evolution)
        media_type = "text/html; charset=utf-8"
        suffix = "html"
    else:
        body = export_json(
            task_id=task.id,
            version=task.current_content_version,
            spec=TaskSpec.model_validate(task.spec),
            content=content,
            evolution=evolution,
            audit=AuditReport.model_validate(task.audit_report),
        )
        media_type = "application/json; charset=utf-8"
        suffix = "json"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}.{suffix}"'},
    )


@router.post("/{task_id}/communication-package/exports")
async def export_communication_package(
    task_id: str, payload: ExportContentRequest, session: SessionDependency
) -> Response:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    if task.cultural_motif is None or len(task.communication_assets or {}) != 3:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="传播成品包尚未生成完整")
    motif = CulturalMotif.model_validate(task.cultural_motif)
    assets = {
        key: CommunicationAsset.model_validate(value)
        for key, value in task.communication_assets.items()
    }
    filename = f"character-vein-package-{task.id}"
    if payload.format == "markdown":
        body = export_communication_package_markdown(motif, assets)
        media_type = "text/markdown; charset=utf-8"
        suffix = "md"
    elif payload.format == "html":
        body = export_communication_package_html(motif, assets)
        media_type = "text/html; charset=utf-8"
        suffix = "html"
    else:
        body = export_communication_package_json(
            task_id=task.id,
            motif=motif,
            assets=assets,
            evaluation=task.artifact_evaluation,
        )
        media_type = "application/json; charset=utf-8"
        suffix = "json"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}.{suffix}"'},
    )
