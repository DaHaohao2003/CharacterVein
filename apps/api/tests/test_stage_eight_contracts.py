import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from character_vein_domain import (
    AgentAction,
    AgentDecision,
    AgentDecisionContext,
    AgentPhase,
    CommunicationAssetType,
    CommunicationChannel,
    CommunicationDeliverable,
    ExplorationBudget,
    TaskSpec,
    communication_brief_from_task_spec,
    task_spec_from_communication_brief,
)
from character_vein_exporters import (
    export_communication_package_json,
    export_communication_package_markdown,
)
from character_vein_providers import DeterministicTextProvider
from character_vein_workflows import accept_decision, allowed_actions, build_stage_two_graph
from character_vein_workflows.fixtures import case_evolution_package


def test_legacy_task_spec_round_trips_through_communication_brief() -> None:
    legacy = TaskSpec(
        target_characters=["礼"],
        theme="礼与当代生活",
        audience="年轻文化兴趣用户",
        duration_minutes=2,
        interaction_count=1,
    )

    brief = communication_brief_from_task_spec(legacy, raw_input="讲述礼的当代文化故事")
    migrated = task_spec_from_communication_brief(brief)

    assert brief.target_characters == ["礼"]
    assert brief.communication_goal == "讲述礼的当代文化故事"
    assert brief.channels == [CommunicationChannel.INTERACTIVE_PAGE]
    assert migrated.target_characters == legacy.target_characters
    assert migrated.duration_minutes == legacy.duration_minutes
    assert migrated.communication_brief == brief


async def test_deterministic_provider_parses_cross_media_brief() -> None:
    provider = DeterministicTextProvider()

    brief = await provider.parse_communication_brief(
        "围绕“礼”制作一套面向年轻人的汉字文化内容，用于互动长页、"
        "五张图文卡片和60秒短视频，有文化感但不要太学术。"
    )

    assert brief.target_characters == ["礼"]
    assert brief.audience == "年轻人"
    assert brief.duration_seconds == 60
    assert brief.channels == [
        CommunicationChannel.INTERACTIVE_PAGE,
        CommunicationChannel.SOCIAL_CARDS,
        CommunicationChannel.SHORT_VIDEO_60S,
    ]
    assert brief.deliverables == [
        CommunicationDeliverable.INTERACTIVE_STORY,
        CommunicationDeliverable.FIVE_CARDS,
        CommunicationDeliverable.VIDEO_SCRIPT,
    ]
    assert "不过度学术" in brief.tone


def test_controlled_decision_rejects_actions_outside_phase_and_budget() -> None:
    context = AgentDecisionContext(phase=AgentPhase.MATERIAL_EXPLORATION)
    budget = ExplorationBudget(search_decisions_remaining=1)

    permitted = allowed_actions(context, budget)
    assert AgentAction.SEARCH_MORE in permitted
    assert AgentAction.RESELECT_GLYPH not in permitted

    decision = AgentDecision(
        action=AgentAction.SEARCH_MORE,
        reason_code="reference_gap",
        decision_summary="继续补充文化资料。",
    )
    exhausted = accept_decision(decision, context, budget)
    assert exhausted.search_decisions_remaining == 0
    assert AgentAction.SEARCH_MORE not in allowed_actions(context, exhausted)

    invalid = AgentDecision(
        action=AgentAction.RESELECT_GLYPH,
        reason_code="wrong_phase",
        decision_summary="错误阶段动作。",
    )
    with pytest.raises(ValueError, match="不允许动作"):
        accept_decision(invalid, context, budget)


async def test_workflow_exposes_brief_action_whitelist_and_budget() -> None:
    events: list[tuple[str, dict]] = []

    async def sink(step: str, _status: str, _summary: str, payload: dict) -> None:
        events.append((step, payload))

    graph = build_stage_two_graph(event_sink=sink)
    spec = TaskSpec(target_characters=["礼"], required_stages=3, interaction_count=2)

    result = await graph.ainvoke({"task_spec": spec.model_dump(mode="json")})

    assert result["communication_brief"]["target_characters"] == ["礼"]
    assert result["current_phase"] == AgentPhase.NARRATIVE_BUILD.value
    assert result["next_action"] == AgentAction.BUILD_NARRATIVES.value
    assert result["budgets"]["search_decisions_remaining"] == 2
    assert result["exploration_history"][0]["action"] == AgentAction.SEARCH_MORE.value
    assert [item["phase"] for item in result["exploration_history"]] == [
        AgentPhase.MATERIAL_EXPLORATION.value,
        AgentPhase.MATERIAL_EXPLORATION.value,
        AgentPhase.GLYPH_EXPLORATION.value,
        AgentPhase.NARRATIVE_BUILD.value,
    ]
    assert len(result["narrative_routes"]) == 3
    assert result["selected_route_id"] == "route-visual"
    assert result["cultural_motif"]["source_route_id"] == "route-visual"
    assert set(result["communication_assets"]) == {
        CommunicationAssetType.INTERACTIVE_STORY.value,
        CommunicationAssetType.SOCIAL_CARDS.value,
        CommunicationAssetType.SHORT_VIDEO_SCRIPT.value,
    }
    assert len(result["communication_assets"]["social_cards"]["content"]["cards"]) == 5
    video = result["communication_assets"]["short_video_script"]["content"]
    assert video["duration_seconds"] == 60
    assert video["scenes"][0]["start_second"] == 0
    assert video["scenes"][-1]["end_second"] == 60
    assert result["artifact_evaluation"]["passed"] is True
    assert set(result["artifact_evaluation"]["assets"]) == {
        CommunicationAssetType.INTERACTIVE_STORY.value,
        CommunicationAssetType.SOCIAL_CARDS.value,
        CommunicationAssetType.SHORT_VIDEO_SCRIPT.value,
    }
    decision_events = [payload for step, payload in events if step == "agent_decision"]
    assert len(decision_events) == 4
    assert AgentAction.SEARCH_MORE.value in decision_events[0]["allowed_actions"]


async def test_workflow_interrupts_for_route_selection_and_resumes_same_checkpoint() -> None:
    graph = build_stage_two_graph(
        checkpointer=InMemorySaver(),
        require_route_selection=True,
    )
    config = {"configurable": {"thread_id": "stage-eight-route-selection"}}
    spec = TaskSpec(target_characters=["礼"], required_stages=3, interaction_count=2)

    interrupted = await graph.ainvoke(
        {"task_spec": spec.model_dump(mode="json")},
        config,
    )

    assert "__interrupt__" in interrupted
    assert len(interrupted["narrative_routes"]) == 3
    assert "generated_content" not in interrupted

    completed = await graph.ainvoke(Command(resume="route-daily-life"), config)

    assert completed["selected_route_id"] == "route-daily-life"
    assert completed["cultural_motif"]["source_route_id"] == "route-daily-life"
    assert completed["communication_assets"]["interactive_story"]["content"]["title"]
    assert completed["constraint_result"]["passed"] is True
    assert "“礼”如何进入日常生活" in completed["generated_content"]["body_markdown"]


async def test_asset_evaluation_rewrites_only_failed_asset_once() -> None:
    class FirstSocialCardsAttemptMissesMotif(DeterministicTextProvider):
        async def generate_communication_asset(
            self,
            asset_type,
            brief,
            evolution,
            narrative_route,
            motif,
            existing_asset=None,
            evaluation=None,
        ):
            asset = await super().generate_communication_asset(
                asset_type,
                brief,
                evolution,
                narrative_route,
                motif,
                existing_asset,
                evaluation,
            )
            if asset_type == CommunicationAssetType.SOCIAL_CARDS and existing_asset is None:
                asset.content.title = "与选定母题无关的卡片标题"
            return asset

    graph = build_stage_two_graph(provider=FirstSocialCardsAttemptMissesMotif())
    spec = TaskSpec(target_characters=["礼"], required_stages=3, interaction_count=2)

    result = await graph.ainvoke({"task_spec": spec.model_dump(mode="json")})

    assert result["artifact_evaluation"]["passed"] is True
    assert result["communication_assets"]["social_cards"]["version"] == 2
    assert result["communication_assets"]["interactive_story"]["version"] == 1
    assert result["communication_assets"]["short_video_script"]["version"] == 1
    rewrite_calls = [
        item
        for item in result["tool_calls"]
        if item["tool_name"] == "generate_communication_asset"
        and "定向返工=social_cards" in item["input_summary"]
    ]
    assert len(rewrite_calls) == 1
    assert result["budgets"]["asset_rewrites_remaining"] == 0


async def test_fragment_rewrite_keeps_locked_identity_fields() -> None:
    provider = DeterministicTextProvider()
    spec = TaskSpec(target_characters=["礼"], audience="年轻文化兴趣用户")
    brief = communication_brief_from_task_spec(spec, raw_input="讲述礼的当代文化故事")
    evolution = case_evolution_package("礼")
    route = (await provider.generate_narrative_routes(brief, evolution))[0]
    motif = await provider.build_cultural_motif(brief, evolution, route)

    for asset_type in CommunicationAssetType:
        asset = await provider.generate_communication_asset(
            asset_type, brief, evolution, route, motif
        )
        fragment = await provider.rewrite_communication_fragment(
            asset,
            1,
            "表达得更轻松，并增加一个贴近日常的提问",
            brief,
            evolution,
            motif,
        )
        if asset_type == CommunicationAssetType.INTERACTIVE_STORY:
            original = asset.content.sections[0]
            assert fragment.section_id == original.section_id
            assert fragment.narrative != original.narrative
        elif asset_type == CommunicationAssetType.SOCIAL_CARDS:
            original = asset.content.cards[0]
            assert fragment.index == original.index
            assert fragment.body != original.body
        else:
            original = asset.content.scenes[0]
            assert fragment.start_second == original.start_second
            assert fragment.end_second == original.end_second
            assert fragment.narration != original.narration


async def test_communication_package_exports_all_three_media() -> None:
    provider = DeterministicTextProvider()
    spec = TaskSpec(target_characters=["礼"], audience="年轻文化兴趣用户")
    brief = communication_brief_from_task_spec(spec, raw_input="讲述礼的当代文化故事")
    evolution = case_evolution_package("礼")
    route = (await provider.generate_narrative_routes(brief, evolution))[0]
    motif = await provider.build_cultural_motif(brief, evolution, route)
    assets = {
        asset_type.value: await provider.generate_communication_asset(
            asset_type, brief, evolution, route, motif
        )
        for asset_type in CommunicationAssetType
    }

    markdown = export_communication_package_markdown(motif, assets)
    payload = export_communication_package_json(
        task_id="task-1", motif=motif, assets=assets, evaluation={"passed": True}
    )

    assert "## 互动文化长页" in markdown
    assert "## 五张图文卡片" in markdown
    assert "## 60 秒短视频脚本" in markdown
    assert '"interactive_story"' in payload
    assert '"social_cards"' in payload
    assert '"short_video_script"' in payload
