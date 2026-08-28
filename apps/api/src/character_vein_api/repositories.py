import hashlib
import re
import uuid
from typing import Any, Literal, cast

from sqlalchemy import Table, and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from character_vein_api.models import (
    AssetRecord,
    AuditRunRecord,
    ClaimEvidenceRecord,
    ClaimRecord,
    CommunicationAssetRecord,
    ContentVersionRecord,
    ConversationMessageRecord,
    CreativeArtifactRecord,
    EvidenceChunkRecord,
    GlyphImageRecord,
    SourceRecord,
    TaskRecord,
    WorkflowEventRecord,
)
from character_vein_domain import (
    AuditReport,
    CommunicationAsset,
    ConversationIntent,
    CreativeArtifactDraft,
    Evidence,
    EvidenceUsability,
    EvolutionPackage,
    RetrievedEvidence,
    Source,
    SourceOrigin,
    TaskSpec,
    TaskStatus,
)


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, raw_input: str, spec: TaskSpec, input_asset_ids: list[str] | None = None
    ) -> TaskRecord:
        record = TaskRecord(
            status=TaskStatus.AWAITING_CONFIRMATION.value,
            raw_input=raw_input,
            spec=spec.model_dump(mode="json"),
            input_asset_ids=input_asset_ids or [],
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get(self, task_id: str) -> TaskRecord | None:
        return await self.session.get(TaskRecord, task_id)

    async def save(self, record: TaskRecord) -> TaskRecord:
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def add_event(
        self,
        task_id: str,
        step: str,
        status: str,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            WorkflowEventRecord(
                task_id=task_id,
                step=step,
                status=status,
                summary=summary,
                payload=payload or {},
            )
        )
        await self.session.commit()

    async def events(self, task_id: str) -> list[WorkflowEventRecord]:
        result = await self.session.scalars(
            select(WorkflowEventRecord)
            .where(WorkflowEventRecord.task_id == task_id)
            .order_by(WorkflowEventRecord.id)
        )
        return list(result)


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        task_id: str,
        role: str,
        content: str,
        intent: str | None = None,
        state: dict[str, Any] | None = None,
    ) -> ConversationMessageRecord:
        record = ConversationMessageRecord(
            task_id=task_id,
            role=role,
            content=content,
            intent=intent,
            state_json=state or {},
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def list(self, task_id: str, *, limit: int = 100) -> list[ConversationMessageRecord]:
        result = await self.session.scalars(
            select(ConversationMessageRecord)
            .where(ConversationMessageRecord.task_id == task_id)
            .order_by(ConversationMessageRecord.created_at.desc())
            .limit(limit)
        )
        return list(reversed(list(result)))


class CreativeArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, task_id: str, artifact_id: str) -> CreativeArtifactRecord | None:
        return cast(
            CreativeArtifactRecord | None,
            await self.session.scalar(
                select(CreativeArtifactRecord).where(
                    CreativeArtifactRecord.id == artifact_id,
                    CreativeArtifactRecord.task_id == task_id,
                )
            ),
        )

    async def create(
        self,
        *,
        task_id: str,
        draft: CreativeArtifactDraft,
        intent: ConversationIntent,
        request_message_id: str,
    ) -> CreativeArtifactRecord:
        parent = (
            await self.get(task_id, draft.target_artifact_id)
            if draft.target_artifact_id is not None
            else None
        )
        record_id = str(uuid.uuid4())
        if intent == ConversationIntent.REVISE and parent is not None:
            lineage_id = parent.lineage_id
        else:
            lineage_id = record_id
        latest_version = await self.session.scalar(
            select(func.max(CreativeArtifactRecord.version)).where(
                CreativeArtifactRecord.lineage_id == lineage_id
            )
        )
        record = CreativeArtifactRecord(
            id=record_id,
            task_id=task_id,
            lineage_id=lineage_id,
            parent_id=parent.id if parent is not None else None,
            request_message_id=request_message_id,
            artifact_type=draft.artifact_type,
            format_label=draft.format_label,
            title=draft.title,
            summary=draft.summary,
            content_markdown=draft.content_markdown,
            version=(latest_version or 0) + 1,
            reference_ids=draft.reference_ids,
            visual_hook_ids=draft.visual_hook_ids,
            status="generated",
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def list(self, task_id: str, *, limit: int = 100) -> list[CreativeArtifactRecord]:
        result = await self.session.scalars(
            select(CreativeArtifactRecord)
            .where(CreativeArtifactRecord.task_id == task_id)
            .order_by(CreativeArtifactRecord.created_at.desc())
            .limit(limit)
        )
        return list(result)


class AssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: AssetRecord) -> AssetRecord:
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get(self, asset_id: str) -> AssetRecord | None:
        return await self.session.get(AssetRecord, asset_id)

    async def get_many(self, asset_ids: list[str]) -> list[AssetRecord]:
        if not asset_ids:
            return []
        result = await self.session.scalars(
            select(AssetRecord).where(AssetRecord.id.in_(asset_ids))
        )
        records = {record.id: record for record in result}
        return [records[asset_id] for asset_id in asset_ids if asset_id in records]

    async def save(self, record: AssetRecord) -> AssetRecord:
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def attach_to_task(self, asset_ids: list[str], task_id: str) -> None:
        records = await self.get_many(asset_ids)
        for record in records:
            record.task_id = task_id
        await self.session.commit()

    async def for_task(self, task_id: str, asset_ids: list[str]) -> list[AssetRecord]:
        if not asset_ids:
            return []
        result = await self.session.scalars(
            select(AssetRecord).where(
                AssetRecord.task_id == task_id,
                AssetRecord.id.in_(asset_ids),
            )
        )
        records = {record.id: record for record in result}
        return [records[asset_id] for asset_id in asset_ids if asset_id in records]


class ContentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_version(
        self,
        *,
        task_id: str,
        content: dict[str, Any],
        spec: dict[str, Any],
        constraints: dict[str, Any],
        origin: str,
        parent_version: int | None,
        evolution_hash: str,
        change_summary: str,
    ) -> ContentVersionRecord:
        latest = await self.session.scalar(
            select(func.max(ContentVersionRecord.version)).where(
                ContentVersionRecord.task_id == task_id
            )
        )
        record = ContentVersionRecord(
            task_id=task_id,
            version=(latest or 0) + 1,
            content_json=content,
            spec_json=spec,
            constraints_json=constraints,
            origin=origin,
            parent_version=parent_version,
            evolution_hash=evolution_hash,
            change_summary=change_summary,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def list_versions(self, task_id: str) -> list[ContentVersionRecord]:
        result = await self.session.scalars(
            select(ContentVersionRecord)
            .where(ContentVersionRecord.task_id == task_id)
            .order_by(ContentVersionRecord.version.desc())
        )
        return list(result)

    async def get_version(self, task_id: str, version: int) -> ContentVersionRecord | None:
        return await self.session.get(ContentVersionRecord, (task_id, version))


class CommunicationAssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_version(
        self,
        *,
        task_id: str,
        asset: CommunicationAsset,
        context_hash: str,
        parent_id: str | None = None,
        evaluation: dict[str, Any] | None = None,
    ) -> CommunicationAssetRecord:
        latest = await self.session.scalar(
            select(func.max(CommunicationAssetRecord.version)).where(
                CommunicationAssetRecord.task_id == task_id,
                CommunicationAssetRecord.asset_type == asset.asset_type.value,
            )
        )
        record = CommunicationAssetRecord(
            task_id=task_id,
            asset_type=asset.asset_type.value,
            version=(latest or 0) + 1,
            content_json=asset.content.model_dump(mode="json"),
            reference_ids=asset.reference_ids,
            visual_hook_ids=asset.visual_hook_ids,
            parent_id=parent_id,
            context_hash=context_hash,
            status=asset.status,
            evaluation_json=evaluation,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def list_versions(self, task_id: str) -> list[CommunicationAssetRecord]:
        result = await self.session.scalars(
            select(CommunicationAssetRecord)
            .where(CommunicationAssetRecord.task_id == task_id)
            .order_by(
                CommunicationAssetRecord.asset_type,
                CommunicationAssetRecord.version.desc(),
            )
        )
        return list(result)

    async def latest_by_type(self, task_id: str) -> dict[str, CommunicationAssetRecord]:
        versions = await self.list_versions(task_id)
        latest: dict[str, CommunicationAssetRecord] = {}
        for record in versions:
            latest.setdefault(record.asset_type, record)
        return latest


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def seed_corpus(
        self,
        sources: list[Source],
        evidence: list[Evidence],
        embeddings: list[list[float]],
    ) -> None:
        source_table = cast(Table, SourceRecord.__table__)
        evidence_table = cast(Table, EvidenceChunkRecord.__table__)
        for source in sources:
            source_values: dict[str, Any] = {
                "id": source.source_id,
                "source_type": source.source_type,
                "title": source.title,
                "author_org": source.author_or_org,
                "publication_date": source.publication_date,
                "locator": source.locator,
                "url": source.url,
                "authority_level": source.authority_level,
                "license": source.license,
                "is_available": source.is_available,
                "origin": source.origin.value,
                "task_id": source.task_id,
                "asset_id": source.asset_id,
                "retrieved_at": source.retrieved_at,
            }
            statement = pg_insert(source_table).values(source_values)
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[source_table.c.id], set_=source_values
                )
            )
        source_by_id = {source.source_id: source for source in sources}
        for item, embedding in zip(evidence, embeddings, strict=True):
            source = source_by_id[item.source_id]
            searchable = " ".join(
                [
                    source.title,
                    item.quote_or_summary,
                    item.locator,
                    *item.keywords,
                    item.character or "",
                    item.script_type or "",
                    item.historical_period or "",
                    item.topic,
                ]
            )
            evidence_values: dict[str, Any] = {
                "id": item.evidence_id,
                "source_id": item.source_id,
                "content": item.quote_or_summary,
                "locator": item.locator,
                "keywords": item.keywords,
                "metadata": item.metadata,
                "character": item.character,
                "script_type": item.script_type,
                "historical_period": item.historical_period,
                "topic": item.topic,
                "chunk_index": item.chunk_index,
                "content_hash": item.content_hash
                or hashlib.sha256(item.quote_or_summary.encode("utf-8")).hexdigest(),
                "search_tokens": " ".join(sorted(self._terms(searchable))),
                "embedding": embedding,
                "task_id": item.task_id,
                "asset_id": item.asset_id,
                "usability": item.usability.value,
                "retrieved_at": item.retrieved_at,
            }
            statement = pg_insert(evidence_table).values(evidence_values)
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[evidence_table.c.id], set_=evidence_values
                )
            )
        await self.session.commit()

    async def count(self) -> int:
        return int(
            await self.session.scalar(select(func.count()).select_from(EvidenceChunkRecord)) or 0
        )

    async def has_task_evidence(self, task_id: str, origin: SourceOrigin) -> bool:
        count = await self.session.scalar(
            select(func.count())
            .select_from(EvidenceChunkRecord)
            .join(SourceRecord, SourceRecord.id == EvidenceChunkRecord.source_id)
            .where(
                EvidenceChunkRecord.task_id == task_id,
                SourceRecord.origin == origin.value,
                EvidenceChunkRecord.usability != "unusable",
            )
        )
        return bool(count)

    async def hybrid_search(
        self,
        query: str,
        query_vector: list[float],
        limit: int = 8,
        *,
        character: str | None = None,
        script_type: str | None = None,
        historical_period: str | None = None,
        topic: str | None = None,
        task_id: str | None = None,
        origins: set[SourceOrigin] | None = None,
    ) -> list[RetrievedEvidence]:
        pool = max(limit * 3, 20)
        common_conditions: list[ColumnElement[bool]] = [SourceRecord.is_available.is_(True)]
        if task_id is not None:
            common_conditions.append(EvidenceChunkRecord.task_id == task_id)
        if origins:
            common_conditions.append(SourceRecord.origin.in_([origin.value for origin in origins]))
        common_conditions.append(EvidenceChunkRecord.usability != "unusable")
        if character:
            common_conditions.append(
                or_(
                    EvidenceChunkRecord.character == character,
                    EvidenceChunkRecord.character.is_(None),
                )
            )
        if script_type:
            common_conditions.append(
                or_(
                    EvidenceChunkRecord.script_type == script_type,
                    EvidenceChunkRecord.script_type.is_(None),
                )
            )
        if historical_period:
            common_conditions.append(
                or_(
                    EvidenceChunkRecord.historical_period == historical_period,
                    EvidenceChunkRecord.historical_period.is_(None),
                )
            )
        if topic:
            common_conditions.append(EvidenceChunkRecord.topic.in_([topic, "framework"]))

        structured_conditions: list[ColumnElement[bool]] = []
        if character:
            structured_conditions.append(EvidenceChunkRecord.character == character)
        if script_type:
            structured_conditions.append(EvidenceChunkRecord.script_type == script_type)
        if historical_period:
            structured_conditions.append(EvidenceChunkRecord.historical_period == historical_period)
        if topic:
            structured_conditions.append(EvidenceChunkRecord.topic == topic)
        structured_rows: list[tuple[EvidenceChunkRecord, SourceRecord]] = []
        if structured_conditions:
            structured_result = await self.session.execute(
                select(EvidenceChunkRecord, SourceRecord)
                .join(SourceRecord, SourceRecord.id == EvidenceChunkRecord.source_id)
                .where(*common_conditions, and_(*structured_conditions))
                .order_by(
                    EvidenceChunkRecord.chunk_index.asc(),
                    EvidenceChunkRecord.id.asc(),
                )
                .limit(pool)
            )
            structured_rows = list(structured_result.tuples())

        query_terms = sorted(self._terms(query))
        search_vector = func.to_tsvector("simple", EvidenceChunkRecord.search_tokens)
        ts_query = func.to_tsquery("simple", " | ".join(query_terms) or "无匹配词")
        keyword_rank_expression = func.ts_rank_cd(search_vector, ts_query).label("keyword_score")
        keyword_rows = (
            await self.session.execute(
                select(EvidenceChunkRecord, SourceRecord, keyword_rank_expression)
                .join(SourceRecord, SourceRecord.id == EvidenceChunkRecord.source_id)
                .where(*common_conditions, search_vector.op("@@")(ts_query))
                .order_by(keyword_rank_expression.desc())
                .limit(pool)
            )
        ).all()

        semantic = func.coalesce(
            1 - EvidenceChunkRecord.embedding.cosine_distance(query_vector), 0.0
        ).label("semantic_score")
        semantic_rows = (
            await self.session.execute(
                select(EvidenceChunkRecord, SourceRecord, semantic)
                .join(SourceRecord, SourceRecord.id == EvidenceChunkRecord.source_id)
                .where(*common_conditions)
                .order_by(semantic.desc())
                .limit(pool)
            )
        ).all()

        structured_ranks = {record.id: rank for rank, (record, _) in enumerate(structured_rows, 1)}
        keyword_ranks = {record.id: rank for rank, (record, _, _) in enumerate(keyword_rows, 1)}
        semantic_ranks = {record.id: rank for rank, (record, _, _) in enumerate(semantic_rows, 1)}
        keyword_scores = {record.id: float(score) for record, _, score in keyword_rows}
        semantic_scores = {record.id: float(score) for record, _, score in semantic_rows}
        records: dict[str, tuple[EvidenceChunkRecord, SourceRecord]] = {}
        for record, source in structured_rows:
            records[record.id] = (record, source)
        for record, source, _ in [*keyword_rows, *semantic_rows]:
            records[record.id] = (record, source)

        max_rrf = 3 / 61
        ranked: list[RetrievedEvidence] = []
        for evidence_id, (record, source) in records.items():
            structured_rank = structured_ranks.get(evidence_id)
            keyword_rank = keyword_ranks.get(evidence_id)
            semantic_rank = semantic_ranks.get(evidence_id)
            rrf_score = sum(
                1 / (60 + rank)
                for rank in (structured_rank, keyword_rank, semantic_rank)
                if rank is not None
            )
            safe_semantic = max(-1.0, min(semantic_scores.get(evidence_id, 0.0), 1.0))
            final_score = min(1.0, rrf_score / max_rrf)
            ranked.append(
                RetrievedEvidence(
                    evidence=self._to_evidence(record, source),
                    exact_score=1.0 if structured_rank is not None else 0.0,
                    keyword_score=min(keyword_scores.get(evidence_id, 0.0), 1.0),
                    semantic_score=safe_semantic,
                    final_score=final_score,
                    structured_rank=structured_rank,
                    keyword_rank=keyword_rank,
                    semantic_rank=semantic_rank,
                    rrf_score=rrf_score,
                )
            )
        return sorted(ranked, key=lambda item: item.final_score, reverse=True)[:limit]

    async def persist_task_results(
        self, task_id: str, evolution: EvolutionPackage, audit: AuditReport
    ) -> None:
        await self.session.execute(
            delete(ClaimEvidenceRecord).where(ClaimEvidenceRecord.task_id == task_id)
        )
        await self.session.execute(delete(ClaimRecord).where(ClaimRecord.task_id == task_id))
        bindings: list[ClaimEvidenceRecord] = []
        for claim in evolution.claims:
            self.session.add(
                ClaimRecord(
                    task_id=task_id,
                    claim_id=claim.claim_id,
                    content=claim.content,
                    claim_type=claim.claim_type.value,
                    evidence_grade=claim.evidence_grade,
                    has_conflict=claim.has_conflict,
                    audit_status=claim.audit_status.value,
                    claim_origin=claim.claim_origin,
                )
            )
            for relation in claim.evidence_relations:
                if any(item.evidence_id == relation.evidence_id for item in evolution.evidence):
                    bindings.append(
                        ClaimEvidenceRecord(
                            task_id=task_id,
                            claim_id=claim.claim_id,
                            evidence_id=relation.evidence_id,
                            support_type=relation.support_type.value,
                        )
                    )
        await self.session.flush()
        self.session.add_all(bindings)
        self.session.add(
            AuditRunRecord(
                task_id=task_id,
                attempt=audit.attempt,
                status=audit.status,
                model=audit.model,
                prompt_version=audit.prompt_version,
                fallback_used=audit.fallback_used,
                summary=audit.summary,
                issues=[item.model_dump(mode="json") for item in audit.issues],
            )
        )
        await self.session.commit()

    async def get_claim(self, claim_id: str) -> ClaimRecord | None:
        record: ClaimRecord | None = await self.session.scalar(
            select(ClaimRecord)
            .where(ClaimRecord.claim_id == claim_id)
            .order_by(ClaimRecord.created_at.desc())
            .limit(1)
        )
        return record

    async def claim_evidence(
        self, task_id: str, claim_id: str
    ) -> list[tuple[EvidenceChunkRecord, SourceRecord, str]]:
        rows = await self.session.execute(
            select(EvidenceChunkRecord, SourceRecord, ClaimEvidenceRecord.support_type)
            .join(
                ClaimEvidenceRecord,
                ClaimEvidenceRecord.evidence_id == EvidenceChunkRecord.id,
            )
            .join(SourceRecord, SourceRecord.id == EvidenceChunkRecord.source_id)
            .where(
                ClaimEvidenceRecord.task_id == task_id,
                ClaimEvidenceRecord.claim_id == claim_id,
            )
        )
        return list(rows.tuples())

    @staticmethod
    def _to_evidence(record: EvidenceChunkRecord, source: SourceRecord) -> Evidence:
        return Evidence(
            evidence_id=record.id,
            source_id=source.id,
            source_type=source.source_type,
            title=source.title,
            author_or_org=source.author_org,
            publication_date=source.publication_date,
            quote_or_summary=record.content,
            locator=record.locator,
            url=source.url,
            authority_level=cast(Literal["A", "B", "C", "D"], source.authority_level),
            license=source.license,
            keywords=record.keywords,
            metadata=record.metadata_json,
            character=record.character,
            script_type=record.script_type,
            historical_period=record.historical_period,
            topic=record.topic,
            chunk_index=record.chunk_index,
            content_hash=record.content_hash,
            origin=SourceOrigin(source.origin),
            task_id=record.task_id,
            asset_id=record.asset_id,
            usability=EvidenceUsability(record.usability),
            retrieved_at=record.retrieved_at,
        )

    @staticmethod
    def _terms(text: str) -> set[str]:
        normalized = "".join(text.lower().split())
        latin = set(re.findall(r"[a-z0-9]+", normalized))
        han = re.findall(r"[\u4e00-\u9fff]", normalized)
        bigrams = {"".join(han[index : index + 2]) for index in range(len(han) - 1)}
        return latin | set(han) | bigrams


class GlyphImageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_many(self, values: list[dict[str, Any]]) -> None:
        if not values:
            return
        table = cast(Table, GlyphImageRecord.__table__)
        statement = pg_insert(table).values(values)
        excluded = statement.excluded
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[table.c.id],
                set_={
                    "character": excluded.character,
                    "codepoint": excluded.codepoint,
                    "script_type": excluded.script_type,
                    "script_code": excluded.script_code,
                    "historical_period": excluded.historical_period,
                    "lineage_role": excluded.lineage_role,
                    "region_or_system": excluded.region_or_system,
                    "source_path": excluded.source_path,
                    "storage_key": excluded.storage_key,
                    "mime_type": excluded.mime_type,
                    "size_bytes": excluded.size_bytes,
                    "sha256": excluded.sha256,
                    "retrieval_text": excluded.retrieval_text,
                    "metadata": excluded.metadata,
                    "embedding": excluded.embedding,
                },
            )
        )
        await self.session.commit()

    async def get(self, image_id: str) -> GlyphImageRecord | None:
        return await self.session.get(GlyphImageRecord, image_id)

    async def get_representative(self, character: str, script_code: str) -> GlyphImageRecord | None:
        return cast(
            GlyphImageRecord | None,
            await self.session.scalar(
                select(GlyphImageRecord)
                .where(
                    GlyphImageRecord.character == character,
                    GlyphImageRecord.script_code == script_code,
                    GlyphImageRecord.metadata_json["is_representative"].as_boolean().is_(True),
                )
                .order_by(GlyphImageRecord.id)
                .limit(1)
            ),
        )

    async def search(
        self,
        query_vector: list[float],
        *,
        character: str | None = None,
        script_code: str | None = None,
        limit: int = 12,
    ) -> list[tuple[GlyphImageRecord, float]]:
        semantic = func.coalesce(
            1 - GlyphImageRecord.embedding.cosine_distance(query_vector), 0.0
        ).label("semantic_score")
        statement = select(GlyphImageRecord, semantic)
        if character:
            statement = statement.where(GlyphImageRecord.character == character)
        if script_code:
            statement = statement.where(GlyphImageRecord.script_code == script_code)
        representative = GlyphImageRecord.metadata_json["is_representative"].as_boolean()
        variant_index = GlyphImageRecord.metadata_json["variant_index"].as_integer()
        rows = (
            await self.session.execute(
                statement.order_by(
                    semantic.desc(),
                    representative.desc().nullslast(),
                    variant_index.asc().nullslast(),
                    GlyphImageRecord.id.asc(),
                ).limit(limit)
            )
        ).all()
        return [(record, max(-1.0, min(float(score), 1.0))) for record, score in rows]

    async def count(self) -> int:
        return int(
            await self.session.scalar(select(func.count()).select_from(GlyphImageRecord)) or 0
        )

    async def delete_not_in(self, image_ids: list[str]) -> None:
        statement = delete(GlyphImageRecord)
        if image_ids:
            statement = statement.where(GlyphImageRecord.id.not_in(image_ids))
        await self.session.execute(statement)
        await self.session.commit()
