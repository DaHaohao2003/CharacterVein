"""Add task-scoped evidence snapshots and explicit source origin.

Revision ID: 20260816_0009
Revises: 20260809_0008
Create Date: 2026-08-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260816_0009"
down_revision: str | None = "20260809_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("origin", sa.String(length=32), server_default="fixture", nullable=False),
    )
    op.add_column("sources", sa.Column("task_id", sa.String(length=36), nullable=True))
    op.add_column("sources", sa.Column("asset_id", sa.String(length=36), nullable=True))
    op.add_column("sources", sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_sources_task_id", "sources", "tasks", ["task_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_sources_asset_id", "sources", "assets", ["asset_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_sources_origin", "sources", ["origin"])
    op.create_index("ix_sources_task_id", "sources", ["task_id"])
    op.create_index("ix_sources_asset_id", "sources", ["asset_id"])

    op.add_column("evidence_chunks", sa.Column("task_id", sa.String(length=36), nullable=True))
    op.add_column("evidence_chunks", sa.Column("asset_id", sa.String(length=36), nullable=True))
    op.add_column(
        "evidence_chunks",
        sa.Column("usability", sa.String(length=32), server_default="usable", nullable=False),
    )
    op.add_column(
        "evidence_chunks", sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_evidence_chunks_task_id",
        "evidence_chunks",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_evidence_chunks_asset_id",
        "evidence_chunks",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_evidence_chunks_task_id", "evidence_chunks", ["task_id"])
    op.create_index("ix_evidence_chunks_asset_id", "evidence_chunks", ["asset_id"])
    op.create_index("ix_evidence_chunks_usability", "evidence_chunks", ["usability"])

    op.add_column(
        "claims",
        sa.Column(
            "claim_origin",
            sa.String(length=32),
            server_default="evidence_derived",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("claims", "claim_origin")
    op.drop_index("ix_evidence_chunks_usability", table_name="evidence_chunks")
    op.drop_index("ix_evidence_chunks_asset_id", table_name="evidence_chunks")
    op.drop_index("ix_evidence_chunks_task_id", table_name="evidence_chunks")
    op.drop_constraint("fk_evidence_chunks_asset_id", "evidence_chunks", type_="foreignkey")
    op.drop_constraint("fk_evidence_chunks_task_id", "evidence_chunks", type_="foreignkey")
    op.drop_column("evidence_chunks", "retrieved_at")
    op.drop_column("evidence_chunks", "usability")
    op.drop_column("evidence_chunks", "asset_id")
    op.drop_column("evidence_chunks", "task_id")
    op.drop_index("ix_sources_asset_id", table_name="sources")
    op.drop_index("ix_sources_task_id", table_name="sources")
    op.drop_index("ix_sources_origin", table_name="sources")
    op.drop_constraint("fk_sources_asset_id", "sources", type_="foreignkey")
    op.drop_constraint("fk_sources_task_id", "sources", type_="foreignkey")
    op.drop_column("sources", "retrieved_at")
    op.drop_column("sources", "asset_id")
    op.drop_column("sources", "task_id")
    op.drop_column("sources", "origin")
