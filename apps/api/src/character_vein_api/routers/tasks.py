from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from character_vein_api.database import async_session_factory, get_session
from character_vein_api.models import TaskRecord
from character_vein_api.repositories import CommunicationAssetRepository, TaskRepository
from character_vein_api.schemas import (
    CommunicationAssetVersionResponse,
    ConfirmTaskRequest,
    CreateTaskRequest,
    RegenerateCommunicationFragmentRequest,
    TaskResponse,
    WorkflowEventResponse,
)
from character_vein_api.services import CommunicationAssetService, TaskService
from character_vein_domain import CommunicationAssetType, EvolutionPackage, GeneratedContent
from character_vein_exporters import export_markdown

router = APIRouter(prefix="/tasks", tags=["tasks"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


async def _require_task(repository: TaskRepository, task_id: str) -> TaskRecord:
    task = await repository.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task


async def _execute_queued_task(task_id: str, resume: bool, route_id: str | None = None) -> None:
    async with async_session_factory() as session:
        repository = TaskRepository(session)
        task = await repository.get(task_id)
        if task is not None:
            await TaskService(repository).run(
                task,
                resume=resume,
                prestarted=True,
                route_id=route_id,
            )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(payload: CreateTaskRequest, session: SessionDependency) -> TaskResponse:
    service = TaskService(TaskRepository(session))
    try:
        task = await service.create(
            payload.raw_input,
            payload.asset_ids,
            web_search_enabled=payload.web_search_enabled,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return TaskResponse.from_record(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, session: SessionDependency) -> TaskResponse:
    repository = TaskRepository(session)
    return TaskResponse.from_record(await _require_task(repository, task_id))


@router.put("/{task_id}/spec", response_model=TaskResponse)
async def confirm_task(
    task_id: str, payload: ConfirmTaskRequest, session: SessionDependency
) -> TaskResponse:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    try:
        task = await TaskService(repository).confirm(task, payload.spec)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return TaskResponse.from_record(task)


@router.post(
    "/{task_id}/run",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    session: SessionDependency,
) -> TaskResponse:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    try:
        task = await TaskService(repository).queue(task)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    background_tasks.add_task(_execute_queued_task, task.id, False)
    return TaskResponse.from_record(task)


@router.post(
    "/{task_id}/resume",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    session: SessionDependency,
) -> TaskResponse:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    try:
        task = await TaskService(repository).queue(task, resume=True)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    background_tasks.add_task(_execute_queued_task, task.id, True)
    return TaskResponse.from_record(task)


@router.post(
    "/{task_id}/narrative-routes/{route_id}/select",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def select_narrative_route(
    task_id: str,
    route_id: str,
    background_tasks: BackgroundTasks,
    session: SessionDependency,
) -> TaskResponse:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    try:
        task = await TaskService(repository).select_narrative_route(task, route_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    background_tasks.add_task(_execute_queued_task, task.id, True, route_id)
    return TaskResponse.from_record(task)


@router.post("/{task_id}/acknowledge-limitations", response_model=TaskResponse)
async def acknowledge_limitations(task_id: str, session: SessionDependency) -> TaskResponse:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    try:
        task = await TaskService(repository).acknowledge_limitations(task)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return TaskResponse.from_record(task)


@router.get("/{task_id}/events", response_model=list[WorkflowEventResponse])
async def get_events(task_id: str, session: SessionDependency) -> list[WorkflowEventResponse]:
    repository = TaskRepository(session)
    await _require_task(repository, task_id)
    return [WorkflowEventResponse.from_record(item) for item in await repository.events(task_id)]


@router.get(
    "/{task_id}/communication-assets/versions",
    response_model=list[CommunicationAssetVersionResponse],
)
async def get_communication_asset_versions(
    task_id: str,
    session: SessionDependency,
) -> list[CommunicationAssetVersionResponse]:
    task_repository = TaskRepository(session)
    await _require_task(task_repository, task_id)
    records = await CommunicationAssetRepository(session).list_versions(task_id)
    return [CommunicationAssetVersionResponse.from_record(item) for item in records]


@router.post(
    "/{task_id}/communication-assets/{asset_type}/fragments/{target_index}/regenerate",
    response_model=CommunicationAssetVersionResponse,
)
async def regenerate_communication_fragment(
    task_id: str,
    asset_type: str,
    target_index: int,
    payload: RegenerateCommunicationFragmentRequest,
    session: SessionDependency,
) -> CommunicationAssetVersionResponse:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    try:
        parsed_type = CommunicationAssetType(asset_type)
        record = await CommunicationAssetService(repository).regenerate_fragment(
            task,
            asset_type=parsed_type,
            target_index=target_index,
            instruction=payload.instruction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CommunicationAssetVersionResponse.from_record(record)


@router.get("/{task_id}/export.md")
async def export_task(task_id: str, session: SessionDependency) -> Response:
    repository = TaskRepository(session)
    task = await _require_task(repository, task_id)
    if task.generated_content is None or task.evolution_package is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务尚未生成内容")
    markdown = export_markdown(
        GeneratedContent.model_validate(task.generated_content),
        EvolutionPackage.model_validate(task.evolution_package),
    )
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="task-{task.id}.md"'},
    )
