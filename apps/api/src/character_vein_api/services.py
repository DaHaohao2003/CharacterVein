import hashlib
import json
import re
from typing import Any, Literal, cast

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from character_vein_api.config import get_settings
from character_vein_api.model_providers import build_embedding_provider, build_text_provider
from character_vein_api.models import ContentVersionRecord, TaskRecord
from character_vein_api.repositories import (
    AssetRepository,
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
    AuditStatus,
    ClaimType,
    ConstraintResult,
    EvolutionPackage,
    GeneratedContent,
    GlyphAvailability,
    GlyphLineageRole,
    TaskSpec,
    TaskStatus,
)
from character_vein_providers import (
    AliyunBailianAuditProvider,
    DeterministicAuditProvider,
    EvidenceAuditProvider,
)
from character_vein_workflows import WorkflowState, build_stage_two_graph
from character_vein_workflows.fixtures import (
    SUPPORTED_DEMO_CHARACTERS,
    all_demo_evidence_corpus,
    all_demo_sources,
)


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository
        self.provider = build_text_provider(get_settings())

    async def create(self, raw_input: str, asset_ids: list[str] | None = None) -> TaskRecord:
        asset_ids = list(dict.fromkeys(asset_ids or []))
        assets = await AssetRepository(self.repository.session).get_many(asset_ids)
        if len(assets) != len(asset_ids):
            raise ValueError("部分上传材料不存在")
        if any(asset.status != AssetStatus.COMPLETED.value for asset in assets):
            raise ValueError("上传材料尚未处理完成")

        analyses = [AssetAnalysis.model_validate(asset.analysis_json) for asset in assets]
        extracted = [analysis.extracted_text for analysis in analyses if analysis.extracted_text]
        combined_input = "\n\n".join([raw_input, *extracted])
        spec = await self.provider.parse_task(combined_input)
        if not spec.target_characters:
            asset_targets = list(
                dict.fromkeys(
                    character
                    for analysis in analyses
                    for character in analysis.target_characters
                    if len(character) == 1
                )
            )
            spec.target_characters = asset_targets[:1]
        contexts: list[str] = []
        for analysis in analyses:
            contexts.extend(analysis.user_sources)
            contexts.extend(analysis.explicit_periods)
            if analysis.extracted_text:
                contexts.append(analysis.extracted_text[:2000])
        spec.source_contexts = list(dict.fromkeys(contexts))
        spec.target_needs_confirmation = not spec.target_characters
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
            "用户确认接受资料不足边界；被拒绝的陈述仍不会进入发布内容",
            {"accepted_evidence_boundary": True},
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

    async def run(
        self,
        task: TaskRecord,
        *,
        resume: bool = False,
        prestarted: bool = False,
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
            corpus = all_demo_evidence_corpus()
            embeddings = await embedding_provider.embed([item.quote_or_summary for item in corpus])
            await evidence_repository.seed_corpus(all_demo_sources(), corpus, embeddings)
            retriever = DatabaseEvidenceRetriever(evidence_repository, embedding_provider)
            glyph_retriever = DatabaseGlyphImageRetriever(
                GlyphImageRepository(self.repository.session), embedding_provider
            )
            auditor: EvidenceAuditProvider = DeterministicAuditProvider()
            api_key = settings.llm_api_key.get_secret_value()
            if settings.llm_audit_enabled and settings.llm_provider == "aliyun-bailian" and api_key:
                auditor = AliyunBailianAuditProvider(
                    api_key=api_key,
                    base_url=settings.llm_base_url,
                    model=settings.llm_model,
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
                await self.repository.add_event(task_id, step, event_status, summary, payload)

            async with AsyncPostgresSaver.from_conn_string(
                settings.checkpoint_database_url
            ) as checkpointer:
                await checkpointer.setup()
                graph = build_stage_two_graph(
                    provider=self.provider,
                    retriever=retriever,
                    glyph_retriever=glyph_retriever,
                    auditor=auditor,
                    checkpointer=checkpointer,
                    event_sink=workflow_event_sink,
                )
                graph_config: Any = {"configurable": {"thread_id": task.id}}
                checkpoint = await checkpointer.aget(graph_config) if resume else None
                graph_input = None if checkpoint is not None else {"task_spec": task.spec}
                result = await graph.ainvoke(graph_input, graph_config)
            state = cast(WorkflowState, result)
            task.plan = state["plan"]
            task.search_queries = state.get("search_queries", [])
            task.tool_calls = state.get("tool_calls", [])
            task.requires_user_confirmation = state.get("requires_user_confirmation", False)
            task.evolution_package = state["evolution_package"]
            task.generated_content = state["generated_content"]
            task.constraint_result = state["constraint_result"]
            task.retrieval_summary = state["retrieval_summaries"]
            task.audit_report = state["audit_report"]
            evolution = EvolutionPackage.model_validate(state["evolution_package"])
            audit = AuditReport.model_validate(state["audit_report"])
            await evidence_repository.persist_task_results(task.id, evolution, audit)
            passed = bool(state["constraint_result"]["passed"])
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
                    "工作流执行完成，存在需要用户确认的资料边界"
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
        evolution, audit = self._require_fact_layer(task)
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
        constraint = evaluate_content_constraints(spec, evolution, candidate, audit)
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
        evolution, audit = self._require_fact_layer(task)
        spec = TaskSpec.model_validate(task.spec)
        content.audience = spec.audience
        content.duration_minutes = spec.duration_minutes
        valid_sources = {item.evidence_id for item in evolution.evidence}
        content.source_ids = [item for item in content.source_ids if item in valid_sources]
        content.estimated_characters = len(re.sub(r"\s|[#*\-]", "", content.body_markdown))
        constraint = evaluate_content_constraints(spec, evolution, content, audit)
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
        evolution, _ = self._require_fact_layer(task)
        source = await self.versions.get_version(task.id, version)
        if source is None:
            raise ValueError("内容版本不存在")
        current_hash = evolution_hash(evolution)
        if source.evolution_hash != current_hash:
            raise ValueError("该版本的事实层与当前任务不一致，不能恢复")
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
    def _require_fact_layer(task: TaskRecord) -> tuple[EvolutionPackage, AuditReport]:
        if (
            task.evolution_package is None
            or task.audit_report is None
            or task.generated_content is None
        ):
            raise ValueError("任务尚未生成可复用的事实层和传播内容")
        return (
            EvolutionPackage.model_validate(task.evolution_package),
            AuditReport.model_validate(task.audit_report),
        )

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


def evolution_hash(evolution: EvolutionPackage) -> str:
    canonical = json.dumps(
        evolution.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluate_content_constraints(
    spec: TaskSpec,
    evolution: EvolutionPackage,
    content: GeneratedContent,
    audit: AuditReport,
) -> ConstraintResult:
    publishable = [
        claim for claim in evolution.claims if claim.audit_status != AuditStatus.REJECTED
    ]
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
        "evidence_bound": all(
            claim.evidence_ids or claim.claim_type == ClaimType.SYSTEM_SYNTHESIS
            for claim in publishable
        ),
        "audit_approved": audit.status == "approved",
        "audience": content.audience == spec.audience,
        "duration": content.duration_minutes == spec.duration_minutes,
    }
    return ConstraintResult(
        passed=all(checks.values()),
        checks=checks,
        messages=[name for name, passed in checks.items() if not passed],
    )
