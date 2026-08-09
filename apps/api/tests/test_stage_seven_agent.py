from typing import Any

import pytest

from character_vein_domain import AuditReport, Claim, Evidence, RetrievedEvidence, TaskSpec
from character_vein_providers import DeterministicAuditProvider
from character_vein_retrieval import InMemoryHybridRetriever
from character_vein_workflows import AgentToolbox, build_stage_two_graph
from character_vein_workflows.fixtures import all_demo_evidence_corpus

SLUGS = {"云": "cloud", "雷": "thunder", "礼": "ritual", "明": "bright"}


def _golden_queries() -> list[tuple[str, str, dict[str, str], str]]:
    rows: list[tuple[str, str, dict[str, str], str]] = []
    for character, slug in SLUGS.items():
        rows.extend(
            [
                (
                    character,
                    f"{character} JieZi 书体覆盖 元数据",
                    {"character": character, "topic": "overview"},
                    f"evidence-jiezi-{slug}",
                ),
                (
                    character,
                    f"{character} 甲骨文 构形 结构",
                    {"character": character, "script_type": "甲骨文", "topic": "shape"},
                    f"evidence-jiezi-{slug}-j-shape",
                ),
                (
                    character,
                    f"{character} 金文 本义 分期",
                    {
                        "character": character,
                        "script_type": "金文",
                        "topic": "meaning_context",
                    },
                    f"evidence-jiezi-{slug}-b-context",
                ),
                (
                    character,
                    f"{character} 楷书 结构 规范形",
                    {"character": character, "script_type": "楷书", "topic": "shape"},
                    f"evidence-jiezi-{slug}-k-shape",
                ),
                (
                    character,
                    "草书 快速书写 支线 不是楷书之后的线性终点",
                    {"character": character, "topic": "framework"},
                    "evidence-moe-framework-clerical-cursive",
                ),
            ]
        )
    return rows


@pytest.mark.parametrize(("character", "query", "filters", "expected_id"), _golden_queries())
async def test_hybrid_retrieval_golden_recall_at_ten(
    character: str,
    query: str,
    filters: dict[str, str],
    expected_id: str,
) -> None:
    retriever = InMemoryHybridRetriever(all_demo_evidence_corpus())

    results = await retriever.retrieve(query, limit=10, **filters)

    assert character in SLUGS
    assert expected_id in {item.evidence.evidence_id for item in results}
    assert any(item.rrf_score > 0 for item in results)
    assert any(
        item.structured_rank or item.keyword_rank or item.semantic_rank for item in results
    )


async def test_normal_agent_run_exposes_dynamic_plan_queries_and_tool_trace() -> None:
    events: list[tuple[str, str, str, dict[str, Any]]] = []

    async def sink(
        step: str, status: str, summary: str, payload: dict[str, Any]
    ) -> None:
        events.append((step, status, summary, payload))

    graph = build_stage_two_graph(event_sink=sink)
    spec = TaskSpec(target_characters=["礼"], required_stages=3, interaction_count=2)

    result = await graph.ainvoke({"task_spec": spec.model_dump(mode="json")})

    assert result["audit_report"]["status"] == "approved"
    assert result["constraint_result"]["passed"] is True
    assert result["requires_user_confirmation"] is False
    assert len(result["search_queries"]) >= 21
    assert {item["status"] for item in result["plan"]} == {"completed"}
    assert all(item["completion_criteria"] for item in result["plan"])
    tool_names = {item["tool_name"] for item in result["tool_calls"]}
    assert {
        "search_literature",
        "search_glyphs",
        "get_source_detail",
        "audit_claims",
        "generate_content",
        "check_constraints",
    } <= tool_names
    assert events[0][:2] == ("plan", "running")
    assert any(step == "claim_support" and status == "completed" for step, status, _, _ in events)
    assert events[-1][0] == "constraints"


class EmptyRetriever:
    async def retrieve(
        self,
        query: str,
        limit: int = 8,
        **_: str | None,
    ) -> list[RetrievedEvidence]:
        return []


async def test_insufficient_evidence_is_retried_then_requires_confirmation() -> None:
    graph = build_stage_two_graph(retriever=EmptyRetriever())
    spec = TaskSpec(target_characters=["明"], required_stages=3, interaction_count=2)

    result = await graph.ainvoke({"task_spec": spec.model_dump(mode="json")})

    assert result["retrieval_attempt"] == 2
    assert result["audit_report"]["status"] == "partial"
    assert result["requires_user_confirmation"] is True
    assert result["constraint_result"]["passed"] is False
    assert all(issue["retryable"] is False for issue in result["audit_report"]["issues"])
    assert all(
        claim["audit_status"] == "rejected"
        for claim in result["evolution_package"]["claims"]
        if claim["claim_type"] != "system_synthesis"
    )


class ConflictAuditor:
    async def audit(
        self, claims: list[Claim], evidence: list[Evidence], attempt: int
    ) -> AuditReport:
        claims[0].has_conflict = True
        return await DeterministicAuditProvider().audit(claims, evidence, attempt)


async def test_conflicting_claim_is_downgraded_without_blocking_safe_content() -> None:
    graph = build_stage_two_graph(auditor=ConflictAuditor())
    spec = TaskSpec(target_characters=["雷"], required_stages=3, interaction_count=2)

    result = await graph.ainvoke({"task_spec": spec.model_dump(mode="json")})

    assert result["audit_report"]["status"] == "approved"
    assert any(
        item["status"] == "downgraded" for item in result["audit_report"]["claim_results"]
    )
    assert result["constraint_result"]["passed"] is True
    assert result["requires_user_confirmation"] is False


def test_tool_registry_declares_six_typed_agent_tools() -> None:
    toolbox = AgentToolbox(InMemoryHybridRetriever(all_demo_evidence_corpus()), None)

    definitions = {item.name: item for item in toolbox.registry.list()}

    assert set(definitions) == {
        "search_literature",
        "search_glyphs",
        "get_source_detail",
        "audit_claims",
        "generate_content",
        "check_constraints",
    }
    assert all(item.input_schema and item.output_schema for item in definitions.values())
    assert definitions["generate_content"].read_only is False
