import logging

from app.ai.embeddings import EmbeddingProvider, GeminiEmbeddingProvider, MockEmbeddingProvider
from app.ai.providers.base import AIProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.mock import MockAIProvider
from app.core.config import Settings

logger = logging.getLogger("socialpilot.ai")


def build_ai(settings: Settings) -> tuple[AIProvider, EmbeddingProvider] | None:
    """None when AI is selected but credentials are missing. The app still starts."""
    if settings.ai_provider == "mock":
        return MockAIProvider(), MockEmbeddingProvider()
    if not settings.gemini_api_key:
        logger.warning("ai_not_configured")
        return None
    provider = GeminiProvider(settings)
    return provider, GeminiEmbeddingProvider(provider._client, settings.embedding_model)
