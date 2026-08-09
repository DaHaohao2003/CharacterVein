from typing import Any

import pytest

from character_vein_providers import AliyunBailianEmbeddingProvider


class _FakeResponse:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, list[dict[str, Any]]]:
        return {"data": self._rows}


class _FakeAsyncClient:
    batch_lengths: list[int] = []

    def __init__(self, **_kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def post(
        self,
        _url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> _FakeResponse:
        assert headers["Authorization"] == "Bearer test-key"
        batch = json["input"]
        assert isinstance(batch, list)
        self.batch_lengths.append(len(batch))
        return _FakeResponse(
            [
                {"index": index, "embedding": [float(index + 1), 0.0, 0.0]}
                for index in range(len(batch))
            ]
        )


async def test_aliyun_embeddings_are_requested_in_bounded_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeAsyncClient.batch_lengths = []
    monkeypatch.setattr(
        "character_vein_providers.embedding.httpx.AsyncClient", _FakeAsyncClient
    )
    provider = AliyunBailianEmbeddingProvider(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="embedding-test",
        dimensions=3,
        batch_size=2,
    )

    vectors = await provider.embed(["一", "二", "三", "四", "五"])

    assert len(vectors) == 5
    assert _FakeAsyncClient.batch_lengths == [2, 2, 1]
    assert provider.last_request_count == 3
    assert provider.last_fallback_used is False


def test_aliyun_embedding_batch_size_must_be_positive() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        AliyunBailianEmbeddingProvider(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="embedding-test",
            batch_size=0,
        )
