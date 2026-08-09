"""Add auditable evidence metadata and agent execution state.

Revision ID: 20260809_0008
Revises: 20260808_0007
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260809_0008"
down_revision: str | None = "20260808_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence_chunks", sa.Column("character", sa.String(length=1), nullable=True))
    op.add_column("evidence_chunks", sa.Column("script_type", sa.String(length=32), nullable=True))
    op.add_column(
        "evidence_chunks",
        sa.Column("historical_period", sa.String(length=96), nullable=True),
    )
    op.add_column(
        "evidence_chunks",
        sa.Column("topic", sa.String(length=64), server_default="general", nullable=False),
    )
    op.add_column(
        "evidence_chunks",
        sa.Column("chunk_index", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "evidence_chunks",
        sa.Column("content_hash", sa.String(length=64), server_default="", nullable=False),
    )
    op.add_column(
        "evidence_chunks",
        sa.Column("search_tokens", sa.Text(), server_default="", nullable=False),
    )
    op.create_index(
        "ix_evidence_chunks_character_script",
        "evidence_chunks",
        ["character", "script_type"],
    )
    op.create_index("ix_evidence_chunks_topic", "evidence_chunks", ["topic"])
    op.create_index("ix_evidence_chunks_content_hash", "evidence_chunks", ["content_hash"])
    op.execute(
        "CREATE INDEX ix_evidence_chunks_search_tokens_fts "
        "ON evidence_chunks USING gin (to_tsvector('simple', search_tokens))"
    )

    op.add_column(
        "tasks",
        sa.Column(
            "search_queries",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "tool_calls",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "requires_user_confirmation", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "requires_user_confirmation")
    op.drop_column("tasks", "tool_calls")
    op.drop_column("tasks", "search_queries")
    op.execute("DROP INDEX IF EXISTS ix_evidence_chunks_search_tokens_fts")
    op.drop_index("ix_evidence_chunks_content_hash", table_name="evidence_chunks")
    op.drop_index("ix_evidence_chunks_topic", table_name="evidence_chunks")
    op.drop_index("ix_evidence_chunks_character_script", table_name="evidence_chunks")
    op.drop_column("evidence_chunks", "search_tokens")
    op.drop_column("evidence_chunks", "content_hash")
    op.drop_column("evidence_chunks", "chunk_index")
    op.drop_column("evidence_chunks", "topic")
    op.drop_column("evidence_chunks", "historical_period")
    op.drop_column("evidence_chunks", "script_type")
    op.drop_column("evidence_chunks", "character")
