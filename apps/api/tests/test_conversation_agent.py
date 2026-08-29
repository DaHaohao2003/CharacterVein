from typing import Any

import pytest

from character_vein_api.conversation_service import ConversationService
from character_vein_api.models import TaskRecord
from character_vein_domain import (
    ConversationIntent,
    ConversationTurnOutput,
    TaskSpec,
)
from character_vein_providers import (
    AliyunBailianTextProvider,
    DeterministicTextProvider,
    extract_explicit_hanzi_target,
)
from character_vein_workflows.fixtures import case_evolution_package


class FakeConversationProvider(AliyunBailianTextProvider):
    def __init__(self) -> None:
        super().__init__("test-key", "https://example.com/v1", "test-model")
        self.calls: list[tuple[str, object]] = []

    async def _json_completion(self, system: str, payload: object) -> dict[str, Any]:
        self.calls.append((system, payload))
        if "意图路由器" in system:
            if isinstance(payload, dict) and "视频" in str(payload.get("message", "")):
                return {
                    "intent": "create",
                    "action_summary": "创作视频内容",
                    "artifact_type": "短视频",
                    "target_artifact_id": None,
                    "needs_web_search": False,
                    "search_query": None,
                    "needs_glyph_context": False,
                }
            return {
                "intent": "create",
                "action_summary": "创作三分钟校园广播稿",
                "artifact_type": "校园广播稿",
                "target_artifact_id": None,
                "needs_web_search": False,
                "search_query": None,
                "needs_glyph_context": True,
            }
        is_video = isinstance(payload, dict) and "视频" in str(payload.get("message", ""))
        return {
            "intent": "create",
            "assistant_message": (
                "视频已经生成。" if is_video else "广播稿已经生成，可以继续调整语气或长度。"
            ),
            "action_summary": "会被规划结果覆盖",
            "workspace_view": "artifact",
            "artifact": {
                "artifact_type": "短视频" if is_video else "校园广播稿",
                "format_label": "视频" if is_video else "广播稿",
                "title": "听见“雷”" if is_video else "听见“雷”：校园午间三分钟",
                "summary": "面向中学生的声音想象广播稿",
                "content_markdown": (
                    "# 听见雷\n\n同学们，先闭上眼睛想象一声由远及近的雷鸣。"
                    "今天我们从字形轮廓出发，看看古人怎样把自然感受写进汉字。"
                ),
                "target_artifact_id": None,
                "reference_ids": ["reference-one", "outside-task"],
                "visual_hook_ids": ["glyph-one", "outside-task"],
            },
        }


async def test_conversation_plan_accepts_user_defined_artifact_type() -> None:
    provider = FakeConversationProvider()
    plan = await provider.plan_conversation_turn(
        "请为学校午间栏目写一份三分钟校园广播稿",
        [],
        [],
        "雷",
    )

    assert plan.intent == ConversationIntent.CREATE
    assert plan.artifact_type == "校园广播稿"
    assert plan.needs_glyph_context is True


async def test_conversation_generation_keeps_open_artifact_and_filters_machine_ids() -> None:
    provider = FakeConversationProvider()
    plan = await provider.plan_conversation_turn("写校园广播稿", [], [], "雷")
    output = await provider.generate_conversation_turn(
        plan,
        "写校园广播稿",
        [],
        {
            "character": "雷",
            "reference_materials": [{"reference_id": "reference-one"}],
            "glyph_stages": [{"image_id": "glyph-one", "script_type": "甲骨文"}],
        },
        [],
    )

    assert output.artifact is not None
    assert output.artifact.artifact_type == "校园广播稿"
    assert output.artifact.reference_ids == ["reference-one"]
    assert output.artifact.visual_hook_ids == ["glyph-one"]
    assert "校园午间三分钟" in output.artifact.title


async def test_video_request_is_always_normalized_to_editable_script() -> None:
    provider = FakeConversationProvider()
    plan = await provider.plan_conversation_turn("生成一段关于雷字的短视频", [], [], "雷")
    output = await provider.generate_conversation_turn(
        plan,
        "生成一段关于雷字的短视频",
        [],
        {"character": "雷", "reference_materials": [], "glyph_stages": []},
        [],
    )

    assert plan.artifact_type == "视频脚本"
    assert output.artifact is not None
    assert output.artifact.artifact_type == "视频脚本"
    assert output.artifact.format_label == "视频脚本"
    assert "脚本" in output.artifact.title
    assert "视频脚本" in output.assistant_message
    assert "视频已经生成" not in output.assistant_message


async def test_deterministic_video_request_creates_script_not_video_file() -> None:
    provider = DeterministicTextProvider()
    plan = await provider.plan_conversation_turn("帮我生成一个雷字动画", [], [], "雷")
    output = await provider.generate_conversation_turn(
        plan,
        "帮我生成一个雷字动画",
        [],
        {"character": "雷"},
        [],
    )

    assert plan.intent == ConversationIntent.CREATE
    assert plan.artifact_type == "视频脚本"
    assert output.artifact is not None
    assert output.artifact.artifact_type == "视频脚本"


async def test_deterministic_planner_distinguishes_discussion_revision_and_transform() -> None:
    provider = DeterministicTextProvider()
    existing = [{"id": "artifact-1", "artifact_type": "文章", "title": "雷的故事"}]

    answer = await provider.plan_conversation_turn("为什么这个字上面有雨？", [], [], "雷")
    revision = await provider.plan_conversation_turn("把开头缩短一点", [], existing, "雷")
    transform = await provider.plan_conversation_turn("把它改成播客稿", [], existing, "雷")

    assert answer.intent == ConversationIntent.ANSWER
    assert revision.intent == ConversationIntent.REVISE
    assert transform.intent == ConversationIntent.TRANSFORM
    assert transform.target_artifact_id == "artifact-1"


def test_creation_turn_requires_an_artifact() -> None:
    with pytest.raises(ValueError, match="必须返回作品"):
        ConversationTurnOutput(
            intent=ConversationIntent.CREATE,
            assistant_message="已经完成创作。",
            action_summary="生成作品",
            workspace_view="artifact",
            artifact=None,
        )


def test_conversation_target_extraction_prefers_explicit_example() -> None:
    assert extract_explicit_hanzi_target("和我研究一个汉字，比如雷") == "雷"


def test_visual_only_context_keeps_positive_scripts_and_removes_references() -> None:
    task = TaskRecord(
        id="task-1",
        status="awaiting_confirmation",
        raw_input="研究雷字",
        spec={},
        selected_route_id=None,
    )
    context = ConversationService._task_context(
        task,
        TaskSpec(target_characters=["雷"]),
        case_evolution_package("雷"),
        "只比较雷字甲骨文和金文图片中直接可见的线条，不谈篆书，不解释字源。",
    )

    assert {item["script_type"] for item in context["glyph_stages"]} == {
        "甲骨文",
        "金文",
    }
    assert context["reference_materials"] == []
    assert context["response_scope"] == "visual_features_only"


def test_conversation_context_keeps_public_fixture_and_hides_glyph_metadata() -> None:
    task = TaskRecord(
        id="task-1",
        status="awaiting_confirmation",
        raw_input="研究雷字",
        spec={},
        selected_route_id=None,
    )

    context = ConversationService._task_context(
        task,
        TaskSpec(target_characters=["雷"]),
        case_evolution_package("雷"),
        "雷字有哪些文化含义？",
    )

    references = context["reference_materials"]
    assert references
    assert {item["title"] for item in references} == {"古今汉字的演变"}
    assert all("JieZi" not in str(item) for item in references)
