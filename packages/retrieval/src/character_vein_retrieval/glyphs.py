from typing import Protocol

from character_vein_domain import RetrievedGlyphImage


class GlyphImageRetriever(Protocol):
    async def retrieve(
        self,
        query: str,
        *,
        character: str,
        script_code: str,
        limit: int = 4,
    ) -> list[RetrievedGlyphImage]: ...
