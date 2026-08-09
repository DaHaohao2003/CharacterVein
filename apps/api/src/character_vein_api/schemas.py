from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from character_vein_api.models import (
    AssetRecord,
    ClaimRecord,
    ContentVersionRecord,
    GlyphImageRecord,
    TaskRecord,
    WorkflowEventRecord,
)
from character_vein_domain import AssetAnalysis, ConstraintResult, GeneratedContent, TaskSpec


class CreateTaskRequest(BaseModel):
    raw_input: str = Field(min_length=2, max_length=4000)
    asset_ids: list[str] = Field(default_factory=list, max_length=20)


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


class TaskResponse(BaseModel):
    id: str
    status: str
    raw_input: str
    spec: TaskSpec
    plan: list[dict[str, Any]] | None
    search_queries: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
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
        return cls(
            id=record.id,
            status=record.status,
            raw_input=record.raw_input,
            spec=TaskSpec.model_validate(record.spec),
            plan=record.plan,
            search_queries=record.search_queries or [],
            tool_calls=record.tool_calls or [],
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
