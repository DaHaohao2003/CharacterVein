import json
from types import SimpleNamespace
from typing import Any

import pytest

from character_vein_api.evidence_providers import (
    UploadEvidenceProvider,
    WebEvidenceProvider,
    WebSearchSnapshot,
    WebSearchSource,
)
from character_vein_domain import (
    AuditStatus,
    Claim,
    ClaimEvidenceRelation,
    ClaimType,
    CommunicationBrief,
    Evidence,
    EvidenceSearchQuery,
    EvidenceUsability,
    GlyphStageVisualObservation,
    GlyphVisualAnalysis,
    RetrievedEvidence,
    Source,
    SourceOrigin,
    SupportType,
    TaskSpec,
)
from character_vein_providers import AliyunBailianTextProvider, DeterministicAuditProvider
from character_vein_retrieval import (
    EvidenceProviderResult,
    EvidenceSearchContext,
)
from character_vein_workflows import build_stage_two_graph
from character_vein_workflows.fixtures import case_evolution_package


def _evidence(
    evidence_id: str,
    *,
    origin: SourceOrigin = SourceOrigin.WEB,
    usability: EvidenceUsability = EvidenceUsability.USABLE,
    candidate_claim: str = "礼的材料陈述",
    support_type: SupportType = SupportType.SUPPORTS,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_id=f"source-{evidence_id}",
        source_type="web_page" if origin == SourceOrigin.WEB else "user_document",
        title=f"资料 {evidence_id}",
        author_or_org="测试机构",
        quote_or_summary=f"可定位正文：{candidate_claim}",
        locator="第 1 段",
        url="https://example.com/source" if origin == SourceOrigin.WEB else None,
        authority_level="D",
        license="测试夹具",
        metadata={
            "candidate_claim": candidate_claim,
            "support_type": support_type.value,
        },
        character="礼",
        topic="shape",
        origin=origin,
        task_id="task-1",
        usability=usability,
    )


def _retrieved(evidence: Evidence) -> RetrievedEvidence:
    return RetrievedEvidence(
        evidence=evidence,
        exact_score=1,
        keyword_score=1,
        semantic_score=1,
        final_score=1,
        structured_rank=1,
        keyword_rank=1,
        semantic_rank=1,
        rrf_score=0.04,
    )


class FakeProvider:
    def __init__(
        self,
        name: str,
        origin: SourceOrigin,
        evidence: list[Evidence],
        *,
        available: bool = True,
    ) -> None:
        self.name = name
        self.origin = origin
        self.evidence = evidence
        self.available = available

    async def search(
        self,
        query: EvidenceSearchQuery,
        context: EvidenceSearchContext,
        *,
        limit: int,
    ) -> EvidenceProviderResult:
        return EvidenceProviderResult(
            candidates=[_retrieved(item) for item in self.evidence[:limit]],
            available=self.available,
            message="provider unavailable" if not self.available else "snapshot",
        )


class FakeWriter(AliyunBailianTextProvider):
    def __init__(self) -> None:
        super().__init__("test-key", "https://example.com/v1", "test-model")
        self.payload: dict[str, Any] = {}

    async def _json_completion(self, system: str, payload: object) -> dict[str, Any]:
        assert "参考资料" in system
        assert isinstance(payload, dict)
        self.payload = payload
        return {
            "title": "模型生成标题",
            "audience": "会被系统覆盖",
            "duration_minutes": 99,
            "outline": ["字形", "文化"],
            "body_markdown": "模型结合检索资料生成的正文。",
            "interaction_questions": ["你观察到了什么？", "资料还提到了什么？"],
            "source_ids": [],
            "estimated_characters": 0,
        }


class AlternateNarrativeShapeWriter(AliyunBailianTextProvider):
    def __init__(self) -> None:
        super().__init__("test-key", "https://example.com/v1", "test-model")

    async def _json_completion(self, system: str, payload: object) -> dict[str, Any]:
        assert "story_beats 必须是 2 到 8 条纯字符串" in system
        assert isinstance(payload, dict)
        stages = payload["glyph_stages"]
        first_id = stages[0]["image_id"]
        second_id = stages[1]["image_id"]
        return {
            "routes": [
                {
                    "route_id": "route-a",
                    "title": "听见字形",
                    "core_message": "从字形变化理解古人如何想象自然声音。",
                    "opening_hook": "先听一声雷，再观察笔画怎样回应。",
                    "visual_hooks": [first_id, second_id],
                    "story_beats": [
                        {"description": "观察早期轮廓与构件。", "image_ref": first_id},
                        {"description": "比较后期结构的组织方式。", "image_ref": second_id},
                    ],
                    "contemporary_connection": "联系声音波形与动态图形。",
                    "recommended_channels": ["web_page", "social_cards"],
                    "reference_ids": ["not-in-task"],
                },
                {
                    "route_id": "route-b",
                    "title": "结构中的节奏",
                    "core_message": "用结构变化组织一条面向学生的观察路线。",
                    "opening_hook": "同一个字为什么会呈现不同节奏？",
                    "visual_hooks": [first_id],
                    "story_beats": ["先看构件位置。", "再看线条组织。"],
                    "contemporary_connection": "联系当代视觉设计。",
                    "recommended_channels": ["short_video_60s"],
                    "reference_ids": [],
                },
            ]
        }


async def _audit(
    support_type: SupportType,
    usability: EvidenceUsability = EvidenceUsability.USABLE,
) -> tuple[Claim, Any]:
    evidence = _evidence("one", usability=usability, support_type=support_type)
    claim = Claim(
        claim_id="claim-one",
        content="礼的材料陈述",
        claim_type=ClaimType.LITERATURE_FACT,
        evidence_ids=[evidence.evidence_id],
        evidence_relations=[
            ClaimEvidenceRelation(
                evidence_id=evidence.evidence_id,
                support_type=support_type,
            )
        ],
        evidence_grade="A",
    )
    report = await DeterministicAuditProvider().audit([claim], [evidence], 1)
    return claim, report


async def test_web_material_flows_into_generation_context() -> None:
    graph = build_stage_two_graph(
        evidence_providers=[FakeProvider("web", SourceOrigin.WEB, [_evidence("web-1")])]
    )
    result = await graph.ainvoke(
        {
            "task_id": "task-1",
            "task_spec": TaskSpec(target_characters=["礼"]).model_dump(mode="json"),
        }
    )
    assert result["evolution_package"]["claims"] == []
    assert {item["evidence_id"] for item in result["evolution_package"]["evidence"]} == {"web-1"}
    assert result["generated_content"]["source_ids"] == ["web-1"]
    assert result["audit_report"]["model"] == "not-run"


async def test_aliyun_writer_receives_reference_materials_as_context() -> None:
    writer = FakeWriter()
    evolution = case_evolution_package("礼")
    evolution.evidence = [_evidence("upload", origin=SourceOrigin.USER_UPLOAD)]
    content = await writer.generate_content(
        TaskSpec(target_characters=["礼"], audience="小学六年级", duration_minutes=4),
        evolution,
    )

    assert writer.payload["reference_materials"][0]["reference_id"] == "upload"
    assert content.body_markdown == "模型结合检索资料生成的正文。"
    assert content.audience == "小学六年级"
    assert content.duration_minutes == 4
    assert content.source_ids == ["upload"]


async def test_writer_keeps_internal_glyph_metadata_out_of_public_generation_context() -> None:
    writer = FakeWriter()
    evolution = case_evolution_package("礼")
    internal = _evidence("jiezi-internal")
    internal.title = "JieZi 元数据"
    internal.metadata["kind"] = "glyph_dataset"
    fixture = _evidence("unrelated-fixture", origin=SourceOrigin.FIXTURE)
    public = _evidence("web-public")
    evolution.evidence = [internal, fixture, public]
    evolution.visual_analysis = GlyphVisualAnalysis(
        character="礼",
        model="test-vlm",
        stage_observations=[
            GlyphStageVisualObservation(
                image_id="U+793C/J/1.png",
                script_type="甲骨文",
                visible_features=["外轮廓较窄"],
                composition="构件呈上下分布",
                stroke_form="线条略有弯曲",
            )
        ],
    )

    content = await writer.generate_content(TaskSpec(target_characters=["礼"]), evolution)

    assert [item["reference_id"] for item in writer.payload["reference_materials"]] == [
        "web-public"
    ]
    visual_payload = json.dumps(writer.payload["glyph_visual_analysis"], ensure_ascii=False)
    assert "image_id" not in visual_payload
    assert "U+793C" not in visual_payload
    stage_payload = json.dumps(writer.payload["glyph_stages"], ensure_ascii=False)
    assert "JieZi" not in stage_payload
    assert "元数据" not in stage_payload
    assert content.source_ids == ["web-public"]


async def test_narrative_writer_repairs_machine_fields_without_replacing_model_copy() -> None:
    writer = AlternateNarrativeShapeWriter()
    evolution = case_evolution_package("礼")
    routes = await writer.generate_narrative_routes(
        CommunicationBrief(target_characters=["礼"]), evolution
    )

    assert [route.title for route in routes] == ["听见字形", "结构中的节奏"]
    assert routes[0].story_beats == ["观察早期轮廓与构件。", "比较后期结构的组织方式。"]
    assert [hook.image_id for hook in routes[0].visual_hooks] == [
        evolution.glyph_stages[0].image_id,
        evolution.glyph_stages[1].image_id,
    ]
    assert routes[0].visual_hooks[0].prompt == "观察早期轮廓与构件。"
    assert routes[0].recommended_channels[0].value == "interactive_page"
    assert routes[0].reference_ids == []


async def test_metadata_only_cannot_directly_support_fact() -> None:
    _, report = await _audit(SupportType.SUPPORTS, EvidenceUsability.METADATA_ONLY)
    assert report.status == "needs_retry"
    assert report.claim_results[0].status == AuditStatus.REJECTED


async def test_web_provider_unavailable_is_a_controlled_evidence_gap() -> None:
    graph = build_stage_two_graph(
        evidence_providers=[FakeProvider("web", SourceOrigin.WEB, [], available=False)]
    )
    result = await graph.ainvoke(
        {
            "task_id": "task-1",
            "task_spec": TaskSpec(target_characters=["礼"]).model_dump(mode="json"),
        }
    )
    assert result["retrieval_attempt"] == 3
    assert result["constraint_result"]["checks"]["reference_context"] is False
    assert result["requires_user_confirmation"] is False
    assert any(call["provider"] == "web" for call in result["tool_calls"])


async def test_live_web_search_persists_urls_and_partial_synthesis() -> None:
    class Repo:
        def __init__(self) -> None:
            self.has_snapshot = False
            self.sources: list[Source] = []
            self.evidence: list[Evidence] = []

        async def has_task_evidence(self, _task_id: str, _origin: SourceOrigin) -> bool:
            return self.has_snapshot

        async def seed_corpus(
            self,
            sources: list[Source],
            evidence: list[Evidence],
            _embeddings: list[list[float]],
        ) -> None:
            self.sources.extend(sources)
            self.evidence.extend(evidence)
            self.has_snapshot = True

    class Retriever:
        def __init__(self, repository: Repo) -> None:
            self.repository = repository

        async def retrieve(self, *_: Any, **__: Any) -> list[RetrievedEvidence]:
            return [_retrieved(self.repository.evidence[-1])] if self.repository.evidence else []

    class SearchClient:
        async def search(self, _query: str, *, limit: int) -> WebSearchSnapshot:
            return WebSearchSnapshot(
                answer="百炼基于联网来源形成的摘要，并非网页原文。",
                sources=[
                    WebSearchSource("来源一", "https://example.com/one", "示例站"),
                    WebSearchSource("来源二", "https://example.org/two", "示例机构"),
                ][:limit],
            )

    class Embedding:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] * 1024 for _ in texts]

    repository = Repo()
    provider = WebEvidenceProvider(
        Retriever(repository),  # type: ignore[arg-type]
        backend="aliyun-bailian",
        search_client=SearchClient(),  # type: ignore[arg-type]
        evidence_repository=repository,  # type: ignore[arg-type]
        embedding_provider=Embedding(),
    )
    result = await provider.search(
        EvidenceSearchQuery(
            query_id="meaning",
            query="礼 字义 文化",
            purpose="收集字义与文化语境",
            character="礼",
            topic="meaning_context",
        ),
        EvidenceSearchContext(task_id="task-live-web", asset_ids=[]),
        limit=2,
    )

    assert result.candidates
    assert {item.url for item in repository.sources if item.url} == {
        "https://example.com/one",
        "https://example.org/two",
    }
    assert (
        sum(item.usability == EvidenceUsability.METADATA_ONLY for item in repository.evidence) == 2
    )
    assert repository.evidence[-1].usability == EvidenceUsability.PARTIAL
    assert repository.evidence[-1].metadata["sources"][0]["url"] == "https://example.com/one"


async def test_upload_snapshot_is_strictly_task_scoped() -> None:
    class AssetRepo:
        async def for_task(self, task_id: str, asset_ids: list[str]) -> list[Any]:
            if task_id != "task-a":
                return []
            return [
                SimpleNamespace(
                    id="asset-1",
                    filename="notes.md",
                    mime_type="text/markdown",
                    kind="document",
                    extracted_text="目标字：礼\n这是当前任务的资料。",
                )
            ]

    class EvidenceRepo:
        async def seed_corpus(self, *_: Any) -> None:
            return None

    class Embedding:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] * 1024 for _ in texts]

    provider = UploadEvidenceProvider(
        EvidenceRepo(),
        AssetRepo(),
        SimpleNamespace(),
        Embedding(),  # type: ignore[arg-type]
    )
    assert await provider.prepare_snapshot("task-a", ["asset-1"]) == 1
    with pytest.raises(ValueError, match="不属于当前任务"):
        await provider.prepare_snapshot("task-b", ["asset-1"])


async def test_user_upload_is_audited_instead_of_trusted_by_origin() -> None:
    _, report = await _audit(SupportType.PARTIALLY_SUPPORTS)
    assert report.status == "partial"
    assert report.claim_results[0].status == AuditStatus.DOWNGRADED


async def test_web_and_upload_are_combined_as_generation_context() -> None:
    graph = build_stage_two_graph(
        evidence_providers=[
            FakeProvider("web", SourceOrigin.WEB, [_evidence("web")]),
            FakeProvider(
                "user_upload",
                SourceOrigin.USER_UPLOAD,
                [_evidence("upload", origin=SourceOrigin.USER_UPLOAD)],
            ),
        ]
    )
    result = await graph.ainvoke(
        {
            "task_id": "task-1",
            "input_asset_ids": ["asset-1"],
            "task_spec": TaskSpec(target_characters=["礼"]).model_dump(mode="json"),
        }
    )
    assert {item["evidence_id"] for item in result["evolution_package"]["evidence"]} == {
        "web",
        "upload",
    }
    assert set(result["generated_content"]["source_ids"]) == {"web", "upload"}


async def test_web_and_upload_metadata_is_not_used_for_fact_judgement() -> None:
    graph = build_stage_two_graph(
        evidence_providers=[
            FakeProvider("web", SourceOrigin.WEB, [_evidence("web")]),
            FakeProvider(
                "user_upload",
                SourceOrigin.USER_UPLOAD,
                [
                    _evidence(
                        "upload",
                        origin=SourceOrigin.USER_UPLOAD,
                        support_type=SupportType.CONTRADICTS,
                    )
                ],
            ),
        ]
    )
    result = await graph.ainvoke(
        {
            "task_id": "task-1",
            "input_asset_ids": ["asset-1"],
            "task_spec": TaskSpec(target_characters=["礼"]).model_dump(mode="json"),
        }
    )
    assert result["evolution_package"]["claims"] == []
    assert set(result["generated_content"]["source_ids"]) == {"web", "upload"}
    assert result["audit_report"]["model"] == "not-run"


async def test_context_only_never_approves() -> None:
    _, report = await _audit(SupportType.CONTEXT_ONLY)
    assert report.claim_results[0].status == AuditStatus.REJECTED


async def test_partial_support_downgrades() -> None:
    _, report = await _audit(SupportType.PARTIALLY_SUPPORTS)
    assert report.claim_results[0].status == AuditStatus.DOWNGRADED


async def test_glyph_assets_remain_available_without_reference_materials() -> None:
    graph = build_stage_two_graph(
        evidence_providers=[FakeProvider("web", SourceOrigin.WEB, [], available=False)]
    )
    result = await graph.ainvoke(
        {
            "task_id": "task-1",
            "task_spec": TaskSpec(target_characters=["礼"]).model_dump(mode="json"),
        }
    )
    assert len(result["evolution_package"]["glyph_stages"]) == 7
    assert result["evolution_package"]["claims"] == []
    assert result["generated_content"]["source_ids"] == []
    assert result["constraint_result"]["checks"]["reference_context"] is False


def test_old_task_models_remain_readable() -> None:
    claim = Claim(
        claim_id="old",
        content="旧陈述",
        claim_type=ClaimType.LITERATURE_FACT,
        evidence_ids=["old-evidence"],
        evidence_grade="B",
    )
    source = Source(
        source_id="old-source",
        source_type="legacy",
        title="旧来源",
        author_or_org="未知",
        locator="旧定位",
        authority_level="B",
        license="旧许可记录",
    )
    assert claim.evidence_relations[0].support_type == SupportType.SUPPORTS
    assert source.origin == SourceOrigin.FIXTURE
