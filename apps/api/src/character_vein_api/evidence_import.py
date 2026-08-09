from __future__ import annotations

import asyncio
import json

from character_vein_api.config import get_settings
from character_vein_api.database import async_session_factory
from character_vein_api.model_providers import build_embedding_provider
from character_vein_api.repositories import EvidenceRepository
from character_vein_workflows.fixtures import all_demo_evidence_corpus, all_demo_sources


async def import_evidence_corpus() -> dict[str, int | str | bool]:
    sources = all_demo_sources()
    evidence = all_demo_evidence_corpus()
    embedding_provider = build_embedding_provider(get_settings())
    embeddings = await embedding_provider.embed([item.quote_or_summary for item in evidence])
    async with async_session_factory() as session:
        repository = EvidenceRepository(session)
        await repository.seed_corpus(sources, evidence, embeddings)
        stored = await repository.count()
    return {
        "sources": len(sources),
        "evidence": len(evidence),
        "stored": stored,
        "embedding_provider": type(embedding_provider).__name__,
        "embedding_requests": getattr(embedding_provider, "last_request_count", 0),
        "embedding_fallback": getattr(
            embedding_provider, "last_fallback_used", False
        ),
    }


def main() -> None:
    print(json.dumps(asyncio.run(import_evidence_corpus()), ensure_ascii=False))


if __name__ == "__main__":
    main()
