# ruff: noqa: E501
"""Attach attributed Hanziyuan images to existing Ding evolution packages.

Revision ID: 20260808_0006
Revises: 20260808_0005
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0006"
down_revision: str | None = "20260808_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH patched AS (
                SELECT
                    id,
                    jsonb_set(
                        jsonb_set(
                            evolution_package,
                            '{glyph_stages}',
                            (
                                SELECT jsonb_agg(
                                    CASE stage->>'stage_id'
                                        WHEN 'ding-oracle' THEN stage || jsonb_build_object(
                                            'image_url', '/glyphs/ding-oracle-j16953.svg',
                                            'image_id', 'J16953',
                                            'source_id', 'source-hanziyuan-ding',
                                            'source_label', '汉字字源网·甲骨文 J16953',
                                            'image_attribution', '字形图：汉字字源网 / Richard Sears'
                                        )
                                        WHEN 'ding-bronze' THEN stage || jsonb_build_object(
                                            'image_url', '/glyphs/ding-bronze-b10696.svg',
                                            'image_id', 'B10696',
                                            'source_id', 'source-hanziyuan-ding',
                                            'source_label', '汉字字源网·金文 B10696',
                                            'image_attribution', '字形图：汉字字源网 / Richard Sears'
                                        )
                                        WHEN 'ding-seal' THEN stage || jsonb_build_object(
                                            'image_url', '/glyphs/ding-seal-s04986.svg',
                                            'image_id', 'S04986',
                                            'source_id', 'source-hanziyuan-ding',
                                            'source_label', '汉字字源网·《说文》篆字 S04986',
                                            'image_attribution', '字形图：汉字字源网 / Richard Sears'
                                        )
                                        ELSE stage
                                    END
                                    ORDER BY ordinal
                                )
                                FROM jsonb_array_elements(
                                    COALESCE(evolution_package->'glyph_stages', '[]'::jsonb)
                                ) WITH ORDINALITY AS stages(stage, ordinal)
                            ),
                            true
                        ),
                        '{sources}',
                        CASE
                            WHEN EXISTS (
                                SELECT 1
                                FROM jsonb_array_elements(
                                    COALESCE(evolution_package->'sources', '[]'::jsonb)
                                ) AS source(item)
                                WHERE item->>'source_id' = 'source-hanziyuan-ding'
                            ) THEN COALESCE(evolution_package->'sources', '[]'::jsonb)
                            ELSE COALESCE(evolution_package->'sources', '[]'::jsonb) || jsonb_build_array(
                                jsonb_build_object(
                                    'source_id', 'source-hanziyuan-ding',
                                    'source_type', 'specialist_glyph_database',
                                    'title', '汉字字源网·鼎',
                                    'author_or_org', 'Richard Sears（汉字叔叔）',
                                    'publication_date', '检索于 2026-08-08',
                                    'locator', '鼎：甲骨文 J16953、金文 B10696、说文篆字 S04986',
                                    'url', 'https://hanziyuan.net/#鼎',
                                    'authority_level', 'B',
                                    'license', 'Copyright Richard Sears; educational display with attribution',
                                    'is_available', true
                                )
                            )
                        END,
                        true
                    ) AS package
                FROM tasks
                WHERE evolution_package->>'character' = '鼎'
            )
            UPDATE tasks AS task
            SET evolution_package = patched.package
            FROM patched
            WHERE task.id = patched.id
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH patched AS (
                SELECT
                    id,
                    jsonb_set(
                        jsonb_set(
                            evolution_package,
                            '{glyph_stages}',
                            (
                                SELECT jsonb_agg(
                                    CASE stage->>'stage_id'
                                        WHEN 'ding-oracle' THEN
                                            (stage - 'image_url' - 'image_id' - 'image_attribution') ||
                                            jsonb_build_object(
                                                'source_id', 'source-met-ding-61239',
                                                'source_label', '大都会艺术博物馆藏品 61239'
                                            )
                                        WHEN 'ding-bronze' THEN
                                            (stage - 'image_url' - 'image_id' - 'image_attribution') ||
                                            jsonb_build_object(
                                                'source_id', 'source-dpm-shiyifu-ding',
                                                'source_label', '故宫博物院·史宜父鼎'
                                            )
                                        WHEN 'ding-seal' THEN
                                            (stage - 'image_url' - 'image_id' - 'image_attribution') ||
                                            jsonb_build_object(
                                                'source_id', 'source-shuowen-ding',
                                                'source_label', '《说文解字》鼎部'
                                            )
                                        ELSE stage
                                    END
                                    ORDER BY ordinal
                                )
                                FROM jsonb_array_elements(
                                    COALESCE(evolution_package->'glyph_stages', '[]'::jsonb)
                                ) WITH ORDINALITY AS stages(stage, ordinal)
                            ),
                            true
                        ),
                        '{sources}',
                        COALESCE(
                            (
                                SELECT jsonb_agg(item ORDER BY ordinal)
                                FROM jsonb_array_elements(
                                    COALESCE(evolution_package->'sources', '[]'::jsonb)
                                ) WITH ORDINALITY AS source(item, ordinal)
                                WHERE item->>'source_id' <> 'source-hanziyuan-ding'
                            ),
                            '[]'::jsonb
                        ),
                        true
                    ) AS package
                FROM tasks
                WHERE evolution_package->>'character' = '鼎'
            )
            UPDATE tasks AS task
            SET evolution_package = patched.package
            FROM patched
            WHERE task.id = patched.id
            """
        )
    )
