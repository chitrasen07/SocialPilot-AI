import hashlib
import math
from typing import Protocol

from app.models import EMBEDDING_DIMENSIONS


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class MockEmbeddingProvider:
    """Stable unit vector from a hash. Same text always maps to the same point."""

    async def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        values: list[float] = []
        while len(values) < EMBEDDING_DIMENSIONS:
            digest = hashlib.sha256(digest).digest()
            values.extend((byte - 128) / 128 for byte in digest)
        vector = values[:EMBEDDING_DIMENSIONS]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class GeminiEmbeddingProvider:
    def __init__(self, client: object, model: str) -> None:
        self._client = client
        self._model = model

    async def embed(self, text: str) -> list[float]:
        from google.genai import types
        from starlette.concurrency import run_in_threadpool

        from app.ai.errors import ai_provider_failed

        def call() -> list[float]:
            response = self._client.models.embed_content(  # type: ignore[attr-defined]
                model=self._model,
                contents=text[:8000],
                config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
            )
            return list(response.embeddings[0].values)

        try:
            vector = await run_in_threadpool(call)
        except Exception as exc:
            raise ai_provider_failed() from exc
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ai_provider_failed()
        return vector
