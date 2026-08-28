from typing import Any

import pytest

from character_vein_domain import (
    RetrievedEvidence,
    TaskSpec,
)
from character_vein_retrieval import FixtureEvidenceProvider, InMemoryHybridRetriever
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
    assert any(item.structured_rank or item.keyword_rank or item.semantic_rank for item in results)


async def test_normal_agent_run_exposes_dynamic_plan_queries_and_tool_trace() -> None:
    events: list[tuple[str, str, str, dict[str, Any]]] = []

    async def sink(step: str, status: str, summary: str, payload: dict[str, Any]) -> None:
        events.append((step, status, summary, payload))

    graph = build_stage_two_graph(event_sink=sink)
    spec = TaskSpec(target_characters=["礼"], required_stages=3, interaction_count=2)

    result = await graph.ainvoke({"task_spec": spec.model_dump(mode="json")})

    assert result["audit_report"]["status"] == "approved"
    assert result["constraint_result"]["passed"] is True
    assert result["requires_user_confirmation"] is False
    assert len(result["search_queries"]) == 10
    assert {item["status"] for item in result["plan"]} == {"completed"}
    assert all(item["completion_criteria"] for item in result["plan"])
    tool_names = {item["tool_name"] for item in result["tool_calls"]}
    assert {
        "search_evidence",
        "search_glyphs",
        "analyze_glyphs",
        "generate_content",
        "check_constraints",
    } <= tool_names
    assert events[0][:2] == ("plan", "running")
    assert not any(step in {"claim_support", "audit"} for step, _, _, _ in events)
    assert events[-1][0] == "constraints"


class EmptyRetriever:
    async def retrieve(
        self,
        query: str,
        limit: int = 8,
        **_: str | None,
    ) -> list[RetrievedEvidence]:
        return []


async def test_missing_reference_context_is_reported_without_audit_retry() -> None:
    graph = build_stage_two_graph(retriever=EmptyRetriever())
    spec = TaskSpec(target_characters=["明"], required_stages=3, interaction_count=2)

    result = await graph.ainvoke({"task_spec": spec.model_dump(mode="json")})

    assert result["retrieval_attempt"] == 3
    assert result["audit_report"]["model"] == "not-run"
    assert result["requires_user_confirmation"] is False
    assert result["constraint_result"]["passed"] is False
    assert result["constraint_result"]["checks"]["reference_context"] is False
    assert result["evolution_package"]["claims"] == []


def test_production_graph_has_no_claim_or_audit_nodes() -> None:
    graph = build_stage_two_graph()

    assert {"bind_claim_evidence", "audit_claims", "prepare_retry"}.isdisjoint(
        graph.get_graph().nodes
    )


def test_tool_registry_declares_typed_agent_tools() -> None:
    toolbox = AgentToolbox(
        [FixtureEvidenceProvider(InMemoryHybridRetriever(all_demo_evidence_corpus()))], None
    )

    definitions = {item.name: item for item in toolbox.registry.list()}

    assert set(definitions) == {
        "search_evidence",
        "search_glyphs",
        "analyze_glyphs",
        "build_cultural_motif",
        "generate_communication_asset",
        "evaluate_communication_asset",
        "generate_content",
        "check_constraints",
    }
    assert all(item.input_schema and item.output_schema for item in definitions.values())
    assert definitions["generate_content"].read_only is False
    assert definitions["generate_communication_asset"].read_only is False
