import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from character_vein_api.database import Base


class TaskRecord(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(32), index=True)
    raw_input: Mapped[str] = mapped_column(Text)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    plan: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    search_queries: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    agent_runtime: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    narrative_routes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    selected_route_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cultural_motif: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    communication_assets: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    artifact_evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    requires_user_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    evolution_package: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    generated_content: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    constraint_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    retrieval_summary: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    audit_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    input_asset_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    current_content_version: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkflowEventRecord(Base):
    __tablename__ = "workflow_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationMessageRecord(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), index=True)
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreativeArtifactRecord(Base):
    __tablename__ = "creative_artifacts"
    __table_args__ = (
        UniqueConstraint("lineage_id", "version", name="uq_creative_artifacts_lineage_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    lineage_id: Mapped[str] = mapped_column(String(36), index=True)
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("creative_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    request_message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True
    )
    artifact_type: Mapped[str] = mapped_column(String(80), index=True)
    format_label: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text)
    content_markdown: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)
    reference_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    visual_hook_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(32), default="generated", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssetRecord(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    origin: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    storage_key: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(128))
    filename: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    analysis_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceRecord(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(Text)
    author_org: Mapped[str] = mapped_column(Text)
    publication_date: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locator: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    authority_level: Mapped[str] = mapped_column(String(1))
    license: Mapped[str] = mapped_column(Text)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    origin: Mapped[str] = mapped_column(String(32), default="fixture", index=True)
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceChunkRecord(Base):
    __tablename__ = "evidence_chunks"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(96), ForeignKey("sources.id", ondelete="RESTRICT"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    locator: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    character: Mapped[str | None] = mapped_column(String(1), nullable=True, index=True)
    script_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    historical_period: Mapped[str | None] = mapped_column(String(96), nullable=True)
    topic: Mapped[str] = mapped_column(String(64), default="general", index=True)
    chunk_index: Mapped[int] = mapped_column(default=0)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    usability: Mapped[str] = mapped_column(String(32), default="usable", index=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_tokens: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GlyphImageRecord(Base):
    __tablename__ = "glyph_images"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    character: Mapped[str] = mapped_column(String(1), index=True)
    codepoint: Mapped[str] = mapped_column(String(16))
    script_type: Mapped[str] = mapped_column(String(32))
    script_code: Mapped[str] = mapped_column(String(1), index=True)
    historical_period: Mapped[str] = mapped_column(String(96))
    lineage_role: Mapped[str] = mapped_column(String(16))
    region_or_system: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_path: Mapped[str] = mapped_column(Text, unique=True)
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    mime_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    retrieval_text: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaimRecord(Base):
    __tablename__ = "claims"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    claim_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(64))
    evidence_grade: Mapped[str] = mapped_column(String(1))
    has_conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    audit_status: Mapped[str] = mapped_column(String(32), index=True)
    claim_origin: Mapped[str] = mapped_column(String(32), default="evidence_derived")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaimEvidenceRecord(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "claim_id"],
            ["claims.task_id", "claims.claim_id"],
            ondelete="CASCADE",
        ),
    )

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(
        String(96), ForeignKey("evidence_chunks.id", ondelete="RESTRICT"), primary_key=True
    )
    support_type: Mapped[str] = mapped_column(String(32), default="supports")


class AuditRunRecord(Base):
    __tablename__ = "audit_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    attempt: Mapped[int]
    status: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str] = mapped_column(Text)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentVersionRecord(Base):
    __tablename__ = "content_versions"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    spec_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    constraints_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    origin: Mapped[str] = mapped_column(String(32), index=True)
    parent_version: Mapped[int | None] = mapped_column(nullable=True)
    evolution_hash: Mapped[str] = mapped_column(String(64), index=True)
    change_summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommunicationAssetRecord(Base):
    __tablename__ = "communication_assets"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "asset_type",
            "version",
            name="uq_communication_assets_task_type_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    asset_type: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int]
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reference_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    visual_hook_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("communication_assets.id", ondelete="SET NULL"), nullable=True
    )
    context_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="generated", index=True)
    evaluation_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
