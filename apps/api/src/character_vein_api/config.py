from functools import lru_cache

from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "字脉 API"
    app_env: str = "development"
    app_log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    web_origin: AnyHttpUrl = AnyHttpUrl("http://localhost:3000")
    database_url: str = (
        "postgresql+asyncpg://character_vein:character_vein_dev@localhost:5432/character_vein"
    )
    checkpoint_database_url: str = (
        "postgresql://character_vein:character_vein_dev@localhost:5432/character_vein"
    )
    s3_endpoint_url: AnyHttpUrl = AnyHttpUrl("http://localhost:9000")
    s3_access_key: str = "character_vein"
    s3_secret_key: str = "character_vein_dev_secret"
    s3_bucket: str = "character-vein"
    s3_region: str = "us-east-1"
    glyph_image_root: str = "/data/jiezi-images"
    glyph_object_prefix: str = "jiezi-demo"
    llm_provider: str = "deterministic"
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen3.8-flash"
    llm_audit_enabled: bool = True
    embedding_provider: str = ""
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    web_search_provider: str = "disabled"
    vlm_provider: str = ""
    vlm_base_url: str = ""
    vlm_model: str = "qwen3.8-flash"
    asset_max_image_bytes: int = 10 * 1024 * 1024
    asset_max_document_bytes: int = 20 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
