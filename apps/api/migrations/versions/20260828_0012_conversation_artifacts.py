"""Add persistent agent conversation and open-ended creative artifacts.

Revision ID: 20260828_0012
Revises: 20260822_0011
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0012"
down_revision: str | None = "20260822_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=32), nullable=True),
        sa.Column(
            "state_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversation_messages_task_id"),
        "conversation_messages",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_messages_role"),
        "conversation_messages",
        ["role"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_messages_intent"),
        "conversation_messages",
        ["intent"],
        unique=False,
    )

    op.create_table(
        "creative_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("lineage_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("request_message_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_type", sa.String(length=80), nullable=False),
        sa.Column("format_label", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
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
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["creative_artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["request_message_id"], ["conversation_messages.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lineage_id", "version", name="uq_creative_artifacts_lineage_version"),
    )
    for column in ("task_id", "lineage_id", "artifact_type", "status"):
        op.create_index(
            op.f(f"ix_creative_artifacts_{column}"),
            "creative_artifacts",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in ("status", "artifact_type", "lineage_id", "task_id"):
        op.drop_index(op.f(f"ix_creative_artifacts_{column}"), table_name="creative_artifacts")
    op.drop_table("creative_artifacts")
    op.drop_index(op.f("ix_conversation_messages_intent"), table_name="conversation_messages")
    op.drop_index(op.f("ix_conversation_messages_role"), table_name="conversation_messages")
    op.drop_index(op.f("ix_conversation_messages_task_id"), table_name="conversation_messages")
    op.drop_table("conversation_messages")
