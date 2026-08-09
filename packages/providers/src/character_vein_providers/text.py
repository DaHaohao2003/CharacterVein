import json
import re
from typing import Any, Protocol

import httpx

from character_vein_domain import (
    AuditStatus,
    EvidenceSearchQuery,
    EvolutionPackage,
    GeneratedContent,
    PlanStep,
    TaskSpec,
)


class TextModelProvider(Protocol):
    async def parse_task(self, raw_input: str) -> TaskSpec: ...

    async def plan_task(self, task_spec: TaskSpec) -> list[PlanStep]: ...

    async def plan_evidence_queries(
        self, task_spec: TaskSpec, retry_context: str = ""
    ) -> list[EvidenceSearchQuery]: ...

    async def generate_content(
        self, task_spec: TaskSpec, evolution: EvolutionPackage
    ) -> GeneratedContent: ...


class DeterministicTextProvider:
    """Repeatable stage-one provider that requires no external model key."""

    async def parse_task(self, raw_input: str) -> TaskSpec:
        target = self._explicit_target(raw_input)
        duration = self._extract_int(raw_input, r"(\d+)\s*分钟", 4)
        required_stages = self._extract_int(
            raw_input, r"(?:至少|展示)?\s*(\d+)\s*个?(?:历史)?阶段", 3
        )
        interactions = self._extract_int(raw_input, r"(\d+)\s*道(?:互动)?题", 2)
        audience_match = re.search(
            r"(?:面向|为)?\s*((?:小学|初中|高中)[一二三四五六七八九\d]+年级)", raw_input
        )
        audience = audience_match.group(1) if audience_match else "普通文化爱好者"
        constraints: list[str] = []
        if "争议" in raw_input:
            constraints.append("争议观点不得写成定论")

        themes = {
            "云": "天象观察、构形与文化意象",
            "雷": "自然认知、构形与声音想象",
            "礼": "礼仪实践、字义与社会秩序",
            "明": "光明、构形与认知引申",
        }
        return TaskSpec(
            target_characters=[target] if target else [],
            theme=themes.get(target or "", "汉字演化与文化"),
            audience=audience,
            duration_minutes=duration,
            required_stages=required_stages,
            interaction_count=interactions,
            constraints=constraints,
        )

    async def plan_task(self, task_spec: TaskSpec) -> list[PlanStep]:
        character = task_spec.target_characters[0] if task_spec.target_characters else "待确认汉字"
        return [
            PlanStep(
                id="plan",
                title=f"规划“{character}”字研究与传播任务",
                agent="规划 Agent",
                tool_names=[],
                completion_criteria="形成包含工具、依赖和失败动作的可执行计划",
                failure_action="使用经过验证的本地计划模板",
            ),
            PlanStep(
                id="query_plan",
                title="拆分字形、字义、分期与争议证据问题",
                agent="规划 Agent",
                tool_names=[],
                depends_on=["plan"],
                completion_criteria="每个问题具有明确检索目的和结构化过滤条件",
                failure_action="按七类书体和三层知识模板拆分",
            ),
            PlanStep(
                id="retrieval",
                title="三路混合检索可信文献",
                agent="文献检索 Agent",
                tool_names=["search_literature"],
                depends_on=["query_plan"],
                completion_criteria="核心问题均返回可定位证据或明确资料不足",
                failure_action="根据审校问题改写查询并最多重试一次",
            ),
            PlanStep(
                id="glyph_retrieval",
                title="分书体检索真实代表字形",
                agent="演化 Agent",
                tool_names=["search_glyphs"],
                depends_on=["query_plan"],
                completion_criteria="所有已登记书体都有数据库中的代表图",
                failure_action="保留真实资料缺口，不使用生成图片补位",
            ),
            PlanStep(
                id="evolution",
                title="构建字形、字义与文化三层知识包",
                agent="演化 Agent",
                tool_names=["get_source_detail"],
                depends_on=["retrieval", "glyph_retrieval"],
                completion_criteria="主时间线、书写支线和来源边界均结构化",
                failure_action="降级为仅展示可证材料",
            ),
            PlanStep(
                id="claim_support",
                title="为每条事实陈述补充直接证据",
                agent="文献检索 Agent",
                tool_names=["search_literature", "get_source_detail"],
                depends_on=["evolution"],
                completion_criteria="事实性陈述至少绑定一条可定位证据",
                failure_action="重新检索；仍不足则拒绝或降低表述",
            ),
            PlanStep(
                id="audit",
                title="执行陈述级证据审校",
                agent="证据审校 Agent",
                tool_names=["audit_claims"],
                depends_on=["claim_support"],
                completion_criteria="所有待发布陈述通过、降级或被拒绝",
                failure_action="回到文献检索或请求用户确认资料边界",
            ),
            PlanStep(
                id="content",
                title=f"生成面向{task_spec.audience}的文化讲解",
                agent="文化传播 Agent",
                tool_names=["generate_content"],
                depends_on=["audit"],
                completion_criteria="只使用审校后事实并满足受众和时长要求",
                failure_action="锁定事实层后重新生成传播层",
            ),
            PlanStep(
                id="constraints",
                title="检查阶段、引用、受众与互动约束",
                agent="约束检查 Agent",
                tool_names=["check_constraints"],
                depends_on=["content"],
                completion_criteria="所有硬约束通过，或明确给出未通过原因",
                failure_action="最多重新生成传播层一次",
            ),
        ]

    async def plan_evidence_queries(
        self, task_spec: TaskSpec, retry_context: str = ""
    ) -> list[EvidenceSearchQuery]:
        character = task_spec.target_characters[0]
        script_types = ("甲骨文", "金文", "战国文字", "篆书", "隶书", "楷书", "草书")
        queries = [
            EvidenceSearchQuery(
                query_id=f"stage-{index + 1}",
                query=(
                    f"{character} {script_type} 构形 结构 演变 历史范围 "
                    f"{task_spec.theme} {retry_context}"
                ).strip(),
                purpose=f"核验{script_type}字形、分期和资料边界",
                character=character,
                script_type=script_type,
                topic="shape",
            )
            for index, script_type in enumerate(script_types)
        ]
        queries.extend(
            [
                EvidenceSearchQuery(
                    query_id="catalog",
                    query=f"{character} JieZi 书体覆盖 图片样本 元数据 {retry_context}".strip(),
                    purpose="核验数据集覆盖范围、样本数量与元数据来源",
                    character=character,
                    topic="overview",
                ),
                EvidenceSearchQuery(
                    query_id="meaning",
                    query=(
                        f"{character} 本义 字义 引申 文化语义 {task_spec.theme} {retry_context}"
                    ).strip(),
                    purpose="核验本义、字义变化与文化解释边界",
                    character=character,
                    topic="meaning_context",
                ),
                EvidenceSearchQuery(
                    query_id="framework",
                    query=(
                        f"{character} 古今文字 分期 主时间线 草书支线 规范化 {retry_context}"
                    ).strip(),
                    purpose="核验演化分期、主线和书写支线规则",
                    character=character,
                    topic="framework",
                ),
            ]
        )
        return queries

    async def generate_content(
        self, task_spec: TaskSpec, evolution: EvolutionPackage
    ) -> GeneratedContent:
        audience_note = self._audience_note(task_spec.audience)
        format_label = {
            "interactive_lesson": "互动讲解",
            "culture_card": "文化卡",
            "article_outline": "文章提纲",
        }[task_spec.output_type]
        mainline_stages = [
            stage for stage in evolution.glyph_stages if stage.lineage_role != "branch"
        ]
        branch_stages = [
            stage for stage in evolution.glyph_stages if stage.lineage_role == "branch"
        ]
        stage_lines = [
            (
                f"- **{stage.period}·{stage.script_type}**：{stage.structure_description}"
                if stage.availability == "available"
                else f"- **{stage.period}·{stage.script_type}**：当前数据集暂无该字样本。"
            )
            for stage in mainline_stages
        ]
        branch_lines = [
            (
                f"- **{stage.script_type}支线**：{stage.structure_description}"
                if stage.availability == "available"
                else f"- **{stage.script_type}支线**：当前数据集暂无该字样本。"
            )
            for stage in branch_stages
        ]
        claim_lines = [
            f"- {claim.content}"
            for claim in evolution.claims
            if claim.audit_status != AuditStatus.REJECTED
        ]
        body = "\n\n".join(
            [
                f"# {evolution.character}：从早期字形到文化语义",
                (
                    f"这是一份面向{task_spec.audience}、预计 {task_spec.duration_minutes} "
                    f"分钟的{format_label}。{audience_note}观察“{evolution.character}”字时，"
                    "我们先把字形、字义和后来的文化解释分开，避免把生动联想误当成历史事实。"
                ),
                "## 字形时间线\n" + "\n".join(stage_lines),
                "## 书写支线\n" + "\n".join(branch_lines),
                "## 字义与文化\n" + "\n".join(claim_lines),
                "## 怎样理解证据\n"
                "不同历史阶段的字形并不是一条毫无分支的直线。我们选择的是便于比较的代表字形；遇到材料不足或解释有争议时，应并列呈现来源并降低表述强度。",
            ]
        )
        questions = [
            f"观察不同阶段的“{evolution.character}”字，哪些构形特征发生了变化？",
            "为什么我们不能只凭现代字形就断定古代文化含义？",
            "如果两份资料解释不同，你会先比较哪些证据？",
        ][: task_spec.interaction_count]
        return GeneratedContent(
            title=f"“{evolution.character}”字文化讲解",
            audience=task_spec.audience,
            duration_minutes=task_spec.duration_minutes,
            outline=["认识任务", "观察字形", "理解字义与文化", "证据与互动"],
            body_markdown=body,
            interaction_questions=questions,
            source_ids=[evidence.evidence_id for evidence in evolution.evidence],
            estimated_characters=len(re.sub(r"\s|[#*\-]", "", body)),
        )

    @staticmethod
    def _extract_int(text: str, pattern: str, default: int) -> int:
        match = re.search(pattern, text)
        return int(match.group(1)) if match else default

    @staticmethod
    def _explicit_target(text: str) -> str | None:
        patterns = (
            r"[“\"『「]([\u4e00-\u9fff])[”\"』」]\s*字?",
            r"(?:目标字|汉字|讲解对象|研究对象|讲解|研究|围绕|关于)\s*[：:]?\s*[“\"『「]?([\u4e00-\u9fff])[”\"』」]?",
            r"([\u4e00-\u9fff])字(?:讲解|演化|文化|课程|故事|研究|介绍|内容)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _audience_note(audience: str) -> str:
        if "小学" in audience:
            return "表达会使用短句和可观察的器物特征，并用问题帮助理解。"
        if "初中" in audience or "高中" in audience:
            return "表达会补充必要的历史背景，并区分材料、解释与推论。"
        if "国际" in audience:
            return "表达会减少生僻术语，并解释关键文化概念。"
        return "表达会保留必要术语与证据边界，方便进一步查阅。"


class AliyunBailianTextProvider:
    """Structured OpenAI-compatible planner, parser and writer with a safe fallback."""

    required_plan_ids = {
        "plan",
        "query_plan",
        "retrieval",
        "glyph_retrieval",
        "evolution",
        "claim_support",
        "audit",
        "content",
        "constraints",
    }

    def __init__(
        self, api_key: str, base_url: str, model: str, timeout_seconds: float = 60
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.fallback = DeterministicTextProvider()
        self.last_fallback_used = False

    async def parse_task(self, raw_input: str) -> TaskSpec:
        system = (
            "你是汉字文化任务解析器。只提取用户明确给出的目标字、受众、时长、阶段数、"
            "互动题数量、主题与限制，不猜测未知古文字。返回 JSON 对象，字段必须符合 TaskSpec。"
        )
        try:
            parsed = await self._json_completion(system, {"raw_input": raw_input})
            spec = TaskSpec.model_validate(parsed)
            if len(spec.target_characters) != 1 or len(spec.target_characters[0]) != 1:
                raise ValueError("模型没有提取出唯一目标汉字")
            self.last_fallback_used = False
            return spec
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.last_fallback_used = True
            return await self.fallback.parse_task(raw_input)

    async def plan_task(self, task_spec: TaskSpec) -> list[PlanStep]:
        system = (
            "你是字脉规划 Agent。根据任务定制九步执行计划。返回 JSON 对象 {steps:[...]}。"
            "步骤 id 必须且只能依次使用 plan、query_plan、retrieval、glyph_retrieval、evolution、"
            "claim_support、audit、content、constraints。每项包含 title、agent、tool_names、"
            "depends_on、"
            "completion_criteria、failure_action，status 固定为 pending。允许的工具为 "
            "search_literature、search_glyphs、get_source_detail、audit_claims、generate_content、"
            "check_constraints。不得输出模型思维过程。"
        )
        try:
            payload = await self._json_completion(system, task_spec.model_dump(mode="json"))
            steps = [PlanStep.model_validate(item) for item in payload["steps"]]
            if {item.id for item in steps} != self.required_plan_ids:
                raise ValueError("动态计划没有覆盖规范执行节点")
            canonical = await self.fallback.plan_task(task_spec)
            contracts = {item.id: item for item in canonical}
            planned = {item.id: item for item in steps}
            ordered_steps = [planned[item.id] for item in canonical]
            for step in ordered_steps:
                contract = contracts[step.id]
                step.status = "pending"
                step.tool_names = contract.tool_names
                step.depends_on = contract.depends_on
                if not step.completion_criteria:
                    step.completion_criteria = contract.completion_criteria
                if not step.failure_action:
                    step.failure_action = contract.failure_action
            self.last_fallback_used = False
            return ordered_steps
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.last_fallback_used = True
            return await self.fallback.plan_task(task_spec)

    async def plan_evidence_queries(
        self, task_spec: TaskSpec, retry_context: str = ""
    ) -> list[EvidenceSearchQuery]:
        system = (
            "你是汉字文献检索规划器。返回 JSON 对象 {queries:[...]}，每项包含 query_id、query、"
            "purpose、character、script_type、historical_period、topic。必须覆盖七类书体、字义文化和"
            "总体分期，并包含一个 topic=overview 的数据集覆盖查询，不得补充输入之外的事实。"
        )
        request = {**task_spec.model_dump(mode="json"), "retry_context": retry_context}
        try:
            payload = await self._json_completion(system, request)
            queries = [EvidenceSearchQuery.model_validate(item) for item in payload["queries"]]
            character = task_spec.target_characters[0]
            if not queries or any(item.character != character for item in queries):
                raise ValueError("检索计划目标字不一致")
            required_scripts = {"甲骨文", "金文", "战国文字", "篆书", "隶书", "楷书", "草书"}
            planned_scripts = {item.script_type for item in queries if item.script_type}
            planned_topics = {item.topic for item in queries if item.topic}
            if not required_scripts.issubset(planned_scripts) or not {
                "overview",
                "framework",
                "meaning_context",
            }.issubset(planned_topics):
                raise ValueError("检索计划未覆盖规范书体或核心主题")
            self.last_fallback_used = False
            return queries[:14]
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.last_fallback_used = True
            return await self.fallback.plan_evidence_queries(task_spec, retry_context)

    async def generate_content(
        self, task_spec: TaskSpec, evolution: EvolutionPackage
    ) -> GeneratedContent:
        # The model plans searches and audits claims, while publication text is rendered from
        # the approved fact layer. This deliberately prevents a fluent model from inserting
        # uncited etymology between otherwise supported sentences.
        self.last_fallback_used = False
        return await self.fallback.generate_content(task_spec, evolution)

    async def _json_completion(self, system: str, payload: object) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("模型未返回 JSON 文本")
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise TypeError("模型返回的顶层结构不是对象")
        return parsed
