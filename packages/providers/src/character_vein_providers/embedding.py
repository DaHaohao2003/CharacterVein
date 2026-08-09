import hashlib
import json
import math
from typing import Protocol

import httpx


class EmbeddingProvider(Protocol):
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class DeterministicEmbeddingProvider:
    """Stable local embeddings for repeatable hybrid-retrieval tests and fallback."""

    dimensions = 1024

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        normalized = "".join(text.lower().split())
        tokens = list(normalized)
        tokens.extend(normalized[index : index + 2] for index in range(len(normalized) - 1))
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(item * item for item in vector)) or 1.0
        return [item / norm for item in vector]


class AliyunBailianEmbeddingProvider:
    """OpenAI-compatible embedding adapter with a deterministic offline fallback."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        dimensions: int = 1024,
        timeout_seconds: float = 45,
        batch_size: int = 10,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size
        self.fallback = DeterministicEmbeddingProvider()
        self.last_fallback_used = False
        self.last_request_count = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self.last_request_count = 0
        try:
            vectors: list[list[float]] = []
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                for offset in range(0, len(texts), self.batch_size):
                    batch = texts[offset : offset + self.batch_size]
                    response = await client.post(
                        f"{self.base_url}/embeddings",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": self.model,
                            "input": batch,
                            "dimensions": self.dimensions,
                        },
                    )
                    self.last_request_count += 1
                    response.raise_for_status()
                    payload = response.json()
                    rows = sorted(
                        payload["data"], key=lambda item: int(item["index"])
                    )
                    batch_vectors = [
                        [float(value) for value in item["embedding"]]
                        for item in rows
                    ]
                    if len(batch_vectors) != len(batch):
                        raise ValueError("embedding response count is invalid")
                    vectors.extend(batch_vectors)
            if len(vectors) != len(texts) or any(
                len(vector) != self.dimensions for vector in vectors
            ):
                raise ValueError("embedding response count or dimensions are invalid")
            self.last_fallback_used = False
            return vectors
        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            self.last_fallback_used = True
            return await self.fallback.embed(texts)
