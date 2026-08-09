import asyncio
import base64
import json
import re
from typing import Protocol

import httpx

from character_vein_domain import AssetAnalysis


class VisionModelProvider(Protocol):
    async def analyze_image(self, content: bytes, mime_type: str) -> AssetAnalysis: ...


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


class AliyunQwenOcrProvider:
    """Modern-label OCR/VLM adapter; ancient-glyph identification is explicitly excluded."""

    def __init__(self, api_key: str, base_url: str, model: str = "qwen-vl-ocr") -> None:
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
