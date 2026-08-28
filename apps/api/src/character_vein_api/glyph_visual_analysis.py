import asyncio
from typing import cast

import boto3  # type: ignore[import-untyped]

from character_vein_api.config import Settings
from character_vein_api.repositories import GlyphImageRepository
from character_vein_domain import GlyphLineageRole, GlyphVisualAnalysis, RetrievedGlyphImage
from character_vein_providers import (
    AliyunQwenVisionProvider,
    DeterministicVisionProvider,
    GlyphVisionInput,
    VisionModelProvider,
)


def build_vision_provider(settings: Settings) -> VisionModelProvider:
    provider_name = settings.vlm_provider or settings.llm_provider
    api_key = settings.llm_api_key.get_secret_value()
    if provider_name == "aliyun-bailian" and api_key:
        return AliyunQwenVisionProvider(
            api_key=api_key,
            base_url=settings.vlm_base_url or settings.llm_base_url,
            model=settings.vlm_model,
        )
    return DeterministicVisionProvider()


class StoredGlyphVisualAnalyzer:
    def __init__(
        self,
        repository: GlyphImageRepository,
        settings: Settings,
        provider: VisionModelProvider,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.provider = provider

    async def analyze(
        self, character: str, images: list[RetrievedGlyphImage]
    ) -> GlyphVisualAnalysis:
        selected = images[:8]
        records = []
        for image in selected:
            record = await self.repository.get(image.image_id)
            if record is None or record.character != character:
                continue
            records.append((image, record.storage_key, record.mime_type))

        def load_images() -> list[GlyphVisionInput]:
            client = boto3.client(
                "s3",
                endpoint_url=str(self.settings.s3_endpoint_url),
                aws_access_key_id=self.settings.s3_access_key,
                aws_secret_access_key=self.settings.s3_secret_key,
                region_name=self.settings.s3_region,
            )
            loaded: list[GlyphVisionInput] = []
            for image, storage_key, mime_type in records:
                response = client.get_object(Bucket=self.settings.s3_bucket, Key=storage_key)
                try:
                    content = cast(bytes, response["Body"].read())
                finally:
                    response["Body"].close()
                loaded.append(
                    GlyphVisionInput(
                        image_id=image.image_id,
                        script_type=image.script_type,
                        mime_type=mime_type,
                        content=content,
                    )
                )
            return loaded

        inputs = await asyncio.to_thread(load_images)
        available_ids = {item.image_id for item in inputs}
        mainline = [
            item
            for item in selected
            if item.lineage_role != GlyphLineageRole.BRANCH and item.image_id in available_ids
        ]
        pairs = [
            (mainline[index - 1].image_id, mainline[index].image_id)
            for index in range(1, len(mainline))
        ]
        branches = [
            item
            for item in selected
            if item.lineage_role == GlyphLineageRole.BRANCH and item.image_id in available_ids
        ]
        branch_anchor = next(
            (item for item in mainline if item.script_type == "隶书"),
            mainline[-1] if mainline else None,
        )
        if branch_anchor is not None:
            pairs.extend((branch_anchor.image_id, item.image_id) for item in branches)
        return await self.provider.analyze_glyph_sequence(character, inputs, pairs)
