from fastapi import APIRouter, HTTPException, Query

from character_vein_domain import GlyphCatalogEntry
from character_vein_workflows.jiezi_catalog import catalog_entry, glyph_catalog

router = APIRouter(prefix="/glyphs", tags=["glyphs"])


@router.get("", response_model=list[GlyphCatalogEntry])
async def list_glyphs(
    all_scripts: bool = Query(default=False),
) -> list[GlyphCatalogEntry]:
    entries = glyph_catalog().characters
    if all_scripts:
        return [entry for entry in entries if entry.available_script_count == 7]
    return entries


@router.get("/{character}", response_model=GlyphCatalogEntry)
async def get_glyph(character: str) -> GlyphCatalogEntry:
    if len(character) != 1:
        raise HTTPException(status_code=404, detail="未登记该汉字")
    try:
        return catalog_entry(character)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
