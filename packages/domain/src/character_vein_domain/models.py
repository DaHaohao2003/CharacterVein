from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TaskStatus(StrEnum):
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    RUNNING = "running"
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
    REJECTED = "rejected"


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
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)
    character: str | None = Field(default=None, min_length=1, max_length=1)
    script_type: str | None = None
    historical_period: str | None = None
    topic: str = "general"
    chunk_index: int = Field(default=0, ge=0)
    content_hash: str = ""


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


class Claim(BaseModel):
    claim_id: str
    content: str
    claim_type: ClaimType
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_grade: Literal["A", "B", "C", "D"]
    has_conflict: bool = False
    audit_status: AuditStatus = AuditStatus.APPROVED


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
    prompt_version: str = "evidence-audit-v1"
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
