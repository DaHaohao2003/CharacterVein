from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
from pathlib import Path

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from character_vein_api.config import get_settings
from character_vein_api.database import async_session_factory
from character_vein_api.repositories import GlyphImageRepository
from character_vein_domain import GlyphCatalogStage
from character_vein_providers import DeterministicEmbeddingProvider
from character_vein_workflows.jiezi_catalog import glyph_catalog


def _image_root() -> Path:
    configured = Path(get_settings().glyph_image_root)
    if configured.is_dir():
        return configured
    return Path(__file__).resolve().parents[4] / ".data" / "jiezi" / "JieZi-Dataset" / "images"


def _retrieval_text(character: str, stage: GlyphCatalogStage) -> str:
    values = [
        character,
        stage.script_type,
        stage.historical_period,
        stage.region_or_system or "",
        stage.structure,
        stage.special_structure,
        stage.evolution,
        stage.original_meaning,
    ]
    return "；".join(str(value) for value in values if value)


def _variant_index(source_path: str, fallback: int) -> int:
    stem = Path(source_path).stem
    return int(stem) if stem.isdecimal() else fallback


async def import_glyph_images() -> dict[str, int]:
    settings = get_settings()
    root = _image_root()
    if not root.is_dir():
        raise FileNotFoundError(f"JieZi demo image directory does not exist: {root}")

    s3 = boto3.client(
        "s3",
        endpoint_url=str(settings.s3_endpoint_url),
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )
    pending: list[dict[str, object]] = []
    texts: list[str] = []
    uploaded = 0
    reused = 0

    for character in glyph_catalog().characters:
        for stage in character.stages:
            retrieval_text = _retrieval_text(character.character, stage)
            for fallback_index, source_path in enumerate(stage.image_paths, start=1):
                variant_index = _variant_index(source_path, fallback_index)
                relative = source_path.removeprefix("JieZi-Dataset/images/")
                local_path = root / Path(relative)
                content = local_path.read_bytes()
                digest = hashlib.sha256(content).hexdigest()
                mime_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
                storage_key = f"{settings.glyph_object_prefix}/{relative}"
                try:
                    head = s3.head_object(Bucket=settings.s3_bucket, Key=storage_key)
                    already_present = head.get("Metadata", {}).get("sha256") == digest
                except ClientError:
                    already_present = False
                if already_present:
                    reused += 1
                else:
                    s3.put_object(
                        Bucket=settings.s3_bucket,
                        Key=storage_key,
                        Body=content,
                        ContentType=mime_type,
                        Metadata={"sha256": digest},
                    )
                    uploaded += 1
                pending.append(
                    {
                        "id": relative,
                        "character": character.character,
                        "codepoint": character.codepoint,
                        "script_type": stage.script_type,
                        "script_code": stage.script_code,
                        "historical_period": stage.historical_period,
                        "lineage_role": stage.lineage_role.value,
                        "region_or_system": stage.region_or_system,
                        "source_path": source_path,
                        "storage_key": storage_key,
                        "mime_type": mime_type,
                        "size_bytes": len(content),
                        "sha256": digest,
                        "retrieval_text": retrieval_text,
                        "metadata": {
                            "is_representative": source_path == stage.representative_source_path,
                            "variant_index": variant_index,
                            "structure": stage.structure,
                            "special_structure": stage.special_structure,
                            "evolution": stage.evolution,
                            "original_meaning": stage.original_meaning,
                        },
                    }
                )
                texts.append(retrieval_text)

    embeddings = await DeterministicEmbeddingProvider().embed(texts)
    for values, embedding in zip(pending, embeddings, strict=True):
        values["embedding"] = embedding

    async with async_session_factory() as session:
        repository = GlyphImageRepository(session)
        await repository.delete_not_in([str(item["id"]) for item in pending])
        for start in range(0, len(pending), 100):
            await repository.upsert_many(pending[start : start + 100])
        stored = await repository.count()

    return {"selected": len(pending), "stored": stored, "uploaded": uploaded, "reused": reused}


def main() -> None:
    print(json.dumps(asyncio.run(import_glyph_images()), ensure_ascii=False))


if __name__ == "__main__":
    main()
