"""Persist controlled agent runtime and narrative route selection.

Revision ID: 20260822_0010
Revises: 20260816_0009
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260822_0010"
down_revision: str | None = "20260816_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "agent_runtime",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "narrative_routes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column("selected_route_id", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tasks", "selected_route_id")
    op.drop_column("tasks", "narrative_routes")
    op.drop_column("tasks", "agent_runtime")
