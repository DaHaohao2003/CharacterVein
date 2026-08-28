from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from character_vein_domain import (
    Evidence,
    EvidenceSearchQuery,
    RetrievedEvidence,
    RetrievedGlyphImage,
    ToolCall,
)
from character_vein_retrieval import EvidenceProvider, EvidenceSearchContext, GlyphImageRetriever


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: str
    output_schema: str
    read_only: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"工具已注册：{definition.name}")
        self._definitions[definition.name] = definition

    def require(self, name: str) -> ToolDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise ValueError(f"工具未注册：{name}") from exc

    def list(self) -> list[ToolDefinition]:
        return list(self._definitions.values())


@dataclass
class ToolExecution[T]:
    result: T
    call: ToolCall


class AgentToolbox:
    def __init__(
        self,
        evidence_providers: list[EvidenceProvider],
        glyph_retriever: GlyphImageRetriever | None,
    ) -> None:
        self.evidence_providers = {provider.name: provider for provider in evidence_providers}
        self.glyph_retriever = glyph_retriever
        self.registry = ToolRegistry()
        for definition in (
            ToolDefinition(
                "search_evidence",
                "按来源路由检索任务级证据快照，并保留来源与可用性信息",
                "provider + EvidenceSearchQuery + EvidenceSearchContext + limit",
                "RetrievedEvidence[]",
            ),
            ToolDefinition(
                "search_glyphs",
                "按汉字和书体从本地字形资料库检索历史字形",
                "query + character + script_code + limit",
                "RetrievedGlyphImage[]",
            ),
            ToolDefinition(
                "analyze_glyphs",
                "使用多模态模型观察已标注字形图片的可见结构并进行阶段对比",
                "character + labelled glyph images + comparison pairs",
                "GlyphVisualAnalysis",
            ),
            ToolDefinition(
                "build_cultural_motif",
                "将已选叙事路线固化为三种传播媒介共享的文化母题",
                "CommunicationBrief + EvolutionPackage + NarrativeRoute",
                "CulturalMotif",
                read_only=False,
            ),
            ToolDefinition(
                "generate_communication_asset",
                "按统一文化母题生成一类结构化跨媒介传播成品",
                "asset_type + CommunicationBrief + CulturalMotif + EvolutionPackage",
                "CommunicationAsset",
                read_only=False,
            ),
            ToolDefinition(
                "evaluate_communication_asset",
                "独立检查单类传播成品的母题、视觉素材和媒介结构",
                "CommunicationBrief + CulturalMotif + CommunicationAsset",
                "ArtifactEvaluation",
            ),
            ToolDefinition(
                "generate_content",
                "使用网络检索与用户资料作为上下文生成受众化文化内容",
                "TaskSpec + EvolutionPackage",
                "GeneratedContent",
                read_only=False,
            ),
            ToolDefinition(
                "check_constraints",
                "检查阶段、参考上下文、受众、时长和互动题硬约束",
                "TaskSpec + generation context + content",
                "ConstraintResult",
            ),
        ):
            self.registry.register(definition)

    async def search_evidence(
        self,
        provider_name: str,
        search_query: EvidenceSearchQuery,
        context: EvidenceSearchContext,
        *,
        limit: int,
        attempt: int,
    ) -> ToolExecution[list[RetrievedEvidence]]:
        provider = self.evidence_providers[provider_name]
        provider_message = ""

        async def search() -> list[RetrievedEvidence]:
            nonlocal provider_message
            result = await provider.search(search_query, context, limit=limit)
            provider_message = result.message
            return result.candidates

        execution = await self.execute(
            "search_evidence",
            (
                f"来源={provider.origin.value}；{search_query.query_id}；"
                f"目标字={search_query.character}；"
                f"书体={search_query.script_type or '不限'}；主题={search_query.topic or '不限'}"
            ),
            search,
            len,
            attempt=attempt,
            provider=provider.origin.value,
        )
        if provider_message:
            execution.call.result_summary = f"{execution.call.result_summary}；{provider_message}"
        return execution

    async def search_glyphs(
        self,
        query: str,
        *,
        character: str,
        script_code: str,
        limit: int,
        attempt: int,
    ) -> ToolExecution[list[RetrievedGlyphImage]]:
        glyph_retriever = self.glyph_retriever
        if glyph_retriever is None:
            return ToolExecution(
                result=[],
                call=ToolCall(
                    tool_call_id=str(uuid.uuid4()),
                    tool_name="search_glyphs",
                    status="completed",
                    input_summary=f"目标字={character}；书体代码={script_code}",
                    result_summary="未配置字形检索器，沿用知识包中的已登记代表图",
                    attempt=attempt,
                ),
            )
        return await self.execute(
            "search_glyphs",
            f"目标字={character}；书体代码={script_code}；查询={query}",
            lambda: glyph_retriever.retrieve(
                query, character=character, script_code=script_code, limit=limit
            ),
            len,
            attempt=attempt,
        )

    async def get_source_detail(
        self,
        evidence_id: str,
        candidates: list[RetrievedEvidence],
        *,
        attempt: int,
        provider: str = "internal",
    ) -> ToolExecution[Evidence | None]:
        async def find() -> Evidence | None:
            return next(
                (item.evidence for item in candidates if item.evidence.evidence_id == evidence_id),
                None,
            )

        return await self.execute(
            "get_source_detail",
            f"evidence_id={evidence_id}",
            find,
            lambda result: int(result is not None),
            attempt=attempt,
        )

    async def execute[T](
        self,
        tool_name: str,
        input_summary: str,
        operation: Callable[[], Awaitable[T]],
        result_counter: Callable[[T], int],
        *,
        attempt: int,
        provider: str = "internal",
    ) -> ToolExecution[T]:
        self.registry.require(tool_name)
        tool_call_id = str(uuid.uuid4())
        started = time.perf_counter()
        try:
            result = await operation()
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            raise ToolExecutionError(
                ToolCall(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    status="failed",
                    input_summary=input_summary,
                    result_summary="工具调用失败",
                    duration_ms=duration_ms,
                    attempt=attempt,
                    error=str(exc),
                    provider=provider,
                )
            ) from exc
        duration_ms = (time.perf_counter() - started) * 1000
        result_count = result_counter(result)
        return ToolExecution(
            result=result,
            call=ToolCall(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                status="completed",
                input_summary=input_summary,
                result_summary=f"返回 {result_count} 项结果",
                result_count=result_count,
                duration_ms=duration_ms,
                attempt=attempt,
                provider=provider,
            ),
        )


class ToolExecutionError(RuntimeError):
    def __init__(self, call: ToolCall) -> None:
        super().__init__(call.error or "工具调用失败")
        self.call = call
