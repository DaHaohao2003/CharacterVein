"""Create immutable propagation content versions.

Revision ID: 20260808_0005
Revises: 20260808_0004
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260808_0005"
down_revision: str | None = "20260808_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("current_content_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "content_versions",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("spec_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("constraints_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("parent_version", sa.Integer(), nullable=True),
        sa.Column("evolution_hash", sa.String(length=64), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "version"),
    )
    op.create_index(
        op.f("ix_content_versions_origin"), "content_versions", ["origin"], unique=False
    )
    op.create_index(
        op.f("ix_content_versions_evolution_hash"),
        "content_versions",
        ["evolution_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_content_versions_evolution_hash"), table_name="content_versions")
    op.drop_index(op.f("ix_content_versions_origin"), table_name="content_versions")
    op.drop_table("content_versions")
    op.drop_column("tasks", "current_content_version")
