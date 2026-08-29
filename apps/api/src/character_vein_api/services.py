import hashlib
import json
import re
from typing import Any, Literal, cast

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from character_vein_api.config import get_settings
from character_vein_api.evidence_providers import (
    AliyunBailianWebSearchClient,
    UploadEvidenceProvider,
    WebEvidenceProvider,
)
from character_vein_api.glyph_visual_analysis import (
    StoredGlyphVisualAnalyzer,
    build_vision_provider,
)
from character_vein_api.model_providers import build_embedding_provider, build_text_provider
from character_vein_api.models import CommunicationAssetRecord, ContentVersionRecord, TaskRecord
from character_vein_api.repositories import (
    AssetRepository,
    CommunicationAssetRepository,
    ContentRepository,
    EvidenceRepository,
    GlyphImageRepository,
    TaskRepository,
)
from character_vein_api.retrieval import DatabaseEvidenceRetriever, DatabaseGlyphImageRetriever
from character_vein_domain import (
    AssetAnalysis,
    AssetStatus,
    AuditReport,
    CommunicationAsset,
    CommunicationAssetType,
    CommunicationBrief,
    ConstraintResult,
    CulturalMotif,
    EvolutionPackage,
    GeneratedContent,
    GlyphAvailability,
    GlyphLineageRole,
    InteractiveStoryContent,
    NarrativeRoute,
    ShortVideoScriptContent,
    SocialCardsContent,
    SourceOrigin,
    TaskSpec,
    TaskStatus,
    communication_brief_from_task_spec,
    task_spec_from_communication_brief,
)
from character_vein_retrieval import EvidenceProvider
from character_vein_workflows import WorkflowState, build_stage_two_graph
from character_vein_workflows.fixtures import SUPPORTED_DEMO_CHARACTERS


def _generation_evidence(evolution: EvolutionPackage) -> list[Any]:
    return [
        item
        for item in evolution.evidence
        if (
            item.origin in {SourceOrigin.WEB, SourceOrigin.USER_UPLOAD}
            or (
                item.origin == SourceOrigin.FIXTURE
                and item.metadata.get("kind") == "evolution_framework"
            )
        )
        and "jiezi"
        not in " ".join([item.evidence_id, item.source_id, item.title, item.url or ""]).lower()
        and item.metadata.get("kind")
        not in {"glyph_dataset", "glyph_stage", "glyph_context"}
    ]


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository
        self.provider = build_text_provider(get_settings())

    async def create(
        self,
        raw_input: str,
        asset_ids: list[str] | None = None,
        *,
        web_search_enabled: bool = True,
    ) -> TaskRecord:
        asset_ids = list(dict.fromkeys(asset_ids or []))
        assets = await AssetRepository(self.repository.session).get_many(asset_ids)
        if len(assets) != len(asset_ids):
            raise ValueError("部分上传材料不存在")
        if any(asset.status != AssetStatus.COMPLETED.value for asset in assets):
            raise ValueError("上传材料尚未处理完成")

        analyses = [AssetAnalysis.model_validate(asset.analysis_json) for asset in assets]
        extracted = [analysis.extracted_text for analysis in analyses if analysis.extracted_text]
        combined_input = "\n\n".join([raw_input, *extracted])
        brief = await self.provider.parse_communication_brief(combined_input)
        if not brief.target_characters:
            asset_targets = list(
                dict.fromkeys(
                    character
                    for analysis in analyses
                    for character in analysis.target_characters
                    if len(character) == 1
                )
            )
            brief.target_characters = asset_targets[:1]
        contexts: list[str] = []
        for analysis in analyses:
            contexts.extend(analysis.user_sources)
            contexts.extend(analysis.explicit_periods)
            if analysis.extracted_text:
                contexts.append(analysis.extracted_text[:2000])
        brief.source_contexts = list(dict.fromkeys(contexts))
        brief.target_needs_confirmation = not brief.target_characters
        brief.web_search_enabled = web_search_enabled
        spec = task_spec_from_communication_brief(brief)
        task = await self.repository.create(raw_input, spec, asset_ids)
        await AssetRepository(self.repository.session).attach_to_task(asset_ids, task.id)
        return task

    async def confirm(self, task: TaskRecord, spec: TaskSpec) -> TaskRecord:
        if len(spec.target_characters) != 1 or len(spec.target_characters[0]) != 1:
            raise ValueError("请先确认一个目标汉字；系统不会根据未知古文字图形猜字")
        if spec.target_characters == ["車"]:
            spec.target_characters = ["车"]
        if spec.target_characters[0] not in SUPPORTED_DEMO_CHARACTERS:
            supported = "、".join(SUPPORTED_DEMO_CHARACTERS)
            raise ValueError(f"比赛版完整演示目前支持：{supported}")
        spec.target_needs_confirmation = False
        brief = communication_brief_from_task_spec(spec, raw_input=task.raw_input)
        brief.target_characters = spec.target_characters
        brief.theme = spec.theme
        brief.audience = spec.audience
        brief.duration_seconds = spec.duration_minutes * 60
        brief.required_stages = spec.required_stages
        brief.interaction_count = spec.interaction_count
        brief.language = spec.language
        brief.constraints = spec.constraints
        brief.source_contexts = spec.source_contexts
        brief.target_needs_confirmation = False
        brief.web_search_enabled = spec.web_search_enabled
        spec.communication_brief = CommunicationBrief.model_validate(brief)
        task.spec = spec.model_dump(mode="json")
        task.status = TaskStatus.CONFIRMED.value
        task.error_message = None
        await self.repository.add_event(
            task.id, "confirmation", "completed", "用户已确认结构化任务要求"
        )
        return await self.repository.save(task)

    async def acknowledge_limitations(self, task: TaskRecord) -> TaskRecord:
        if not task.requires_user_confirmation:
            raise ValueError("当前任务没有待确认的资料边界")
        task.requires_user_confirmation = False
        await self.repository.add_event(
            task.id,
            "user_confirmation",
            "completed",
            "用户确认接受参考资料不足，继续使用现有上下文生成",
            {"accepted_reference_gap": True},
        )
        return await self.repository.save(task)

    async def queue(self, task: TaskRecord, *, resume: bool = False) -> TaskRecord:
        allowed_statuses = (
            {TaskStatus.FAILED.value, TaskStatus.RUNNING.value}
            if resume
            else {TaskStatus.CONFIRMED.value}
        )
        if task.status not in allowed_statuses:
            message = "只有失败或中断的任务可以恢复" if resume else "任务必须先确认后才能执行"
            raise ValueError(message)
        task.status = TaskStatus.RUNNING.value
        task.error_message = None
        await self.repository.add_event(
            task.id,
            "workflow",
            "queued",
            "已进入后台恢复队列" if resume else "已进入后台执行队列",
        )
        return await self.repository.save(task)

    async def select_narrative_route(self, task: TaskRecord, route_id: str) -> TaskRecord:
        if task.status != TaskStatus.AWAITING_ROUTE_SELECTION.value:
            raise ValueError("任务当前不在叙事路线选择阶段")
        routes = [NarrativeRoute.model_validate(item) for item in task.narrative_routes or []]
        selected = next((item for item in routes if item.route_id == route_id), None)
        if selected is None:
            raise ValueError("选择的文化叙事路线不存在")
        task.selected_route_id = selected.route_id
        task.status = TaskStatus.RUNNING.value
        task.error_message = None
        await self.repository.add_event(
            task.id,
            "narrative_route_selection",
            "queued",
            f"已选择文化叙事路线：{selected.title}，等待恢复生成",
            {"selected_route_id": selected.route_id},
        )
        return await self.repository.save(task)

    async def run(
        self,
        task: TaskRecord,
        *,
        resume: bool = False,
        prestarted: bool = False,
        route_id: str | None = None,
    ) -> TaskRecord:
        allowed_statuses = (
            {TaskStatus.RUNNING.value}
            if prestarted
            else (
                {TaskStatus.FAILED.value, TaskStatus.RUNNING.value}
                if resume
                else {TaskStatus.CONFIRMED.value}
            )
        )
        if task.status not in allowed_statuses:
            message = "只有失败或中断的任务可以恢复" if resume else "任务必须先确认后才能执行"
            raise ValueError(message)

        task_id = task.id
        if not prestarted:
            task.status = TaskStatus.RUNNING.value
            task.error_message = None
            await self.repository.save(task)
        await self.repository.add_event(
            task.id,
            "workflow",
            "running",
            "从最近检查点恢复工作流" if resume else "后台工作流开始执行",
        )

        settings = get_settings()
        try:
            evidence_repository = EvidenceRepository(self.repository.session)
            embedding_provider = build_embedding_provider(settings)
            retriever = DatabaseEvidenceRetriever(evidence_repository, embedding_provider)
            upload_provider = UploadEvidenceProvider(
                evidence_repository,
                AssetRepository(self.repository.session),
                retriever,
                embedding_provider,
            )
            await upload_provider.prepare_snapshot(task.id, task.input_asset_ids or [])
            evidence_providers: list[EvidenceProvider] = [upload_provider]
            task_spec = TaskSpec.model_validate(task.spec)
            if task_spec.web_search_enabled:
                search_client = None
                if (
                    settings.web_search_provider == "aliyun-bailian"
                    and settings.llm_api_key.get_secret_value()
                ):
                    search_client = AliyunBailianWebSearchClient(
                        api_key=settings.llm_api_key.get_secret_value(),
                        compatible_base_url=settings.llm_base_url,
                        model=settings.llm_model,
                    )
                evidence_providers.insert(
                    0,
                    WebEvidenceProvider(
                        retriever,
                        backend=settings.web_search_provider,
                        search_client=search_client,
                        evidence_repository=evidence_repository,
                        embedding_provider=embedding_provider,
                    ),
                )
            glyph_repository = GlyphImageRepository(self.repository.session)
            glyph_retriever = DatabaseGlyphImageRetriever(glyph_repository, embedding_provider)
            glyph_visual_analyzer = StoredGlyphVisualAnalyzer(
                glyph_repository,
                settings,
                build_vision_provider(settings),
            )

            async def workflow_event_sink(
                step: str,
                event_status: str,
                summary: str,
                payload: dict[str, Any],
            ) -> None:
                if step == "plan" and isinstance(payload.get("steps"), list):
                    task.plan = cast(list[dict[str, Any]], payload["steps"])
                elif task.plan and step in {str(item["id"]) for item in task.plan}:
                    updated_plan = [dict(item) for item in task.plan]
                    for item in updated_plan:
                        if item["id"] == step:
                            item["status"] = (
                                event_status
                                if event_status in {"pending", "running", "completed", "failed"}
                                else "completed"
                            )
                            item["summary"] = summary
                    task.plan = updated_plan
                if step == "query_plan" and isinstance(payload.get("queries"), list):
                    task.search_queries = cast(list[dict[str, Any]], payload["queries"])
                if step == "tool_call":
                    task.tool_calls = [*(task.tool_calls or []), payload]
                if step == "agent_decision":
                    task.agent_runtime = {
                        "current_phase": payload.get("phase"),
                        "next_action": payload.get("action"),
                        "decision_summary": summary,
                        "allowed_actions": payload.get("allowed_actions", []),
                        "budgets": payload.get("budget_after", {}),
                    }
                if step == "narrative_routes" and isinstance(payload.get("routes"), list):
                    task.narrative_routes = cast(list[dict[str, Any]], payload["routes"])
                if step == "narrative_route_selection":
                    selected = payload.get("selected_route_id")
                    if isinstance(selected, str):
                        task.selected_route_id = selected
                if step == "cultural_motif" and event_status == "completed":
                    task.cultural_motif = payload
                if step == "communication_assets" and isinstance(payload.get("assets"), dict):
                    task.communication_assets = cast(dict[str, Any], payload["assets"])
                if step == "artifact_evaluation" and event_status == "completed":
                    task.artifact_evaluation = payload
                await self.repository.add_event(task_id, step, event_status, summary, payload)

            async with AsyncPostgresSaver.from_conn_string(
                settings.checkpoint_database_url
            ) as checkpointer:
                await checkpointer.setup()
                graph = build_stage_two_graph(
                    provider=self.provider,
                    evidence_providers=evidence_providers,
                    glyph_retriever=glyph_retriever,
                    glyph_visual_analyzer=glyph_visual_analyzer.analyze,
                    checkpointer=checkpointer,
                    event_sink=workflow_event_sink,
                    require_route_selection=True,
                )
                graph_config: Any = {"configurable": {"thread_id": task.id}}
                checkpoint = await checkpointer.aget(graph_config) if resume else None
                graph_input: Any = (
                    Command(resume=route_id)
                    if checkpoint is not None and route_id is not None
                    else (
                        None
                        if checkpoint is not None
                        else {
                            "task_id": task.id,
                            "input_asset_ids": task.input_asset_ids or [],
                            "task_spec": task.spec,
                        }
                    )
                )
                result = await graph.ainvoke(graph_input, graph_config)
            state = cast(WorkflowState, result)
            task.plan = state["plan"]
            task.search_queries = state.get("search_queries", [])
            task.tool_calls = state.get("tool_calls", [])
            task.requires_user_confirmation = state.get("requires_user_confirmation", False)
            task.evolution_package = state["evolution_package"]
            task.narrative_routes = state.get("narrative_routes", [])
            task.selected_route_id = state.get("selected_route_id") or task.selected_route_id
            task.cultural_motif = state.get("cultural_motif") or task.cultural_motif
            task.communication_assets = (
                state.get("communication_assets") or task.communication_assets or {}
            )
            task.artifact_evaluation = state.get("artifact_evaluation") or task.artifact_evaluation
            task.agent_runtime = {
                "current_phase": state.get("current_phase"),
                "next_action": state.get("next_action"),
                "decision_summary": state.get("decision_summary"),
                "allowed_actions": state.get("allowed_actions", []),
                "budgets": state.get("budgets", {}),
                "exploration_history": state.get("exploration_history", []),
            }
            evolution = EvolutionPackage.model_validate(state["evolution_package"])
            audit = AuditReport.model_validate(state["audit_report"])
            await evidence_repository.persist_task_results(task.id, evolution, audit)
            if "__interrupt__" in result:
                task.status = TaskStatus.AWAITING_ROUTE_SELECTION.value
                await self.repository.add_event(
                    task.id,
                    "workflow",
                    TaskStatus.AWAITING_ROUTE_SELECTION.value,
                    "文化资料与字形探索已完成，等待选择叙事路线",
                    {
                        "route_count": len(task.narrative_routes),
                        "allowed_route_ids": [item["route_id"] for item in task.narrative_routes],
                    },
                )
                return await self.repository.save(task)
            task.generated_content = state["generated_content"]
            task.constraint_result = state["constraint_result"]
            task.retrieval_summary = state["retrieval_summaries"]
            task.audit_report = state["audit_report"]
            motif = CulturalMotif.model_validate(state["cultural_motif"])
            brief = CommunicationBrief.model_validate(state["communication_brief"])
            package_hash = communication_context_hash(brief, evolution, motif)
            asset_repository = CommunicationAssetRepository(self.repository.session)
            latest_assets = await asset_repository.latest_by_type(task.id)
            for asset_payload in task.communication_assets.values():
                asset = CommunicationAsset.model_validate(asset_payload)
                latest = latest_assets.get(asset.asset_type.value)
                if (
                    latest is not None
                    and latest.context_hash == package_hash
                    and latest.content_json == asset.content.model_dump(mode="json")
                ):
                    continue
                await asset_repository.create_version(
                    task_id=task.id,
                    asset=asset,
                    context_hash=package_hash,
                    parent_id=latest.id if latest is not None else None,
                    evaluation=(state["artifact_evaluation"]["assets"].get(asset.asset_type.value)),
                )
            passed = bool(state["constraint_result"]["passed"]) and bool(
                state["artifact_evaluation"]["passed"]
            )
            task.status = (
                TaskStatus.COMPLETED.value
                if passed and not task.requires_user_confirmation
                else TaskStatus.PARTIAL_COMPLETE.value
            )
            content_repository = ContentRepository(self.repository.session)
            existing_versions = await content_repository.list_versions(task.id)
            current_hash = evolution_hash(evolution)
            if (
                existing_versions
                and existing_versions[0].evolution_hash == current_hash
                and existing_versions[0].content_json == task.generated_content
            ):
                task.current_content_version = existing_versions[0].version
            else:
                version = await content_repository.create_version(
                    task_id=task.id,
                    content=task.generated_content,
                    spec=task.spec,
                    constraints=task.constraint_result,
                    origin="generated",
                    parent_version=None,
                    evolution_hash=current_hash,
                    change_summary="检查点恢复后生成" if resume else "主工作流首次生成",
                )
                task.current_content_version = version.version
            await self.repository.add_event(
                task.id,
                "workflow",
                task.status,
                (
                    "工作流执行完成，存在需要用户确认的参考资料缺口"
                    if task.requires_user_confirmation
                    else "工作流执行完成"
                ),
                {
                    "tool_call_count": len(task.tool_calls),
                    "search_query_count": len(task.search_queries),
                    "requires_user_confirmation": task.requires_user_confirmation,
                },
            )
        except Exception as exc:
            await self.repository.session.rollback()
            recovered_task = await self.repository.get(task_id)
            if recovered_task is None:
                raise RuntimeError("任务在失败恢复时不存在") from exc
            task = recovered_task
            task.status = TaskStatus.FAILED.value
            task.error_message = str(exc)
            await self.repository.add_event(task.id, "workflow", "failed", str(exc))
        return await self.repository.save(task)


class ContentService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository
        self.versions = ContentRepository(repository.session)
        self.provider = build_text_provider(get_settings())

    async def list_versions(self, task_id: str) -> list[ContentVersionRecord]:
        return await self.versions.list_versions(task_id)

    async def regenerate(
        self,
        task: TaskRecord,
        *,
        audience: str | None,
        duration_minutes: int | None,
        output_type: Literal["interactive_lesson", "culture_card", "article_outline"] | None,
        interaction_count: int | None,
        mode: Literal["full", "body", "interactions"],
    ) -> ContentVersionRecord:
        evolution = self._require_generation_context(task)
        spec = TaskSpec.model_validate(task.spec)
        before = spec.model_copy(deep=True)
        if audience is not None:
            spec.audience = audience
        if duration_minutes is not None:
            spec.duration_minutes = duration_minutes
        if output_type is not None:
            spec.output_type = output_type
        if interaction_count is not None:
            spec.interaction_count = interaction_count

        candidate = await self.provider.generate_content(spec, evolution)
        current = GeneratedContent.model_validate(task.generated_content)
        if mode == "body":
            candidate.interaction_questions = current.interaction_questions
        elif mode == "interactions":
            candidate.body_markdown = current.body_markdown
            candidate.outline = current.outline
            candidate.estimated_characters = current.estimated_characters
        constraint = evaluate_content_constraints(spec, evolution, candidate)
        parent = task.current_content_version or None
        task.spec = spec.model_dump(mode="json")
        task.generated_content = candidate.model_dump(mode="json")
        task.constraint_result = constraint.model_dump(mode="json")
        record = await self.versions.create_version(
            task_id=task.id,
            content=task.generated_content,
            spec=task.spec,
            constraints=task.constraint_result,
            origin="regenerated",
            parent_version=parent,
            evolution_hash=evolution_hash(evolution),
            change_summary=self._change_summary(before, spec, mode),
        )
        task.current_content_version = record.version
        await self.repository.save(task)
        await self.repository.add_event(
            task.id,
            "local_regeneration",
            "completed",
            f"仅重建传播层并生成内容版本 v{record.version}",
            {
                "version": record.version,
                "parent_version": parent,
                "mode": mode,
                "reused_evolution_package": True,
                "evolution_hash": record.evolution_hash,
                "retrieval_rerun": False,
            },
        )
        return record

    async def save_edit(
        self, task: TaskRecord, content: GeneratedContent, change_summary: str
    ) -> ContentVersionRecord:
        evolution = self._require_generation_context(task)
        spec = TaskSpec.model_validate(task.spec)
        content.audience = spec.audience
        content.duration_minutes = spec.duration_minutes
        valid_sources = {item.evidence_id for item in _generation_evidence(evolution)}
        content.source_ids = [item for item in content.source_ids if item in valid_sources]
        content.estimated_characters = len(re.sub(r"\s|[#*\-]", "", content.body_markdown))
        constraint = evaluate_content_constraints(spec, evolution, content)
        parent = task.current_content_version or None
        task.generated_content = content.model_dump(mode="json")
        task.constraint_result = constraint.model_dump(mode="json")
        record = await self.versions.create_version(
            task_id=task.id,
            content=task.generated_content,
            spec=task.spec,
            constraints=task.constraint_result,
            origin="edited",
            parent_version=parent,
            evolution_hash=evolution_hash(evolution),
            change_summary=change_summary or "用户编辑传播内容",
        )
        task.current_content_version = record.version
        await self.repository.save(task)
        await self.repository.add_event(
            task.id,
            "content_edit",
            "completed",
            f"保存用户编辑为内容版本 v{record.version}",
            {"version": record.version, "parent_version": parent},
        )
        return record

    async def activate(self, task: TaskRecord, version: int) -> ContentVersionRecord:
        evolution = self._require_generation_context(task)
        source = await self.versions.get_version(task.id, version)
        if source is None:
            raise ValueError("内容版本不存在")
        current_hash = evolution_hash(evolution)
        if source.evolution_hash != current_hash:
            raise ValueError("该版本的生成参考上下文与当前任务不一致，不能恢复")
        parent = task.current_content_version or None
        task.generated_content = source.content_json
        task.spec = source.spec_json
        task.constraint_result = source.constraints_json
        record = await self.versions.create_version(
            task_id=task.id,
            content=source.content_json,
            spec=source.spec_json,
            constraints=source.constraints_json,
            origin="restored",
            parent_version=parent,
            evolution_hash=current_hash,
            change_summary=f"从 v{version} 恢复",
        )
        task.current_content_version = record.version
        await self.repository.save(task)
        await self.repository.add_event(
            task.id,
            "content_restore",
            "completed",
            f"从 v{version} 恢复并创建 v{record.version}",
            {"source_version": version, "version": record.version},
        )
        return record

    @staticmethod
    def _require_generation_context(task: TaskRecord) -> EvolutionPackage:
        if task.evolution_package is None or task.generated_content is None:
            raise ValueError("任务尚未生成可复用的参考上下文和传播内容")
        return EvolutionPackage.model_validate(task.evolution_package)

    @staticmethod
    def _change_summary(before: TaskSpec, after: TaskSpec, mode: str) -> str:
        changes: list[str] = []
        for label, old, new in (
            ("受众", before.audience, after.audience),
            ("时长", before.duration_minutes, after.duration_minutes),
            ("输出形式", before.output_type, after.output_type),
            ("互动题", before.interaction_count, after.interaction_count),
        ):
            if old != new:
                changes.append(f"{label}：{old} → {new}")
        return f"{mode} 局部再生成；" + ("；".join(changes) if changes else "配置未变")


class CommunicationAssetService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository
        self.versions = CommunicationAssetRepository(repository.session)
        self.provider = build_text_provider(get_settings())

    async def regenerate_fragment(
        self,
        task: TaskRecord,
        *,
        asset_type: CommunicationAssetType,
        target_index: int,
        instruction: str,
    ) -> CommunicationAssetRecord:
        if task.evolution_package is None or task.cultural_motif is None:
            raise ValueError("任务尚未生成可复用的文化传播上下文")
        current_payload = (task.communication_assets or {}).get(asset_type.value)
        if current_payload is None:
            raise ValueError("指定传播成品尚未生成")
        asset = CommunicationAsset.model_validate(current_payload)
        count = self._fragment_count(asset)
        if target_index < 1 or target_index > count:
            raise ValueError(f"片段序号必须在 1 到 {count} 之间")

        evolution = EvolutionPackage.model_validate(task.evolution_package)
        motif = CulturalMotif.model_validate(task.cultural_motif)
        brief = communication_brief_from_task_spec(
            TaskSpec.model_validate(task.spec), raw_input=task.raw_input
        )
        fragment = await self.provider.rewrite_communication_fragment(
            asset,
            target_index,
            instruction,
            brief,
            evolution,
            motif,
        )
        candidate = asset.model_copy(deep=True)
        position = target_index - 1
        if isinstance(candidate.content, InteractiveStoryContent):
            candidate.content.sections[position] = fragment  # type: ignore[assignment]
        elif isinstance(candidate.content, SocialCardsContent):
            candidate.content.cards[position] = fragment  # type: ignore[assignment]
        elif isinstance(candidate.content, ShortVideoScriptContent):
            candidate.content.scenes[position] = fragment  # type: ignore[assignment]
            candidate.content.full_narration = " ".join(
                item.narration for item in candidate.content.scenes
            )
        candidate = CommunicationAsset.model_validate(candidate.model_dump(mode="json"))
        evaluation = await self.provider.evaluate_communication_asset(
            brief, evolution, motif, candidate
        )

        latest = (await self.versions.latest_by_type(task.id)).get(asset_type.value)
        candidate.version = (latest.version + 1) if latest is not None else asset.version + 1
        candidate.status = "approved" if evaluation.passed else "needs_revision"
        record = await self.versions.create_version(
            task_id=task.id,
            asset=candidate,
            context_hash=communication_context_hash(brief, evolution, motif),
            parent_id=latest.id if latest is not None else None,
            evaluation=evaluation.model_dump(mode="json"),
        )
        updated_assets = {
            **(task.communication_assets or {}),
            asset_type.value: candidate.model_dump(mode="json"),
        }
        task.communication_assets = updated_assets
        evaluations = dict((task.artifact_evaluation or {}).get("assets", {}))
        evaluations[asset_type.value] = evaluation.model_dump(mode="json")
        for stored_type, stored_payload in updated_assets.items():
            if stored_type in evaluations:
                continue
            stored_asset = CommunicationAsset.model_validate(stored_payload)
            stored_evaluation = await self.provider.evaluate_communication_asset(
                brief, evolution, motif, stored_asset
            )
            evaluations[stored_type] = stored_evaluation.model_dump(mode="json")
        task.artifact_evaluation = {
            "passed": len(evaluations) == 3
            and all(bool(item.get("passed")) for item in evaluations.values()),
            "assets": evaluations,
            "retry_targets": [
                key for key, value in evaluations.items() if not bool(value.get("passed"))
            ],
        }
        await self.repository.save(task)
        await self.repository.add_event(
            task.id,
            "communication_fragment_regeneration",
            "completed",
            f"仅重写 {asset_type.value} 第 {target_index} 个片段并生成 v{record.version}",
            {
                "asset_type": asset_type.value,
                "target_index": target_index,
                "version": record.version,
                "parent_id": record.parent_id,
                "instruction": instruction,
                "retrieval_rerun": False,
                "evaluation": evaluation.model_dump(mode="json"),
            },
        )
        return record

    @staticmethod
    def _fragment_count(asset: CommunicationAsset) -> int:
        if isinstance(asset.content, InteractiveStoryContent):
            return len(asset.content.sections)
        if isinstance(asset.content, SocialCardsContent):
            return len(asset.content.cards)
        return len(asset.content.scenes)


def evolution_hash(evolution: EvolutionPackage) -> str:
    canonical = json.dumps(
        evolution.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def communication_context_hash(
    brief: CommunicationBrief,
    evolution: EvolutionPackage,
    motif: CulturalMotif,
) -> str:
    canonical = json.dumps(
        {
            "brief": brief.model_dump(mode="json"),
            "evolution_hash": evolution_hash(evolution),
            "motif": motif.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_content_constraints(
    spec: TaskSpec,
    evolution: EvolutionPackage,
    content: GeneratedContent,
) -> ConstraintResult:
    generation_evidence = _generation_evidence(evolution)
    checks = {
        "target_character": evolution.character in spec.target_characters,
        "historical_stages": (
            sum(
                stage.availability == GlyphAvailability.AVAILABLE
                and stage.lineage_role != GlyphLineageRole.BRANCH
                for stage in evolution.glyph_stages
            )
            >= spec.required_stages
        ),
        "interaction_count": len(content.interaction_questions) >= spec.interaction_count,
        "reference_context": not generation_evidence
        or bool(set(content.source_ids) & {item.evidence_id for item in generation_evidence}),
        "visual_context_usage": (
            evolution.visual_analysis is None
            or not evolution.visual_analysis.stage_observations
            or (
                "## 多模态字形观察" in content.body_markdown and "图中可见" in content.body_markdown
            )
        ),
        "audience": content.audience == spec.audience,
        "duration": content.duration_minutes == spec.duration_minutes,
    }
    return ConstraintResult(
        passed=all(checks.values()),
        checks=checks,
        messages=[name for name, passed in checks.items() if not passed],
    )
