import asyncio
import base64
import json
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from character_vein_domain import AssetAnalysis, GlyphVisualAnalysis


@dataclass(frozen=True)
class GlyphVisionInput:
    image_id: str
    script_type: str
    mime_type: str
    content: bytes


class VisionModelProvider(Protocol):
    async def analyze_image(self, content: bytes, mime_type: str) -> AssetAnalysis: ...

    async def analyze_glyph_sequence(
        self,
        character: str,
        images: list[GlyphVisionInput],
        comparison_pairs: list[tuple[str, str]],
    ) -> GlyphVisualAnalysis: ...


class DeterministicVisionProvider:
    """Safe fallback: preserve the image as context without guessing ancient glyphs."""

    async def analyze_image(self, content: bytes, mime_type: str) -> AssetAnalysis:
        del content, mime_type
        return AssetAnalysis(
            warnings=["图像模型不可用，系统未尝试识别古文字；请人工填写要讲解的目标汉字。"],
            uncertain_glyphs=True,
            requires_target_confirmation=True,
            model="deterministic-safe-fallback",
            fallback_used=True,
        )

    async def analyze_glyph_sequence(
        self,
        character: str,
        images: list[GlyphVisionInput],
        comparison_pairs: list[tuple[str, str]],
    ) -> GlyphVisualAnalysis:
        del images, comparison_pairs
        return GlyphVisualAnalysis(
            character=character,
            warnings=["多模态模型不可用，未生成字形视觉观察。"],
            model="deterministic-safe-fallback",
            fallback_used=True,
        )


class AliyunQwenVisionProvider:
    """General visual adapter for modern OCR and labelled glyph observation."""

    def __init__(self, api_key: str, base_url: str, model: str = "qwen3.8-flash") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.fallback = DeterministicVisionProvider()

    async def analyze_image(self, content: bytes, mime_type: str) -> AssetAnalysis:
        encoded = base64.b64encode(content).decode("ascii")
        prompt = (
            "你是博物馆展签与现代印刷文字的信息提取器。只读取清晰的现代文字，"
            "禁止根据甲骨文、金文、篆书等古文字字形猜测它是什么汉字。若目标汉字没有在"
            "现代文字中被明确写出，target_characters 必须为空，并把 "
            "requires_target_confirmation 和 uncertain_glyphs 设为 true。"
            "返回且只返回 JSON："
            '{"target_characters":[],"extracted_text":"","artifact_names":[],"explicit_periods":[],'
            '"themes":[],"user_sources":[],"warnings":[],"uncertain_glyphs":false,'
            '"requires_target_confirmation":false}。target_characters 中每项只能是单个汉字。'
        )
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "temperature": 0,
            "enable_thinking": False,
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                for attempt in range(2):
                    try:
                        response = await client.post(
                            f"{self.base_url}/chat/completions",
                            headers={"Authorization": f"Bearer {self.api_key}"},
                            json=payload,
                        )
                        break
                    except (httpx.ConnectError, httpx.TimeoutException):
                        if attempt == 1:
                            raise
                        await asyncio.sleep(1)
                response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
            parsed = self._parse_json(raw)
            analysis = AssetAnalysis.model_validate(parsed)
            analysis.target_characters = [
                item for item in analysis.target_characters if len(item) == 1
            ]
            analysis.model = self.model
            analysis.fallback_used = False
            if not analysis.target_characters:
                analysis.requires_target_confirmation = True
            return analysis
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            analysis = await self.fallback.analyze_image(content, mime_type)
            analysis.warnings.append(f"图像分析失败，已进入安全回退：{type(exc).__name__}")
            return analysis

    async def analyze_glyph_sequence(
        self,
        character: str,
        images: list[GlyphVisionInput],
        comparison_pairs: list[tuple[str, str]],
    ) -> GlyphVisualAnalysis:
        if not images:
            return await self.fallback.analyze_glyph_sequence(character, images, comparison_pairs)
        valid_images = {item.image_id: item for item in images}
        valid_pairs = {
            pair for pair in comparison_pairs if pair[0] in valid_images and pair[1] in valid_images
        }
        content_blocks: list[dict[str, object]] = []
        for index, image in enumerate(images, start=1):
            encoded = base64.b64encode(image.content).decode("ascii")
            content_blocks.extend(
                [
                    {
                        "type": "text",
                        "text": (
                            f"图片 {index}：已知目标字“{character}”，"
                            f"书体标签“{image.script_type}”，"
                            f"image_id={image.image_id}。"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image.mime_type};base64,{encoded}",
                        },
                    },
                ]
            )
        content_blocks.append(
            {
                "type": "text",
                "text": (
                    "你是字形视觉观察助手。目标汉字和每张图的书体标签已经由数据库给出，"
                    "不要识别或猜测图片是什么字，不要根据图像判断年代、出处、本义或直接传承关系。"
                    "只描述图片中可见的外轮廓、构件相对位置、方向、疏密、对称性、线条曲直和连接方式。"
                    "对长宽比例、裁切或缺笔保持谨慎。返回且只返回 JSON："
                    '{"stage_observations":[{"image_id":"...","script_type":"...",'
                    '"visible_features":["..."],"composition":"...","stroke_form":"..."}],'
                    '"comparisons":[{"from_image_id":"...","to_image_id":"...",'
                    '"visible_changes":["..."],"summary":"..."}],'
                    '"overall_summary":"...","warnings":[]}。'
                    f"只允许比较这些 image_id 对：{sorted(valid_pairs)}。"
                ),
            }
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content_blocks}],
            "temperature": 0,
            "enable_thinking": False,
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
            raw = self._message_text(response.json()["choices"][0]["message"]["content"])
            parsed = self._parse_json(raw)
            analysis = GlyphVisualAnalysis.model_validate(
                {**parsed, "character": character, "model": self.model, "fallback_used": False}
            )
            analysis.stage_observations = [
                item
                for item in analysis.stage_observations
                if item.image_id in valid_images
                and item.script_type == valid_images[item.image_id].script_type
            ]
            analysis.comparisons = [
                item
                for item in analysis.comparisons
                if (item.from_image_id, item.to_image_id) in valid_pairs
            ]
            filtered = False
            for observation in analysis.stage_observations:
                original_features = list(observation.visible_features)
                observation.visible_features = [
                    value
                    for value in (
                        self._visible_text(item, observation.script_type)
                        for item in observation.visible_features
                    )
                    if value
                ]
                original_composition = observation.composition
                original_stroke_form = observation.stroke_form
                observation.composition = self._visible_text(
                    observation.composition, observation.script_type
                )
                observation.stroke_form = self._visible_text(
                    observation.stroke_form, observation.script_type
                )
                filtered = filtered or (
                    original_features != observation.visible_features
                    or original_composition != observation.composition
                    or original_stroke_form != observation.stroke_form
                )
            valid_comparisons = []
            for comparison in analysis.comparisons:
                original_changes = list(comparison.visible_changes)
                comparison.visible_changes = [
                    value
                    for value in (self._visible_text(item) for item in comparison.visible_changes)
                    if value
                ]
                filtered = filtered or original_changes != comparison.visible_changes
                if comparison.visible_changes:
                    comparison.summary = "对照两张已标注图片可见：" + "；".join(
                        comparison.visible_changes[:3]
                    )
                    valid_comparisons.append(comparison)
            analysis.comparisons = valid_comparisons
            analysis.overall_summary = (
                f"多模态模型读取了 {len(images)} 张已标注字形图片；"
                "以下结果只保留外轮廓、构件位置、疏密和线条形态等可见信息。"
            )
            if filtered:
                analysis.warnings.append("模型原始输出已按“只描述可见特征”规则过滤。")
            if not analysis.stage_observations:
                raise ValueError("多模态模型没有返回有效字形观察")
            return analysis
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            analysis = await self.fallback.analyze_glyph_sequence(
                character, images, comparison_pairs
            )
            analysis.warnings.append(f"字形视觉分析失败，已安全降级：{type(exc).__name__}")
            return analysis

    @staticmethod
    def _parse_json(raw: str) -> dict[str, object]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match is None:
            raise ValueError("模型响应中没有 JSON 对象")
        value = json.loads(match.group(0))
        if not isinstance(value, dict):
            raise ValueError("模型响应不是 JSON 对象")
        return value

    @staticmethod
    def _message_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        raise TypeError("模型响应内容类型不受支持")

    @staticmethod
    def _visible_text(value: str, own_script_type: str | None = None) -> str:
        text = value.strip()
        if not text:
            return ""
        forbidden = re.compile(
            "象形|会意|表意|本义|含义|代表|象征|模拟|演变|演化|发展|传承|"
            "源于|来源于|基础|规范|标准|时代|年代|古人|现代汉字|文字系统|"
            "隶变|书写速度|书写|笔法|风格|艺术|气势|规律|符号|字源|语义|意象|"
            "功能|用途|典型|云气|天气|摆脱|恢复|重新|早期|中期|晚期"
        )
        if forbidden.search(text):
            return ""
        if own_script_type is not None:
            other_scripts = {
                "甲骨文",
                "金文",
                "战国文字",
                "篆书",
                "隶书",
                "楷书",
                "草书",
            } - {own_script_type}
            if any(script in text for script in other_scripts):
                return ""
        return text


# Compatibility name for callers created when this adapter only performed OCR.
AliyunQwenOcrProvider = AliyunQwenVisionProvider
