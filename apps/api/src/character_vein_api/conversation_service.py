from __future__ import annotations

from typing import Any

import httpx
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from character_vein_api.config import get_settings
from character_vein_api.evidence_providers import AliyunBailianWebSearchClient
from character_vein_api.glyph_visual_analysis import (
    StoredGlyphVisualAnalyzer,
    build_vision_provider,
)
from character_vein_api.model_providers import build_text_provider
from character_vein_api.models import CreativeArtifactRecord, TaskRecord
from character_vein_api.repositories import (
    ConversationRepository,
    CreativeArtifactRepository,
    GlyphImageRepository,
    TaskRepository,
)
from character_vein_api.schemas import ConversationTurnResponse
from character_vein_domain import (
    ConversationIntent,
    ConversationTurnPlan,
    EvolutionPackage,
    GlyphLineageRole,
    RetrievedGlyphImage,
    SourceOrigin,
    TaskSpec,
)
from character_vein_providers import extract_explicit_hanzi_target
from character_vein_workflows.fixtures import SUPPORTED_DEMO_CHARACTERS, case_evolution_package


class ConversationService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository
        self.messages = ConversationRepository(repository.session)
        self.artifacts = CreativeArtifactRepository(repository.session)
        self.settings = get_settings()
        self.provider = build_text_provider(self.settings)

    async def respond(
        self,
        task: TaskRecord,
        content: str,
        *,
        active_artifact_id: str | None = None,
        active_page_id: str | None = None,
        active_block_id: str | None = None,
    ) -> ConversationTurnResponse:
        user_message = await self.messages.add(task_id=task.id, role="user", content=content)
        history_records = await self.messages.list(task.id, limit=30)
        artifact_records = await self.artifacts.list(task.id, limit=30)
        history = [
            {"role": item.role, "content": item.content}
            for item in history_records
            if item.id != user_message.id
        ]
        if active_artifact_id is not None:
            artifact_records.sort(key=lambda item: item.id != active_artifact_id)
        artifacts = [self._artifact_context(item) for item in artifact_records]
        if artifacts and active_artifact_id is not None:
            artifacts[0]["selection"] = {
                "page_id": active_page_id,
                "block_id": active_block_id,
            }
        spec = TaskSpec.model_validate(task.spec)
        explicit_target = extract_explicit_hanzi_target(content)
        if explicit_target is not None and (
            not spec.target_characters
            or (
                content.strip() == task.raw_input.strip()
                and spec.target_characters != [explicit_target]
            )
        ):
            previous_target = spec.target_characters[0] if spec.target_characters else None
            spec.target_characters = [explicit_target]
            spec.target_needs_confirmation = False
            if spec.communication_brief is not None:
                spec.communication_brief.target_characters = [explicit_target]
                spec.communication_brief.target_needs_confirmation = False
            task.spec = spec.model_dump(mode="json")
            if previous_target != explicit_target:
                task.evolution_package = None
            await self.repository.save(task)
        character = spec.target_characters[0] if spec.target_characters else None
        plan = await self.provider.plan_conversation_turn(content, history, artifacts, character)
        if character is not None and plan.intent in {
            ConversationIntent.CREATE,
            ConversationIntent.TRANSFORM,
        }:
            plan.needs_glyph_context = True
        if (
            plan.intent in {ConversationIntent.REVISE, ConversationIntent.TRANSFORM}
            and not artifacts
        ):
            plan = ConversationTurnPlan(
                intent=ConversationIntent.CLARIFY,
                action_summary="先确认需要修改或转换的作品",
                needs_glyph_context=False,
            )

        tools_used: list[str] = []
        evolution = await self._prepare_evolution_context(task, character, plan, tools_used)
        web_search_context = await self._search_web(content, plan, tools_used)
        task_context = self._task_context(task, spec, evolution, content)
        output = await self.provider.generate_conversation_turn(
            plan,
            content,
            history,
            task_context,
            artifacts,
            web_search_context,
        )

        artifact_record: CreativeArtifactRecord | None = None
        if output.artifact is not None:
            output.artifact.target_page_id = active_page_id
            output.artifact.target_block_id = active_block_id
            if evolution is not None and not output.artifact.visual_hook_ids:
                output.artifact.visual_hook_ids = [
                    stage.image_id for stage in evolution.glyph_stages if stage.image_id is not None
                ][:6]
            artifact_record = await self.artifacts.create(
                task_id=task.id,
                draft=output.artifact,
                intent=output.intent,
                request_message_id=user_message.id,
            )
            tools_used.append("create_artifact")

        assistant_state: dict[str, Any] = {
            "action_summary": output.action_summary,
            "workspace_view": output.workspace_view,
            "tools_used": tools_used,
            "artifact_id": artifact_record.id if artifact_record is not None else None,
            "web_sources": (web_search_context.get("sources", []) if web_search_context else []),
        }
        assistant_message = await self.messages.add(
            task_id=task.id,
            role="assistant",
            content=output.assistant_message,
            intent=output.intent.value,
            state=assistant_state,
        )
        task.agent_runtime = {
            **(task.agent_runtime or {}),
            "current_phase": "conversation",
            "next_action": output.intent.value,
            "decision_summary": output.action_summary,
            "allowed_actions": [item.value for item in ConversationIntent],
        }
        await self.repository.save(task)
        await self.repository.add_event(
            task.id,
            "conversation",
            "completed",
            output.action_summary,
            {
                "intent": output.intent.value,
                "workspace_view": output.workspace_view,
                "artifact_id": artifact_record.id if artifact_record else None,
                "tools_used": tools_used,
            },
        )
        from character_vein_api.schemas import (
            ConversationMessageResponse,
            CreativeArtifactResponse,
        )

        return ConversationTurnResponse(
            intent=output.intent,
            action_summary=output.action_summary,
            workspace_view=output.workspace_view,
            user_message=ConversationMessageResponse.from_record(user_message),
            assistant_message=ConversationMessageResponse.from_record(assistant_message),
            artifact=(
                CreativeArtifactResponse.from_record(artifact_record)
                if artifact_record is not None
                else None
            ),
            tools_used=tools_used,
        )

    async def _prepare_evolution_context(
        self,
        task: TaskRecord,
        character: str | None,
        plan: ConversationTurnPlan,
        tools_used: list[str],
    ) -> EvolutionPackage | None:
        if character is None or character not in SUPPORTED_DEMO_CHARACTERS:
            return None
        evolution = (
            EvolutionPackage.model_validate(task.evolution_package)
            if task.evolution_package is not None
            else case_evolution_package(character)
        )
        if not plan.needs_glyph_context:
            return evolution
        tools_used.append("search_glyphs")
        if evolution.visual_analysis is None:
            images = await self._representative_images(evolution)
            if images:
                try:
                    analyzer = StoredGlyphVisualAnalyzer(
                        GlyphImageRepository(self.repository.session),
                        self.settings,
                        build_vision_provider(self.settings),
                    )
                    evolution.visual_analysis = await analyzer.analyze(character, images)
                    tools_used.append("analyze_glyphs")
                except (
                    BotoCoreError,
                    ClientError,
                    httpx.HTTPError,
                    KeyError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ):
                    tools_used.append("analyze_glyphs_unavailable")
        task.evolution_package = evolution.model_dump(mode="json")
        await self.repository.save(task)
        return evolution

    async def _representative_images(
        self, evolution: EvolutionPackage
    ) -> list[RetrievedGlyphImage]:
        repository = GlyphImageRepository(self.repository.session)
        images: list[RetrievedGlyphImage] = []
        for stage in evolution.glyph_stages:
            if stage.image_id is None or stage.script_code is None:
                continue
            record = await repository.get_representative(evolution.character, stage.script_code)
            if record is None:
                continue
            images.append(
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
                    score=1,
                    content_url=f"/backend/api/v1/glyph-images/{record.id}",
                )
            )
        return images

    async def _search_web(
        self,
        content: str,
        plan: ConversationTurnPlan,
        tools_used: list[str],
    ) -> dict[str, object] | None:
        api_key = self.settings.llm_api_key.get_secret_value()
        if not plan.needs_web_search or not api_key:
            return None
        try:
            client = AliyunBailianWebSearchClient(
                api_key=api_key,
                compatible_base_url=self.settings.llm_base_url,
                model=self.settings.llm_model,
                timeout_seconds=45,
            )
            snapshot = await client.search(plan.search_query or content, limit=8)
            tools_used.append("search_web")
            return {
                "summary": snapshot.answer,
                "sources": [
                    {"title": item.title, "url": item.url, "site_name": item.site_name}
                    for item in snapshot.sources
                ],
            }
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            tools_used.append("search_web_unavailable")
            return None

    @staticmethod
    def _artifact_context(record: CreativeArtifactRecord) -> dict[str, object]:
        return {
            "id": record.id,
            "lineage_id": record.lineage_id,
            "parent_id": record.parent_id,
            "artifact_type": record.artifact_type,
            "format_label": record.format_label,
            "title": record.title,
            "summary": record.summary,
            "content_markdown": record.content_markdown,
            "rich_document": record.document_json,
            "version": record.version,
        }

    @staticmethod
    def _task_context(
        task: TaskRecord,
        spec: TaskSpec,
        evolution: EvolutionPackage | None,
        message: str,
    ) -> dict[str, object]:
        references: list[dict[str, object]] = []
        glyph_stages: list[dict[str, object]] = []
        visual_analysis: dict[str, object] | None = None
        script_aliases = {
            "甲骨": "甲骨文",
            "金文": "金文",
            "战国": "战国文字",
            "小篆": "篆书",
            "篆书": "篆书",
            "隶书": "隶书",
            "楷书": "楷书",
            "草书": "草书",
        }
        excluded_prefixes = ("不谈", "不要谈", "不比较", "排除", "不包括", "不涉及", "无需")
        requested_scripts = {
            script_type
            for marker, script_type in script_aliases.items()
            if marker in message
            and not any(f"{prefix}{marker}" in message for prefix in excluded_prefixes)
        }
        visual_only = "可见" in message and any(
            marker in message for marker in ("只", "不要解释字源", "不涉及字源")
        )
        if evolution is not None:
            for item in evolution.evidence:
                if item.origin not in {SourceOrigin.WEB, SourceOrigin.USER_UPLOAD} and not (
                    item.origin == SourceOrigin.FIXTURE
                    and item.metadata.get("kind") == "evolution_framework"
                ):
                    continue
                searchable = " ".join(
                    [item.evidence_id, item.source_id, item.title, item.url or ""]
                ).lower()
                if "jiezi" in searchable or item.metadata.get("kind") == "glyph_dataset":
                    continue
                references.append(
                    {
                        "reference_id": item.evidence_id,
                        "title": item.title,
                        "author_or_org": item.author_or_org,
                        "url": item.url,
                        "content": item.quote_or_summary[:1600],
                    }
                )
            glyph_stages = [
                {
                    "image_id": stage.image_id,
                    "script_type": stage.script_type,
                    "period": stage.period,
                    "structure_description": (
                        ""
                        if any(
                            marker in stage.structure_description.lower()
                            for marker in ("jiezi", "元数据", "原始路径", "u+")
                        )
                        else stage.structure_description
                    ),
                }
                for stage in evolution.glyph_stages
                if stage.image_id is not None
                and (not requested_scripts or stage.script_type in requested_scripts)
            ]
            if evolution.visual_analysis is not None:
                visual_analysis = {
                    "stage_observations": [
                        {
                            "script_type": item.script_type,
                            "visible_features": item.visible_features,
                            "composition": item.composition,
                            "stroke_form": item.stroke_form,
                        }
                        for item in evolution.visual_analysis.stage_observations
                        if not requested_scripts or item.script_type in requested_scripts
                    ],
                    "overall_summary": (
                        "" if requested_scripts else evolution.visual_analysis.overall_summary
                    ),
                    "warnings": evolution.visual_analysis.warnings,
                }
        return {
            "initial_request": task.raw_input,
            "character": spec.target_characters[0] if spec.target_characters else None,
            "theme": spec.theme,
            "audience": spec.audience,
            "constraints": spec.constraints,
            "user_documents": spec.source_contexts[:12],
            "glyph_stages": glyph_stages,
            "glyph_visual_analysis": visual_analysis,
            "reference_materials": [] if visual_only else references[:20],
            "response_scope": "visual_features_only" if visual_only else "general",
            "selected_narrative_route": task.selected_route_id,
        }
