from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from character_vein_domain import EvidenceSearchQuery, RetrievedEvidence, SourceOrigin
from character_vein_retrieval.hybrid import EvidenceRetriever


@dataclass(frozen=True)
class EvidenceSearchContext:
    task_id: str
    asset_ids: list[str] = field(default_factory=list)
    attempt: int = 1


@dataclass
class EvidenceProviderResult:
    candidates: list[RetrievedEvidence]
    available: bool = True
    reused_snapshot: bool = False
    message: str = ""


class EvidenceProvider(Protocol):
    name: str
    origin: SourceOrigin

    async def search(
        self,
        query: EvidenceSearchQuery,
        context: EvidenceSearchContext,
        *,
        limit: int,
    ) -> EvidenceProviderResult: ...


class FixtureEvidenceProvider:
    """Explicit test/dev adapter. It is never selected by the production API."""

    name = "fixture"
    origin = SourceOrigin.FIXTURE

    def __init__(self, retriever: EvidenceRetriever) -> None:
        self.retriever = retriever

    async def search(
        self,
        query: EvidenceSearchQuery,
        context: EvidenceSearchContext,
        *,
        limit: int,
    ) -> EvidenceProviderResult:
        candidates = await self.retriever.retrieve(
            query.query,
            limit,
            character=query.character,
            script_type=query.script_type,
            historical_period=query.historical_period,
            topic=query.topic,
        )
        return EvidenceProviderResult(candidates=candidates, reused_snapshot=True)
