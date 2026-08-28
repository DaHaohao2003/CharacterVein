import asyncio
import hashlib
import re
import uuid
from io import BytesIO
from pathlib import PurePath

import boto3  # type: ignore[import-untyped]
from PIL import Image

from character_vein_api.config import Settings, get_settings
from character_vein_api.document_processing import analyze_document_text, extract_document_text
from character_vein_api.glyph_visual_analysis import build_vision_provider
from character_vein_api.models import AssetRecord
from character_vein_api.repositories import AssetRepository
from character_vein_domain import AssetKind, AssetOrigin, AssetStatus
from character_vein_providers import VisionModelProvider

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
DOCUMENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
}
EXTENSION_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
    "markdown": "text/markdown",
}


class AssetService:
    def __init__(self, repository: AssetRepository, settings: Settings | None = None) -> None:
        self.repository = repository
        self.settings = settings or get_settings()

    async def upload(self, filename: str, mime_type: str, content: bytes) -> AssetRecord:
        filename = PurePath(filename or "upload").name
        mime_type = self._resolve_mime(filename, mime_type)
        kind = self._kind(mime_type)
        limit = (
            self.settings.asset_max_image_bytes
            if kind == AssetKind.IMAGE
            else self.settings.asset_max_document_bytes
        )
        if not content:
            raise ValueError("上传文件为空")
        if len(content) > limit:
            raise ValueError(f"文件超过大小限制（{limit // 1024 // 1024} MB）")
        if kind == AssetKind.IMAGE:
            self._validate_image(content)

        asset_id = str(uuid.uuid4())
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "upload"
        storage_key = f"user-uploads/{asset_id}/{safe_name}"
        record = AssetRecord(
            id=asset_id,
            origin=AssetOrigin.USER_UPLOAD.value,
            kind=kind.value,
            status=AssetStatus.PROCESSING.value,
            storage_key=storage_key,
            mime_type=mime_type,
            filename=filename,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            extracted_text="",
            analysis_json={},
        )
        await self.repository.create(record)
        try:
            await asyncio.to_thread(self._put_object, storage_key, mime_type, content)
            if kind == AssetKind.IMAGE:
                analysis = await self._vision_provider().analyze_image(content, mime_type)
                if analysis.extracted_text:
                    modern_text = analyze_document_text(analysis.extracted_text)
                    # A target is accepted only when explicit modern OCR text corroborates it.
                    analysis.target_characters = modern_text.target_characters
                    analysis.explicit_periods = (
                        analysis.explicit_periods or modern_text.explicit_periods
                    )
                    analysis.themes = analysis.themes or modern_text.themes
                    analysis.user_sources = analysis.user_sources or modern_text.user_sources
                else:
                    analysis.target_characters = []
                analysis.requires_target_confirmation = not analysis.target_characters
            else:
                text = extract_document_text(content, mime_type, filename)
                analysis = analyze_document_text(text)
            record.extracted_text = analysis.extracted_text
            record.analysis_json = analysis.model_dump(mode="json")
            record.status = AssetStatus.COMPLETED.value
            record.error_message = None
            return await self.repository.save(record)
        except Exception as exc:
            record.status = AssetStatus.FAILED.value
            record.error_message = str(exc)
            await self.repository.save(record)
            raise ValueError(f"文件处理失败：{exc}") from exc

    def _put_object(self, key: str, mime_type: str, content: bytes) -> None:
        client = boto3.client(
            "s3",
            endpoint_url=str(self.settings.s3_endpoint_url),
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            region_name=self.settings.s3_region,
        )
        client.put_object(
            Bucket=self.settings.s3_bucket,
            Key=key,
            Body=content,
            ContentType=mime_type,
        )

    def _vision_provider(self) -> VisionModelProvider:
        return build_vision_provider(self.settings)

    @staticmethod
    def _resolve_mime(filename: str, supplied: str) -> str:
        suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        return EXTENSION_TYPES.get(suffix, supplied.split(";", 1)[0].lower())

    @staticmethod
    def _kind(mime_type: str) -> AssetKind:
        if mime_type in IMAGE_TYPES:
            return AssetKind.IMAGE
        if mime_type in DOCUMENT_TYPES:
            return AssetKind.DOCUMENT
        raise ValueError("仅支持 JPG、PNG、WEBP、PDF、DOCX、TXT 和 Markdown 文件")

    @staticmethod
    def _validate_image(content: bytes) -> None:
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            if width < 11 or height < 11:
                raise ValueError("图像宽高必须大于 10 像素")
            image.verify()
