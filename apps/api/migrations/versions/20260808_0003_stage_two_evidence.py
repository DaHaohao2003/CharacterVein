"""Create stage-two evidence, claim binding, and audit tables.

Revision ID: 20260808_0003
Revises: 20260807_0002
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260808_0003"
down_revision: str | None = "20260807_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("retrieval_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("audit_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author_org", sa.Text(), nullable=False),
        sa.Column("publication_date", sa.String(length=128), nullable=True),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("authority_level", sa.String(length=1), nullable=False),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sources_source_type"), "sources", ["source_type"], unique=False)
    op.create_table(
        "evidence_chunks",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("source_id", sa.String(length=96), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evidence_chunks_source_id"), "evidence_chunks", ["source_id"], unique=False
    )
    op.create_table(
        "claims",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=96), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(length=64), nullable=False),
        sa.Column("evidence_grade", sa.String(length=1), nullable=False),
        sa.Column("has_conflict", sa.Boolean(), nullable=False),
        sa.Column("audit_status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "claim_id"),
    )
    op.create_index(op.f("ix_claims_audit_status"), "claims", ["audit_status"], unique=False)
    op.create_table(
        "claim_evidence",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=96), nullable=False),
        sa.Column("evidence_id", sa.String(length=96), nullable=False),
        sa.Column("support_type", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_chunks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["task_id", "claim_id"],
            ["claims.task_id", "claims.claim_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_id", "claim_id", "evidence_id"),
    )
    op.create_table(
        "audit_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("issues", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_runs_task_id"), "audit_runs", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_runs_task_id"), table_name="audit_runs")
    op.drop_table("audit_runs")
    op.drop_table("claim_evidence")
    op.drop_index(op.f("ix_claims_audit_status"), table_name="claims")
    op.drop_table("claims")
    op.drop_index(op.f("ix_evidence_chunks_source_id"), table_name="evidence_chunks")
    op.drop_table("evidence_chunks")
    op.drop_index(op.f("ix_sources_source_type"), table_name="sources")
    op.drop_table("sources")
    op.drop_column("tasks", "audit_report")
    op.drop_column("tasks", "retrieval_summary")
