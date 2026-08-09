from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from character_vein_domain import GlyphCatalog, GlyphCatalogEntry

STAGE_CLASSIFICATION: dict[str, dict[str, str]] = {
    "甲骨文": {
        "historical_period": "商代文字",
        "lineage_role": "mainline",
        "region_or_system": "甲骨材料",
    },
    "金文": {
        "historical_period": "商周文字",
        "lineage_role": "mainline",
        "region_or_system": "青铜器铭文材料",
    },
    "战国文字": {
        "historical_period": "战国时期",
        "lineage_role": "mainline",
        "region_or_system": "地域未详",
    },
    "篆书": {
        "historical_period": "篆书阶段",
        "lineage_role": "mainline",
        "region_or_system": "来源未细分为秦小篆",
    },
    "隶书": {
        "historical_period": "隶变与隶书阶段",
        "lineage_role": "transition",
        "region_or_system": "来源未细分为秦隶或汉隶",
    },
    "楷书": {
        "historical_period": "汉魏以后",
        "lineage_role": "mainline",
        "region_or_system": "楷书主干",
    },
    "草书": {
        "historical_period": "汉代以后",
        "lineage_role": "branch",
        "region_or_system": "快速书写与书法支线",
    },
}


def default_selection_path() -> Path:
    configured = os.getenv("JIEZI_SELECTION_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4] / "data" / "jiezi" / "selection.json"


@lru_cache(maxsize=1)
def glyph_catalog() -> GlyphCatalog:
    path = default_selection_path()
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    for character in payload["characters"]:
        for stage in character["stages"]:
            stage.update(STAGE_CLASSIFICATION[stage["script_type"]])
    return GlyphCatalog.model_validate(payload)


def catalog_entry(character: str) -> GlyphCatalogEntry:
    normalized = "车" if character == "車" else character
    for item in glyph_catalog().characters:
        if item.character == normalized:
            return item
    raise ValueError(f"JieZi 精选目录尚未登记：{character}")


def selected_characters() -> tuple[str, ...]:
    return tuple(item.character for item in glyph_catalog().characters)
