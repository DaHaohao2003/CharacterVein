"""Create the five-character glyph image RAG catalog.

Revision ID: 20260808_0007
Revises: 20260808_0006
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260808_0007"
down_revision: str | None = "20260808_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "glyph_images",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column("character", sa.String(length=1), nullable=False),
        sa.Column("codepoint", sa.String(length=16), nullable=False),
        sa.Column("script_type", sa.String(length=32), nullable=False),
        sa.Column("script_code", sa.String(length=1), nullable=False),
        sa.Column("historical_period", sa.String(length=96), nullable=False),
        sa.Column("lineage_role", sa.String(length=16), nullable=False),
        sa.Column("region_or_system", sa.String(length=160), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=False, unique=True),
        sa.Column("storage_key", sa.Text(), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("retrieval_text", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=1024), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_glyph_images_character_script",
        "glyph_images",
        ["character", "script_code"],
    )
    op.create_index("ix_glyph_images_sha256", "glyph_images", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_glyph_images_sha256", table_name="glyph_images")
    op.drop_index("ix_glyph_images_character_script", table_name="glyph_images")
    op.drop_table("glyph_images")
