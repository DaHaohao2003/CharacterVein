from character_vein_api.repositories import EvidenceRepository, GlyphImageRepository
from character_vein_domain import (
    GlyphLineageRole,
    RetrievedEvidence,
    RetrievedGlyphImage,
    SourceOrigin,
)
from character_vein_providers import DeterministicEmbeddingProvider, EmbeddingProvider


class DatabaseEvidenceRetriever:
    def __init__(
        self,
        repository: EvidenceRepository,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider or DeterministicEmbeddingProvider()

    async def retrieve(
        self,
        query: str,
        limit: int = 8,
        *,
        character: str | None = None,
        script_type: str | None = None,
        historical_period: str | None = None,
        topic: str | None = None,
        task_id: str | None = None,
        origins: set[SourceOrigin] | None = None,
    ) -> list[RetrievedEvidence]:
        query_vector = (await self.embedding_provider.embed([query]))[0]
        return await self.repository.hybrid_search(
            query,
            query_vector,
            limit,
            character=character,
            script_type=script_type,
            historical_period=historical_period,
            topic=topic,
            task_id=task_id,
            origins=origins,
        )


class DatabaseGlyphImageRetriever:
    def __init__(
        self,
        repository: GlyphImageRepository,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider or DeterministicEmbeddingProvider()

    async def retrieve(
        self,
        query: str,
        *,
        character: str,
        script_code: str,
        limit: int = 4,
    ) -> list[RetrievedGlyphImage]:
        query_vector = (await self.embedding_provider.embed([query]))[0]
        rows = await self.repository.search(
            query_vector,
            character=character,
            script_code=script_code,
            limit=limit,
        )
        return [
            RetrievedGlyphImage(
                image_id=record.id,
                character=record.character,
                codepoint=record.codepoint,
                script_type=record.script_type,
                script_code=record.script_code,
                historical_period=record.historical_period,
                lineage_role=GlyphLineageRole(record.lineage_role),
                region_or_system=record.region_or_system,
                source_path=record.source_path,
                mime_type=record.mime_type,
                sha256=record.sha256,
                metadata=record.metadata_json,
                score=score,
                content_url=f"/backend/api/v1/glyph-images/{record.id}",
            )
            for record, score in rows
        ]
