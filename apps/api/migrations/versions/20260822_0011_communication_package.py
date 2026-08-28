"""Persist cultural motif and versioned cross-media communication assets.

Revision ID: 20260822_0011
Revises: 20260822_0010
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260822_0011"
down_revision: str | None = "20260822_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "cultural_motif",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "communication_assets",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "artifact_evaluation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_table(
        "communication_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "content_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "reference_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "visual_hook_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("context_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "evaluation_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["communication_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "asset_type",
            "version",
            name="uq_communication_assets_task_type_version",
        ),
    )
    op.create_index(
        op.f("ix_communication_assets_task_id"),
        "communication_assets",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_communication_assets_asset_type"),
        "communication_assets",
        ["asset_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_communication_assets_context_hash"),
        "communication_assets",
        ["context_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_communication_assets_status"),
        "communication_assets",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_communication_assets_status"), table_name="communication_assets")
    op.drop_index(op.f("ix_communication_assets_context_hash"), table_name="communication_assets")
    op.drop_index(op.f("ix_communication_assets_asset_type"), table_name="communication_assets")
    op.drop_index(op.f("ix_communication_assets_task_id"), table_name="communication_assets")
    op.drop_table("communication_assets")
    op.drop_column("tasks", "artifact_evaluation")
    op.drop_column("tasks", "communication_assets")
    op.drop_column("tasks", "cultural_motif")
