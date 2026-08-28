import math
import re
from typing import Protocol

from character_vein_domain import Evidence, RetrievedEvidence, SourceOrigin
from character_vein_providers import DeterministicEmbeddingProvider, EmbeddingProvider


class EvidenceRetriever(Protocol):
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
    ) -> list[RetrievedEvidence]: ...


class InMemoryHybridRetriever:
    """Reference hybrid ranker used by tests and as a database-independent fallback."""

    def __init__(
        self,
        corpus: list[Evidence],
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.corpus = corpus
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
        corpus = [
            item
            for item in self.corpus
            if self._eligible(item, character, script_type, historical_period, topic)
            and (task_id is None or item.task_id == task_id)
            and (not origins or item.origin in origins)
        ]
        if not corpus:
            return []
        vectors = await self.embedding_provider.embed(
            [query, *[self._searchable(item) for item in corpus]]
        )
        query_vector, document_vectors = vectors[0], vectors[1:]
        query_terms = self._terms(query)
        scored: list[tuple[Evidence, float, float, bool]] = []
        for evidence, vector in zip(corpus, document_vectors, strict=True):
            searchable = self._searchable(evidence)
            document_terms = self._terms(searchable)
            overlap = query_terms & document_terms
            keyword_score = len(overlap) / max(len(query_terms), 1)
            semantic_score = sum(a * b for a, b in zip(query_vector, vector, strict=True))
            structured = bool(
                (character and evidence.character == character)
                or (script_type and evidence.script_type == script_type)
                or (historical_period and evidence.historical_period == historical_period)
                or (topic and evidence.topic == topic)
            )
            scored.append((evidence, keyword_score, semantic_score, structured))

        pool = max(limit * 3, 20)
        structured_rows = [item for item in scored if item[3]][:pool]
        keyword_rows = sorted(scored, key=lambda item: item[1], reverse=True)
        keyword_rows = [item for item in keyword_rows if item[1] > 0][:pool]
        semantic_rows = sorted(scored, key=lambda item: item[2], reverse=True)[:pool]
        structured_ranks = {
            item[0].evidence_id: rank for rank, item in enumerate(structured_rows, 1)
        }
        keyword_ranks = {item[0].evidence_id: rank for rank, item in enumerate(keyword_rows, 1)}
        semantic_ranks = {item[0].evidence_id: rank for rank, item in enumerate(semantic_rows, 1)}
        by_id = {item[0].evidence_id: item for item in scored}
        fused: list[RetrievedEvidence] = []
        max_rrf = 3 / 61
        for evidence_id in set(structured_ranks) | set(keyword_ranks) | set(semantic_ranks):
            evidence, keyword_score, semantic_score, _ = by_id[evidence_id]
            structured_rank = structured_ranks.get(evidence_id)
            keyword_rank = keyword_ranks.get(evidence_id)
            semantic_rank = semantic_ranks.get(evidence_id)
            rrf_score = sum(
                1 / (60 + rank)
                for rank in (structured_rank, keyword_rank, semantic_rank)
                if rank is not None
            )
            final_score = min(1.0, rrf_score / max_rrf)
            fused.append(
                RetrievedEvidence(
                    evidence=evidence,
                    exact_score=1.0 if structured_rank is not None else 0.0,
                    keyword_score=min(keyword_score, 1.0),
                    semantic_score=max(-1.0, min(semantic_score, 1.0)),
                    final_score=final_score,
                    structured_rank=structured_rank,
                    keyword_rank=keyword_rank,
                    semantic_rank=semantic_rank,
                    rrf_score=rrf_score,
                )
            )
        return sorted(fused, key=lambda item: item.final_score, reverse=True)[:limit]

    @staticmethod
    def _eligible(
        evidence: Evidence,
        character: str | None,
        script_type: str | None,
        historical_period: str | None,
        topic: str | None,
    ) -> bool:
        if character and evidence.character not in {None, character}:
            return False
        if script_type and evidence.script_type not in {None, script_type}:
            return False
        if historical_period and evidence.historical_period not in {None, historical_period}:
            return False
        return not topic or evidence.topic in {"framework", topic}

    @staticmethod
    def _searchable(evidence: Evidence) -> str:
        return " ".join(
            [
                evidence.title,
                evidence.quote_or_summary,
                evidence.locator,
                evidence.character or "",
                evidence.script_type or "",
                evidence.historical_period or "",
                evidence.topic,
                *evidence.keywords,
                *[str(value) for value in evidence.metadata.values()],
            ]
        )

    @staticmethod
    def _terms(text: str) -> set[str]:
        normalized = "".join(text.lower().split())
        latin = set(re.findall(r"[a-z0-9]+", normalized))
        han = re.findall(r"[\u4e00-\u9fff]", normalized)
        bigrams = {"".join(han[index : index + 2]) for index in range(len(han) - 1)}
        return latin | set(han) | bigrams


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0
