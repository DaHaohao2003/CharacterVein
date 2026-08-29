import json
import re
from typing import Any, Protocol

import httpx

from character_vein_domain import (
    AgentAction,
    AgentDecision,
    AgentDecisionContext,
    AgentPhase,
    ArtifactEvaluation,
    CommunicationAsset,
    CommunicationAssetType,
    CommunicationBrief,
    CommunicationChannel,
    CommunicationDeliverable,
    ConversationIntent,
    ConversationTurnOutput,
    ConversationTurnPlan,
    CreativeArtifactDraft,
    CulturalMotif,
    Evidence,
    EvidenceSearchQuery,
    EvolutionPackage,
    ExplorationBudget,
    GeneratedContent,
    InteractiveStoryContent,
    InteractiveStorySection,
    NarrativeRoute,
    PlanStep,
    ShortVideoScriptContent,
    SocialCard,
    SocialCardsContent,
    SourceOrigin,
    TaskSpec,
    VideoScene,
    VisualHook,
    communication_brief_from_task_spec,
)


def _generation_evidence(evolution: EvolutionPackage) -> list[Evidence]:
    """Return only material that may be exposed to text-generation paths.

    Glyph dataset records remain internal image catalog data. They may supply
    registered images and model-produced visual observations, but never source
    prose, citations, identifiers, paths, or authorship metadata.
    """

    result: list[Evidence] = []
    for item in evolution.evidence:
        if item.origin not in {SourceOrigin.WEB, SourceOrigin.USER_UPLOAD} and not (
            item.origin == SourceOrigin.FIXTURE
            and item.metadata.get("kind") == "evolution_framework"
        ):
            continue
        searchable = " ".join(
            [item.evidence_id, item.source_id, item.title, item.url or ""]
        ).lower()
        if "jiezi" in searchable or item.metadata.get("kind") in {
            "glyph_dataset",
            "glyph_stage",
            "glyph_context",
        }:
            continue
        result.append(item)
    return result


def extract_explicit_hanzi_target(text: str) -> str | None:
    """Extract a Hanzi that the user explicitly presents as the research target.

    The patterns deliberately require target-language context. This prevents a
    phrase such as ``研究一个汉字，比如雷`` from treating the numeral ``一``
    in ``一个`` as the target character.
    """

    patterns = (
        r"[“\"『「]([\u4e00-\u9fff])[”\"』」]\s*字?",
        r"(?:比如|例如|譬如)\s*[“\"『「]?([\u4e00-\u9fff])[”\"』」]?(?:这个)?字?",
        r"(?:目标字|汉字|讲解对象|研究对象)\s*(?:是|为)?\s*[：:]?\s*[“\"『「]?([\u4e00-\u9fff])[”\"』」]?",
        r"(?:讲解|研究|围绕|关于)\s*[“\"『「]?([\u4e00-\u9fff])[”\"』」]?(?:这个)?字",
        r"(?:讲解|研究|围绕|关于)\s*[“\"『「]?([\u4e00-\u9fff])[”\"』」]?的(?:字形|演化|文化|字义|故事)",
        r"([\u4e00-\u9fff])字(?:讲解|演化|文化|课程|故事|研究|介绍|内容|字形|字义)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


class TextModelProvider(Protocol):
    async def parse_task(self, raw_input: str) -> TaskSpec: ...

    async def parse_communication_brief(self, raw_input: str) -> CommunicationBrief: ...

    async def plan_conversation_turn(
        self,
        message: str,
        history: list[dict[str, str]],
        artifacts: list[dict[str, object]],
        character: str | None,
    ) -> ConversationTurnPlan: ...

    async def generate_conversation_turn(
        self,
        plan: ConversationTurnPlan,
        message: str,
        history: list[dict[str, str]],
        task_context: dict[str, object],
        artifacts: list[dict[str, object]],
        web_search_context: dict[str, object] | None = None,
    ) -> ConversationTurnOutput: ...

    async def plan_task(self, task_spec: TaskSpec) -> list[PlanStep]: ...

    async def decide_next_action(
        self,
        brief: CommunicationBrief,
        context: AgentDecisionContext,
        budget: ExplorationBudget,
        allowed_actions: list[AgentAction],
    ) -> AgentDecision: ...

    async def plan_evidence_queries(
        self, task_spec: TaskSpec, retry_context: str = ""
    ) -> list[EvidenceSearchQuery]: ...

    async def generate_narrative_routes(
        self, brief: CommunicationBrief, evolution: EvolutionPackage
    ) -> list[NarrativeRoute]: ...

    async def build_cultural_motif(
        self,
        brief: CommunicationBrief,
        evolution: EvolutionPackage,
        narrative_route: NarrativeRoute,
    ) -> CulturalMotif: ...

    async def generate_communication_asset(
        self,
        asset_type: CommunicationAssetType,
        brief: CommunicationBrief,
        evolution: EvolutionPackage,
        narrative_route: NarrativeRoute,
        motif: CulturalMotif,
        existing_asset: CommunicationAsset | None = None,
        evaluation: ArtifactEvaluation | None = None,
    ) -> CommunicationAsset: ...

    async def evaluate_communication_asset(
        self,
        brief: CommunicationBrief,
        evolution: EvolutionPackage,
        motif: CulturalMotif,
        asset: CommunicationAsset,
    ) -> ArtifactEvaluation: ...

    async def rewrite_communication_fragment(
        self,
        asset: CommunicationAsset,
        target_index: int,
        instruction: str,
        brief: CommunicationBrief,
        evolution: EvolutionPackage,
        motif: CulturalMotif,
    ) -> InteractiveStorySection | SocialCard | VideoScene: ...

    async def generate_content(
        self,
        task_spec: TaskSpec,
        evolution: EvolutionPackage,
        narrative_route: NarrativeRoute | None = None,
    ) -> GeneratedContent: ...


class DeterministicTextProvider:
    """Repeatable stage-one provider that requires no external model key."""

    async def parse_task(self, raw_input: str) -> TaskSpec:
        target = self._explicit_target(raw_input)
        duration = self._extract_int(raw_input, r"(\d+)\s*分钟", 4)
        required_stages = self._extract_int(
            raw_input, r"(?:至少|展示)?\s*(\d+)\s*个?(?:历史)?阶段", 3
        )
        interactions = self._extract_int(raw_input, r"(\d+)\s*道(?:互动)?题", 2)
        audience_match = re.search(
            r"(?:面向|为)?\s*((?:小学|初中|高中)[一二三四五六七八九\d]+年级)", raw_input
        )
        audience = audience_match.group(1) if audience_match else "普通文化爱好者"
        constraints: list[str] = []
        if "争议" in raw_input:
            constraints.append("争议观点不得写成定论")

        themes = {
            "云": "天象观察、构形与文化意象",
            "雷": "自然认知、构形与声音想象",
            "礼": "礼仪实践、字义与社会秩序",
            "明": "光明、构形与认知引申",
        }
        return TaskSpec(
            target_characters=[target] if target else [],
            theme=themes.get(target or "", "汉字演化与文化"),
            audience=audience,
            duration_minutes=duration,
            required_stages=required_stages,
            interaction_count=interactions,
            constraints=constraints,
        )

    async def parse_communication_brief(self, raw_input: str) -> CommunicationBrief:
        spec = await self.parse_task(raw_input)
        audience_match = re.search(
            r"面向\s*([^，。；,;\s]{2,12}?)(?:的|，|,|制作|传播|内容)", raw_input
        )
        if audience_match:
            spec.audience = audience_match.group(1)

        channels: list[CommunicationChannel] = []
        deliverables: list[CommunicationDeliverable] = []
        if any(term in raw_input for term in ("互动长页", "互动页", "长页")):
            channels.append(CommunicationChannel.INTERACTIVE_PAGE)
            deliverables.append(CommunicationDeliverable.INTERACTIVE_STORY)
        if any(term in raw_input for term in ("图文卡", "卡片", "小红书")):
            channels.append(CommunicationChannel.SOCIAL_CARDS)
            deliverables.append(CommunicationDeliverable.FIVE_CARDS)
        if any(term in raw_input for term in ("短视频", "视频脚本", "分镜")):
            channels.append(CommunicationChannel.SHORT_VIDEO_60S)
            deliverables.append(CommunicationDeliverable.VIDEO_SCRIPT)
        if not channels:
            channels = [CommunicationChannel.INTERACTIVE_PAGE]
            deliverables = [CommunicationDeliverable.INTERACTIVE_STORY]

        tone = [
            item for item in ("有文化感", "年轻", "轻松", "庄重", "清晰易懂") if item in raw_input
        ]
        if "不要太学术" in raw_input or "不过度学术" in raw_input:
            tone.append("不过度学术")
        if not tone:
            tone = ["有文化感", "清晰易懂"]

        seconds_match = re.search(r"(\d+)\s*秒", raw_input)
        duration_seconds = (
            int(seconds_match.group(1)) if seconds_match else spec.duration_minutes * 60
        )
        brief = communication_brief_from_task_spec(spec, raw_input=raw_input)
        brief.audience = spec.audience
        brief.channels = channels
        brief.deliverables = deliverables
        brief.tone = tone
        brief.duration_seconds = duration_seconds
        brief.success_criteria = [
            "真实字形图片进入叙事",
            "不同媒介共享同一文化母题",
            "表达适合目标受众",
        ]
        return brief

    async def plan_conversation_turn(
        self,
        message: str,
        history: list[dict[str, str]],
        artifacts: list[dict[str, object]],
        character: str | None,
    ) -> ConversationTurnPlan:
        del history
        lower = message.lower()
        has_artifact = bool(artifacts)
        if has_artifact and any(term in message for term in ("改成", "转换成", "再写成")):
            intent = ConversationIntent.TRANSFORM
        elif has_artifact and any(
            term in message for term in ("修改", "改写", "缩短", "扩写", "调整", "重写")
        ):
            intent = ConversationIntent.REVISE
        elif any(
            term in message
            for term in (
                "生成",
                "写一",
                "创作",
                "设计",
                "制作",
                "脚本",
                "文案",
                "文章",
                "讲稿",
                "教案",
                "播客",
                "视频",
                "动画",
                "卡片",
                "海报",
            )
        ):
            intent = ConversationIntent.CREATE
        elif any(term in message for term in ("研究", "查找", "搜索", "比较", "演化")):
            intent = ConversationIntent.EXPLORE
        else:
            intent = ConversationIntent.ANSWER
        artifact_labels = (
            "公众号文章",
            "短视频脚本",
            "视频脚本",
            "播客稿",
            "课堂活动",
            "教案",
            "展板文案",
            "社交卡片",
            "讲解词",
            "故事",
            "问答游戏",
        )
        artifact_type = next((item for item in artifact_labels if item in message), None)
        if artifact_type is None and any(term in message for term in ("视频", "动画", "短片")):
            artifact_type = "视频脚本"
        needs_glyph = bool(character) and any(
            term in message for term in ("字形", "演化", "甲骨", "金文", "篆", "隶", "楷", "草书")
        )
        needs_web = any(term in lower for term in ("搜索", "查找", "资料", "文献", "联网"))
        return ConversationTurnPlan(
            intent=intent,
            action_summary={
                ConversationIntent.ANSWER: "结合当前会话回答文化问题",
                ConversationIntent.EXPLORE: "调取资料与字形上下文进行探索",
                ConversationIntent.CREATE: "按用户要求创作新的传播内容",
                ConversationIntent.REVISE: "根据反馈修改当前作品",
                ConversationIntent.TRANSFORM: "把当前作品转换为新的传播形式",
                ConversationIntent.CLARIFY: "向用户确认创作要求",
            }[intent],
            artifact_type=artifact_type,
            target_artifact_id=(
                str(artifacts[0].get("id")) if has_artifact and artifacts[0].get("id") else None
            ),
            needs_web_search=needs_web,
            search_query=message if needs_web else None,
            needs_glyph_context=needs_glyph,
        )

    async def generate_conversation_turn(
        self,
        plan: ConversationTurnPlan,
        message: str,
        history: list[dict[str, str]],
        task_context: dict[str, object],
        artifacts: list[dict[str, object]],
        web_search_context: dict[str, object] | None = None,
    ) -> ConversationTurnOutput:
        del history, web_search_context
        character = str(task_context.get("character") or "这个汉字")
        if plan.intent in {ConversationIntent.ANSWER, ConversationIntent.EXPLORE}:
            return ConversationTurnOutput(
                intent=plan.intent,
                assistant_message=(f"我会围绕“{character}”结合当前字形与资料上下文回答：{message}"),
                action_summary=plan.action_summary,
                workspace_view=("evolution" if plan.needs_glyph_context else "conversation"),
            )
        target = artifacts[0] if artifacts else {}
        artifact_type = plan.artifact_type or str(target.get("artifact_type") or "文化传播内容")
        title = f"{character} · {artifact_type}"
        body = (
            f"# {title}\n\n"
            f"## 创作目标\n\n{message}\n\n"
            f"## 核心内容\n\n围绕“{character}”组织字形观察、文化语境与当代表达。\n\n"
            "## 传播收束\n\n邀请受众继续观察汉字在历史书写与今天生活之间的联系。"
        )
        artifact = CreativeArtifactDraft(
            artifact_type=artifact_type,
            format_label=artifact_type,
            title=title,
            summary=f"根据当前对话生成的{artifact_type}",
            content_markdown=body,
            target_artifact_id=plan.target_artifact_id,
        )
        return ConversationTurnOutput(
            intent=plan.intent,
            assistant_message=f"已按你的要求生成“{title}”，可以继续告诉我修改哪一部分。",
            action_summary=plan.action_summary,
            workspace_view="artifact",
            artifact=artifact,
        )

    async def decide_next_action(
        self,
        brief: CommunicationBrief,
        context: AgentDecisionContext,
        budget: ExplorationBudget,
        allowed_actions: list[AgentAction],
    ) -> AgentDecision:
        if not brief.target_characters and AgentAction.ASK_USER in allowed_actions:
            return AgentDecision(
                action=AgentAction.ASK_USER,
                reason_code="target_missing",
                decision_summary="需要用户确认目标现代汉字后才能继续。",
                gap="目标汉字未确认",
            )
        if (
            context.phase == AgentPhase.MATERIAL_EXPLORATION
            and context.reference_count == 0
            and AgentAction.SEARCH_MORE in allowed_actions
        ):
            character = brief.target_characters[0]
            return AgentDecision(
                action=AgentAction.SEARCH_MORE,
                reason_code="reference_gap",
                decision_summary="当前还没有任务级文化资料，先围绕传播目标进行一次搜索。",
                gap="缺少可用于文化叙事的参考资料",
                query=f"{character} {brief.theme} {brief.audience} 文化故事",
            )
        if (
            context.phase == AgentPhase.GLYPH_EXPLORATION
            and context.glyph_count < brief.required_stages
            and AgentAction.RESELECT_GLYPH in allowed_actions
        ):
            return AgentDecision(
                action=AgentAction.RESELECT_GLYPH,
                reason_code="glyph_gap",
                decision_summary="当前没有可用代表字形，重新选择已登记图片。",
                gap="缺少可用字形",
            )
        if (
            context.phase == AgentPhase.NARRATIVE_BUILD
            and context.narrative_route_count == 0
            and AgentAction.BUILD_NARRATIVES in allowed_actions
        ):
            return AgentDecision(
                action=AgentAction.BUILD_NARRATIVES,
                reason_code="ready_for_routes",
                decision_summary="资料和字形上下文已具备，可以生成多条文化叙事路线。",
            )
        if (
            context.phase == AgentPhase.ASSET_EVALUATION
            and context.unmet_criteria
            and AgentAction.REWRITE_ASSET in allowed_actions
        ):
            target = context.unmet_criteria[0].split(":", 1)[0]
            return AgentDecision(
                action=AgentAction.REWRITE_ASSET,
                reason_code="asset_quality_gap",
                decision_summary=f"仅重新生成未通过验收的传播成品：{target}。",
                gap="；".join(context.unmet_criteria),
                target_asset=target,
            )
        return AgentDecision(
            action=AgentAction.FINISH,
            reason_code="phase_complete",
            decision_summary="当前阶段已满足继续条件。",
        )

    async def generate_narrative_routes(
        self, brief: CommunicationBrief, evolution: EvolutionPackage
    ) -> list[NarrativeRoute]:
        character = evolution.character
        available_stages = [
            stage for stage in evolution.glyph_stages if stage.image_id and stage.image_url
        ]
        opening_stage = available_stages[0] if available_stages else None
        comparison_stage = available_stages[-1] if available_stages else None
        visual_hooks: list[VisualHook] = []
        if opening_stage is not None:
            visual_hooks.append(
                VisualHook(
                    image_id=opening_stage.image_id or "",
                    script_type=opening_stage.script_type,
                    role="opening",
                    prompt=f"先观察早期“{character}”字的整体轮廓，引出观众的第一印象。",
                )
            )
        if comparison_stage is not None:
            visual_hooks.append(
                VisualHook(
                    image_id=comparison_stage.image_id or "",
                    script_type=comparison_stage.script_type,
                    role="comparison",
                    prompt=f"与较晚阶段并排观察，寻找“{character}”字形态组织的变化。",
                )
            )
        references = [item.evidence_id for item in _generation_evidence(evolution)[:8]]
        channels = brief.channels
        special_title = {
            "礼": "礼不是距离，而是分寸",
            "云": "一朵云，如何装下古人的天空",
            "雷": "看得见的雷声",
            "明": "古人怎样写下光明",
        }.get(character, f"今天为什么还要理解“{character}”")
        return [
            NarrativeRoute(
                route_id="route-visual",
                title=f"从字形看见“{character}”",
                core_message=f"用真实字形的可见变化打开“{character}”的文化故事。",
                opening_hook=f"如果只看轮廓，你会怎样描述最早的“{character}”？",
                visual_hooks=visual_hooks,
                story_beats=["观察早期轮廓", "比较构件与线条", "连接文化语境", "回到当代"],
                contemporary_connection=f"邀请观众重新观察今天熟悉的“{character}”字。",
                recommended_channels=channels,
                reference_ids=references,
            ),
            NarrativeRoute(
                route_id="route-daily-life",
                title=f"“{character}”如何进入日常生活",
                core_message=f"从历史材料走向今天仍能感受到的“{character}”文化经验。",
                opening_hook=f"我们每天说到“{character}”时，真正想到的是什么？",
                visual_hooks=visual_hooks[:1],
                story_beats=["提出日常问题", "回看字形材料", "寻找文化连接", "邀请观众回应"],
                contemporary_connection="用一个具体生活场景承接历史材料。",
                recommended_channels=channels,
                reference_ids=references,
            ),
            NarrativeRoute(
                route_id="route-contemporary-question",
                title=special_title,
                core_message=f"把“{character}”变成一个值得当代观众讨论的文化问题。",
                opening_hook=special_title + "？",
                visual_hooks=visual_hooks[-1:],
                story_beats=["制造观点张力", "展示字形线索", "引入参考材料", "留下开放问题"],
                contemporary_connection="不替观众下结论，而是提供可以继续讨论的入口。",
                recommended_channels=channels,
                reference_ids=references,
            ),
        ]

    async def build_cultural_motif(
        self,
        brief: CommunicationBrief,
        evolution: EvolutionPackage,
        narrative_route: NarrativeRoute,
    ) -> CulturalMotif:
        return CulturalMotif(
            source_route_id=narrative_route.route_id,
            title=narrative_route.title,
            core_message=narrative_route.core_message,
            opening_hook=narrative_route.opening_hook,
            visual_sequence=narrative_route.visual_hooks,
            story_beats=narrative_route.story_beats,
            contemporary_connection=narrative_route.contemporary_connection,
            audience_promise=(
                f"让{brief.audience}通过真实字形和一个当代问题理解“{evolution.character}”"
                "的文化故事。"
            ),
            tone=brief.tone,
            reference_ids=narrative_route.reference_ids,
        )

    async def generate_communication_asset(
        self,
        asset_type: CommunicationAssetType,
        brief: CommunicationBrief,
        evolution: EvolutionPackage,
        narrative_route: NarrativeRoute,
        motif: CulturalMotif,
        existing_asset: CommunicationAsset | None = None,
        evaluation: ArtifactEvaluation | None = None,
    ) -> CommunicationAsset:
        character = evolution.character
        hook_ids = [item.image_id for item in motif.visual_sequence]
        references = motif.reference_ids or [
            item.evidence_id for item in _generation_evidence(evolution)[:8]
        ]
        beats = motif.story_beats or narrative_route.story_beats
        if asset_type == CommunicationAssetType.INTERACTIVE_STORY:
            sections = [
                InteractiveStorySection(
                    section_id=f"story-{index}",
                    title=beat,
                    narrative=(
                        f"围绕“{character}”的“{beat}”展开：{motif.core_message}"
                        f"这一段面向{brief.audience}，把字形观察与文化语境连接起来。"
                    ),
                    visual_hook_id=(hook_ids[(index - 1) % len(hook_ids)] if hook_ids else None),
                    interaction_prompt=(
                        f"你从这一处“{character}”字形中最先注意到什么？" if index == 1 else None
                    ),
                )
                for index, beat in enumerate(beats[:6], start=1)
            ]
            while len(sections) < 3:
                index = len(sections) + 1
                sections.append(
                    InteractiveStorySection(
                        section_id=f"story-{index}",
                        title=f"继续观察“{character}”",
                        narrative=f"从新的观察角度继续理解“{character}”：{motif.core_message}",
                    )
                )
            content: InteractiveStoryContent | SocialCardsContent | ShortVideoScriptContent = (
                InteractiveStoryContent(
                    title=motif.title,
                    lede=motif.opening_hook,
                    sections=sections,
                    closing=(
                        f"{motif.contemporary_connection} 这也是“{character}”今天仍值得传播的原因。"
                    ),
                    interaction_questions=[
                        f"观察不同阶段的“{character}”，你发现了哪些可见变化？",
                        f"你会用哪个当代场景继续讲述“{character}”？",
                    ][: brief.interaction_count],
                )
            )
        elif asset_type == CommunicationAssetType.SOCIAL_CARDS:
            card_beats = [*beats, motif.contemporary_connection or "回到当代生活"]
            cards = [
                SocialCard(
                    index=index,
                    headline=(
                        motif.opening_hook
                        if index == 1
                        else card_beats[(index - 1) % len(card_beats)]
                    )[:60],
                    body=(
                        f"第 {index} 张从“{card_beats[(index - 1) % len(card_beats)]}”切入，"
                        f"共同表达：{motif.core_message}"
                    ),
                    visual_hook_id=(hook_ids[(index - 1) % len(hook_ids)] if hook_ids else None),
                    visual_direction=(
                        f"使用“{character}”的真实字形图作为主体，保留原图比例并突出可见结构。"
                    ),
                )
                for index in range(1, 6)
            ]
            content = SocialCardsContent(
                title=f"五张卡片读懂：{motif.title}",
                cards=cards,
                posting_caption=(
                    f"从一个真实字形出发，重新认识“{character}”。你最想把哪一张分享给朋友？"
                ),
            )
        else:
            ranges = [(0, 6), (6, 18), (18, 32), (32, 47), (47, 60)]
            scenes = [
                VideoScene(
                    start_second=start,
                    end_second=end,
                    visual=(f"展示“{character}”字形与“{card_beat}”的画面线索。"),
                    narration=(
                        motif.opening_hook if index == 1 else f"{card_beat}。{motif.core_message}"
                    ),
                    subtitle=(motif.opening_hook if index == 1 else card_beat)[:200],
                    visual_hook_id=(hook_ids[(index - 1) % len(hook_ids)] if hook_ids else None),
                )
                for index, ((start, end), card_beat) in enumerate(
                    zip(ranges, [*beats, motif.contemporary_connection] * 2, strict=False),
                    start=1,
                )
            ]
            content = ShortVideoScriptContent(
                title=f"60 秒看懂：{motif.title}",
                opening_hook=motif.opening_hook,
                scenes=scenes,
                closing_cta=f"你会怎样用今天的生活继续解释“{character}”？",
                full_narration=" ".join(item.narration for item in scenes),
            )
        return CommunicationAsset(
            asset_type=asset_type,
            content=content,
            reference_ids=references,
            visual_hook_ids=hook_ids,
        )

    async def evaluate_communication_asset(
        self,
        brief: CommunicationBrief,
        evolution: EvolutionPackage,
        motif: CulturalMotif,
        asset: CommunicationAsset,
    ) -> ArtifactEvaluation:
        serialized = json.dumps(asset.content.model_dump(mode="json"), ensure_ascii=False)
        checks = {
            "motif_alignment": motif.title in serialized,
            "visual_usage": (
                not motif.visual_sequence
                or bool(
                    set(asset.visual_hook_ids) & {item.image_id for item in motif.visual_sequence}
                )
            ),
            "reference_context": not _generation_evidence(evolution)
            or bool(asset.reference_ids),
            "audience_fit": bool(brief.audience),
        }
        if isinstance(asset.content, InteractiveStoryContent):
            checks["media_structure"] = len(asset.content.sections) >= 3
            checks["interaction"] = (
                len(asset.content.interaction_questions) >= brief.interaction_count
            )
        elif isinstance(asset.content, SocialCardsContent):
            checks["media_structure"] = len(asset.content.cards) == 5
            checks["interaction"] = bool(asset.content.posting_caption)
        else:
            checks["media_structure"] = (
                asset.content.duration_seconds == 60
                and asset.content.scenes[0].start_second == 0
                and asset.content.scenes[-1].end_second == 60
            )
            checks["interaction"] = bool(asset.content.closing_cta)
        messages = [name for name, passed in checks.items() if not passed]
        next_action = AgentAction.FINISH
        if messages:
            next_action = (
                AgentAction.ASK_USER
                if messages == ["reference_context"]
                else AgentAction.REWRITE_ASSET
            )
        return ArtifactEvaluation(
            passed=not messages,
            checks=checks,
            messages=messages,
            next_action=next_action,
            retry_targets=(
                [asset.asset_type.value] if next_action == AgentAction.REWRITE_ASSET else []
            ),
        )

    async def rewrite_communication_fragment(
        self,
        asset: CommunicationAsset,
        target_index: int,
        instruction: str,
        brief: CommunicationBrief,
        evolution: EvolutionPackage,
        motif: CulturalMotif,
    ) -> InteractiveStorySection | SocialCard | VideoScene:
        del brief, evolution, motif
        position = target_index - 1
        if isinstance(asset.content, InteractiveStoryContent):
            current_story = asset.content.sections[position]
            return current_story.model_copy(
                update={
                    "narrative": f"{current_story.narrative} 修改方向：{instruction}。",
                    "interaction_prompt": current_story.interaction_prompt
                    or "你从这个字形片段中观察到了什么？",
                }
            )
        if isinstance(asset.content, SocialCardsContent):
            current_card = asset.content.cards[position]
            return current_card.model_copy(
                update={"body": f"{current_card.body} 修改方向：{instruction}。"}
            )
        current_scene = asset.content.scenes[position]
        return current_scene.model_copy(
            update={"narration": f"{current_scene.narration} 修改方向：{instruction}。"}
        )

    async def plan_task(self, task_spec: TaskSpec) -> list[PlanStep]:
        character = task_spec.target_characters[0] if task_spec.target_characters else "待确认汉字"
        return [
            PlanStep(
                id="plan",
                title=f"规划“{character}”字研究与传播任务",
                agent="规划 Agent",
                tool_names=[],
                completion_criteria="形成包含工具、依赖和失败动作的可执行计划",
                failure_action="使用经过验证的本地计划模板",
            ),
            PlanStep(
                id="query_plan",
                title="拆分字形、字义、分期与文化检索问题",
                agent="规划 Agent",
                tool_names=[],
                depends_on=["plan"],
                completion_criteria="每个问题具有明确检索目的和结构化过滤条件",
                failure_action="按七类书体和三层知识模板拆分",
            ),
            PlanStep(
                id="retrieval",
                title="从网络与当前任务资料获取参考内容",
                agent="资料检索 Agent",
                tool_names=["search_evidence"],
                depends_on=["query_plan"],
                completion_criteria="返回与任务相关的网络或用户资料片段",
                failure_action="记录资料不足并继续生成可用部分",
            ),
            PlanStep(
                id="glyph_retrieval",
                title="分书体检索真实代表字形",
                agent="演化 Agent",
                tool_names=["search_glyphs"],
                depends_on=["query_plan"],
                completion_criteria="所有已登记书体都有数据库中的代表图",
                failure_action="保留真实资料缺口，不使用生成图片补位",
            ),
            PlanStep(
                id="visual_observation",
                title="用多模态模型观察字形结构与阶段差异",
                agent="字形视觉 Agent",
                tool_names=["analyze_glyphs"],
                depends_on=["glyph_retrieval"],
                completion_criteria="每条观察都对应已登记字形，且只描述可见特征",
                failure_action="明确记录模型降级，不猜测或补绘字形细节",
            ),
            PlanStep(
                id="evolution",
                title="组织字形与生成参考上下文",
                agent="上下文组织 Agent",
                tool_names=[],
                depends_on=["retrieval", "visual_observation"],
                completion_criteria="字形阶段与检索资料已整理为模型上下文",
                failure_action="保留已有字形和资料继续生成",
            ),
            PlanStep(
                id="narrative_routes",
                title="生成并选择文化叙事路线",
                agent="文化叙事 Agent",
                tool_names=[],
                depends_on=["evolution"],
                completion_criteria="形成 2–3 条差异化路线并确定其中一条",
                failure_action="使用本地路线模板并等待用户选择",
            ),
            PlanStep(
                id="cultural_motif",
                title="固化跨媒介统一文化母题",
                agent="文化叙事 Agent",
                tool_names=["build_cultural_motif"],
                depends_on=["narrative_routes"],
                completion_criteria="母题保留选定路线的核心信息、视觉顺序和当代连接",
                failure_action="从已选路线确定性生成兼容母题",
            ),
            PlanStep(
                id="communication_assets",
                title="生成互动长页、五张图文卡片和 60 秒短视频脚本",
                agent="跨媒介传播 Agent",
                tool_names=["generate_communication_asset"],
                depends_on=["cultural_motif"],
                completion_criteria="三类成品结构完整并共享同一文化母题和视觉线索",
                failure_action="单项降级为本地结构化传播模板",
            ),
            PlanStep(
                id="artifact_evaluation",
                title="独立验收三类传播成品并定向返工",
                agent="传播成品验收 Agent",
                tool_names=["evaluate_communication_asset"],
                depends_on=["communication_assets"],
                completion_criteria="分别记录母题、视觉素材、媒介结构和互动要求检查结果",
                failure_action="保留现有成品并明确显示未满足项",
            ),
            PlanStep(
                id="content",
                title=f"生成面向{task_spec.audience}的文化讲解",
                agent="文化传播 Agent",
                tool_names=["generate_content"],
                depends_on=["artifact_evaluation"],
                completion_criteria="模型参考检索资料完成内容并满足受众和时长要求",
                failure_action="复用相同参考上下文重新生成传播层",
            ),
            PlanStep(
                id="constraints",
                title="检查阶段、受众与互动约束",
                agent="约束检查 Agent",
                tool_names=["check_constraints"],
                depends_on=["content"],
                completion_criteria="所有硬约束通过，或明确给出未通过原因",
                failure_action="最多重新生成传播层一次",
            ),
        ]

    async def plan_evidence_queries(
        self, task_spec: TaskSpec, retry_context: str = ""
    ) -> list[EvidenceSearchQuery]:
        character = task_spec.target_characters[0]
        script_types = ("甲骨文", "金文", "战国文字", "篆书", "隶书", "楷书", "草书")
        queries = [
            EvidenceSearchQuery(
                query_id=f"stage-{index + 1}",
                query=(
                    f"{character} {script_type} 构形 结构 演变 历史范围 "
                    f"{task_spec.theme} {retry_context}"
                ).strip(),
                purpose=f"收集{script_type}字形、分期和相关介绍",
                character=character,
                script_type=script_type,
                topic="shape",
            )
            for index, script_type in enumerate(script_types)
        ]
        queries.extend(
            [
                EvidenceSearchQuery(
                    query_id="catalog",
                    query=(
                        f"{character} 历史字形 书体覆盖 甲骨文 金文 篆书 隶书 楷书 草书 "
                        f"{retry_context}"
                    ).strip(),
                    purpose="了解不同书体的字形资料覆盖情况",
                    character=character,
                    topic="overview",
                ),
                EvidenceSearchQuery(
                    query_id="meaning",
                    query=(
                        f"{character} 本义 字义 引申 文化语义 {task_spec.theme} {retry_context}"
                    ).strip(),
                    purpose="收集本义、字义变化与文化解释内容",
                    character=character,
                    topic="meaning_context",
                ),
                EvidenceSearchQuery(
                    query_id="framework",
                    query=(
                        f"{character} 古今文字 分期 主时间线 草书支线 规范化 {retry_context}"
                    ).strip(),
                    purpose="收集演化分期、主线和书写支线相关内容",
                    character=character,
                    topic="framework",
                ),
            ]
        )
        return queries

    async def generate_content(
        self,
        task_spec: TaskSpec,
        evolution: EvolutionPackage,
        narrative_route: NarrativeRoute | None = None,
    ) -> GeneratedContent:
        audience_note = self._audience_note(task_spec.audience)
        format_label = {
            "interactive_lesson": "互动讲解",
            "culture_card": "文化卡",
            "article_outline": "文章提纲",
        }[task_spec.output_type]
        mainline_stages = [
            stage for stage in evolution.glyph_stages if stage.lineage_role != "branch"
        ]
        branch_stages = [
            stage for stage in evolution.glyph_stages if stage.lineage_role == "branch"
        ]
        stage_lines = [
            (
                f"- **{stage.period}·{stage.script_type}**：{stage.structure_description}"
                if stage.availability == "available"
                else f"- **{stage.period}·{stage.script_type}**：当前数据集暂无该字样本。"
            )
            for stage in mainline_stages
        ]
        branch_lines = [
            (
                f"- **{stage.script_type}支线**：{stage.structure_description}"
                if stage.availability == "available"
                else f"- **{stage.script_type}支线**：当前数据集暂无该字样本。"
            )
            for stage in branch_stages
        ]
        reference_lines = [
            f"- **{item.title}**（{item.author_or_org}）：{item.quote_or_summary}"
            for item in _generation_evidence(evolution)[:12]
        ]
        visual_lines = [
            (
                f"- **{item.script_type}**："
                + "；".join([*item.visible_features, item.composition, item.stroke_form]).strip(
                    "；"
                )
            )
            for item in (
                evolution.visual_analysis.stage_observations
                if evolution.visual_analysis is not None
                else []
            )
        ]
        body = "\n\n".join(
            [
                f"# {evolution.character}：从早期字形到文化语义",
                (
                    f"这是一份面向{task_spec.audience}、预计 {task_spec.duration_minutes} "
                    f"分钟的{format_label}。{audience_note}观察“{evolution.character}”字时，"
                    "我们先把字形、字义和后来的文化解释分开，避免把生动联想误当成历史事实。"
                ),
                "## 字形时间线\n" + "\n".join(stage_lines),
                "## 书写支线\n" + "\n".join(branch_lines),
                "## 多模态字形观察\n"
                + (
                    "以下均为图中可见的线条、构件和位置特征：\n" + "\n".join(visual_lines)
                    if visual_lines
                    else "当前没有模型视觉观察结果。"
                ),
                "## 参考资料摘录\n"
                + ("\n".join(reference_lines) if reference_lines else "当前没有可用参考资料。"),
                (
                    "## 选定的文化叙事路线\n"
                    f"**{narrative_route.title}**：{narrative_route.core_message}\n\n"
                    f"开场：{narrative_route.opening_hook}"
                    if narrative_route is not None
                    else ""
                ),
                "## 说明\n"
                "以上内容由本地模板整理，仅用于外部模型不可用时的降级展示。参考资料用于减少无依据补写，系统不执行事实核验。",
            ]
        )
        questions = [
            f"观察不同阶段的“{evolution.character}”字，哪些构形特征发生了变化？",
            "参考资料中提到了哪些与这个字有关的信息？",
            "如果不同资料说法不同，你还想继续了解哪一部分？",
        ][: task_spec.interaction_count]
        return GeneratedContent(
            title=f"“{evolution.character}”字文化讲解",
            audience=task_spec.audience,
            duration_minutes=task_spec.duration_minutes,
            outline=["认识任务", "观察字形", "参考资料", "互动讨论"],
            body_markdown=body,
            interaction_questions=questions,
            source_ids=[evidence.evidence_id for evidence in _generation_evidence(evolution)],
            estimated_characters=len(re.sub(r"\s|[#*\-]", "", body)),
        )

    @staticmethod
    def _extract_int(text: str, pattern: str, default: int) -> int:
        match = re.search(pattern, text)
        return int(match.group(1)) if match else default

    @staticmethod
    def _explicit_target(text: str) -> str | None:
        return extract_explicit_hanzi_target(text)

    @staticmethod
    def _audience_note(audience: str) -> str:
        if "小学" in audience:
            return "表达会使用短句和可观察的器物特征，并用问题帮助理解。"
        if "初中" in audience or "高中" in audience:
            return "表达会补充必要的历史背景，并区分材料、解释与推论。"
        if "国际" in audience:
            return "表达会减少生僻术语，并解释关键文化概念。"
        return "表达会保留必要术语，并结合检索与上传资料组织内容。"


class AliyunBailianTextProvider:
    """Structured OpenAI-compatible planner, parser and writer with a safe fallback."""

    required_plan_ids = {
        "plan",
        "query_plan",
        "retrieval",
        "glyph_retrieval",
        "visual_observation",
        "evolution",
        "narrative_routes",
        "cultural_motif",
        "communication_assets",
        "artifact_evaluation",
        "content",
        "constraints",
    }

    def __init__(
        self, api_key: str, base_url: str, model: str, timeout_seconds: float = 60
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.fallback = DeterministicTextProvider()
        self.last_fallback_used = False

    async def parse_task(self, raw_input: str) -> TaskSpec:
        system = (
            "你是汉字文化任务解析器。只提取用户明确给出的目标字、受众、时长、阶段数、"
            "互动题数量、主题与限制，不猜测未知古文字。返回且只返回包含以下字段的 JSON 对象："
            "target_characters（单个现代汉字组成的数组）、theme、audience、duration_minutes、"
            "output_type（只能是 interactive_lesson、culture_card、article_outline 之一）、"
            "required_stages、interaction_count、language、constraints、source_contexts、"
            "target_needs_confirmation、web_search_enabled。没有明确说明的字段分别使用默认值："
            "theme=汉字演化与文化、audience=普通文化爱好者、duration_minutes=4、"
            "output_type=interactive_lesson、required_stages=3、interaction_count=2、"
            "language=zh-CN、constraints=[]、source_contexts=[]、"
            "target_needs_confirmation=false、web_search_enabled=true。不要使用近义字段名。"
        )
        try:
            parsed = await self._json_completion(system, {"raw_input": raw_input})
            spec = TaskSpec.model_validate(parsed)
            if len(spec.target_characters) != 1 or len(spec.target_characters[0]) != 1:
                raise ValueError("模型没有提取出唯一目标汉字")
            self.last_fallback_used = False
            return spec
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.last_fallback_used = True
            return await self.fallback.parse_task(raw_input)

    async def parse_communication_brief(self, raw_input: str) -> CommunicationBrief:
        system = (
            "你是汉字文化传播任务解析器。提取用户明确给出的目标汉字、传播目标、主题、受众、"
            "媒介、语气、时长、交付物、成功标准和限制。媒介只允许 interactive_page、"
            "social_cards、short_video_60s；交付物只允许 interactive_story、five_cards、"
            "video_script。未指定时长默认 60 秒，不猜测未知古文字。返回且只返回包含以下字段的 "
            "JSON 对象：target_characters、communication_goal、theme、audience、channels、tone、"
            "duration_seconds、deliverables、required_stages、interaction_count、success_criteria、"
            "language、constraints、source_contexts、target_needs_confirmation、"
            "web_search_enabled。数组字段必须始终返回数组，不要使用近义字段名，不输出解释。"
        )
        try:
            parsed = await self._json_completion(system, {"raw_input": raw_input})
            brief = CommunicationBrief.model_validate(parsed)
            explicit_target = extract_explicit_hanzi_target(raw_input)
            if explicit_target is not None:
                brief.target_characters = [explicit_target]
            if len(brief.target_characters) != 1 or len(brief.target_characters[0]) != 1:
                raise ValueError("模型没有提取出唯一目标汉字")
            self.last_fallback_used = False
            return brief
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.last_fallback_used = True
            return await self.fallback.parse_communication_brief(raw_input)

    async def plan_conversation_turn(
        self,
        message: str,
        history: list[dict[str, str]],
        artifacts: list[dict[str, object]],
        character: str | None,
    ) -> ConversationTurnPlan:
        system = (
            "你是汉字文化传播创作智能体的意图路由器。根据最新消息、最近对话和已有作品，"
            "选择一个 intent：answer=直接讨论或回答，explore=研究字形或资料，create=创作新作品，"
            "revise=修改已有作品，transform=把已有作品转换成另一种形式，clarify=缺少关键要求。"
            "用户没有要求生成作品时不要擅自选择 create。artifact_type 使用用户自己的内容形式名称，"
            "不受固定枚举限制。系统不生成视频文件：当用户要求创作视频、动画或短片时，"
            "artifact_type 必须设为视频脚本。只有回答确实需要新网络资料时 "
            "needs_web_search=true；涉及真实字形观察"
            "或演化比较时 needs_glyph_context=true。target_artifact_id 只能使用已有作品 ID。"
            "返回 JSON：intent、action_summary、artifact_type、target_artifact_id、"
            "needs_web_search、search_query、needs_glyph_context。不要输出思维过程。"
        )
        payload = {
            "message": message,
            "character": character,
            "recent_history": history[-10:],
            "available_artifacts": [
                {
                    "id": item.get("id"),
                    "artifact_type": item.get("artifact_type"),
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                }
                for item in artifacts[:12]
            ],
        }
        try:
            parsed = await self._json_completion(system, payload)
            plan = ConversationTurnPlan.model_validate(parsed)
            available_ids = {
                str(item["id"]) for item in artifacts if isinstance(item.get("id"), str)
            }
            if plan.target_artifact_id not in available_ids:
                plan.target_artifact_id = None
            if (
                plan.intent in {ConversationIntent.REVISE, ConversationIntent.TRANSFORM}
                and plan.target_artifact_id is None
                and artifacts
            ):
                first_id = artifacts[0].get("id")
                plan.target_artifact_id = str(first_id) if first_id else None
            if not plan.needs_web_search:
                plan.search_query = None
            if plan.intent in {ConversationIntent.CREATE, ConversationIntent.TRANSFORM} and any(
                term in message for term in ("视频", "动画", "短片")
            ):
                plan.artifact_type = "视频脚本"
            self.last_fallback_used = False
            return plan
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.last_fallback_used = True
            return await self.fallback.plan_conversation_turn(
                message, history, artifacts, character
            )

    async def generate_conversation_turn(
        self,
        plan: ConversationTurnPlan,
        message: str,
        history: list[dict[str, str]],
        task_context: dict[str, object],
        artifacts: list[dict[str, object]],
        web_search_context: dict[str, object] | None = None,
    ) -> ConversationTurnOutput:
        system = (
            "你是“字脉”，一个可持续对话的汉字文化传播创作智能体。你可以讨论问题、研究字形，"
            "也可以按照用户指定的任意形式创作、修改或转换文化传播内容。不要把输出限制为互动网页、"
            "五张卡片或 60 秒视频。回答应直接回应最新消息，并自然承接历史对话。"
            "最新消息的范围和否定要求优先级最高；历史消息只用于承接上下文，不得复制旧回答。"
            "如果最新消息点名了若干书体，只讨论 task_context.glyph_stages 实际提供的这些书体。"
            "网络搜索、用户文档和字形资料只是生成参考；不要声称完成了事实审查。"
            "涉及图像时只描述输入提供的可见特征，"
            "不要仅凭图像解释构件含义、造字法、字源、年代或传承；只有参考资料明确提供时才能引用。"
            "所有面向用户的文字不得出现图片编号、代码点、数据集名称、"
            "元数据、原始路径或内部字段名，也不要输出模型思维过程。"
            "系统不具备视频渲染、合成或视频文件导出能力。若用户要求生成视频、动画或短片，"
            "必须交付可编辑的视频脚本，内容应按需包含分镜、旁白、字幕、时长和素材建议；"
            "不得声称已经生成视频、动画或 MP4 文件。"
            "返回 JSON：intent、assistant_message、action_summary、workspace_view、artifact。"
            "workspace_view 只能是 conversation、evolution、sources、artifact。"
            "answer、explore、clarify 时 artifact=null；create、revise、transform 时 artifact 必须"
            "包含 artifact_type、format_label、title、summary、content_markdown、"
            "target_artifact_id、reference_ids、visual_hook_ids。content_markdown 是可直接"
            "交付的完整"
            "作品，不是提纲或生成说明；形式、长度、语气和结构服从用户要求。修改时保留未要求改变的"
            "部分，转换时生成适合新媒介的完整版本。编号只能放在 reference_ids、visual_hook_ids、"
            "target_artifact_id 这些机器字段中。若 available_artifacts 中提供 selection，用户说"
            "“这里”“这一页”“这段”时必须只修改 selection 指向的页面或内容块，保留其他内容。"
            "系统公开支持 Word、HTML、TXT、PDF、PPT 五种格式；作品正文需要有明确的图片使用位置"
            "和图注。TXT 只能输出图片说明，不得声称能嵌入图片。available_artifacts 中 source_kind="
            "glyph 且 locked=true 的真实历史字形不得替换、重绘或虚构；修改时只可调整其位置、大小、"
            "顺序、图注以及周围文字。"
        )
        payload = {
            "plan": plan.model_dump(mode="json"),
            "message": message,
            "recent_history": history[-12:],
            "task_context": task_context,
            "available_artifacts": artifacts[:8],
            "web_search_context": web_search_context,
        }
        try:
            parsed = await self._json_completion(system, payload)
            parsed["intent"] = plan.intent.value
            parsed["action_summary"] = plan.action_summary
            output = ConversationTurnOutput.model_validate(parsed)
            if output.artifact is not None:
                if plan.intent in {ConversationIntent.CREATE, ConversationIntent.TRANSFORM} and any(
                    term in message for term in ("视频", "动画", "短片")
                ):
                    output.artifact.artifact_type = "视频脚本"
                    output.artifact.format_label = "视频脚本"
                    if "脚本" not in output.artifact.title:
                        output.artifact.title = f"{output.artifact.title}（视频脚本）"
                    output.assistant_message = (
                        f"已生成“{output.artifact.title}”视频脚本。"
                        "你可以继续修改分镜、旁白、字幕、时长或素材建议。"
                    )
                raw_references = task_context.get("reference_materials", [])
                reference_items = raw_references if isinstance(raw_references, list) else []
                allowed_references = {
                    str(item.get("reference_id"))
                    for item in reference_items
                    if isinstance(item, dict) and item.get("reference_id")
                }
                raw_stages = task_context.get("glyph_stages", [])
                stage_items = raw_stages if isinstance(raw_stages, list) else []
                allowed_images = {
                    str(item.get("image_id"))
                    for item in stage_items
                    if isinstance(item, dict) and item.get("image_id")
                }
                output.artifact.reference_ids = [
                    item for item in output.artifact.reference_ids if item in allowed_references
                ]
                output.artifact.visual_hook_ids = [
                    item for item in output.artifact.visual_hook_ids if item in allowed_images
                ]
                output.artifact.target_artifact_id = plan.target_artifact_id
                output.workspace_view = "artifact"
            elif plan.needs_glyph_context:
                output.workspace_view = "evolution"
            elif plan.needs_web_search:
                output.workspace_view = "sources"
            self.last_fallback_used = False
            return output
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.last_fallback_used = False
            raise RuntimeError("多模态主模型未能完成这轮对话") from exc

    async def decide_next_action(
        self,
        brief: CommunicationBrief,
        context: AgentDecisionContext,
        budget: ExplorationBudget,
        allowed_actions: list[AgentAction],
    ) -> AgentDecision:
        if not allowed_actions:
            raise ValueError("当前阶段没有可执行动作")
        system = (
            "你是字脉受控决策器。根据传播任务、当前阶段摘要和剩余预算，从 allowed_actions 中"
            "选择且只选择一个下一动作。返回 JSON：action、reason_code、decision_summary、gap、"
            "query、target_asset。decision_summary 是面向用户的一句话，不输出思维过程，不发明"
            "allowed_actions 之外的动作。"
        )
        payload = {
            "communication_brief": brief.model_dump(mode="json"),
            "context": context.model_dump(mode="json"),
            "budget": budget.model_dump(mode="json"),
            "allowed_actions": [item.value for item in allowed_actions],
        }
        try:
            parsed = await self._json_completion(system, payload)
            decision = AgentDecision.model_validate(parsed)
            if decision.action not in allowed_actions:
                raise ValueError("模型选择了白名单之外的动作")
            self.last_fallback_used = False
            return decision
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.last_fallback_used = True
            return await self.fallback.decide_next_action(brief, context, budget, allowed_actions)

    async def plan_task(self, task_spec: TaskSpec) -> list[PlanStep]:
        system = (
            "你是字脉规划 Agent。根据任务定制八步执行计划。返回 JSON 对象 {steps:[...]}。"
            "步骤 id 必须且只能依次使用 plan、query_plan、retrieval、glyph_retrieval、"
            "visual_observation、evolution、narrative_routes、cultural_motif、"
            "communication_assets、artifact_evaluation、content、constraints。每项包含 "
            "title、agent、tool_names、"
            "depends_on、"
            "completion_criteria、failure_action，status 固定为 pending。允许的工具为 "
            "search_evidence、search_glyphs、analyze_glyphs、build_cultural_motif、"
            "generate_communication_asset、evaluate_communication_asset、generate_content、"
            "check_constraints。"
            "网络和用户资料仅作为生成参考，不安排事实核验或逐条证据绑定步骤。不得输出模型思维过程。"
        )
        try:
            payload = await self._json_completion(system, task_spec.model_dump(mode="json"))
            steps = [PlanStep.model_validate(item) for item in payload["steps"]]
            if {item.id for item in steps} != self.required_plan_ids:
                raise ValueError("动态计划没有覆盖规范执行节点")
            canonical = await self.fallback.plan_task(task_spec)
            contracts = {item.id: item for item in canonical}
            planned = {item.id: item for item in steps}
            ordered_steps = [planned[item.id] for item in canonical]
            for step in ordered_steps:
                contract = contracts[step.id]
                step.status = "pending"
                step.tool_names = contract.tool_names
                step.depends_on = contract.depends_on
                step.completion_criteria = contract.completion_criteria
                step.failure_action = contract.failure_action
            self.last_fallback_used = False
            return ordered_steps
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.last_fallback_used = True
            return await self.fallback.plan_task(task_spec)

    async def plan_evidence_queries(
        self, task_spec: TaskSpec, retry_context: str = ""
    ) -> list[EvidenceSearchQuery]:
        system = (
            "你是汉字文献检索规划器。返回 JSON 对象 {queries:[...]}，每项包含 query_id、query、"
            "purpose、character、script_type、historical_period、topic。必须覆盖七类书体、字义文化和"
            "总体分期，并包含一个 topic=overview 的字形资料覆盖查询。不得搜索或输出内部数据集名称、"
            "图片编号、存储路径或元数据字段，不得补充输入之外的事实。"
        )
        request = {**task_spec.model_dump(mode="json"), "retry_context": retry_context}
        try:
            payload = await self._json_completion(system, request)
            queries = [EvidenceSearchQuery.model_validate(item) for item in payload["queries"]]
            character = task_spec.target_characters[0]
            if not queries or any(item.character != character for item in queries):
                raise ValueError("检索计划目标字不一致")
            required_scripts = {"甲骨文", "金文", "战国文字", "篆书", "隶书", "楷书", "草书"}
            planned_scripts = {item.script_type for item in queries if item.script_type}
            planned_topics = {item.topic for item in queries if item.topic}
            if not required_scripts.issubset(planned_scripts) or not {
                "overview",
                "framework",
                "meaning_context",
            }.issubset(planned_topics):
                raise ValueError("检索计划未覆盖规范书体或核心主题")
            self.last_fallback_used = False
            return queries[:14]
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.last_fallback_used = True
            return await self.fallback.plan_evidence_queries(task_spec, retry_context)

    async def generate_narrative_routes(
        self, brief: CommunicationBrief, evolution: EvolutionPackage
    ) -> list[NarrativeRoute]:
        allowed_images = {
            stage.image_id for stage in evolution.glyph_stages if stage.image_id is not None
        }
        allowed_references = {item.evidence_id for item in _generation_evidence(evolution)}
        system = (
            "你是汉字文化叙事策划 Agent。基于传播 Brief、真实字形阶段、结构化视觉观察和参考"
            "资料，生成 2 到 3 条明显不同的 NarrativeRoute。每条包含 route_id、title、"
            "core_message、opening_hook、visual_hooks、story_beats、contemporary_connection、"
            "recommended_channels、reference_ids。visual_hooks 只能引用输入中的 image_id，"
            "且每项必须是对象 {image_id,script_type,role,prompt}，role 只能是 opening、"
            "comparison、transition、interaction；story_beats 必须是 2 到 8 条纯字符串，不能"
            "返回对象；recommended_channels 只能使用 interactive_page、social_cards、"
            "short_video_60s。"
            "reference_ids 只能引用输入中的 evidence_id。image_id 和 evidence_id 只允许出现在"
            "对应的机器字段中，标题、正文、提示语等面向用户的文字不得出现图片编号、数据集名称、"
            "元数据、原始路径或内部字段名；不要输出学术定论或模型思维过程。"
            "返回 JSON 对象 {routes:[...]}。"
        )
        payload = {
            "communication_brief": brief.model_dump(mode="json"),
            "glyph_stages": [
                {
                    "image_id": stage.image_id,
                    "script_type": stage.script_type,
                    "period": stage.period,
                    "structure_description": stage.structure_description,
                }
                for stage in evolution.glyph_stages
                if stage.image_id is not None
            ],
            "glyph_visual_analysis": self._public_visual_analysis(evolution),
            "reference_materials": self._public_reference_materials(evolution, 16, 1200),
        }
        try:
            parsed = await self._json_completion(system, payload)
            script_by_image = {
                stage.image_id: stage.script_type
                for stage in evolution.glyph_stages
                if stage.image_id is not None
            }
            routes = [
                NarrativeRoute.model_validate(
                    self._normalize_narrative_route_payload(
                        item,
                        index=index,
                        script_by_image=script_by_image,
                        allowed_references=allowed_references,
                        fallback_channels=brief.channels,
                    )
                )
                for index, item in enumerate(parsed["routes"])
            ]
            if not 2 <= len(routes) <= 3:
                raise ValueError("叙事路线数量必须为 2 到 3 条")
            if len({route.route_id for route in routes}) != len(routes):
                raise ValueError("叙事路线编号重复")
            if any(
                hook.image_id not in allowed_images
                for route in routes
                for hook in route.visual_hooks
            ):
                raise ValueError("叙事路线引用了未登记字形")
            if any(
                reference_id not in allowed_references
                for route in routes
                for reference_id in route.reference_ids
            ):
                raise ValueError("叙事路线引用了当前任务之外的资料")
            self.last_fallback_used = False
            return routes
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.last_fallback_used = False
            raise RuntimeError("多模态主模型未能生成有效叙事路线") from exc

    @staticmethod
    def _normalize_narrative_route_payload(
        item: object,
        *,
        index: int,
        script_by_image: dict[str, str],
        allowed_references: set[str],
        fallback_channels: list[CommunicationChannel],
    ) -> dict[str, Any]:
        """Repair machine-only fields without replacing model-authored narrative copy."""
        if not isinstance(item, dict):
            raise TypeError("叙事路线必须是对象")
        normalized = dict(item)
        route_id = normalized.get("route_id")
        if not isinstance(route_id, str) or not route_id.strip():
            normalized["route_id"] = f"route-{index + 1}"

        beats: list[str] = []
        beat_by_image: dict[str, str] = {}
        raw_beats = normalized.get("story_beats", [])
        if not isinstance(raw_beats, list):
            raw_beats = []
        for beat in raw_beats:
            if isinstance(beat, str):
                description = beat.strip()
                image_ref = None
            elif isinstance(beat, dict):
                description = next(
                    (
                        value.strip()
                        for key in ("description", "narrative", "content", "text")
                        if isinstance((value := beat.get(key)), str) and value.strip()
                    ),
                    "",
                )
                image_ref = beat.get("image_ref")
            else:
                continue
            if description:
                beats.append(description)
                if isinstance(image_ref, str) and image_ref in script_by_image:
                    beat_by_image[image_ref] = description
        normalized["story_beats"] = beats

        hooks: list[dict[str, str]] = []
        raw_hooks = normalized.get("visual_hooks", [])
        if not isinstance(raw_hooks, list):
            raw_hooks = []
        role_aliases = {
            "开场": "opening",
            "对比": "comparison",
            "转场": "transition",
            "互动": "interaction",
        }
        allowed_roles = {"opening", "comparison", "transition", "interaction"}
        for hook_index, hook in enumerate(raw_hooks):
            hook_data = hook if isinstance(hook, dict) else {}
            image_id = hook if isinstance(hook, str) else hook_data.get("image_id")
            if not isinstance(image_id, str) or image_id not in script_by_image:
                continue
            role_value = hook_data.get("role")
            role = role_aliases.get(str(role_value), str(role_value))
            if role not in allowed_roles:
                role = "opening" if hook_index == 0 else "transition"
            prompt_value = hook_data.get("prompt")
            prompt = (
                prompt_value.strip()
                if isinstance(prompt_value, str) and prompt_value.strip()
                else beat_by_image.get(image_id)
            )
            if not prompt:
                opening_hook = normalized.get("opening_hook")
                prompt = opening_hook.strip() if isinstance(opening_hook, str) else ""
            hooks.append(
                {
                    "image_id": image_id,
                    "script_type": script_by_image[image_id],
                    "role": role,
                    "prompt": prompt,
                }
            )
        if not hooks:
            raise ValueError("叙事路线没有引用可用字形")
        normalized["visual_hooks"] = hooks

        channel_aliases = {"web_page": CommunicationChannel.INTERACTIVE_PAGE.value}
        allowed_channels = {item.value for item in CommunicationChannel}
        raw_channels = normalized.get("recommended_channels", [])
        channels = (
            [
                channel_aliases.get(str(channel), str(channel))
                for channel in raw_channels
                if isinstance(channel, str)
            ]
            if isinstance(raw_channels, list)
            else []
        )
        normalized["recommended_channels"] = list(
            dict.fromkeys(channel for channel in channels if channel in allowed_channels)
        ) or [item.value for item in fallback_channels]

        raw_references = normalized.get("reference_ids", [])
        normalized["reference_ids"] = (
            list(
                dict.fromkeys(
                    reference_id
                    for reference_id in raw_references
                    if isinstance(reference_id, str) and reference_id in allowed_references
                )
            )
            if isinstance(raw_references, list)
            else []
        )
        return normalized

    async def build_cultural_motif(
        self,
        brief: CommunicationBrief,
        evolution: EvolutionPackage,
        narrative_route: NarrativeRoute,
    ) -> CulturalMotif:
        allowed_images = {
            stage.image_id for stage in evolution.glyph_stages if stage.image_id is not None
        }
        allowed_references = {item.evidence_id for item in _generation_evidence(evolution)}
        system = (
            "你是汉字文化传播母题设计器。把用户已选择的 NarrativeRoute 固化成一个跨媒介"
            "CulturalMotif，互动长页、五张图文卡片和 60 秒短视频后续都必须复用它。"
            "返回 JSON：source_route_id、title、core_message、opening_hook、visual_sequence、"
            "story_beats、contemporary_connection、audience_promise、tone、reference_ids。"
            "不得改变 route_id；图片和参考资料编号只能取自输入，并且只允许出现在机器字段中。"
            "所有面向用户的文字不得出现图片编号、数据集名称、元数据、原始路径或内部字段名。"
        )
        payload = {
            "communication_brief": brief.model_dump(mode="json"),
            "selected_narrative_route": narrative_route.model_dump(mode="json"),
            "character": evolution.character,
        }
        try:
            parsed = await self._json_completion(system, payload)
            motif = CulturalMotif.model_validate(parsed)
            if motif.source_route_id != narrative_route.route_id:
                raise ValueError("文化母题没有绑定已选路线")
            if any(item.image_id not in allowed_images for item in motif.visual_sequence):
                raise ValueError("文化母题引用了未登记字形")
            if any(item not in allowed_references for item in motif.reference_ids):
                raise ValueError("文化母题引用了当前任务之外的资料")
            self.last_fallback_used = False
            return motif
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.last_fallback_used = False
            raise RuntimeError("多模态主模型未能生成有效文化母题") from exc

    async def generate_communication_asset(
        self,
        asset_type: CommunicationAssetType,
        brief: CommunicationBrief,
        evolution: EvolutionPackage,
        narrative_route: NarrativeRoute,
        motif: CulturalMotif,
        existing_asset: CommunicationAsset | None = None,
        evaluation: ArtifactEvaluation | None = None,
    ) -> CommunicationAsset:
        allowed_images = {
            stage.image_id for stage in evolution.glyph_stages if stage.image_id is not None
        }
        allowed_references = {item.evidence_id for item in _generation_evidence(evolution)}
        structure_requirement = {
            CommunicationAssetType.INTERACTIVE_STORY: (
                "content 必须包含 title、lede、3–8 个 sections、closing、interaction_questions；"
                "每个 section 包含 section_id、title、narrative、visual_hook_id、"
                "interaction_prompt。"
            ),
            CommunicationAssetType.SOCIAL_CARDS: (
                "content 必须包含 title、严格 5 张 cards、posting_caption；每张卡按 1–5 编号并包含"
                "headline、body、visual_hook_id、visual_direction。"
            ),
            CommunicationAssetType.SHORT_VIDEO_SCRIPT: (
                "content 必须包含 title、duration_seconds=60、opening_hook、"
                "4–10 个连续分镜 scenes、"
                "closing_cta、full_narration；分镜从 0 秒连续覆盖到 60 秒，每项包含 start_second、"
                "end_second、visual、narration、subtitle、visual_hook_id。"
            ),
        }[asset_type]
        system = (
            "你是汉字文化跨媒介创作 Agent。只生成指定的一类传播成品，严格复用输入 CulturalMotif "
            "的核心信息、开场和视觉顺序，不把三个媒介写成同一篇文案。"
            + structure_requirement
            + "返回符合 CommunicationAsset 的 JSON：asset_type、version=1、content、reference_ids、"
            "visual_hook_ids、status=generated。visual_hook_id 只能使用输入中的 image_id，"
            "reference_ids 只能使用输入中的 evidence_id。编号只允许出现在机器字段中；content 内"
            "所有面向用户的标题、正文、旁白、字幕和画面说明不得出现图片编号、数据集名称、元数据、"
            "原始路径或内部字段名，不输出解释。"
        )
        payload = {
            "asset_type": asset_type.value,
            "communication_brief": brief.model_dump(mode="json"),
            "selected_narrative_route": narrative_route.model_dump(mode="json"),
            "cultural_motif": motif.model_dump(mode="json"),
            "character": evolution.character,
            "reference_materials": self._public_reference_materials(evolution, 16, 1200),
            "rewrite_context": (
                {
                    "existing_asset": existing_asset.model_dump(mode="json"),
                    "evaluation": evaluation.model_dump(mode="json") if evaluation else None,
                    "instruction": "只修复验收未通过项，保持其他结构和统一文化母题不变。",
                }
                if existing_asset is not None
                else None
            ),
        }
        try:
            parsed = await self._json_completion(system, payload)
            asset = CommunicationAsset.model_validate(
                {**parsed, "asset_type": asset_type.value, "version": 1}
            )
            if any(item not in allowed_images for item in asset.visual_hook_ids):
                raise ValueError("传播成品引用了未登记字形")
            if any(item not in allowed_references for item in asset.reference_ids):
                raise ValueError("传播成品引用了当前任务之外的资料")
            self.last_fallback_used = False
            return asset
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.last_fallback_used = False
            raise RuntimeError("多模态主模型未能生成有效传播成品") from exc

    async def evaluate_communication_asset(
        self,
        brief: CommunicationBrief,
        evolution: EvolutionPackage,
        motif: CulturalMotif,
        asset: CommunicationAsset,
    ) -> ArtifactEvaluation:
        return await self.fallback.evaluate_communication_asset(
            brief,
            evolution,
            motif,
            asset,
        )

    async def rewrite_communication_fragment(
        self,
        asset: CommunicationAsset,
        target_index: int,
        instruction: str,
        brief: CommunicationBrief,
        evolution: EvolutionPackage,
        motif: CulturalMotif,
    ) -> InteractiveStorySection | SocialCard | VideoScene:
        position = target_index - 1
        if isinstance(asset.content, InteractiveStoryContent):
            fragment_name = "互动长页段落"
            current_payload = asset.content.sections[position].model_dump(mode="json")
        elif isinstance(asset.content, SocialCardsContent):
            fragment_name = "社交图文卡片"
            current_payload = asset.content.cards[position].model_dump(mode="json")
        else:
            fragment_name = "短视频分镜"
            current_payload = asset.content.scenes[position].model_dump(mode="json")
        system = (
            f"你是汉字文化传播编辑 Agent。只重写输入中的一个{fragment_name}，不要生成整套成品。"
            "必须服从用户修改要求，同时保持统一文化母题、目标受众、参考资料边界和原有图片引用。"
            "不得改动输入片段的身份字段：section_id、index 或 start_second/end_second。"
            "除身份字段和 visual_hook_id 外，面向用户的文字不得出现图片编号、数据集名称、元数据、"
            "原始路径或内部字段名。"
            "只返回与输入片段字段完全相同的 JSON 对象，不输出解释。"
        )
        payload = {
            "instruction": instruction,
            "target_index": target_index,
            "current_fragment": current_payload,
            "communication_brief": brief.model_dump(mode="json"),
            "cultural_motif": motif.model_dump(mode="json"),
            "character": evolution.character,
            "reference_materials": self._public_reference_materials(evolution, 10, 800),
        }
        try:
            parsed = await self._json_completion(system, payload)
            if isinstance(asset.content, InteractiveStoryContent):
                current_story = asset.content.sections[position]
                story_fragment = InteractiveStorySection.model_validate(parsed)
                story_fragment.section_id = current_story.section_id
                fragment: InteractiveStorySection | SocialCard | VideoScene = story_fragment
            elif isinstance(asset.content, SocialCardsContent):
                current_card = asset.content.cards[position]
                card_fragment = SocialCard.model_validate(parsed)
                card_fragment.index = current_card.index
                fragment = card_fragment
            else:
                current_scene = asset.content.scenes[position]
                scene_fragment = VideoScene.model_validate(parsed)
                scene_fragment.start_second = current_scene.start_second
                scene_fragment.end_second = current_scene.end_second
                fragment = scene_fragment
            allowed_hooks = set(asset.visual_hook_ids)
            if fragment.visual_hook_id and fragment.visual_hook_id not in allowed_hooks:
                fragment.visual_hook_id = current_payload.get("visual_hook_id")
            self.last_fallback_used = False
            return fragment
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.last_fallback_used = False
            raise RuntimeError("多模态主模型未能完成片段改写") from exc

    async def generate_content(
        self,
        task_spec: TaskSpec,
        evolution: EvolutionPackage,
        narrative_route: NarrativeRoute | None = None,
    ) -> GeneratedContent:
        references = self._public_reference_materials(evolution, 24, 1800)
        stages = [
            {
                "period": item.period,
                "script_type": item.script_type,
                "availability": item.availability.value,
                "lineage_role": item.lineage_role.value,
                "structure_description": self._public_stage_description(item.structure_description),
            }
            for item in evolution.glyph_stages
        ]
        visual_analysis = self._public_visual_analysis(evolution)
        system = (
            "你是汉字文化内容生成助手。根据用户任务、检索到的网络内容、用户上传资料和字形阶段信息"
            "以及多模态模型对已标注字形图的可见特征观察生成文化讲解。若提供"
            "selected_narrative_route，正文必须遵循其核心信息、开场和故事节拍。参考资料是写作上下文，"
            "视觉观察不是年代或传承结论；不要声称系统完成了事实审查，"
            "也不要声称内容绝对正确。优先使用参考资料中的信息，避免补充上下文没有提供的具体年代、"
            "出处、器物名称或确定性演化关系。当 glyph_visual_analysis.stage_observations 非空时，"
            "body_markdown 必须包含二级标题‘## 多模态字形观察’，准确转述至少两条"
            "visible_features、composition 或 stroke_form，并用‘图中可见’来说明这是视觉观察；"
            "不得把这些可见特征扩写成字义、年代、字源或直接演化关系。最终面向用户的任何文字中"
            "不得出现图片编号、代码点、数据集名称、元数据、原始路径、image_id 或其他内部字段名。"
            "正文必须由你完整生成，不要要求程序追加模板段落。返回 JSON 对象，字段必须符合"
            "GeneratedContent：title、"
            "audience、duration_minutes、outline、body_markdown、interaction_questions、source_ids、"
            "estimated_characters。source_ids 由系统覆盖，无需自行生成。"
        )
        payload = {
            "task": task_spec.model_dump(mode="json"),
            "character": evolution.character,
            "selected_narrative_route": (
                narrative_route.model_dump(mode="json") if narrative_route is not None else None
            ),
            "glyph_stages": stages,
            "glyph_visual_analysis": visual_analysis,
            "reference_materials": references,
        }
        try:
            parsed = await self._json_completion(system, payload)
            content = GeneratedContent.model_validate(
                {
                    **parsed,
                    "audience": task_spec.audience,
                    "duration_minutes": task_spec.duration_minutes,
                    "source_ids": [item["reference_id"] for item in references],
                }
            )
            content.estimated_characters = len(re.sub(r"\s|[#*\-]", "", content.body_markdown))
            self.last_fallback_used = False
            return content
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.last_fallback_used = False
            raise RuntimeError("多模态主模型未能生成有效文化内容") from exc

    @staticmethod
    def _public_visual_analysis(evolution: EvolutionPackage) -> dict[str, object] | None:
        analysis = evolution.visual_analysis
        if analysis is None:
            return None
        script_by_image = {
            observation.image_id: observation.script_type
            for observation in analysis.stage_observations
        }
        return {
            "stage_observations": [
                {
                    "script_type": observation.script_type,
                    "visible_features": observation.visible_features,
                    "composition": observation.composition,
                    "stroke_form": observation.stroke_form,
                }
                for observation in analysis.stage_observations
            ],
            "comparisons": [
                {
                    "from_script_type": script_by_image.get(comparison.from_image_id, "前一阶段"),
                    "to_script_type": script_by_image.get(comparison.to_image_id, "后一阶段"),
                    "visible_changes": comparison.visible_changes,
                    "summary": comparison.summary,
                }
                for comparison in analysis.comparisons
            ],
            "overall_summary": analysis.overall_summary,
            "warnings": analysis.warnings,
        }

    @staticmethod
    def _public_reference_materials(
        evolution: EvolutionPackage, limit: int, content_limit: int
    ) -> list[dict[str, object]]:
        materials: list[dict[str, object]] = []
        for item in _generation_evidence(evolution):
            materials.append(
                {
                    "reference_id": item.evidence_id,
                    "evidence_id": item.evidence_id,
                    "title": item.title,
                    "author_or_org": item.author_or_org,
                    "publication_date": item.publication_date,
                    "locator": item.locator,
                    "url": item.url,
                    "content": item.quote_or_summary[:content_limit],
                    "origin": item.origin.value,
                }
            )
            if len(materials) >= limit:
                break
        return materials

    @staticmethod
    def _public_stage_description(value: str) -> str:
        internal_markers = (
            "jiezi",
            "元数据",
            "原始路径",
            "image_id",
            "u+",
        )
        return "" if any(marker in value.lower() for marker in internal_markers) else value

    async def _json_completion(self, system: str, payload: object) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    "temperature": 0,
                    "enable_thinking": False,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("模型未返回 JSON 文本")
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise TypeError("模型返回的顶层结构不是对象")
        return parsed
