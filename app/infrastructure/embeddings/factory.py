"""Factory for embedding providers."""

from __future__ import annotations

import httpx

from app.core.config import EmbeddingProviderName, Settings
from app.core.logging import get_logger
from app.infrastructure.embeddings.hash_embeddings import HashEmbeddingProvider
from app.infrastructure.embeddings.openai_embeddings import OpenAIEmbeddingProvider
from app.interfaces.embeddings import EmbeddingProvider

logger = get_logger(__name__)


def build_embedding_provider(settings: Settings, client: httpx.AsyncClient) -> EmbeddingProvider:
    """Build the embedding provider based on the configuration.

    If OpenAI is requested but no API key is available, fall back to the
    deterministic hash provider so the system can still start (with a log
    warning).
    """
    if settings.embedding_provider == EmbeddingProviderName.OPENAI:
        if settings.openai_api_key:
            return OpenAIEmbeddingProvider(
                settings.openai_api_key,
                settings.embedding_model,
                settings.embedding_dim,
                client=client,
            )
        logger.warning(
            "embedding.fallback_to_hash",
            reason="OPENAI_API_KEY ausente; usando embeddings hash",
        )
    return HashEmbeddingProvider(dimension=settings.embedding_dim)
