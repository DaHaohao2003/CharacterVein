from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from character_vein_domain import (
    AuditReport,
    AuditStatus,
    Claim,
    ClaimType,
    ConstraintResult,
    Evidence,
    EvidenceSearchQuery,
    EvolutionPackage,
    GeneratedContent,
    GlyphAvailability,
    GlyphLineageRole,
    GlyphRetrievalSummary,
    PlanStep,
    RetrievalSummary,
    RetrievedEvidence,
    RetrievedGlyphImage,
    Source,
    TaskSpec,
    ToolCall,
)
from character_vein_providers import (
    DeterministicAuditProvider,
    DeterministicTextProvider,
    EvidenceAuditProvider,
    TextModelProvider,
)
from character_vein_retrieval import EvidenceRetriever, GlyphImageRetriever, InMemoryHybridRetriever
from character_vein_workflows.fixtures import all_demo_evidence_corpus, case_evolution_package
from character_vein_workflows.jiezi_catalog import catalog_entry
from character_vein_workflows.tools import AgentToolbox, ToolExecutionError

EventSink = Callable[[str, str, str, dict[str, Any]], Awaitable[None]]
PlanStatus = Literal["pending", "running", "completed", "failed"]


class WorkflowState(TypedDict, total=False):
    task_spec: dict[str, Any]
    plan: list[dict[str, Any]]
    search_queries: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    retrieval_attempt: int
    generation_attempt: int
    retrieval_results: list[dict[str, Any]]
    retrieval_summaries: list[dict[str, Any]]
    glyph_retrieval_results: list[dict[str, Any]]
    glyph_retrieval_summaries: list[dict[str, Any]]
    evolution_package: dict[str, Any]
    audit_report: dict[str, Any]
    generated_content: dict[str, Any]
    constraint_result: dict[str, Any]
    requires_user_confirmation: bool


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
    )


def _constraint_result(
    spec: TaskSpec,
    evolution: EvolutionPackage,
    content: GeneratedContent,
    report: AuditReport,
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
        "audit_approved": report.status == "approved",
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
    glyph_retriever: GlyphImageRetriever | None = None,
    auditor: EvidenceAuditProvider | None = None,
    checkpointer: Any | None = None,
    event_sink: EventSink | None = None,
) -> Any:
    text_provider = provider or DeterministicTextProvider()
    evidence_retriever = retriever or InMemoryHybridRetriever(all_demo_evidence_corpus())
    evidence_auditor = auditor or DeterministicAuditProvider()
    toolbox = AgentToolbox(evidence_retriever, glyph_retriever)

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
        return {
            **plan_state,
            "search_queries": [item.model_dump(mode="json") for item in queries],
            "tool_calls": [],
            "retrieval_attempt": 1,
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
            try:
                execution = await toolbox.search_literature(
                    search_query, limit=10, attempt=attempt
                )
            except ToolExecutionError as exc:
                await emit_tool(exc.call)
                raise
            calls.append(execution.call.model_dump(mode="json"))
            await emit_tool(execution.call)
            results = [
                item
                for item in execution.result
                if item.evidence.character in (None, character)
            ]
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
        attempt = state.get("retrieval_attempt", 1)
        plan_state = _set_plan_status(state, "glyph_retrieval", "running")
        await emit("glyph_retrieval", "running", "图 RAG 正在按书体检索代表字形", {})
        calls = list(state.get("tool_calls", []))
        results: list[RetrievedGlyphImage] = []
        summaries: list[GlyphRetrievalSummary] = []
        for stage in catalog_entry(character).stages:
            if stage.availability != GlyphAvailability.AVAILABLE:
                continue
            query = (
                f"{character} {stage.script_type} {stage.historical_period} "
                f"代表字形 {spec.theme}"
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
                stage.source_label = (
                    f"JieZi-Dataset · {stage.script_type} · {stage.image_id}（图 RAG 召回）"
                )
                stage.historical_period = selected.historical_period
                stage.period = selected.historical_period
                stage.lineage_role = selected.lineage_role
                stage.region_or_system = selected.region_or_system
                stage.variant_type = "rag_selected_representative"

        retrieved = [
            RetrievedEvidence.model_validate(item) for item in state.get("retrieval_results", [])
        ]
        selected_evidence = [item.evidence for item in retrieved if item.final_score > 0]
        evidence_by_id = {item.evidence_id: item for item in selected_evidence}
        base.evidence = list(evidence_by_id.values())
        sources = {item.source_id: item for item in base.sources}
        for evidence in base.evidence:
            sources[evidence.source_id] = _source_from_evidence(evidence)
        base.sources = list(sources.values())
        plan_state = _set_plan_status(
            {**state, "plan": plan_state},
            "evolution",
            "completed",
            f"知识包包含 {len(base.glyph_stages)} 个字形阶段和 {len(base.evidence)} 条证据",
        )
        await emit(
            "evolution",
            "completed",
            "字形、字义、文化三层知识包已构建",
            {"stage_count": len(base.glyph_stages), "evidence_count": len(base.evidence)},
        )
        return {"plan": plan_state, "evolution_package": base.model_dump(mode="json")}

    def claim_topic(claim: Claim) -> str | None:
        if any(term in claim.content for term in ("分期", "直线", "支线", "古今文字")):
            return "framework"
        if any(term in claim.content for term in ("本义", "字义", "引申", "文化")):
            return "meaning_context"
        return "shape"

    async def bind_claim_evidence(state: WorkflowState) -> WorkflowState:
        evolution = EvolutionPackage.model_validate(state["evolution_package"])
        attempt = state.get("retrieval_attempt", 1)
        plan_state = _set_plan_status(state, "claim_support", "running")
        await emit("claim_support", "running", "正在为每条陈述检索并绑定直接证据", {})
        calls = list(state.get("tool_calls", []))
        summaries = list(state.get("retrieval_summaries", []))
        queries = [
            EvidenceSearchQuery.model_validate(item) for item in state.get("search_queries", [])
        ]
        evidence_by_id = {item.evidence_id: item for item in evolution.evidence}
        initial_retrieval = [
            RetrievedEvidence.model_validate(item)
            for item in state.get("retrieval_results", [])
        ]
        for claim in evolution.claims:
            topic = claim_topic(claim)
            search_query = EvidenceSearchQuery(
                query_id=f"claim-{claim.claim_id}-a{attempt}",
                query=f"{evolution.character} {claim.content}",
                purpose=f"为陈述 {claim.claim_id} 查找直接支持证据",
                character=evolution.character,
                topic=topic,
            )
            queries.append(search_query)
            try:
                execution = await toolbox.search_literature(
                    search_query, limit=6, attempt=attempt
                )
            except ToolExecutionError as exc:
                await emit_tool(exc.call)
                raise
            calls.append(execution.call.model_dump(mode="json"))
            await emit_tool(execution.call)
            candidates = [
                item
                for item in execution.result
                if item.evidence.character in (None, evolution.character)
            ]
            for item in candidates:
                evidence_by_id[item.evidence.evidence_id] = item.evidence
            preferred = [
                item
                for item in candidates
                if item.evidence.topic == topic
                or (topic == "framework" and item.evidence.topic == "framework")
            ]
            chosen = (preferred or candidates)[:3]
            existing = [
                evidence_id
                for evidence_id in claim.evidence_ids
                if evidence_id in evidence_by_id
            ]
            claim.evidence_ids = list(
                dict.fromkeys([*existing, *(item.evidence.evidence_id for item in chosen)])
            )[:3]
            for evidence_id in claim.evidence_ids[:1]:
                detail = await toolbox.get_source_detail(
                    evidence_id, [*candidates, *initial_retrieval], attempt=attempt
                )
                calls.append(detail.call.model_dump(mode="json"))
                await emit_tool(detail.call)
            summaries.append(
                RetrievalSummary(
                    query_id=search_query.query_id,
                    query=search_query.query,
                    purpose=search_query.purpose,
                    candidate_count=len(candidates),
                    selected_count=len(chosen),
                    structured_matches=sum(
                        item.structured_rank is not None for item in candidates
                    ),
                    exact_matches=sum(item.exact_score > 0 for item in candidates),
                    keyword_matches=sum(item.keyword_rank is not None for item in candidates),
                    semantic_matches=sum(item.semantic_rank is not None for item in candidates),
                    channel_candidate_counts={
                        "structured": sum(
                            item.structured_rank is not None for item in candidates
                        ),
                        "keyword": sum(item.keyword_rank is not None for item in candidates),
                        "semantic": sum(item.semantic_rank is not None for item in candidates),
                    },
                    attempt=attempt,
                ).model_dump(mode="json")
            )

        evolution.evidence = list(evidence_by_id.values())
        source_by_id = {item.source_id: item for item in evolution.sources}
        for evidence in evolution.evidence:
            source_by_id[evidence.source_id] = _source_from_evidence(evidence)
        evolution.sources = list(source_by_id.values())
        bound_count = sum(bool(claim.evidence_ids) for claim in evolution.claims)
        plan_state = _set_plan_status(
            {**state, "plan": plan_state},
            "claim_support",
            "completed",
            f"{bound_count}/{len(evolution.claims)} 条陈述已绑定可定位证据",
        )
        await emit(
            "claim_support",
            "completed",
            f"完成陈述级证据绑定：{bound_count}/{len(evolution.claims)}",
            {
                "claims": [
                    {"claim_id": item.claim_id, "evidence_ids": item.evidence_ids}
                    for item in evolution.claims
                ]
            },
        )
        return {
            "plan": plan_state,
            "search_queries": [item.model_dump(mode="json") for item in queries],
            "tool_calls": calls,
            "retrieval_summaries": summaries,
            "evolution_package": evolution.model_dump(mode="json"),
        }

    async def audit_claims(state: WorkflowState) -> WorkflowState:
        evolution = EvolutionPackage.model_validate(state["evolution_package"])
        attempt = state.get("retrieval_attempt", 1)
        plan_state = _set_plan_status(state, "audit", "running")
        await emit("audit", "running", f"证据审校 Agent 开始第 {attempt} 次审校", {})

        async def operation() -> AuditReport:
            return await evidence_auditor.audit(evolution.claims, evolution.evidence, attempt)

        try:
            execution = await toolbox.execute(
                "audit_claims",
                f"{len(evolution.claims)} 条陈述；{len(evolution.evidence)} 条证据",
                operation,
                lambda result: len(result.claim_results),
                attempt=attempt,
            )
        except ToolExecutionError as exc:
            await emit_tool(exc.call)
            raise
        calls = [*state.get("tool_calls", []), execution.call.model_dump(mode="json")]
        await emit_tool(execution.call)
        report = execution.result
        requires_confirmation = state.get("requires_user_confirmation", False)
        if report.status == "needs_retry" and attempt >= 2:
            report.status = "partial"
            report.summary = "两次检索后仍有陈述缺少直接证据，已隐藏该陈述并等待用户确认资料边界。"
            for issue in report.issues:
                if issue.retryable:
                    issue.retryable = False
                    issue.action = "reject"
                    issue.message = "两次检索仍未找到直接证据；该陈述不进入发布内容。"
            requires_confirmation = True
        statuses = {item.claim_id: item.status for item in report.claim_results}
        for claim in evolution.claims:
            claim.audit_status = statuses.get(claim.claim_id, AuditStatus.REJECTED)
        evolution.audit_summary = {
            "approved_claims": sum(
                claim.audit_status == AuditStatus.APPROVED for claim in evolution.claims
            ),
            "downgraded_claims": sum(
                claim.audit_status == AuditStatus.DOWNGRADED for claim in evolution.claims
            ),
            "rejected_claims": sum(
                claim.audit_status == AuditStatus.REJECTED for claim in evolution.claims
            ),
            "status": report.status,
        }
        plan_state = _set_plan_status(
            {**state, "plan": plan_state},
            "audit",
            "completed",
            report.summary,
        )
        await emit(
            "audit",
            report.status,
            report.summary,
            {
                "attempt": attempt,
                "issues": [item.model_dump(mode="json") for item in report.issues],
                "requires_user_confirmation": requires_confirmation,
            },
        )
        return {
            "plan": plan_state,
            "tool_calls": calls,
            "audit_report": report.model_dump(mode="json"),
            "evolution_package": evolution.model_dump(mode="json"),
            "requires_user_confirmation": requires_confirmation,
        }

    def route_after_audit(state: WorkflowState) -> Literal["retry", "continue"]:
        report = AuditReport.model_validate(state["audit_report"])
        if report.status == "needs_retry" and state.get("retrieval_attempt", 1) < 2:
            return "retry"
        return "continue"

    async def prepare_retry(state: WorkflowState) -> WorkflowState:
        next_attempt = state.get("retrieval_attempt", 1) + 1
        report = AuditReport.model_validate(state["audit_report"])
        retry_context = "；".join(item.message for item in report.issues if item.retryable)
        spec = TaskSpec.model_validate(state["task_spec"])
        queries = await text_provider.plan_evidence_queries(spec, retry_context)
        plan_state = state.get("plan", [])
        temp: WorkflowState = {**state, "plan": plan_state}
        for step_id in ("retrieval", "claim_support", "audit"):
            temp["plan"] = _set_plan_status(temp, step_id, "pending", "根据审校问题重新执行")
        await emit(
            "retry",
            "running",
            f"审校触发第 {next_attempt} 次定向检索",
            {
                "retry_context": retry_context,
                "queries": [q.model_dump(mode="json") for q in queries],
            },
        )
        return {
            "plan": temp["plan"],
            "search_queries": [item.model_dump(mode="json") for item in queries],
            "retrieval_attempt": next_attempt,
        }

    async def generate(state: WorkflowState) -> WorkflowState:
        spec = TaskSpec.model_validate(state["task_spec"])
        evolution = EvolutionPackage.model_validate(state["evolution_package"])
        attempt = state.get("generation_attempt", 1)
        plan_state = _set_plan_status(state, "content", "running")
        await emit("content", "running", f"文化传播 Agent 正在生成内容（第 {attempt} 次）", {})

        async def operation() -> GeneratedContent:
            return await text_provider.generate_content(spec, evolution)

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
        await emit("content", "completed", "审校后的事实层已转化为传播内容", {})
        return {
            "plan": plan_state,
            "tool_calls": calls,
            "generated_content": content.model_dump(mode="json"),
        }

    async def check_constraints(state: WorkflowState) -> WorkflowState:
        spec = TaskSpec.model_validate(state["task_spec"])
        evolution = EvolutionPackage.model_validate(state["evolution_package"])
        content = GeneratedContent.model_validate(state["generated_content"])
        report = AuditReport.model_validate(state["audit_report"])
        attempt = state.get("generation_attempt", 1)
        plan_state = _set_plan_status(state, "constraints", "running")
        await emit("constraints", "running", "约束检查 Agent 正在执行硬约束检查", {})

        async def operation() -> ConstraintResult:
            return _constraint_result(spec, evolution, content, report)

        try:
            execution = await toolbox.execute(
                "check_constraints",
                "阶段、引用、审校、受众、时长与互动题",
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
        retryable_checks = {"interaction_count", "audience", "duration"}
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
    builder.add_node("retrieve_glyph_images", retrieve_glyph_images)
    builder.add_node("build_evolution", build_evolution)
    builder.add_node("bind_claim_evidence", bind_claim_evidence)
    builder.add_node("audit_claims", audit_claims)
    builder.add_node("prepare_retry", prepare_retry)
    builder.add_node("generate_content", generate)
    builder.add_node("check_constraints", check_constraints)
    builder.add_node("prepare_generation_retry", prepare_generation_retry)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "retrieve_evidence")
    builder.add_edge("retrieve_evidence", "retrieve_glyph_images")
    builder.add_edge("retrieve_glyph_images", "build_evolution")
    builder.add_edge("build_evolution", "bind_claim_evidence")
    builder.add_edge("bind_claim_evidence", "audit_claims")
    builder.add_conditional_edges(
        "audit_claims",
        route_after_audit,
        {"retry": "prepare_retry", "continue": "generate_content"},
    )
    builder.add_edge("prepare_retry", "retrieve_evidence")
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
