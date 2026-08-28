from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from character_vein_api.repositories import AssetRepository, EvidenceRepository
from character_vein_api.retrieval import DatabaseEvidenceRetriever
from character_vein_domain import (
    Evidence,
    EvidenceSearchQuery,
    EvidenceUsability,
    Source,
    SourceOrigin,
)
from character_vein_retrieval import (
    EvidenceProviderResult,
    EvidenceSearchContext,
)


@dataclass(frozen=True)
class WebSearchSource:
    title: str
    url: str
    site_name: str = ""


@dataclass(frozen=True)
class WebSearchSnapshot:
    answer: str
    sources: list[WebSearchSource]


class AliyunBailianWebSearchClient:
    def __init__(
        self,
        *,
        api_key: str,
        compatible_base_url: str,
        model: str,
        timeout_seconds: float = 90,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.endpoint = compatible_base_url.rstrip("/").replace(
            "/compatible-mode/v1",
            "/api/v1/services/aigc/text-generation/generation",
        )

    async def search(self, query: str, *, limit: int) -> WebSearchSnapshot:
        search_prompt = (
            "请联网检索并用中文简要整理以下汉字文化问题。优先采用政府、博物馆、大学、"
            "专业汉字数据库和原始数据集页面；排除素材下载、营销软文和无正文聚合页。"
            "明确区分网页信息与综合概括，不把搜索摘要称为网页原文。\n\n"
            f"问题：{query}"
        )
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "input": {"messages": [{"role": "user", "content": search_prompt}]},
                    "parameters": {
                        "enable_search": True,
                        "result_format": "message",
                        "search_options": {
                            "forced_search": True,
                            "enable_source": True,
                            "enable_citation": True,
                            "citation_format": "[ref_<number>]",
                            "search_strategy": "max",
                        },
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
        output = payload.get("output") or {}
        choices = output.get("choices") or []
        answer = ""
        if choices:
            answer = str((choices[0].get("message") or {}).get("content") or "").strip()
        raw_sources = (output.get("search_info") or {}).get("search_results") or []
        sources = [
            WebSearchSource(
                title=str(item.get("title") or item.get("url") or "网络来源"),
                url=str(item.get("url") or ""),
                site_name=str(item.get("site_name") or ""),
            )
            for item in raw_sources[:limit]
            if str(item.get("url") or "").startswith(("http://", "https://"))
        ]
        if not answer or not sources:
            raise ValueError("百炼联网搜索未返回摘要或来源 URL")
        return WebSearchSnapshot(answer=answer, sources=sources)


class WebEvidenceProvider:
    """Live web search plus task-scoped, reusable reference snapshots."""

    name = "web"
    origin = SourceOrigin.WEB

    def __init__(
        self,
        retriever: DatabaseEvidenceRetriever,
        *,
        backend: str = "disabled",
        search_client: AliyunBailianWebSearchClient | None = None,
        evidence_repository: EvidenceRepository | None = None,
        embedding_provider: object | None = None,
        max_live_queries: int = 3,
    ) -> None:
        self.retriever = retriever
        self.backend = backend
        self.search_client = search_client
        self.evidence_repository = evidence_repository
        self.embedding_provider = embedding_provider
        self.max_live_queries = max_live_queries
        self._searched_queries: set[str] = set()

    async def search(
        self,
        query: EvidenceSearchQuery,
        context: EvidenceSearchContext,
        *,
        limit: int,
    ) -> EvidenceProviderResult:
        has_snapshot = await self.retriever.repository.has_task_evidence(
            context.task_id, SourceOrigin.WEB
        )
        query_key = hashlib.sha256(query.query.encode("utf-8")).hexdigest()[:16]
        eligible_live_query = query.topic in {"overview", "meaning_context", "framework"}
        can_search_live = (
            eligible_live_query
            and query_key not in self._searched_queries
            and len(self._searched_queries) < self.max_live_queries
            and self.search_client is not None
            and self.evidence_repository is not None
            and self.embedding_provider is not None
        )
        if can_search_live:
            search_client = self.search_client
            if search_client is None:
                raise RuntimeError("联网搜索客户端未配置")
            self._searched_queries.add(query_key)
            try:
                snapshot = await search_client.search(query.query, limit=limit)
                await self._persist_snapshot(context.task_id, query, query_key, snapshot)
                has_snapshot = True
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                if not has_snapshot:
                    return EvidenceProviderResult(
                        candidates=[],
                        available=False,
                        message=f"百炼联网搜索暂不可用：{type(exc).__name__}",
                    )
        if not has_snapshot:
            return EvidenceProviderResult(
                candidates=[],
                available=self.search_client is not None,
                message=(
                    "仓库尚未配置真实 Web Search backend；已受控降级为 reference gap"
                    if self.backend == "disabled"
                    else "等待文化语义、总体分期或数据覆盖问题触发联网搜索"
                ),
            )
        candidates = await self.retriever.retrieve(
            query.query,
            limit,
            character=query.character,
            script_type=query.script_type,
            historical_period=query.historical_period,
            topic=query.topic,
            task_id=context.task_id,
            origins={SourceOrigin.WEB},
        )
        if candidates:
            return EvidenceProviderResult(
                candidates=candidates,
                reused_snapshot=True,
                message="复用当前任务已保存的网络证据快照",
            )
        return EvidenceProviderResult(candidates=[], message="当前任务网络快照没有匹配片段")

    async def _persist_snapshot(
        self,
        task_id: str,
        query: EvidenceSearchQuery,
        query_key: str,
        snapshot: WebSearchSnapshot,
    ) -> None:
        if self.evidence_repository is None or self.embedding_provider is None:
            raise RuntimeError("联网搜索快照存储依赖未配置")
        now = datetime.now(UTC)
        sources: list[Source] = []
        evidence: list[Evidence] = []
        source_urls: list[dict[str, Any]] = []
        for index, item in enumerate(snapshot.sources, 1):
            source_id = f"source-web-{task_id}-{query_key}-{index}"
            sources.append(
                Source(
                    source_id=source_id,
                    source_type="web_search_result",
                    title=item.title,
                    author_or_org=item.site_name or "网络来源",
                    locator=f"联网搜索结果 {index}",
                    url=item.url,
                    authority_level="D",
                    license="链接与搜索标题；网页内容版权归原网站",
                    origin=SourceOrigin.WEB,
                    task_id=task_id,
                    retrieved_at=now,
                )
            )
            source_urls.append({"title": item.title, "url": item.url})
            evidence.append(
                Evidence(
                    evidence_id=f"evidence-web-meta-{task_id}-{query_key}-{index}",
                    source_id=source_id,
                    source_type="web_search_result",
                    title=item.title,
                    author_or_org=item.site_name or "网络来源",
                    quote_or_summary=item.title,
                    locator=f"联网搜索结果 {index}；仅保存标题与 URL",
                    url=item.url,
                    authority_level="D",
                    license="链接与搜索标题；网页内容版权归原网站",
                    metadata={"query": query.query, "search_result_index": index},
                    character=query.character,
                    script_type=query.script_type,
                    historical_period=query.historical_period,
                    topic=query.topic or "general",
                    content_hash=hashlib.sha256(item.url.encode("utf-8")).hexdigest(),
                    origin=SourceOrigin.WEB,
                    task_id=task_id,
                    usability=EvidenceUsability.METADATA_ONLY,
                    retrieved_at=now,
                )
            )
        synthesis_source_id = f"source-web-synthesis-{task_id}-{query_key}"
        sources.append(
            Source(
                source_id=synthesis_source_id,
                source_type="web_search_synthesis",
                title=f"百炼联网搜索摘要：{query.purpose}",
                author_or_org="阿里云百炼联网搜索",
                locator=f"查询：{query.query}",
                authority_level="D",
                license="模型基于联网结果生成的参考摘要；不是网页原文",
                origin=SourceOrigin.WEB,
                task_id=task_id,
                retrieved_at=now,
            )
        )
        evidence.append(
            Evidence(
                evidence_id=f"evidence-web-synthesis-{task_id}-{query_key}",
                source_id=synthesis_source_id,
                source_type="web_search_synthesis",
                title=f"百炼联网搜索摘要：{query.purpose}",
                author_or_org="阿里云百炼联网搜索",
                quote_or_summary=snapshot.answer[:5000],
                locator=f"查询：{query.query}",
                authority_level="D",
                license="模型基于联网结果生成的参考摘要；不是网页原文",
                keywords=[],
                metadata={"query": query.query, "sources": source_urls},
                character=query.character,
                script_type=query.script_type,
                historical_period=query.historical_period,
                topic=query.topic or "general",
                content_hash=hashlib.sha256(snapshot.answer.encode("utf-8")).hexdigest(),
                origin=SourceOrigin.WEB,
                task_id=task_id,
                usability=EvidenceUsability.PARTIAL,
                retrieved_at=now,
            )
        )
        embeddings = await self.embedding_provider.embed(  # type: ignore[attr-defined]
            [item.quote_or_summary for item in evidence]
        )
        await self.evidence_repository.seed_corpus(sources, evidence, embeddings)


class UploadEvidenceProvider:
    name = "user_upload"
    origin = SourceOrigin.USER_UPLOAD

    def __init__(
        self,
        evidence_repository: EvidenceRepository,
        asset_repository: AssetRepository,
        retriever: DatabaseEvidenceRetriever,
        embedding_provider: object,
    ) -> None:
        self.evidence_repository = evidence_repository
        self.asset_repository = asset_repository
        self.retriever = retriever
        self.embedding_provider = embedding_provider

    async def prepare_snapshot(self, task_id: str, asset_ids: list[str]) -> int:
        assets = await self.asset_repository.for_task(task_id, asset_ids)
        if len(assets) != len(asset_ids):
            raise ValueError("上传资料不属于当前任务，拒绝建立证据快照")
        sources: list[Source] = []
        evidence: list[Evidence] = []
        now = datetime.now(UTC)
        for asset in assets:
            source_id = f"source-upload-{task_id}-{asset.id}"
            usability = (
                EvidenceUsability.USABLE
                if asset.mime_type in {"text/plain", "text/markdown", "text/x-markdown"}
                else EvidenceUsability.PARTIAL
            )
            sources.append(
                Source(
                    source_id=source_id,
                    source_type="user_document",
                    title=asset.filename,
                    author_or_org="用户提供",
                    locator=f"文件：{asset.filename}",
                    authority_level="D",
                    license="用户上传；仅限当前任务处理，不代表内容已被验证",
                    origin=SourceOrigin.USER_UPLOAD,
                    task_id=task_id,
                    asset_id=asset.id,
                    retrieved_at=now,
                )
            )
            for index, (content, locator) in enumerate(
                _chunk_text(asset.extracted_text, asset.filename), 1
            ):
                evidence.append(
                    Evidence(
                        evidence_id=f"evidence-upload-{task_id}-{asset.id}-{index}",
                        source_id=source_id,
                        source_type="user_document",
                        title=asset.filename,
                        author_or_org="用户提供",
                        quote_or_summary=content,
                        locator=locator,
                        authority_level="D",
                        license="用户上传；仅限当前任务处理，不代表内容已被验证",
                        keywords=[],
                        metadata={"filename": asset.filename, "kind": asset.kind},
                        topic="general",
                        chunk_index=index - 1,
                        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                        origin=SourceOrigin.USER_UPLOAD,
                        task_id=task_id,
                        asset_id=asset.id,
                        usability=usability,
                        retrieved_at=now,
                    )
                )
        if evidence:
            embeddings = await self.embedding_provider.embed(  # type: ignore[attr-defined]
                [item.quote_or_summary for item in evidence]
            )
            await self.evidence_repository.seed_corpus(sources, evidence, embeddings)
        return len(evidence)

    async def search(
        self,
        query: EvidenceSearchQuery,
        context: EvidenceSearchContext,
        *,
        limit: int,
    ) -> EvidenceProviderResult:
        if not context.asset_ids:
            return EvidenceProviderResult(candidates=[], message="当前任务没有用户上传资料")
        candidates = await self.retriever.retrieve(
            query.query,
            limit,
            character=None,
            script_type=None,
            historical_period=None,
            topic=None,
            task_id=context.task_id,
            origins={SourceOrigin.USER_UPLOAD},
        )
        return EvidenceProviderResult(
            candidates=candidates,
            reused_snapshot=True,
            message="仅检索当前任务的上传资料快照",
        )


def _chunk_text(text: str, filename: str, *, max_chars: int = 1200) -> list[tuple[str, str]]:
    lines = text.splitlines()
    chunks: list[tuple[str, str]] = []
    buffer: list[str] = []
    start_line = 1
    for line_number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        if not buffer:
            start_line = line_number
        if buffer and sum(len(item) for item in buffer) + len(stripped) > max_chars:
            chunks.append(
                ("\n".join(buffer), f"文件：{filename}；行 {start_line}-{line_number - 1}")
            )
            buffer = []
            start_line = line_number
        buffer.append(stripped)
    if buffer:
        chunks.append(("\n".join(buffer), f"文件：{filename}；行 {start_line}-{len(lines)}"))
    return chunks
