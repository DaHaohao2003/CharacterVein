import pytest
from langgraph.checkpoint.memory import InMemorySaver

from character_vein_domain import RetrievedEvidence, RetrievedGlyphImage, TaskSpec
from character_vein_providers import DeterministicTextProvider
from character_vein_retrieval import InMemoryHybridRetriever
from character_vein_workflows import build_stage_one_graph, build_stage_two_graph
from character_vein_workflows.fixtures import (
    SUPPORTED_DEMO_CHARACTERS,
    all_demo_evidence_corpus,
    case_evolution_package,
)
from character_vein_workflows.jiezi_catalog import glyph_catalog


async def test_parse_cloud_task() -> None:
    provider = DeterministicTextProvider()

    spec = await provider.parse_task(
        "为小学六年级制作4分钟的云字讲解，至少3个历史阶段，生成2道互动题，争议不要写成定论。"
    )

    assert spec.target_characters == ["云"]
    assert spec.audience == "小学六年级"
    assert spec.duration_minutes == 4
    assert spec.required_stages == 3
    assert spec.interaction_count == 2
    assert spec.constraints == ["争议观点不得写成定论"]


@pytest.mark.parametrize("character", SUPPORTED_DEMO_CHARACTERS)
async def test_stage_one_graph_completes_without_external_model(
    character: str,
) -> None:
    graph = build_stage_one_graph()
    spec = TaskSpec(
        target_characters=[character],
        audience="小学六年级",
        duration_minutes=4,
        required_stages=3,
        interaction_count=2,
        constraints=["争议观点不得写成定论"],
    )

    result = await graph.ainvoke({"task_spec": spec.model_dump(mode="json")})

    assert result["evolution_package"]["character"] == character
    stages = result["evolution_package"]["glyph_stages"]
    assert len(stages) == 7
    assert [stage["script_type"] for stage in stages] == [
        "甲骨文",
        "金文",
        "战国文字",
        "篆书",
        "隶书",
        "楷书",
        "草书",
    ]
    assert [stage["script_code"] for stage in stages] == list("JBGSLKC")
    codepoint = f"U+{ord(character):04X}"
    assert [stage["image_id"] for stage in stages] == [
        f"{codepoint}/{code}/1" for code in ("J", "B", "G", "S", "L", "K", "C")
    ]
    assert all(
        stage["image_url"].startswith("/backend/api/v1/glyph-images/U+") and stage["source_path"]
        for stage in stages
        if stage["availability"] == "available"
    )
    assert all(stage["availability"] == "available" for stage in stages)
    assert stages[-1]["lineage_role"] == "branch"
    assert len(result["generated_content"]["interaction_questions"]) == 2
    assert result["constraint_result"]["passed"] is True
    assert {source["authority_level"] for source in result["evolution_package"]["sources"]} == {
        "A",
        "B",
    }
    assert any(
        source["url"] == "https://huggingface.co/datasets/Ran0/JieZi"
        for source in result["evolution_package"]["sources"]
    )
    assert result["audit_report"]["status"] == "approved"
    assert result["retrieval_summaries"][0]["selected_count"] >= 1
    assert all(
        item.get("character") in (None, character)
        for item in result["evolution_package"]["evidence"]
    )
    assert f"“{character}”" in result["generated_content"]["body_markdown"]
    assert "书写支线" in result["generated_content"]["body_markdown"]


class EmptyRetriever:
    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(
        self,
        query: str,
        limit: int = 8,
        **_: str | None,
    ) -> list[RetrievedEvidence]:
        self.calls += 1
        return []


async def test_stage_two_retries_missing_evidence_once_then_returns_partial() -> None:
    retriever = EmptyRetriever()
    graph = build_stage_two_graph(retriever=retriever)
    spec = TaskSpec(target_characters=["云"], required_stages=3, interaction_count=2)

    result = await graph.ainvoke({"task_spec": spec.model_dump(mode="json")})

    assert retriever.calls == 42
    assert {item["attempt"] for item in result["retrieval_summaries"]} == {1, 2}
    assert result["audit_report"]["status"] == "partial"
    assert result["requires_user_confirmation"] is True
    assert result["constraint_result"]["passed"] is False
    assert result["constraint_result"]["checks"]["audit_approved"] is False


class FailOnceRetriever:
    def __init__(self) -> None:
        self.calls = 0
        self.fallback = InMemoryHybridRetriever(all_demo_evidence_corpus())

    async def retrieve(
        self,
        query: str,
        limit: int = 8,
        **filters: str | None,
    ) -> list[RetrievedEvidence]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("模拟单节点失败")
        return await self.fallback.retrieve(query, limit, **filters)


async def test_workflow_resumes_from_last_checkpoint_after_node_failure() -> None:
    retriever = FailOnceRetriever()
    graph = build_stage_two_graph(retriever=retriever, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "stage-five-recovery"}}
    spec = TaskSpec(target_characters=["云"], required_stages=3, interaction_count=2)

    with pytest.raises(RuntimeError, match="模拟单节点失败"):
        await graph.ainvoke({"task_spec": spec.model_dump(mode="json")}, config)

    result = await graph.ainvoke(None, config)

    assert retriever.calls > 2
    assert result["evolution_package"]["character"] == "云"
    assert result["constraint_result"]["passed"] is True


@pytest.mark.parametrize("character", SUPPORTED_DEMO_CHARACTERS)
def test_demo_package_has_auditable_glyphs_and_claims(character: str) -> None:
    package = case_evolution_package(character)
    evidence_ids = {item.evidence_id for item in package.evidence}
    source_ids = {item.source_id for item in package.sources}

    assert len(package.glyph_stages) == 7
    assert all(
        stage.image_url and stage.image_id and stage.source_path
        for stage in package.glyph_stages
        if stage.availability == "available"
    )
    assert all(
        not stage.image_url and not stage.image_id
        for stage in package.glyph_stages
        if stage.availability == "dataset_gap"
    )
    assert all(stage.source_id in source_ids for stage in package.glyph_stages)
    assert all(
        stage.image_attribution
        for stage in package.glyph_stages
        if stage.availability == "available"
    )
    assert all(source.url and source.license for source in package.sources)
    assert all(set(claim.evidence_ids) <= evidence_ids for claim in package.claims)


def test_jiezi_catalog_contains_four_complete_demo_characters() -> None:
    catalog = glyph_catalog()

    assert len(catalog.characters) == 4
    assert all(item.available_script_count == 7 for item in catalog.characters)
    assert catalog.total_selected_images == sum(
        item.total_image_count for item in catalog.characters
    )
    assert {"云", "雷", "礼", "明"} == {item.character for item in catalog.characters}


def test_wind_is_not_a_supported_demo_character() -> None:
    assert "风" not in SUPPORTED_DEMO_CHARACTERS

    with pytest.raises(ValueError, match="尚未登记演示字"):
        case_evolution_package("风")


class FakeGlyphRetriever:
    def __init__(self, missing_script_code: str | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.missing_script_code = missing_script_code

    async def retrieve(
        self,
        query: str,
        *,
        character: str,
        script_code: str,
        limit: int = 4,
    ) -> list[RetrievedGlyphImage]:
        self.calls.append((character, script_code))
        if script_code == self.missing_script_code:
            return []
        stage = next(
            item for item in glyph_catalog().characters[0].stages if item.script_code == script_code
        )
        codepoint = f"U+{ord(character):04X}"
        image_id = f"{codepoint}/{script_code}/2.png"
        return [
            RetrievedGlyphImage(
                image_id=image_id,
                character=character,
                codepoint=codepoint,
                script_type=stage.script_type,
                script_code=script_code,
                historical_period=stage.historical_period,
                lineage_role=stage.lineage_role,
                region_or_system=stage.region_or_system,
                source_path=f"JieZi-Dataset/images/{image_id}",
                mime_type="image/png",
                sha256="0" * 64,
                metadata={},
                score=0.75,
                content_url=f"/backend/api/v1/glyph-images/{image_id}",
            )
        ]


async def test_graph_selects_representative_images_through_glyph_rag() -> None:
    glyph_retriever = FakeGlyphRetriever()
    graph = build_stage_two_graph(glyph_retriever=glyph_retriever)
    spec = TaskSpec(target_characters=["云"], required_stages=3, interaction_count=2)

    result = await graph.ainvoke({"task_spec": spec.model_dump(mode="json")})

    stages = result["evolution_package"]["glyph_stages"]
    assert [code for _, code in glyph_retriever.calls] == ["J", "B", "G", "S", "L", "K", "C"]
    assert len(result["glyph_retrieval_summaries"]) == 7
    assert all(stage["image_id"].endswith("/2") for stage in stages)
    assert all(stage["variant_type"] == "rag_selected_representative" for stage in stages)
    assert all("图 RAG 召回" in stage["source_label"] for stage in stages)


async def test_graph_rejects_static_image_fallback_when_glyph_rag_is_incomplete() -> None:
    graph = build_stage_two_graph(glyph_retriever=FakeGlyphRetriever(missing_script_code="G"))
    spec = TaskSpec(target_characters=["云"], required_stages=3, interaction_count=2)

    with pytest.raises(RuntimeError, match="战国文字"):
        await graph.ainvoke({"task_spec": spec.model_dump(mode="json")})
