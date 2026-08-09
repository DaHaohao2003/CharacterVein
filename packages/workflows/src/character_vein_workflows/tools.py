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
from character_vein_retrieval import EvidenceRetriever, GlyphImageRetriever


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
        evidence_retriever: EvidenceRetriever,
        glyph_retriever: GlyphImageRetriever | None,
    ) -> None:
        self.evidence_retriever = evidence_retriever
        self.glyph_retriever = glyph_retriever
        self.registry = ToolRegistry()
        for definition in (
            ToolDefinition(
                "search_literature",
                "按结构化字段、中文关键词和语义向量检索可信证据并执行 RRF 融合",
                "EvidenceSearchQuery + limit",
                "RetrievedEvidence[]",
            ),
            ToolDefinition(
                "search_glyphs",
                "按汉字和书体从 PostgreSQL/pgvector 检索真实 JieZi 字形",
                "query + character + script_code + limit",
                "RetrievedGlyphImage[]",
            ),
            ToolDefinition(
                "get_source_detail",
                "读取候选证据携带的来源、定位、许可和权威等级",
                "evidence_id",
                "Evidence | null",
            ),
            ToolDefinition(
                "audit_claims",
                "检查陈述是否被证据直接支持并给出重试、降级或拒绝动作",
                "Claim[] + Evidence[]",
                "AuditReport",
            ),
            ToolDefinition(
                "generate_content",
                "使用审校后的事实层生成受众化文化内容",
                "TaskSpec + EvolutionPackage",
                "GeneratedContent",
                read_only=False,
            ),
            ToolDefinition(
                "check_constraints",
                "检查阶段、引用、受众、时长和互动题硬约束",
                "TaskSpec + fact layer + content",
                "ConstraintResult",
            ),
        ):
            self.registry.register(definition)

    async def search_literature(
        self, search_query: EvidenceSearchQuery, *, limit: int, attempt: int
    ) -> ToolExecution[list[RetrievedEvidence]]:
        return await self.execute(
            "search_literature",
            (
                f"{search_query.query_id}；目标字={search_query.character}；"
                f"书体={search_query.script_type or '不限'}；主题={search_query.topic or '不限'}"
            ),
            lambda: self.evidence_retriever.retrieve(
                search_query.query,
                limit,
                character=search_query.character,
                script_type=search_query.script_type,
                historical_period=search_query.historical_period,
                topic=search_query.topic,
            ),
            len,
            attempt=attempt,
        )

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
            ),
        )


class ToolExecutionError(RuntimeError):
    def __init__(self, call: ToolCall) -> None:
        super().__init__(call.error or "工具调用失败")
        self.call = call
