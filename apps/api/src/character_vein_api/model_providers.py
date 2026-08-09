from character_vein_api.config import Settings
from character_vein_providers import (
    AliyunBailianEmbeddingProvider,
    AliyunBailianTextProvider,
    DeterministicEmbeddingProvider,
    DeterministicTextProvider,
    EmbeddingProvider,
    TextModelProvider,
)


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    provider_name = settings.embedding_provider or settings.llm_provider
    api_key = settings.llm_api_key.get_secret_value()
    if provider_name == "aliyun-bailian" and api_key:
        return AliyunBailianEmbeddingProvider(
            api_key=api_key,
            base_url=settings.llm_base_url,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    return DeterministicEmbeddingProvider()


def build_text_provider(settings: Settings) -> TextModelProvider:
    api_key = settings.llm_api_key.get_secret_value()
    if settings.llm_provider == "aliyun-bailian" and api_key:
        return AliyunBailianTextProvider(
            api_key=api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    return DeterministicTextProvider()
