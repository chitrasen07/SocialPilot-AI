import hashlib
import math
import re
from typing import Protocol

from app.models import EMBEDDING_DIMENSIONS

# Keyword axes live in the first dimensions. Text with none of them is hashed into the
# remaining dimensions, so unrelated text stays orthogonal (cosine distance 1).
_AXES: tuple[tuple[int, str], ...] = (
    (0, r"\bshoes?\b|షూస్"),
    (1, r"\bblue\b|బ్లూ"),
    (2, r"\b(price|pricing|cost|kitna)\b|₹|कीमत|ధర"),
    (3, r"\breturns?\b|\brefunds?\b"),
    (4, r"\b(shipping|delivery)\b"),
    (5, r"\bsizes?\b"),
)


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...

    async def embed_many(self, texts: list[str]) -> list[list[float]]: ...


class MockEmbeddingProvider:
    """Deterministic vectors for tests. Same text always maps to the same point.

    Related business phrases land near each other. This is not a semantic model.
    Gemini embeddings are used when AI_PROVIDER=gemini.
    """

    async def embed(self, text: str) -> list[float]:
        return _mock_vector(text)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [_mock_vector(text) for text in texts]


def _mock_vector(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    matched = False
    for axis, pattern in _AXES:
        if re.search(pattern, text, re.I):
            vector[axis] = 1.0
            matched = True
    if not matched:
        digest = hashlib.sha256(text.encode()).digest()
        for offset in range(0, 24, 2):
            index = 64 + (
                int.from_bytes(digest[offset : offset + 2], "big") % (EMBEDDING_DIMENSIONS - 64)
            )
            vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class GeminiEmbeddingProvider:
    def __init__(self, client: object, model: str) -> None:
        self._client = client
        self._model = model

    async def embed(self, text: str) -> list[float]:
        vectors = await self.embed_many([text])
        return vectors[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        from google.genai import types
        from starlette.concurrency import run_in_threadpool

        from app.ai.errors import ai_provider_failed

        def call() -> list[list[float]]:
            response = self._client.models.embed_content(  # type: ignore[attr-defined]
                model=self._model,
                contents=[text[:8000] for text in texts],
                config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
            )
            return [list(item.values) for item in response.embeddings]

        try:
            vectors = await run_in_threadpool(call)
        except Exception as exc:
            raise ai_provider_failed() from exc
        if len(vectors) != len(texts) or any(
            len(vector) != EMBEDDING_DIMENSIONS for vector in vectors
        ):
            raise ai_provider_failed()
        return vectors
