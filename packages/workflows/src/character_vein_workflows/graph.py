from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from character_vein_domain import (
    AgentAction,
    AgentDecisionContext,
    AgentPhase,
    ArtifactEvaluation,
    AuditReport,
    CommunicationAsset,
    CommunicationAssetType,
    CommunicationBrief,
    ConstraintResult,
    CulturalMotif,
    Evidence,
    EvidenceSearchQuery,
    EvolutionPackage,
    ExplorationBudget,
    GeneratedContent,
    GlyphAvailability,
    GlyphLineageRole,
    GlyphRetrievalSummary,
    GlyphVisualAnalysis,
    InteractiveStoryContent,
    NarrativeRoute,
    PlanStep,
    RetrievalSummary,
    RetrievedEvidence,
    RetrievedGlyphImage,
    ShortVideoScriptContent,
    SocialCardsContent,
    Source,
    TaskSpec,
    ToolCall,
    communication_brief_from_task_spec,
)
from character_vein_providers import DeterministicTextProvider, TextModelProvider
from character_vein_retrieval import (
    EvidenceProvider,
    EvidenceRetriever,
    EvidenceSearchContext,
    FixtureEvidenceProvider,
    GlyphImageRetriever,
    InMemoryHybridRetriever,
)
from character_vein_workflows.decisions import accept_decision, allowed_actions
from character_vein_workflows.fixtures import all_demo_evidence_corpus, case_evolution_package
from character_vein_workflows.jiezi_catalog import catalog_entry
from character_vein_workflows.tools import AgentToolbox, ToolExecutionError

EventSink = Callable[[str, str, str, dict[str, Any]], Awaitable[None]]
GlyphVisualAnalyzer = Callable[[str, list[RetrievedGlyphImage]], Awaitable[GlyphVisualAnalysis]]
PlanStatus = Literal["pending", "running", "completed", "failed"]


class WorkflowState(TypedDict, total=False):
    task_id: str
    input_asset_ids: list[str]
    task_spec: dict[str, Any]
    communication_brief: dict[str, Any]
    plan: list[dict[str, Any]]
    allowed_actions: list[str]
    budgets: dict[str, int]
    current_phase: str
    next_action: str
    decision_summary: str
    exploration_history: list[dict[str, Any]]
    search_queries: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    retrieval_attempt: int
    glyph_attempt: int
    generation_attempt: int
    retrieval_results: list[dict[str, Any]]
    retrieval_summaries: list[dict[str, Any]]
    glyph_retrieval_results: list[dict[str, Any]]
    glyph_retrieval_summaries: list[dict[str, Any]]
    glyph_visual_analysis: dict[str, Any]
    evolution_package: dict[str, Any]
    audit_report: dict[str, Any]
    generated_content: dict[str, Any]
    constraint_result: dict[str, Any]
    requires_user_confirmation: bool
    narrative_routes: list[dict[str, Any]]
    selected_route_id: str
    cultural_motif: dict[str, Any]
    communication_assets: dict[str, dict[str, Any]]
    artifact_evaluation: dict[str, Any]
    retry_targets: list[str]


def _set_plan_status(
    state: WorkflowState,
    step_id: str,
    status: PlanStatus,
    summary: str = "",
) -> list[dict[str, Any]]:
    steps = [PlanStep.model_validate(item) for item in state.get("plan", [])]
    for step in steps:
        if step.id == step_id:
            step.status = status
            if summary:
                step.summary = summary
            break
    return [step.model_dump(mode="json") for step in steps]


def _source_from_evidence(evidence: Evidence) -> Source:
    return Source(
        source_id=evidence.source_id,
        source_type=evidence.source_type,
        title=evidence.title,
        author_or_org=evidence.author_or_org,
        publication_date=evidence.publication_date,
        locator=evidence.locator,
        url=evidence.url,
        authority_level=evidence.authority_level,
        license=evidence.license,
        origin=evidence.origin,
        task_id=evidence.task_id,
        asset_id=evidence.asset_id,
        retrieved_at=evidence.retrieved_at,
    )


def _constraint_result(
    spec: TaskSpec,
    evolution: EvolutionPackage,
    content: GeneratedContent,
) -> ConstraintResult:
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
        "reference_context": bool(evolution.evidence),
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


def build_stage_two_graph(
    provider: TextModelProvider | None = None,
    retriever: EvidenceRetriever | None = None,
    evidence_providers: list[EvidenceProvider] | None = None,
    glyph_retriever: GlyphImageRetriever | None = None,
    glyph_visual_analyzer: GlyphVisualAnalyzer | None = None,
    checkpointer: Any | None = None,
    event_sink: EventSink | None = None,
    require_route_selection: bool = False,
) -> Any:
    text_provider = provider or DeterministicTextProvider()
    fixture_retriever = retriever or InMemoryHybridRetriever(all_demo_evidence_corpus())
    providers = evidence_providers or [FixtureEvidenceProvider(fixture_retriever)]
    toolbox = AgentToolbox(providers, glyph_retriever)

    async def emit(step: str, status: str, summary: str, payload: dict[str, Any]) -> None:
        if event_sink is not None:
            await event_sink(step, status, summary, payload)

    async def emit_tool(call: ToolCall) -> None:
        await emit(
            "tool_call",
            call.status,
            f"{call.tool_name}：{call.result_summary or call.error or call.status}",
            call.model_dump(mode="json"),
        )

    async def plan(state: WorkflowState) -> WorkflowState:
        spec = TaskSpec.model_validate(state["task_spec"])
        if len(spec.target_characters) != 1:
            raise ValueError("演示工作流一次只支持一个已确认汉字")
        await emit("plan", "running", "规划 Agent 正在生成任务专属执行计划", {})
        steps = await text_provider.plan_task(spec)
        normalized_steps: list[PlanStep] = []
        for step in steps:
            step.status = "pending"
            normalized_steps.append(step)
        plan_state: WorkflowState = {
            "plan": [item.model_dump(mode="json") for item in normalized_steps]
        }
        plan_state["plan"] = _set_plan_status(
            plan_state,
            "plan",
            "completed",
            f"已为“{spec.target_characters[0]}”生成 {len(normalized_steps)} 个执行步骤",
        )
        await emit("plan", "completed", "动态执行计划已生成", {"steps": plan_state["plan"]})

        await emit("query_plan", "running", "正在拆分文献检索问题", {})
        queries = await text_provider.plan_evidence_queries(spec)
        plan_state["plan"] = _set_plan_status(
            plan_state,
            "query_plan",
            "completed",
            f"形成 {len(queries)} 个分阶段、分主题检索问题",
        )
        await emit(
            "query_plan",
            "completed",
            f"检索规划完成，共 {len(queries)} 个问题",
            {"queries": [item.model_dump(mode="json") for item in queries]},
        )
        brief = communication_brief_from_task_spec(spec)
        budget = ExplorationBudget()
        decision_context = AgentDecisionContext(phase=AgentPhase.MATERIAL_EXPLORATION)
        permitted_actions = allowed_actions(decision_context, budget)
        decision = await text_provider.decide_next_action(
            brief,
            decision_context,
            budget,
            permitted_actions,
        )
        remaining_budget = accept_decision(decision, decision_context, budget)
        decision_payload = {
            **decision.model_dump(mode="json"),
            "phase": decision_context.phase.value,
            "allowed_actions": [item.value for item in permitted_actions],
            "budget_before": budget.model_dump(mode="json"),
            "budget_after": remaining_budget.model_dump(mode="json"),
        }
        await emit(
            "agent_decision",
            "completed",
            decision.decision_summary,
            decision_payload,
        )
        return {
            **plan_state,
            "communication_brief": brief.model_dump(mode="json"),
            "allowed_actions": [item.value for item in permitted_actions],
            "budgets": remaining_budget.model_dump(mode="json"),
            "current_phase": decision_context.phase.value,
            "next_action": decision.action.value,
            "decision_summary": decision.decision_summary,
            "exploration_history": [decision_payload],
            "search_queries": [item.model_dump(mode="json") for item in queries],
            "tool_calls": [],
            "retrieval_attempt": 1,
            "glyph_attempt": 1,
            "generation_attempt": 1,
            "retrieval_summaries": [],
            "glyph_retrieval_summaries": [],
            "requires_user_confirmation": False,
        }

    async def retrieve_evidence(state: WorkflowState) -> WorkflowState:
        spec = TaskSpec.model_validate(state["task_spec"])
        character = spec.target_characters[0]
        attempt = state.get("retrieval_attempt", 1)
        plan_state = _set_plan_status(state, "retrieval", "running", f"第 {attempt} 次检索")
        await emit(
            "retrieval",
            "running",
            f"文献检索 Agent 开始第 {attempt} 次三通道混合检索",
            {"attempt": attempt},
        )
        calls = list(state.get("tool_calls", []))
        summaries = list(state.get("retrieval_summaries", []))
        best_results: dict[str, RetrievedEvidence] = {}
        queries = [
            EvidenceSearchQuery.model_validate(item) for item in state.get("search_queries", [])
        ]
        for search_query in queries:
            results: list[RetrievedEvidence] = []
            context = EvidenceSearchContext(
                task_id=state.get("task_id", "fixture-task"),
                asset_ids=state.get("input_asset_ids", []),
                attempt=attempt,
            )
            for provider_name in toolbox.evidence_providers:
                try:
                    execution = await toolbox.search_evidence(
                        provider_name,
                        search_query,
                        context,
                        limit=10,
                        attempt=attempt,
                    )
                except ToolExecutionError as exc:
                    await emit_tool(exc.call)
                    raise
                calls.append(execution.call.model_dump(mode="json"))
                await emit_tool(execution.call)
                results.extend(execution.result)
            results = [item for item in results if item.evidence.character in (None, character)]
            for item in results:
                current = best_results.get(item.evidence.evidence_id)
                if current is None or item.final_score > current.final_score:
                    best_results[item.evidence.evidence_id] = item
            summary = RetrievalSummary(
                query_id=search_query.query_id,
                query=search_query.query,
                purpose=search_query.purpose,
                candidate_count=len(results),
                selected_count=sum(item.final_score > 0 for item in results),
                structured_matches=sum(item.structured_rank is not None for item in results),
                exact_matches=sum(item.exact_score > 0 for item in results),
                keyword_matches=sum(item.keyword_rank is not None for item in results),
                semantic_matches=sum(item.semantic_rank is not None for item in results),
                channel_candidate_counts={
                    "structured": sum(item.structured_rank is not None for item in results),
                    "keyword": sum(item.keyword_rank is not None for item in results),
                    "semantic": sum(item.semantic_rank is not None for item in results),
                },
                attempt=attempt,
            )
            summaries.append(summary.model_dump(mode="json"))

        ranked = sorted(best_results.values(), key=lambda item: item.final_score, reverse=True)
        plan_state = _set_plan_status(
            {**state, "plan": plan_state},
            "retrieval",
            "completed",
            f"{len(queries)} 次工具调用合并为 {len(ranked)} 条去重证据",
        )
        await emit(
            "retrieval",
            "completed",
            f"第 {attempt} 次检索完成，保留 {len(ranked)} 条去重证据",
            {"attempt": attempt, "query_count": len(queries), "evidence_count": len(ranked)},
        )
        return {
            "plan": plan_state,
            "tool_calls": calls,
            "retrieval_results": [item.model_dump(mode="json") for item in ranked],
            "retrieval_summaries": summaries,
        }

    async def evaluate_materials(state: WorkflowState) -> WorkflowState:
        brief = CommunicationBrief.model_validate(state["communication_brief"])
        budget = ExplorationBudget.model_validate(state["budgets"])
        context = AgentDecisionContext(
            phase=AgentPhase.MATERIAL_EXPLORATION,
            reference_count=len(state.get("retrieval_results", [])),
        )
        permitted_actions = allowed_actions(context, budget)
        decision = await text_provider.decide_next_action(brief, context, budget, permitted_actions)
        remaining_budget = accept_decision(decision, context, budget)
        payload = {
            **decision.model_dump(mode="json"),
            "phase": context.phase.value,
            "allowed_actions": [item.value for item in permitted_actions],
            "budget_before": budget.model_dump(mode="json"),
            "budget_after": remaining_budget.model_dump(mode="json"),
        }
        await emit("agent_decision", "completed", decision.decision_summary, payload)
        return {
            "budgets": remaining_budget.model_dump(mode="json"),
            "current_phase": context.phase.value,
            "next_action": decision.action.value,
            "decision_summary": decision.decision_summary,
            "exploration_history": [*state.get("exploration_history", []), payload],
        }

    def route_after_materials(state: WorkflowState) -> Literal["retry", "continue"]:
        action = AgentAction(state["next_action"])
        if action in {AgentAction.SEARCH_MORE, AgentAction.REWRITE_QUERY}:
            return "retry"
        return "continue"

    async def prepare_material_retry(state: WorkflowState) -> WorkflowState:
        next_attempt = state.get("retrieval_attempt", 1) + 1
        latest = state.get("exploration_history", [])[-1]
        retry_context = str(latest.get("gap") or latest.get("decision_summary") or "补充资料")
        spec = TaskSpec.model_validate(state["task_spec"])
        queries = await text_provider.plan_evidence_queries(spec, retry_context)
        plan_state = _set_plan_status(
            state,
            "retrieval",
            "pending",
            f"根据资料缺口执行第 {next_attempt} 次检索",
        )
        await emit(
            "material_retry",
            "running",
            f"资料探索进入第 {next_attempt} 轮",
            {
                "attempt": next_attempt,
                "retry_context": retry_context,
                "queries": [item.model_dump(mode="json") for item in queries],
            },
        )
        return {
            "plan": plan_state,
            "search_queries": [item.model_dump(mode="json") for item in queries],
            "retrieval_attempt": next_attempt,
        }

    async def retrieve_glyph_images(state: WorkflowState) -> WorkflowState:
        if state.get("glyph_retrieval_results"):
            return {
                "plan": _set_plan_status(
                    state,
                    "glyph_retrieval",
                    "completed",
                    "复用首次检索得到的真实字形",
                )
            }

        spec = TaskSpec.model_validate(state["task_spec"])
        character = spec.target_characters[0]
        attempt = state.get("glyph_attempt", 1)
        plan_state = _set_plan_status(state, "glyph_retrieval", "running")
        await emit("glyph_retrieval", "running", "图 RAG 正在按书体检索代表字形", {})
        calls = list(state.get("tool_calls", []))
        results: list[RetrievedGlyphImage] = []
        summaries: list[GlyphRetrievalSummary] = []
        for stage in catalog_entry(character).stages:
            if stage.availability != GlyphAvailability.AVAILABLE:
                continue
            query = (
                f"{character} {stage.script_type} {stage.historical_period} 代表字形 {spec.theme}"
            )
            try:
                execution = await toolbox.search_glyphs(
                    query,
                    character=character,
                    script_code=stage.script_code,
                    limit=4,
                    attempt=attempt,
                )
            except ToolExecutionError as exc:
                await emit_tool(exc.call)
                raise
            calls.append(execution.call.model_dump(mode="json"))
            await emit_tool(execution.call)
            candidates = [
                item
                for item in execution.result
                if item.character == character and item.script_code == stage.script_code
            ]
            selected = candidates[0] if candidates else None
            if selected is not None:
                results.append(selected)
            summaries.append(
                GlyphRetrievalSummary(
                    character=character,
                    script_type=stage.script_type,
                    script_code=stage.script_code,
                    query=query,
                    candidate_count=len(candidates),
                    selected_image_id=selected.image_id if selected else None,
                    selected_score=selected.score if selected else None,
                )
            )
        plan_state = _set_plan_status(
            {**state, "plan": plan_state},
            "glyph_retrieval",
            "completed",
            f"检索 {len(summaries)} 类书体，选出 {len(results)} 张代表图",
        )
        await emit(
            "glyph_retrieval",
            "completed",
            f"图 RAG 完成，选出 {len(results)} 张真实代表字形",
            {"stages": [item.model_dump(mode="json") for item in summaries]},
        )
        return {
            "plan": plan_state,
            "tool_calls": calls,
            "glyph_retrieval_results": [item.model_dump(mode="json") for item in results],
            "glyph_retrieval_summaries": [item.model_dump(mode="json") for item in summaries],
        }

    async def build_evolution(state: WorkflowState) -> WorkflowState:
        spec = TaskSpec.model_validate(state["task_spec"])
        character = spec.target_characters[0]
        await emit("evolution", "running", "演化 Agent 正在构建三层知识包", {})
        plan_state = _set_plan_status(state, "evolution", "running")
        base = case_evolution_package(character)
        if state.get("glyph_visual_analysis"):
            base.visual_analysis = GlyphVisualAnalysis.model_validate(
                state["glyph_visual_analysis"]
            )
        if glyph_retriever is not None:
            glyph_results = [
                RetrievedGlyphImage.model_validate(item)
                for item in state.get("glyph_retrieval_results", [])
            ]
            selected_by_script = {item.script_type: item for item in glyph_results}
            expected_scripts = {
                stage.script_type
                for stage in base.glyph_stages
                if stage.availability == GlyphAvailability.AVAILABLE
            }
            missing_scripts = sorted(expected_scripts - set(selected_by_script))
            if missing_scripts:
                raise RuntimeError(
                    "图 RAG 目录不完整，拒绝使用静态图片补位：" + "、".join(missing_scripts)
                )
            for stage in base.glyph_stages:
                if stage.availability != GlyphAvailability.AVAILABLE:
                    continue
                selected = selected_by_script[stage.script_type]
                stage.image_url = selected.content_url
                stage.image_id = str(PurePosixPath(selected.image_id).with_suffix(""))
                stage.source_path = selected.source_path
                stage.source_label = f"{stage.script_type}代表字形"
                stage.historical_period = selected.historical_period
                stage.period = selected.historical_period
                stage.lineage_role = selected.lineage_role
                stage.region_or_system = selected.region_or_system
                stage.variant_type = "rag_selected_representative"

        observations = (
            base.visual_analysis.stage_observations if base.visual_analysis is not None else []
        )
        observation_by_script = {item.script_type: item for item in observations}
        script_by_image = {item.image_id: item.script_type for item in observations}
        comparison_by_target = {
            str(PurePosixPath(item.to_image_id).with_suffix("")): item
            for item in (
                base.visual_analysis.comparisons if base.visual_analysis is not None else []
            )
        }
        for stage in base.glyph_stages:
            observation = observation_by_script.get(stage.script_type)
            if observation is None:
                stage.structure_description = (
                    f"这里展示一张{stage.script_type}字形样本，具体形态请直接观察图片。"
                )
            else:
                visible_details = [
                    *observation.visible_features[:2],
                    observation.composition,
                    observation.stroke_form,
                ]
                stage.structure_description = "图中可见：" + "；".join(
                    item for item in visible_details if item
                )
            comparison = comparison_by_target.get(stage.image_id or "")
            stage.change_from_previous = (
                "与上一阶段对照可见：" + "；".join(comparison.visible_changes[:3])
                if comparison is not None and comparison.visible_changes
                else None
            )
        base.shape_changes = [
            (
                f"{script_by_image.get(item.from_image_id, '前一阶段')}到"
                f"{script_by_image.get(item.to_image_id, '后一阶段')}："
                + "；".join(item.visible_changes[:3])
            )
            for item in (
                base.visual_analysis.comparisons if base.visual_analysis is not None else []
            )
            if item.visible_changes
        ]

        retrieved = [
            RetrievedEvidence.model_validate(item) for item in state.get("retrieval_results", [])
        ]
        selected_evidence = [item.evidence for item in retrieved if item.final_score > 0]
        evidence_by_id = {item.evidence_id: item for item in selected_evidence}
        base.evidence = list(evidence_by_id.values())
        base.sources = list(
            {item.source_id: _source_from_evidence(item) for item in base.evidence}.values()
        )
        # Reference materials are passed to the writer as context. Production generation
        # no longer creates or evaluates per-sentence Claim–Evidence relationships.
        base.claims = []
        base.meaning_changes = []
        base.cultural_contexts = []
        base.controversies = []
        base.audit_summary = {
            "approved_claims": 0,
            "downgraded_claims": 0,
            "disputed_claims": 0,
            "rejected_claims": 0,
            "status": "not_run",
        }
        compatibility_report = AuditReport(
            status="approved",
            claim_results=[],
            issues=[],
            model="not-run",
            prompt_version="reference-context-v1",
            summary="未执行事实核验；检索结果和用户资料仅作为模型生成参考。",
        )
        plan_state = _set_plan_status(
            {**state, "plan": plan_state},
            "evolution",
            "completed",
            (
                f"上下文包含 {len(base.glyph_stages)} 个字形阶段和 "
                f"{len(base.evidence)} 条参考资料片段"
            ),
        )
        await emit(
            "evolution",
            "completed",
            "字形与生成参考上下文已构建",
            {"stage_count": len(base.glyph_stages), "evidence_count": len(base.evidence)},
        )
        return {
            "plan": plan_state,
            "evolution_package": base.model_dump(mode="json"),
            # Retained so old API responses and stored tasks remain readable.
            "audit_report": compatibility_report.model_dump(mode="json"),
        }

    async def analyze_glyphs(state: WorkflowState) -> WorkflowState:
        spec = TaskSpec.model_validate(state["task_spec"])
        character = spec.target_characters[0]
        images = [
            RetrievedGlyphImage.model_validate(item)
            for item in state.get("glyph_retrieval_results", [])
        ]
        attempt = state.get("glyph_attempt", 1)
        plan_state = _set_plan_status(state, "visual_observation", "running")
        await emit(
            "visual_observation",
            "running",
            f"多模态视觉 Agent 正在观察 {len(images)} 张已标注字形",
            {},
        )

        async def operation() -> GlyphVisualAnalysis:
            if glyph_visual_analyzer is None:
                return GlyphVisualAnalysis(
                    character=character,
                    warnings=["未配置多模态字形观察器，跳过视觉观察。"],
                    model="not-configured",
                    fallback_used=True,
                )
            return await glyph_visual_analyzer(character, images)

        try:
            execution = await toolbox.execute(
                "analyze_glyphs",
                f"目标字={character}；已标注代表图={len(images)} 张",
                operation,
                lambda result: len(result.stage_observations) + len(result.comparisons),
                attempt=attempt,
                provider="vlm",
            )
        except ToolExecutionError as exc:
            await emit_tool(exc.call)
            raise
        calls = [*state.get("tool_calls", []), execution.call.model_dump(mode="json")]
        await emit_tool(execution.call)
        analysis = execution.result
        summary = (
            f"形成 {len(analysis.stage_observations)} 条单图观察和 "
            f"{len(analysis.comparisons)} 组阶段对比"
            if not analysis.fallback_used
            else "多模态观察已降级，不补写不可见细节"
        )
        plan_state = _set_plan_status(
            {**state, "plan": plan_state},
            "visual_observation",
            "completed",
            summary,
        )
        await emit(
            "visual_observation",
            "completed",
            summary,
            analysis.model_dump(mode="json"),
        )
        return {
            "plan": plan_state,
            "tool_calls": calls,
            "glyph_visual_analysis": analysis.model_dump(mode="json"),
        }

    async def evaluate_visuals(state: WorkflowState) -> WorkflowState:
        brief = CommunicationBrief.model_validate(state["communication_brief"])
        budget = ExplorationBudget.model_validate(state["budgets"])
        glyph_count = len(state.get("glyph_retrieval_results", []))
        if glyph_retriever is None:
            glyph_count = sum(
                stage.availability == GlyphAvailability.AVAILABLE
                for stage in catalog_entry(brief.target_characters[0]).stages
            )
        analysis = GlyphVisualAnalysis.model_validate(state["glyph_visual_analysis"])
        context = AgentDecisionContext(
            phase=AgentPhase.GLYPH_EXPLORATION,
            glyph_count=glyph_count,
            visual_observation_count=len(analysis.stage_observations),
        )
        permitted_actions = allowed_actions(context, budget)
        decision = await text_provider.decide_next_action(brief, context, budget, permitted_actions)
        remaining_budget = accept_decision(decision, context, budget)
        payload = {
            **decision.model_dump(mode="json"),
            "phase": context.phase.value,
            "allowed_actions": [item.value for item in permitted_actions],
            "budget_before": budget.model_dump(mode="json"),
            "budget_after": remaining_budget.model_dump(mode="json"),
            "glyph_count": glyph_count,
            "visual_observation_count": len(analysis.stage_observations),
        }
        await emit("agent_decision", "completed", decision.decision_summary, payload)
        return {
            "budgets": remaining_budget.model_dump(mode="json"),
            "current_phase": context.phase.value,
            "next_action": decision.action.value,
            "decision_summary": decision.decision_summary,
            "exploration_history": [*state.get("exploration_history", []), payload],
        }

    def route_after_visuals(state: WorkflowState) -> Literal["retry", "continue"]:
        return "retry" if state["next_action"] == AgentAction.RESELECT_GLYPH.value else "continue"

    async def prepare_glyph_retry(state: WorkflowState) -> WorkflowState:
        next_attempt = state.get("glyph_attempt", 1) + 1
        plan_state = state.get("plan", [])
        temp: WorkflowState = {**state, "plan": plan_state}
        for step_id in ("glyph_retrieval", "visual_observation"):
            temp["plan"] = _set_plan_status(
                temp,
                step_id,
                "pending",
                f"重新选择代表图，第 {next_attempt} 轮",
            )
        await emit(
            "glyph_retry",
            "running",
            f"字形探索进入第 {next_attempt} 轮",
            {"attempt": next_attempt},
        )
        return {
            "plan": temp["plan"],
            "glyph_attempt": next_attempt,
            "glyph_retrieval_results": [],
            "glyph_retrieval_summaries": [],
            "glyph_visual_analysis": {},
        }

    async def generate_narrative_routes(state: WorkflowState) -> WorkflowState:
        brief = CommunicationBrief.model_validate(state["communication_brief"])
        evolution = EvolutionPackage.model_validate(state["evolution_package"])
        budget = ExplorationBudget.model_validate(state["budgets"])
        context = AgentDecisionContext(
            phase=AgentPhase.NARRATIVE_BUILD,
            reference_count=len(evolution.evidence),
            glyph_count=sum(stage.image_id is not None for stage in evolution.glyph_stages),
            visual_observation_count=(
                len(evolution.visual_analysis.stage_observations)
                if evolution.visual_analysis is not None
                else 0
            ),
        )
        permitted_actions = allowed_actions(context, budget)
        decision = await text_provider.decide_next_action(brief, context, budget, permitted_actions)
        remaining_budget = accept_decision(decision, context, budget)
        if decision.action != AgentAction.BUILD_NARRATIVES:
            raise RuntimeError("叙事构建阶段未返回 BUILD_NARRATIVES")
        routes = await text_provider.generate_narrative_routes(brief, evolution)
        if not 2 <= len(routes) <= 3:
            raise RuntimeError("叙事路线必须为 2 到 3 条")
        decision_payload = {
            **decision.model_dump(mode="json"),
            "phase": context.phase.value,
            "allowed_actions": [item.value for item in permitted_actions],
            "budget_before": budget.model_dump(mode="json"),
            "budget_after": remaining_budget.model_dump(mode="json"),
        }
        await emit("agent_decision", "completed", decision.decision_summary, decision_payload)
        routes_payload = [item.model_dump(mode="json") for item in routes]
        await emit(
            "narrative_routes",
            "completed",
            f"已形成 {len(routes)} 条文化叙事路线",
            {"routes": routes_payload},
        )
        return {
            "budgets": remaining_budget.model_dump(mode="json"),
            "current_phase": context.phase.value,
            "next_action": decision.action.value,
            "decision_summary": decision.decision_summary,
            "exploration_history": [
                *state.get("exploration_history", []),
                decision_payload,
            ],
            "narrative_routes": routes_payload,
        }

    async def select_narrative_route(state: WorkflowState) -> WorkflowState:
        routes = [NarrativeRoute.model_validate(item) for item in state["narrative_routes"]]
        selected_route_id = state.get("selected_route_id")
        if require_route_selection and not selected_route_id:
            selected_route_id = str(
                interrupt(
                    {
                        "kind": "narrative_route_selection",
                        "routes": [item.model_dump(mode="json") for item in routes],
                    }
                )
            )
        if not selected_route_id:
            selected_route_id = routes[0].route_id
        selected = next(
            (item for item in routes if item.route_id == selected_route_id),
            None,
        )
        if selected is None:
            raise ValueError("选择的文化叙事路线不存在")
        plan_state = _set_plan_status(
            state,
            "narrative_routes",
            "completed",
            f"已选择路线：{selected.title}",
        )
        await emit(
            "narrative_route_selection",
            "completed",
            f"已选择文化叙事路线：{selected.title}",
            {"selected_route_id": selected.route_id},
        )
        return {"plan": plan_state, "selected_route_id": selected.route_id}

    async def build_cultural_motif(state: WorkflowState) -> WorkflowState:
        brief = CommunicationBrief.model_validate(state["communication_brief"])
        evolution = EvolutionPackage.model_validate(state["evolution_package"])
        routes = [NarrativeRoute.model_validate(item) for item in state["narrative_routes"]]
        narrative_route = next(
            item for item in routes if item.route_id == state["selected_route_id"]
        )
        plan_state = _set_plan_status(state, "cultural_motif", "running")
        await emit(
            "cultural_motif",
            "running",
            "文化叙事 Agent 正在固化跨媒介统一母题",
            {"selected_route_id": narrative_route.route_id},
        )

        async def operation() -> CulturalMotif:
            return await text_provider.build_cultural_motif(brief, evolution, narrative_route)

        try:
            execution = await toolbox.execute(
                "build_cultural_motif",
                f"已选路线={narrative_route.route_id}；目标字={evolution.character}",
                operation,
                lambda result: len(result.visual_sequence),
                attempt=1,
            )
        except ToolExecutionError as exc:
            await emit_tool(exc.call)
            raise
        calls = [*state.get("tool_calls", []), execution.call.model_dump(mode="json")]
        await emit_tool(execution.call)
        motif = execution.result
        plan_state = _set_plan_status(
            {**state, "plan": plan_state},
            "cultural_motif",
            "completed",
            f"统一母题“{motif.title}”已固化，包含 {len(motif.visual_sequence)} 个视觉钩子",
        )
        payload = motif.model_dump(mode="json")
        await emit("cultural_motif", "completed", f"统一文化母题已形成：{motif.title}", payload)
        return {
            "plan": plan_state,
            "tool_calls": calls,
            "cultural_motif": payload,
        }

    async def generate_communication_assets(state: WorkflowState) -> WorkflowState:
        brief = CommunicationBrief.model_validate(state["communication_brief"])
        evolution = EvolutionPackage.model_validate(state["evolution_package"])
        motif = CulturalMotif.model_validate(state["cultural_motif"])
        routes = [NarrativeRoute.model_validate(item) for item in state["narrative_routes"]]
        narrative_route = next(
            item for item in routes if item.route_id == state["selected_route_id"]
        )
        asset_types = [
            CommunicationAssetType.INTERACTIVE_STORY,
            CommunicationAssetType.SOCIAL_CARDS,
            CommunicationAssetType.SHORT_VIDEO_SCRIPT,
        ]
        plan_state = _set_plan_status(state, "communication_assets", "running")
        await emit(
            "communication_assets",
            "running",
            "跨媒介传播 Agent 正在并行生成互动长页、五张卡片与 60 秒视频脚本",
            {"asset_types": [item.value for item in asset_types]},
        )

        def item_count(asset: CommunicationAsset) -> int:
            if isinstance(asset.content, InteractiveStoryContent):
                return len(asset.content.sections)
            if isinstance(asset.content, SocialCardsContent):
                return len(asset.content.cards)
            if isinstance(asset.content, ShortVideoScriptContent):
                return len(asset.content.scenes)
            raise TypeError("未知传播成品结构")

        async def generate_one(asset_type: CommunicationAssetType) -> Any:
            return await toolbox.execute(
                "generate_communication_asset",
                f"目标字={evolution.character}；成品类型={asset_type.value}；母题={motif.title}",
                lambda: text_provider.generate_communication_asset(
                    asset_type,
                    brief,
                    evolution,
                    narrative_route,
                    motif,
                ),
                item_count,
                attempt=1,
            )

        try:
            executions = await asyncio.gather(*(generate_one(item) for item in asset_types))
        except ToolExecutionError as exc:
            await emit_tool(exc.call)
            raise
        calls = [*state.get("tool_calls", [])]
        assets: dict[str, dict[str, Any]] = {}
        for execution in executions:
            await emit_tool(execution.call)
            calls.append(execution.call.model_dump(mode="json"))
            asset = execution.result
            assets[asset.asset_type.value] = asset.model_dump(mode="json")
        plan_state = _set_plan_status(
            {**state, "plan": plan_state},
            "communication_assets",
            "completed",
            "已生成互动文化长页、5 张图文卡片和覆盖 0–60 秒的短视频脚本",
        )
        await emit(
            "communication_assets",
            "completed",
            "三类传播成品已共享同一文化母题和视觉顺序",
            {"assets": assets},
        )
        return {
            "plan": plan_state,
            "tool_calls": calls,
            "communication_assets": assets,
        }

    async def evaluate_communication_assets(state: WorkflowState) -> WorkflowState:
        brief = CommunicationBrief.model_validate(state["communication_brief"])
        evolution = EvolutionPackage.model_validate(state["evolution_package"])
        motif = CulturalMotif.model_validate(state["cultural_motif"])
        assets = {
            key: CommunicationAsset.model_validate(value)
            for key, value in state["communication_assets"].items()
        }
        plan_state = _set_plan_status(state, "artifact_evaluation", "running")
        await emit(
            "artifact_evaluation",
            "running",
            "传播成品验收 Agent 正在独立检查三类成品",
            {},
        )

        async def evaluate_one(asset: CommunicationAsset) -> Any:
            return await toolbox.execute(
                "evaluate_communication_asset",
                f"成品类型={asset.asset_type.value}；母题={motif.title}",
                lambda: text_provider.evaluate_communication_asset(
                    brief,
                    evolution,
                    motif,
                    asset,
                ),
                lambda result: sum(result.checks.values()),
                attempt=asset.version,
            )

        try:
            executions = await asyncio.gather(*(evaluate_one(item) for item in assets.values()))
        except ToolExecutionError as exc:
            await emit_tool(exc.call)
            raise
        calls = [*state.get("tool_calls", [])]
        evaluations: dict[str, dict[str, Any]] = {}
        retry_targets: list[str] = []
        for execution in executions:
            await emit_tool(execution.call)
            calls.append(execution.call.model_dump(mode="json"))
            evaluation = execution.result
            asset_type = execution.call.input_summary.split("；", 1)[0].split("=", 1)[1]
            evaluations[asset_type] = evaluation.model_dump(mode="json")
            retry_targets.extend(evaluation.retry_targets)
        retry_targets = list(dict.fromkeys(retry_targets))
        passed = all(item["passed"] for item in evaluations.values())
        messages = [
            f"{asset_type}:{message}"
            for asset_type, evaluation in evaluations.items()
            for message in evaluation["messages"]
        ]
        aggregate: dict[str, Any] = {
            "passed": passed,
            "assets": evaluations,
            "retry_targets": retry_targets,
            "messages": messages,
        }
        summary = "三类传播成品均通过独立验收" if passed else "存在未满足项：" + "、".join(messages)
        plan_state = _set_plan_status(
            {**state, "plan": plan_state},
            "artifact_evaluation",
            "completed",
            summary,
        )
        await emit("artifact_evaluation", "completed", summary, aggregate)
        return {
            "plan": plan_state,
            "tool_calls": calls,
            "artifact_evaluation": aggregate,
            "retry_targets": retry_targets,
        }

    def route_after_asset_evaluation(state: WorkflowState) -> Literal["retry", "continue"]:
        budget = ExplorationBudget.model_validate(state["budgets"])
        return (
            "retry"
            if state.get("retry_targets") and budget.can_execute(AgentAction.REWRITE_ASSET)
            else "continue"
        )

    async def rewrite_failed_assets(state: WorkflowState) -> WorkflowState:
        brief = CommunicationBrief.model_validate(state["communication_brief"])
        evolution = EvolutionPackage.model_validate(state["evolution_package"])
        motif = CulturalMotif.model_validate(state["cultural_motif"])
        routes = [NarrativeRoute.model_validate(item) for item in state["narrative_routes"]]
        narrative_route = next(
            item for item in routes if item.route_id == state["selected_route_id"]
        )
        budget = ExplorationBudget.model_validate(state["budgets"])
        targets = state["retry_targets"]
        context = AgentDecisionContext(
            phase=AgentPhase.ASSET_EVALUATION,
            unmet_criteria=state["artifact_evaluation"]["messages"],
        )
        decision = await text_provider.decide_next_action(
            brief,
            context,
            budget,
            [AgentAction.REWRITE_ASSET],
        )
        remaining_budget = accept_decision(decision, context, budget)
        decision_payload = {
            **decision.model_dump(mode="json"),
            "phase": context.phase.value,
            "allowed_actions": [AgentAction.REWRITE_ASSET.value],
            "budget_before": budget.model_dump(mode="json"),
            "budget_after": remaining_budget.model_dump(mode="json"),
            "retry_targets": targets,
        }
        await emit("agent_decision", "completed", decision.decision_summary, decision_payload)
        assets = {
            key: CommunicationAsset.model_validate(value)
            for key, value in state["communication_assets"].items()
        }
        evaluations = {
            key: ArtifactEvaluation.model_validate(value)
            for key, value in state["artifact_evaluation"]["assets"].items()
        }

        async def rewrite_one(target: str) -> Any:
            existing = assets[target]
            return await toolbox.execute(
                "generate_communication_asset",
                f"定向返工={target}；母题={motif.title}",
                lambda: text_provider.generate_communication_asset(
                    existing.asset_type,
                    brief,
                    evolution,
                    narrative_route,
                    motif,
                    existing,
                    evaluations[target],
                ),
                lambda _result: 1,
                attempt=existing.version + 1,
            )

        executions = await asyncio.gather(*(rewrite_one(target) for target in targets))
        calls = [*state.get("tool_calls", [])]
        for target, execution in zip(targets, executions, strict=True):
            await emit_tool(execution.call)
            calls.append(execution.call.model_dump(mode="json"))
            rewritten = execution.result
            rewritten.version = assets[target].version + 1
            assets[target] = rewritten
        await emit(
            "asset_rewrite",
            "completed",
            "仅重新生成未通过验收的传播成品：" + "、".join(targets),
            {"retry_targets": targets},
        )
        return {
            "budgets": remaining_budget.model_dump(mode="json"),
            "tool_calls": calls,
            "communication_assets": {
                key: value.model_dump(mode="json") for key, value in assets.items()
            },
            "retry_targets": [],
            "exploration_history": [
                *state.get("exploration_history", []),
                decision_payload,
            ],
        }

    async def generate(state: WorkflowState) -> WorkflowState:
        spec = TaskSpec.model_validate(state["task_spec"])
        evolution = EvolutionPackage.model_validate(state["evolution_package"])
        routes = [NarrativeRoute.model_validate(item) for item in state["narrative_routes"]]
        narrative_route = next(
            item for item in routes if item.route_id == state["selected_route_id"]
        )
        attempt = state.get("generation_attempt", 1)
        plan_state = _set_plan_status(state, "content", "running")
        await emit("content", "running", f"文化传播 Agent 正在生成内容（第 {attempt} 次）", {})

        async def operation() -> GeneratedContent:
            return await text_provider.generate_content(spec, evolution, narrative_route)

        try:
            execution = await toolbox.execute(
                "generate_content",
                f"目标字={evolution.character}；受众={spec.audience}；时长={spec.duration_minutes}分钟",
                operation,
                lambda result: result.estimated_characters,
                attempt=attempt,
            )
        except ToolExecutionError as exc:
            await emit_tool(exc.call)
            raise
        calls = [*state.get("tool_calls", []), execution.call.model_dump(mode="json")]
        await emit_tool(execution.call)
        content = execution.result
        plan_state = _set_plan_status(
            {**state, "plan": plan_state},
            "content",
            "completed",
            (
                f"生成约 {content.estimated_characters} 字，含 "
                f"{len(content.interaction_questions)} 道互动题"
            ),
        )
        await emit("content", "completed", "模型已参考检索与上传资料生成传播内容", {})
        return {
            "plan": plan_state,
            "tool_calls": calls,
            "generated_content": content.model_dump(mode="json"),
        }

    async def check_constraints(state: WorkflowState) -> WorkflowState:
        spec = TaskSpec.model_validate(state["task_spec"])
        evolution = EvolutionPackage.model_validate(state["evolution_package"])
        content = GeneratedContent.model_validate(state["generated_content"])
        attempt = state.get("generation_attempt", 1)
        plan_state = _set_plan_status(state, "constraints", "running")
        await emit("constraints", "running", "约束检查 Agent 正在执行硬约束检查", {})

        async def operation() -> ConstraintResult:
            return _constraint_result(spec, evolution, content)

        try:
            execution = await toolbox.execute(
                "check_constraints",
                "参考上下文、阶段、受众、时长与互动题",
                operation,
                lambda result: sum(result.checks.values()),
                attempt=attempt,
            )
        except ToolExecutionError as exc:
            await emit_tool(exc.call)
            raise
        calls = [*state.get("tool_calls", []), execution.call.model_dump(mode="json")]
        await emit_tool(execution.call)
        result = execution.result
        summary = "全部硬约束通过" if result.passed else "未通过：" + "、".join(result.messages)
        plan_state = _set_plan_status(
            {**state, "plan": plan_state}, "constraints", "completed", summary
        )
        await emit("constraints", "completed", summary, result.model_dump(mode="json"))
        return {
            "plan": plan_state,
            "tool_calls": calls,
            "constraint_result": result.model_dump(mode="json"),
        }

    def route_after_constraints(state: WorkflowState) -> Literal["retry", "finish"]:
        result = ConstraintResult.model_validate(state["constraint_result"])
        retryable_checks = {
            "interaction_count",
            "visual_context_usage",
            "audience",
            "duration",
        }
        failed = {name for name, passed in result.checks.items() if not passed}
        if failed and failed <= retryable_checks and state.get("generation_attempt", 1) < 2:
            return "retry"
        return "finish"

    async def prepare_generation_retry(state: WorkflowState) -> WorkflowState:
        next_attempt = state.get("generation_attempt", 1) + 1
        temp: WorkflowState = {**state}
        for step_id in ("content", "constraints"):
            temp["plan"] = _set_plan_status(temp, step_id, "pending", "根据约束检查重新生成")
        await emit(
            "content_retry",
            "running",
            f"传播层触发第 {next_attempt} 次生成",
            {"failed_checks": state.get("constraint_result", {}).get("messages", [])},
        )
        return {"plan": temp["plan"], "generation_attempt": next_attempt}

    builder = StateGraph(WorkflowState)
    builder.add_node("plan", plan)
    builder.add_node("retrieve_evidence", retrieve_evidence)
    builder.add_node("evaluate_materials", evaluate_materials)
    builder.add_node("prepare_material_retry", prepare_material_retry)
    builder.add_node("retrieve_glyph_images", retrieve_glyph_images)
    builder.add_node("analyze_glyphs", analyze_glyphs)
    builder.add_node("evaluate_visuals", evaluate_visuals)
    builder.add_node("prepare_glyph_retry", prepare_glyph_retry)
    builder.add_node("build_evolution", build_evolution)
    builder.add_node("generate_narrative_routes", generate_narrative_routes)
    builder.add_node("select_narrative_route", select_narrative_route)
    builder.add_node("build_cultural_motif", build_cultural_motif)
    builder.add_node("generate_communication_assets", generate_communication_assets)
    builder.add_node("evaluate_communication_assets", evaluate_communication_assets)
    builder.add_node("rewrite_failed_assets", rewrite_failed_assets)
    builder.add_node("generate_content", generate)
    builder.add_node("check_constraints", check_constraints)
    builder.add_node("prepare_generation_retry", prepare_generation_retry)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "retrieve_evidence")
    builder.add_edge("retrieve_evidence", "evaluate_materials")
    builder.add_conditional_edges(
        "evaluate_materials",
        route_after_materials,
        {"retry": "prepare_material_retry", "continue": "retrieve_glyph_images"},
    )
    builder.add_edge("prepare_material_retry", "retrieve_evidence")
    builder.add_edge("retrieve_glyph_images", "analyze_glyphs")
    builder.add_edge("analyze_glyphs", "evaluate_visuals")
    builder.add_conditional_edges(
        "evaluate_visuals",
        route_after_visuals,
        {"retry": "prepare_glyph_retry", "continue": "build_evolution"},
    )
    builder.add_edge("prepare_glyph_retry", "retrieve_glyph_images")
    builder.add_edge("build_evolution", "generate_narrative_routes")
    builder.add_edge("generate_narrative_routes", "select_narrative_route")
    builder.add_edge("select_narrative_route", "build_cultural_motif")
    builder.add_edge("build_cultural_motif", "generate_communication_assets")
    builder.add_edge("generate_communication_assets", "evaluate_communication_assets")
    builder.add_conditional_edges(
        "evaluate_communication_assets",
        route_after_asset_evaluation,
        {"retry": "rewrite_failed_assets", "continue": "generate_content"},
    )
    builder.add_edge("rewrite_failed_assets", "evaluate_communication_assets")
    builder.add_edge("generate_content", "check_constraints")
    builder.add_conditional_edges(
        "check_constraints",
        route_after_constraints,
        {"retry": "prepare_generation_retry", "finish": END},
    )
    builder.add_edge("prepare_generation_retry", "generate_content")
    return builder.compile(checkpointer=checkpointer)


def build_stage_one_graph(
    provider: TextModelProvider | None = None, checkpointer: Any | None = None
) -> Any:
    """Backward-compatible alias retained while stage-one tests migrate."""

    return build_stage_two_graph(provider=provider, checkpointer=checkpointer)
