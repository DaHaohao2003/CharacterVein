from datetime import datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from character_vein_api.artifact_documents import build_rich_document
from character_vein_api.models import (
    AssetRecord,
    ClaimRecord,
    CommunicationAssetRecord,
    ContentVersionRecord,
    ConversationMessageRecord,
    CreativeArtifactRecord,
    GlyphImageRecord,
    TaskRecord,
    WorkflowEventRecord,
)
from character_vein_domain import (
    AssetAnalysis,
    CommunicationAsset,
    CommunicationBrief,
    ConstraintResult,
    ConversationIntent,
    CreativeArtifactDraft,
    CulturalMotif,
    GeneratedContent,
    RichArtifactDocument,
    TaskSpec,
    communication_brief_from_task_spec,
)


class CreateTaskRequest(BaseModel):
    raw_input: str = Field(min_length=2, max_length=4000)
    asset_ids: list[str] = Field(default_factory=list, max_length=20)
    web_search_enabled: bool = True


class ConfirmTaskRequest(BaseModel):
    spec: TaskSpec


class RegenerateContentRequest(BaseModel):
    audience: str | None = Field(default=None, min_length=2, max_length=100)
    duration_minutes: int | None = Field(default=None, ge=1, le=30)
    output_type: Literal["interactive_lesson", "culture_card", "article_outline"] | None = None
    interaction_count: int | None = Field(default=None, ge=0, le=10)
    mode: Literal["full", "body", "interactions"] = "full"


class UpdateContentRequest(BaseModel):
    content: GeneratedContent
    change_summary: str = Field(default="用户编辑传播内容", max_length=500)


class ExportContentRequest(BaseModel):
    format: Literal["markdown", "html", "json"]


class RegenerateCommunicationFragmentRequest(BaseModel):
    instruction: str = Field(min_length=2, max_length=500)


class ConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    active_artifact_id: str | None = Field(default=None, max_length=36)
    active_page_id: str | None = Field(default=None, max_length=80)
    active_block_id: str | None = Field(default=None, max_length=80)


class ConversationMessageResponse(BaseModel):
    id: str
    task_id: str
    role: Literal["user", "assistant"]
    content: str
    intent: ConversationIntent | None
    state: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_record(cls, record: ConversationMessageRecord) -> "ConversationMessageResponse":
        return cls(
            id=record.id,
            task_id=record.task_id,
            role=cast(Literal["user", "assistant"], record.role),
            content=record.content,
            intent=ConversationIntent(record.intent) if record.intent else None,
            state=record.state_json or {},
            created_at=record.created_at,
        )


class CreativeArtifactResponse(BaseModel):
    id: str
    task_id: str
    lineage_id: str
    parent_id: str | None
    artifact_type: str
    format_label: str
    title: str
    summary: str
    content_markdown: str
    rich_document: RichArtifactDocument
    version: int
    reference_ids: list[str]
    visual_hook_ids: list[str]
    status: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: CreativeArtifactRecord) -> "CreativeArtifactResponse":
        document = (
            RichArtifactDocument.model_validate(record.document_json)
            if record.document_json
            else build_rich_document(
                CreativeArtifactDraft(
                    artifact_type=record.artifact_type,
                    format_label=record.format_label,
                    title=record.title,
                    summary=record.summary,
                    content_markdown=record.content_markdown,
                    reference_ids=record.reference_ids or [],
                    visual_hook_ids=record.visual_hook_ids or [],
                )
            )
        )
        return cls(
            id=record.id,
            task_id=record.task_id,
            lineage_id=record.lineage_id,
            parent_id=record.parent_id,
            artifact_type=record.artifact_type,
            format_label=record.format_label,
            title=record.title,
            summary=record.summary,
            content_markdown=record.content_markdown,
            rich_document=document,
            version=record.version,
            reference_ids=record.reference_ids or [],
            visual_hook_ids=record.visual_hook_ids or [],
            status=record.status,
            created_at=record.created_at,
        )


class ConversationTurnResponse(BaseModel):
    intent: ConversationIntent
    action_summary: str
    workspace_view: Literal["conversation", "evolution", "sources", "artifact"]
    user_message: ConversationMessageResponse
    assistant_message: ConversationMessageResponse
    artifact: CreativeArtifactResponse | None
    tools_used: list[str] = Field(default_factory=list)


class TaskResponse(BaseModel):
    id: str
    status: str
    raw_input: str
    spec: TaskSpec
    communication_brief: CommunicationBrief
    plan: list[dict[str, Any]] | None
    search_queries: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    agent_runtime: dict[str, Any]
    narrative_routes: list[dict[str, Any]]
    selected_route_id: str | None
    cultural_motif: CulturalMotif | None
    communication_assets: dict[str, CommunicationAsset]
    artifact_evaluation: dict[str, Any] | None
    requires_user_confirmation: bool
    evolution_package: dict[str, Any] | None
    generated_content: dict[str, Any] | None
    constraint_result: dict[str, Any] | None
    retrieval_summary: list[dict[str, Any]] | None
    audit_report: dict[str, Any] | None
    input_asset_ids: list[str]
    current_content_version: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: TaskRecord) -> "TaskResponse":
        spec = TaskSpec.model_validate(record.spec)
        return cls(
            id=record.id,
            status=record.status,
            raw_input=record.raw_input,
            spec=spec,
            communication_brief=communication_brief_from_task_spec(
                spec, raw_input=record.raw_input
            ),
            plan=record.plan,
            search_queries=record.search_queries or [],
            tool_calls=record.tool_calls or [],
            agent_runtime=record.agent_runtime or {},
            narrative_routes=record.narrative_routes or [],
            selected_route_id=record.selected_route_id,
            cultural_motif=(
                CulturalMotif.model_validate(record.cultural_motif)
                if record.cultural_motif is not None
                else None
            ),
            communication_assets={
                key: CommunicationAsset.model_validate(value)
                for key, value in (record.communication_assets or {}).items()
            },
            artifact_evaluation=record.artifact_evaluation,
            requires_user_confirmation=record.requires_user_confirmation or False,
            evolution_package=record.evolution_package,
            generated_content=record.generated_content,
            constraint_result=record.constraint_result,
            retrieval_summary=record.retrieval_summary,
            audit_report=record.audit_report,
            input_asset_ids=record.input_asset_ids or [],
            current_content_version=record.current_content_version or 0,
            error_message=record.error_message,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class ContentVersionResponse(BaseModel):
    task_id: str
    version: int
    content: GeneratedContent
    spec: TaskSpec
    constraints: ConstraintResult
    origin: str
    parent_version: int | None
    evolution_hash: str
    change_summary: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: ContentVersionRecord) -> "ContentVersionResponse":
        return cls(
            task_id=record.task_id,
            version=record.version,
            content=GeneratedContent.model_validate(record.content_json),
            spec=TaskSpec.model_validate(record.spec_json),
            constraints=ConstraintResult.model_validate(record.constraints_json),
            origin=record.origin,
            parent_version=record.parent_version,
            evolution_hash=record.evolution_hash,
            change_summary=record.change_summary,
            created_at=record.created_at,
        )


class CommunicationAssetVersionResponse(BaseModel):
    id: str
    task_id: str
    asset_type: str
    version: int
    content: dict[str, Any]
    reference_ids: list[str]
    visual_hook_ids: list[str]
    parent_id: str | None
    context_hash: str
    status: str
    evaluation: dict[str, Any] | None
    created_at: datetime

    @classmethod
    def from_record(cls, record: CommunicationAssetRecord) -> "CommunicationAssetVersionResponse":
        return cls(
            id=record.id,
            task_id=record.task_id,
            asset_type=record.asset_type,
            version=record.version,
            content=record.content_json,
            reference_ids=record.reference_ids or [],
            visual_hook_ids=record.visual_hook_ids or [],
            parent_id=record.parent_id,
            context_hash=record.context_hash,
            status=record.status,
            evaluation=record.evaluation_json,
            created_at=record.created_at,
        )


class AssetResponse(BaseModel):
    id: str
    task_id: str | None
    origin: str
    kind: str
    status: str
    mime_type: str
    filename: str
    size_bytes: int
    sha256: str
    extracted_text: str
    analysis: AssetAnalysis
    error_message: str | None
    created_at: datetime

    @classmethod
    def from_record(cls, record: AssetRecord) -> "AssetResponse":
        return cls(
            id=record.id,
            task_id=record.task_id,
            origin=record.origin,
            kind=record.kind,
            status=record.status,
            mime_type=record.mime_type,
            filename=record.filename,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            extracted_text=record.extracted_text,
            analysis=AssetAnalysis.model_validate(record.analysis_json),
            error_message=record.error_message,
            created_at=record.created_at,
        )


class GlyphImageSearchResult(BaseModel):
    id: str
    character: str
    codepoint: str
    script_type: str
    script_code: str
    historical_period: str
    lineage_role: str
    region_or_system: str | None
    source_path: str
    mime_type: str
    size_bytes: int
    sha256: str
    metadata: dict[str, Any]
    score: float
    content_url: str

    @classmethod
    def from_record(cls, record: GlyphImageRecord, score: float) -> "GlyphImageSearchResult":
        return cls(
            id=record.id,
            character=record.character,
            codepoint=record.codepoint,
            script_type=record.script_type,
            script_code=record.script_code,
            historical_period=record.historical_period,
            lineage_role=record.lineage_role,
            region_or_system=record.region_or_system,
            source_path=record.source_path,
            mime_type=record.mime_type,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            metadata=record.metadata_json,
            score=score,
            content_url=f"/backend/api/v1/glyph-images/{record.id}",
        )


class WorkflowEventResponse(BaseModel):
    id: int
    step: str
    status: str
    summary: str
    payload: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_record(cls, record: WorkflowEventRecord) -> "WorkflowEventResponse":
        return cls(
            id=record.id,
            step=record.step,
            status=record.status,
            summary=record.summary,
            payload=record.payload,
            created_at=record.created_at,
        )


class ClaimResponse(BaseModel):
    task_id: str
    claim_id: str
    content: str
    claim_type: str
    evidence_grade: str
    has_conflict: bool
    audit_status: str
    claim_origin: str

    @classmethod
    def from_record(cls, record: ClaimRecord) -> "ClaimResponse":
        return cls(
            task_id=record.task_id,
            claim_id=record.claim_id,
            content=record.content,
            claim_type=record.claim_type,
            evidence_grade=record.evidence_grade,
            has_conflict=record.has_conflict,
            audit_status=record.audit_status,
            claim_origin=record.claim_origin,
        )


class ClaimEvidenceResponse(BaseModel):
    evidence_id: str
    source_id: str
    title: str
    author_or_org: str
    publication_date: str | None
    quote_or_summary: str
    locator: str
    url: str | None
    authority_level: str
    license: str
    support_type: str
    origin: str
    usability: str
    retrieved_at: datetime | None
    asset_id: str | None
