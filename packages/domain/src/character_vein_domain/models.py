from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TaskStatus(StrEnum):
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    RUNNING = "running"
    AWAITING_ROUTE_SELECTION = "awaiting_route_selection"
    COMPLETED = "completed"
    PARTIAL_COMPLETE = "partial_complete"
    FAILED = "failed"


class ClaimType(StrEnum):
    LITERATURE_FACT = "literature_fact"
    MAINSTREAM_INTERPRETATION = "mainstream_interpretation"
    OTHER_VIEW = "other_view"
    SYSTEM_SYNTHESIS = "system_synthesis"
    POPULAR_EXPLANATION = "popular_explanation"


class AuditStatus(StrEnum):
    APPROVED = "approved"
    DOWNGRADED = "downgraded"
    DISPUTED = "disputed"
    REJECTED = "rejected"


class SourceOrigin(StrEnum):
    WEB = "web"
    USER_UPLOAD = "user_upload"
    FIXTURE = "fixture"


class EvidenceUsability(StrEnum):
    USABLE = "usable"
    PARTIAL = "partial"
    METADATA_ONLY = "metadata_only"
    UNUSABLE = "unusable"


class SupportType(StrEnum):
    SUPPORTS = "supports"
    PARTIALLY_SUPPORTS = "partially_supports"
    CONTRADICTS = "contradicts"
    CONTEXT_ONLY = "context_only"


class AssetKind(StrEnum):
    IMAGE = "image"
    DOCUMENT = "document"


class AssetOrigin(StrEnum):
    USER_UPLOAD = "user_upload"


class AssetStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class GlyphAvailability(StrEnum):
    AVAILABLE = "available"
    DATASET_GAP = "dataset_gap"


class GlyphLineageRole(StrEnum):
    MAINLINE = "mainline"
    BRANCH = "branch"
    TRANSITION = "transition"


class CommunicationChannel(StrEnum):
    INTERACTIVE_PAGE = "interactive_page"
    SOCIAL_CARDS = "social_cards"
    SHORT_VIDEO_60S = "short_video_60s"


class CommunicationDeliverable(StrEnum):
    INTERACTIVE_STORY = "interactive_story"
    FIVE_CARDS = "five_cards"
    VIDEO_SCRIPT = "video_script"


class AgentAction(StrEnum):
    SEARCH_MORE = "SEARCH_MORE"
    REWRITE_QUERY = "REWRITE_QUERY"
    RESELECT_GLYPH = "RESELECT_GLYPH"
    BUILD_NARRATIVES = "BUILD_NARRATIVES"
    REWRITE_ASSET = "REWRITE_ASSET"
    ASK_USER = "ASK_USER"
    FINISH = "FINISH"


class AgentPhase(StrEnum):
    MATERIAL_EXPLORATION = "material_exploration"
    GLYPH_EXPLORATION = "glyph_exploration"
    NARRATIVE_BUILD = "narrative_build"
    ASSET_EVALUATION = "asset_evaluation"


class CommunicationAssetType(StrEnum):
    INTERACTIVE_STORY = "interactive_story"
    SOCIAL_CARDS = "social_cards"
    SHORT_VIDEO_SCRIPT = "short_video_script"


class CommunicationBrief(BaseModel):
    target_characters: list[str] = Field(default_factory=list, max_length=4)
    communication_goal: str = Field(default="传播汉字文化故事", min_length=2, max_length=500)
    theme: str = "汉字演化与文化"
    audience: str = "年轻文化兴趣用户"
    channels: list[CommunicationChannel] = Field(
        default_factory=lambda: [CommunicationChannel.INTERACTIVE_PAGE],
        min_length=1,
    )
    tone: list[str] = Field(default_factory=lambda: ["有文化感", "清晰易懂"])
    duration_seconds: int = Field(default=60, ge=15, le=1800)
    deliverables: list[CommunicationDeliverable] = Field(
        default_factory=lambda: [CommunicationDeliverable.INTERACTIVE_STORY],
        min_length=1,
    )
    required_stages: int = Field(default=3, ge=1, le=10)
    interaction_count: int = Field(default=2, ge=0, le=10)
    success_criteria: list[str] = Field(
        default_factory=lambda: ["真实字形图片进入叙事", "表达适合目标受众"]
    )
    language: str = "zh-CN"
    constraints: list[str] = Field(default_factory=list)
    source_contexts: list[str] = Field(default_factory=list)
    target_needs_confirmation: bool = False
    web_search_enabled: bool = True

    @model_validator(mode="after")
    def normalize_collections(self) -> "CommunicationBrief":
        self.target_characters = list(dict.fromkeys(self.target_characters))
        self.channels = list(dict.fromkeys(self.channels))
        self.deliverables = list(dict.fromkeys(self.deliverables))
        self.tone = list(dict.fromkeys(item.strip() for item in self.tone if item.strip()))
        self.success_criteria = list(
            dict.fromkeys(item.strip() for item in self.success_criteria if item.strip())
        )
        self.constraints = list(
            dict.fromkeys(item.strip() for item in self.constraints if item.strip())
        )
        return self


class ExplorationBudget(BaseModel):
    search_decisions_remaining: int = Field(default=3, ge=0, le=10)
    glyph_reselections_remaining: int = Field(default=2, ge=0, le=10)
    asset_rewrites_remaining: int = Field(default=1, ge=0, le=5)

    def can_execute(self, action: AgentAction) -> bool:
        if action in {AgentAction.SEARCH_MORE, AgentAction.REWRITE_QUERY}:
            return self.search_decisions_remaining > 0
        if action == AgentAction.RESELECT_GLYPH:
            return self.glyph_reselections_remaining > 0
        if action == AgentAction.REWRITE_ASSET:
            return self.asset_rewrites_remaining > 0
        return True

    def consume(self, action: AgentAction) -> "ExplorationBudget":
        if not self.can_execute(action):
            raise ValueError(f"动作 {action.value} 已超过预算")
        updated = self.model_copy(deep=True)
        if action in {AgentAction.SEARCH_MORE, AgentAction.REWRITE_QUERY}:
            updated.search_decisions_remaining -= 1
        elif action == AgentAction.RESELECT_GLYPH:
            updated.glyph_reselections_remaining -= 1
        elif action == AgentAction.REWRITE_ASSET:
            updated.asset_rewrites_remaining -= 1
        return updated


class AgentDecisionContext(BaseModel):
    phase: AgentPhase
    reference_count: int = Field(default=0, ge=0)
    glyph_count: int = Field(default=0, ge=0)
    visual_observation_count: int = Field(default=0, ge=0)
    narrative_route_count: int = Field(default=0, ge=0)
    unmet_criteria: list[str] = Field(default_factory=list)


class AgentDecision(BaseModel):
    action: AgentAction
    reason_code: str = Field(min_length=2, max_length=80)
    decision_summary: str = Field(min_length=2, max_length=500)
    gap: str | None = Field(default=None, max_length=500)
    query: str | None = Field(default=None, max_length=500)
    target_asset: str | None = Field(default=None, max_length=100)


class VisualHook(BaseModel):
    image_id: str
    script_type: str
    role: Literal["opening", "comparison", "transition", "interaction"]
    prompt: str = Field(min_length=2, max_length=500)


class NarrativeRoute(BaseModel):
    route_id: str
    title: str = Field(min_length=2, max_length=100)
    core_message: str = Field(min_length=2, max_length=500)
    opening_hook: str = Field(min_length=2, max_length=500)
    visual_hooks: list[VisualHook] = Field(default_factory=list)
    story_beats: list[str] = Field(default_factory=list, min_length=2, max_length=8)
    contemporary_connection: str = Field(default="", max_length=500)
    recommended_channels: list[CommunicationChannel] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_route(self) -> "NarrativeRoute":
        self.story_beats = list(
            dict.fromkeys(item.strip() for item in self.story_beats if item.strip())
        )
        self.reference_ids = list(dict.fromkeys(self.reference_ids))
        self.recommended_channels = list(dict.fromkeys(self.recommended_channels))
        return self


class CulturalMotif(BaseModel):
    source_route_id: str = Field(default="", max_length=100)
    title: str = Field(min_length=2, max_length=100)
    core_message: str = Field(min_length=2, max_length=500)
    opening_hook: str = Field(default="", max_length=500)
    visual_sequence: list[VisualHook] = Field(default_factory=list)
    story_beats: list[str] = Field(default_factory=list, min_length=2, max_length=8)
    contemporary_connection: str = Field(default="", max_length=500)
    audience_promise: str = Field(default="", max_length=500)
    tone: list[str] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_motif(self) -> "CulturalMotif":
        self.story_beats = list(
            dict.fromkeys(item.strip() for item in self.story_beats if item.strip())
        )
        self.tone = list(dict.fromkeys(item.strip() for item in self.tone if item.strip()))
        self.reference_ids = list(dict.fromkeys(self.reference_ids))
        return self


class InteractiveStorySection(BaseModel):
    section_id: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=100)
    narrative: str = Field(min_length=10, max_length=3000)
    visual_hook_id: str | None = Field(default=None, max_length=160)
    interaction_prompt: str | None = Field(default=None, max_length=500)


class InteractiveStoryContent(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    lede: str = Field(min_length=10, max_length=1000)
    sections: list[InteractiveStorySection] = Field(min_length=3, max_length=8)
    closing: str = Field(min_length=10, max_length=1000)
    interaction_questions: list[str] = Field(default_factory=list, max_length=10)


class SocialCard(BaseModel):
    index: int = Field(ge=1, le=5)
    headline: str = Field(min_length=2, max_length=60)
    body: str = Field(min_length=10, max_length=800)
    visual_hook_id: str | None = Field(default=None, max_length=160)
    visual_direction: str = Field(min_length=2, max_length=500)


class SocialCardsContent(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    cards: list[SocialCard] = Field(min_length=5, max_length=5)
    posting_caption: str = Field(min_length=10, max_length=1000)

    @model_validator(mode="after")
    def validate_card_sequence(self) -> "SocialCardsContent":
        if [item.index for item in self.cards] != [1, 2, 3, 4, 5]:
            raise ValueError("图文卡片必须按 1 到 5 编号")
        return self


class VideoScene(BaseModel):
    start_second: int = Field(ge=0, le=59)
    end_second: int = Field(ge=1, le=60)
    visual: str = Field(min_length=2, max_length=500)
    narration: str = Field(min_length=2, max_length=800)
    subtitle: str = Field(min_length=1, max_length=200)
    visual_hook_id: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validate_time_range(self) -> "VideoScene":
        if self.end_second <= self.start_second:
            raise ValueError("分镜结束时间必须晚于开始时间")
        return self


class ShortVideoScriptContent(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    duration_seconds: Literal[60] = 60
    opening_hook: str = Field(min_length=2, max_length=300)
    scenes: list[VideoScene] = Field(min_length=4, max_length=10)
    closing_cta: str = Field(min_length=2, max_length=300)
    full_narration: str = Field(min_length=20, max_length=3000)

    @model_validator(mode="after")
    def validate_timeline(self) -> "ShortVideoScriptContent":
        if self.scenes[0].start_second != 0 or self.scenes[-1].end_second != 60:
            raise ValueError("60 秒视频分镜必须覆盖第 0 秒到第 60 秒")
        for previous, current in zip(self.scenes, self.scenes[1:], strict=False):
            if previous.end_second != current.start_second:
                raise ValueError("视频分镜时间必须连续且不得重叠")
        return self


class CommunicationAsset(BaseModel):
    asset_type: CommunicationAssetType
    version: int = Field(default=1, ge=1)
    content: InteractiveStoryContent | SocialCardsContent | ShortVideoScriptContent
    reference_ids: list[str] = Field(default_factory=list)
    visual_hook_ids: list[str] = Field(default_factory=list)
    status: Literal["generated", "needs_revision", "approved"] = "generated"

    @model_validator(mode="after")
    def validate_asset_content(self) -> "CommunicationAsset":
        self.reference_ids = list(dict.fromkeys(self.reference_ids))
        self.visual_hook_ids = list(dict.fromkeys(self.visual_hook_ids))
        if self.asset_type == CommunicationAssetType.INTERACTIVE_STORY:
            if not isinstance(self.content, InteractiveStoryContent):
                raise ValueError("interactive_story 的内容结构不匹配")
            content_hooks = {
                item.visual_hook_id for item in self.content.sections if item.visual_hook_id
            }
        elif self.asset_type == CommunicationAssetType.SOCIAL_CARDS:
            if not isinstance(self.content, SocialCardsContent):
                raise ValueError("social_cards 的内容结构不匹配")
            content_hooks = {
                item.visual_hook_id for item in self.content.cards if item.visual_hook_id
            }
        else:
            if not isinstance(self.content, ShortVideoScriptContent):
                raise ValueError("short_video_script 的内容结构不匹配")
            content_hooks = {
                item.visual_hook_id for item in self.content.scenes if item.visual_hook_id
            }
        if not content_hooks.issubset(self.visual_hook_ids):
            raise ValueError("成品内容引用了 visual_hook_ids 之外的图片")
        return self


class ConversationIntent(StrEnum):
    ANSWER = "answer"
    EXPLORE = "explore"
    CREATE = "create"
    REVISE = "revise"
    TRANSFORM = "transform"
    CLARIFY = "clarify"


class ConversationTurnPlan(BaseModel):
    intent: ConversationIntent
    action_summary: str = Field(min_length=2, max_length=300)
    artifact_type: str | None = Field(default=None, max_length=80)
    target_artifact_id: str | None = Field(default=None, max_length=36)
    needs_web_search: bool = False
    search_query: str | None = Field(default=None, max_length=500)
    needs_glyph_context: bool = False


class RichBlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    QUOTE = "quote"
    IMAGE = "image"
    CAPTION = "caption"


class RichContentBlock(BaseModel):
    block_id: str = Field(min_length=2, max_length=80)
    kind: RichBlockKind
    text: str = Field(default="", max_length=12000)
    level: int | None = Field(default=None, ge=1, le=3)
    image_id: str | None = Field(default=None, max_length=160)
    image_url: str | None = Field(default=None, max_length=500)
    alt_text: str = Field(default="", max_length=300)
    caption: str = Field(default="", max_length=500)
    source_kind: Literal["glyph", "generated", "upload"] | None = None
    locked: bool = False


class RichContentPage(BaseModel):
    page_id: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    layout: Literal["cover", "feature", "split", "text", "gallery"] = "text"
    blocks: list[RichContentBlock] = Field(default_factory=list, max_length=24)


RichExportFormat = Literal["docx", "html", "txt", "pdf", "pptx"]


def _default_rich_export_formats() -> list[RichExportFormat]:
    return ["docx", "html", "txt", "pdf", "pptx"]


class RichArtifactDocument(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    title: str = Field(min_length=2, max_length=200)
    theme: Literal["character-vein", "museum", "ink", "classroom", "minimal"] = "character-vein"
    pages: list[RichContentPage] = Field(min_length=1, max_length=40)
    supported_formats: list[RichExportFormat] = Field(default_factory=_default_rich_export_formats)


class CreativeArtifactDraft(BaseModel):
    artifact_type: str = Field(min_length=2, max_length=80)
    format_label: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=160)
    summary: str = Field(min_length=2, max_length=500)
    content_markdown: str = Field(min_length=10, max_length=30000)
    target_artifact_id: str | None = Field(default=None, max_length=36)
    reference_ids: list[str] = Field(default_factory=list)
    visual_hook_ids: list[str] = Field(default_factory=list)
    rich_document: RichArtifactDocument | None = None
    target_page_id: str | None = Field(default=None, max_length=80)
    target_block_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def normalize_artifact_references(self) -> "CreativeArtifactDraft":
        self.reference_ids = list(dict.fromkeys(self.reference_ids))
        self.visual_hook_ids = list(dict.fromkeys(self.visual_hook_ids))
        return self


class ConversationTurnOutput(BaseModel):
    intent: ConversationIntent
    assistant_message: str = Field(min_length=2, max_length=4000)
    action_summary: str = Field(min_length=2, max_length=300)
    workspace_view: Literal["conversation", "evolution", "sources", "artifact"] = "conversation"
    artifact: CreativeArtifactDraft | None = None

    @model_validator(mode="after")
    def require_artifact_for_creation_actions(self) -> "ConversationTurnOutput":
        if (
            self.intent
            in {
                ConversationIntent.CREATE,
                ConversationIntent.REVISE,
                ConversationIntent.TRANSFORM,
            }
            and self.artifact is None
        ):
            raise ValueError("创作、修改或转换操作必须返回作品")
        return self


class ArtifactEvaluation(BaseModel):
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    messages: list[str] = Field(default_factory=list)
    next_action: AgentAction = AgentAction.FINISH
    retry_targets: list[str] = Field(default_factory=list)


class AssetAnalysis(BaseModel):
    target_characters: list[str] = Field(default_factory=list)
    extracted_text: str = ""
    artifact_names: list[str] = Field(default_factory=list)
    explicit_periods: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    user_sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    uncertain_glyphs: bool = False
    requires_target_confirmation: bool = False
    model: str = "local"
    fallback_used: bool = False


class TaskSpec(BaseModel):
    target_characters: list[str] = Field(default_factory=list)
    theme: str = "汉字演化与文化"
    audience: str = "普通文化爱好者"
    duration_minutes: int = Field(default=4, ge=1, le=30)
    output_type: Literal["interactive_lesson", "culture_card", "article_outline"] = (
        "interactive_lesson"
    )
    required_stages: int = Field(default=3, ge=1, le=10)
    interaction_count: int = Field(default=2, ge=0, le=10)
    language: str = "zh-CN"
    constraints: list[str] = Field(default_factory=list)
    source_contexts: list[str] = Field(default_factory=list)
    target_needs_confirmation: bool = False
    web_search_enabled: bool = True
    communication_brief: CommunicationBrief | None = None


def communication_brief_from_task_spec(
    task_spec: TaskSpec,
    *,
    raw_input: str = "",
) -> CommunicationBrief:
    if task_spec.communication_brief is not None:
        return task_spec.communication_brief.model_copy(deep=True)
    channel = {
        "interactive_lesson": CommunicationChannel.INTERACTIVE_PAGE,
        "culture_card": CommunicationChannel.SOCIAL_CARDS,
        "article_outline": CommunicationChannel.INTERACTIVE_PAGE,
    }[task_spec.output_type]
    deliverable = {
        CommunicationChannel.INTERACTIVE_PAGE: CommunicationDeliverable.INTERACTIVE_STORY,
        CommunicationChannel.SOCIAL_CARDS: CommunicationDeliverable.FIVE_CARDS,
        CommunicationChannel.SHORT_VIDEO_60S: CommunicationDeliverable.VIDEO_SCRIPT,
    }[channel]
    return CommunicationBrief(
        target_characters=task_spec.target_characters,
        communication_goal=raw_input.strip() or f"围绕{task_spec.theme}进行汉字文化传播",
        theme=task_spec.theme,
        audience=task_spec.audience,
        channels=[channel],
        duration_seconds=task_spec.duration_minutes * 60,
        deliverables=[deliverable],
        required_stages=task_spec.required_stages,
        interaction_count=task_spec.interaction_count,
        language=task_spec.language,
        constraints=task_spec.constraints,
        source_contexts=task_spec.source_contexts,
        target_needs_confirmation=task_spec.target_needs_confirmation,
        web_search_enabled=task_spec.web_search_enabled,
    )


def task_spec_from_communication_brief(brief: CommunicationBrief) -> TaskSpec:
    output_type: Literal["interactive_lesson", "culture_card", "article_outline"] = (
        "culture_card"
        if brief.channels == [CommunicationChannel.SOCIAL_CARDS]
        else "interactive_lesson"
    )
    return TaskSpec(
        target_characters=brief.target_characters,
        theme=brief.theme,
        audience=brief.audience,
        duration_minutes=max(1, (brief.duration_seconds + 59) // 60),
        output_type=output_type,
        required_stages=brief.required_stages,
        interaction_count=brief.interaction_count,
        language=brief.language,
        constraints=brief.constraints,
        source_contexts=brief.source_contexts,
        target_needs_confirmation=brief.target_needs_confirmation,
        web_search_enabled=brief.web_search_enabled,
        communication_brief=brief,
    )


class PlanStep(BaseModel):
    id: str
    title: str
    agent: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    summary: str = ""
    tool_names: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    completion_criteria: str = ""
    failure_action: str = ""


class GlyphStage(BaseModel):
    stage_id: str
    character: str
    script_type: str
    script_code: str | None = Field(default=None, min_length=1, max_length=1)
    period: str
    approximate_date: str
    historical_period: str | None = None
    lineage_role: GlyphLineageRole = GlyphLineageRole.MAINLINE
    region_or_system: str | None = None
    sample_date: str | None = None
    image_url: str | None = None
    image_id: str | None = None
    source_id: str
    source_label: str
    source_path: str | None = None
    image_attribution: str | None = None
    source_url: str | None = None
    source_license: str | None = None
    availability: GlyphAvailability = GlyphAvailability.AVAILABLE
    variant_type: str = "representative"
    structure_description: str
    change_from_previous: str | None = None

    @model_validator(mode="after")
    def normalize_historical_metadata(self) -> "GlyphStage":
        # Backward-compatible defaults for evolution packages created before
        # historical period and single-sample dating were separated.
        if self.script_code is None:
            self.script_code = {
                "甲骨文": "J",
                "金文": "B",
                "战国文字": "G",
                "篆书": "S",
                "隶书": "L",
                "楷书": "K",
                "草书": "C",
            }.get(self.script_type)
        if self.historical_period is None:
            self.historical_period = self.period
        if self.sample_date is None:
            self.sample_date = self.approximate_date
        if self.availability == GlyphAvailability.DATASET_GAP and (self.image_url or self.image_id):
            raise ValueError("dataset_gap 阶段不得绑定字形图片或图片编号")
        return self


class GlyphCatalogStage(BaseModel):
    script_type: str
    script_code: str
    historical_period: str
    lineage_role: GlyphLineageRole
    region_or_system: str | None = None
    availability: GlyphAvailability
    metadata_path: str | None = None
    image_count: int = Field(ge=0)
    image_paths: list[str] = Field(default_factory=list)
    representative_source_path: str | None = None
    structure: str = ""
    special_structure: str = ""
    evolution: str = ""
    original_meaning: str = ""

    @model_validator(mode="after")
    def validate_catalog_stage(self) -> "GlyphCatalogStage":
        if self.image_count != len(self.image_paths):
            raise ValueError("image_count 必须与 image_paths 数量一致")
        if self.availability == GlyphAvailability.DATASET_GAP and (
            self.image_paths or self.representative_source_path or self.metadata_path
        ):
            raise ValueError("dataset_gap 分类不得绑定图片或元数据路径")
        return self


class GlyphCatalogEntry(BaseModel):
    character: str = Field(min_length=1, max_length=1)
    codepoint: str
    selection_tier: str
    available_script_count: int = Field(ge=0, le=7)
    total_image_count: int = Field(ge=0)
    stages: list[GlyphCatalogStage]

    @model_validator(mode="after")
    def validate_catalog_entry(self) -> "GlyphCatalogEntry":
        available = sum(stage.availability == GlyphAvailability.AVAILABLE for stage in self.stages)
        images = sum(stage.image_count for stage in self.stages)
        if available != self.available_script_count:
            raise ValueError("available_script_count 与分类数据不一致")
        if images != self.total_image_count:
            raise ValueError("total_image_count 与分类数据不一致")
        return self


class GlyphCatalog(BaseModel):
    dataset: str
    dataset_revision: str
    license: str
    selection_policy: dict[str, str | int | list[str]]
    coverage_summary: dict[str, int]
    total_selected_images: int = Field(ge=0)
    characters: list[GlyphCatalogEntry]

    @model_validator(mode="after")
    def validate_catalog(self) -> "GlyphCatalog":
        if self.total_selected_images != sum(item.total_image_count for item in self.characters):
            raise ValueError("total_selected_images 与字符目录不一致")
        return self


class Source(BaseModel):
    source_id: str
    source_type: str
    title: str
    author_or_org: str
    publication_date: str | None = None
    locator: str
    url: str | None = None
    authority_level: Literal["A", "B", "C", "D"]
    license: str
    is_available: bool = True
    origin: SourceOrigin = SourceOrigin.FIXTURE
    task_id: str | None = None
    asset_id: str | None = None
    retrieved_at: datetime | None = None


class Evidence(BaseModel):
    evidence_id: str
    source_id: str
    source_type: str
    title: str
    author_or_org: str
    publication_date: str | None = None
    quote_or_summary: str
    locator: str
    url: str | None = None
    authority_level: Literal["A", "B", "C", "D"]
    license: str
    keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    character: str | None = Field(default=None, min_length=1, max_length=1)
    script_type: str | None = None
    historical_period: str | None = None
    topic: str = "general"
    chunk_index: int = Field(default=0, ge=0)
    content_hash: str = ""
    origin: SourceOrigin = SourceOrigin.FIXTURE
    task_id: str | None = None
    asset_id: str | None = None
    usability: EvidenceUsability = EvidenceUsability.USABLE
    retrieved_at: datetime | None = None


class RetrievedEvidence(BaseModel):
    evidence: Evidence
    exact_score: float = Field(ge=0, le=1)
    keyword_score: float = Field(ge=0, le=1)
    semantic_score: float = Field(ge=-1, le=1)
    final_score: float
    structured_rank: int | None = Field(default=None, ge=1)
    keyword_rank: int | None = Field(default=None, ge=1)
    semantic_rank: int | None = Field(default=None, ge=1)
    rrf_score: float = Field(default=0, ge=0)


class EvidenceSearchQuery(BaseModel):
    query_id: str
    query: str
    purpose: str
    character: str = Field(min_length=1, max_length=1)
    script_type: str | None = None
    historical_period: str | None = None
    topic: str | None = None


class ToolCall(BaseModel):
    tool_call_id: str
    tool_name: str
    status: Literal["running", "completed", "failed"]
    input_summary: str
    result_summary: str = ""
    result_count: int = Field(default=0, ge=0)
    duration_ms: float = Field(default=0, ge=0)
    attempt: int = Field(default=1, ge=1)
    error: str | None = None
    provider: str = "internal"


class RetrievedGlyphImage(BaseModel):
    image_id: str
    character: str = Field(min_length=1, max_length=1)
    codepoint: str
    script_type: str
    script_code: str = Field(min_length=1, max_length=1)
    historical_period: str
    lineage_role: GlyphLineageRole
    region_or_system: str | None = None
    source_path: str
    mime_type: str
    sha256: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = Field(ge=-1, le=1)
    content_url: str


class GlyphRetrievalSummary(BaseModel):
    character: str = Field(min_length=1, max_length=1)
    script_type: str
    script_code: str = Field(min_length=1, max_length=1)
    query: str
    candidate_count: int = Field(ge=0)
    selected_image_id: str | None = None
    selected_score: float | None = Field(default=None, ge=-1, le=1)


class GlyphStageVisualObservation(BaseModel):
    image_id: str
    script_type: str
    visible_features: list[str] = Field(default_factory=list, max_length=8)
    composition: str = ""
    stroke_form: str = ""


class GlyphVisualComparison(BaseModel):
    from_image_id: str
    to_image_id: str
    visible_changes: list[str] = Field(default_factory=list, max_length=8)
    summary: str = ""


class GlyphVisualAnalysis(BaseModel):
    character: str = Field(min_length=1, max_length=1)
    stage_observations: list[GlyphStageVisualObservation] = Field(default_factory=list)
    comparisons: list[GlyphVisualComparison] = Field(default_factory=list)
    overall_summary: str = ""
    warnings: list[str] = Field(default_factory=list)
    model: str
    fallback_used: bool = False


class ClaimEvidenceRelation(BaseModel):
    evidence_id: str
    support_type: SupportType = SupportType.SUPPORTS


class Claim(BaseModel):
    claim_id: str
    content: str
    claim_type: ClaimType
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_grade: Literal["A", "B", "C", "D"]
    has_conflict: bool = False
    audit_status: AuditStatus = AuditStatus.APPROVED
    claim_origin: Literal["evidence_derived", "hypothesis", "system_synthesis"] = "evidence_derived"
    evidence_relations: list[ClaimEvidenceRelation] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_evidence_relations(self) -> "Claim":
        # Older persisted tasks only have evidence_ids. Preserve readability while new
        # tasks store the explicit support relationship used by the audit rules.
        if not self.evidence_relations and self.evidence_ids:
            self.evidence_relations = [
                ClaimEvidenceRelation(evidence_id=item) for item in self.evidence_ids
            ]
        elif self.evidence_relations:
            self.evidence_ids = list(
                dict.fromkeys(item.evidence_id for item in self.evidence_relations)
            )
        return self


class ClaimAuditResult(BaseModel):
    claim_id: str
    status: AuditStatus
    reason: str
    supported_evidence_ids: list[str] = Field(default_factory=list)


class AuditIssue(BaseModel):
    issue_code: str
    claim_id: str | None = None
    message: str
    severity: Literal["info", "warning", "error"]
    action: Literal["none", "retry_retrieval", "downgrade", "reject"]
    retryable: bool = False


class AuditReport(BaseModel):
    status: Literal["approved", "needs_retry", "partial"]
    claim_results: list[ClaimAuditResult]
    issues: list[AuditIssue] = Field(default_factory=list)
    model: str
    prompt_version: str = "reference-check-v1"
    attempt: int = Field(default=1, ge=1)
    fallback_used: bool = False
    summary: str

    @property
    def approved(self) -> bool:
        return self.status == "approved"


class EvolutionPackage(BaseModel):
    character: str
    sources: list[Source]
    glyph_stages: list[GlyphStage]
    shape_changes: list[str]
    meaning_changes: list[str]
    cultural_contexts: list[str]
    claims: list[Claim]
    evidence: list[Evidence]
    controversies: list[str] = Field(default_factory=list)
    audit_summary: dict[str, int | str]
    visual_analysis: GlyphVisualAnalysis | None = None


class RetrievalSummary(BaseModel):
    query_id: str = "general"
    query: str
    purpose: str = ""
    candidate_count: int
    selected_count: int
    structured_matches: int = 0
    exact_matches: int
    keyword_matches: int
    semantic_matches: int
    channel_candidate_counts: dict[str, int] = Field(default_factory=dict)
    attempt: int = 1


class GeneratedContent(BaseModel):
    title: str
    audience: str
    duration_minutes: int
    outline: list[str]
    body_markdown: str
    interaction_questions: list[str]
    source_ids: list[str]
    estimated_characters: int


class ConstraintResult(BaseModel):
    passed: bool
    checks: dict[str, bool]
    messages: list[str]
