"""Agent 3 — Duplicate Detector.

Avoids publishing repeated news. It applies two layers of defense:
  1. Exact URL match (normalized SHA-256 fingerprint).
  2. Semantic similarity via embeddings (cosine distance) against the history.

The embedding provider and the repository are injected, so the model or the
vector store can be swapped without touching this agent.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger
from app.domain.entities import NewsItem
from app.interfaces.agent import Agent
from app.interfaces.embeddings import EmbeddingProvider
from app.interfaces.repositories import NewsRepository

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DuplicateDecision:
    """Result of the duplicate analysis of a news item."""

    item: NewsItem
    is_duplicate: bool
    reason: str
    embedding: list[float]
    best_similarity: float = 0.0


class DuplicateDetectorAgent(Agent[NewsItem, DuplicateDecision]):
    """Decides whether a news item duplicates something already published."""

    name = "duplicate_detector"

    def __init__(
        self,
        repository: NewsRepository,
        embeddings: EmbeddingProvider,
        *,
        similarity_threshold: float,
    ) -> None:
        self._repo = repository
        self._embeddings = embeddings
        self._threshold = similarity_threshold

    async def run(self, input_data: NewsItem) -> DuplicateDecision:
        embedding = await self._embeddings.embed(input_data.embedding_text)

        if await self._repo.url_exists(input_data.url_fingerprint):
            logger.info("duplicate.url_match", url=input_data.url)
            return DuplicateDecision(
                item=input_data,
                is_duplicate=True,
                reason="url_already_published",
                embedding=embedding,
                best_similarity=1.0,
            )

        similar = await self._repo.find_similar(embedding, self._threshold, limit=1)
        if similar:
            top = similar[0]
            logger.info(
                "duplicate.semantic_match",
                url=input_data.url,
                similar_to=top.url,
                similarity=round(top.similarity, 4),
            )
            return DuplicateDecision(
                item=input_data,
                is_duplicate=True,
                reason="semantically_similar",
                embedding=embedding,
                best_similarity=top.similarity,
            )

        return DuplicateDecision(
            item=input_data,
            is_duplicate=False,
            reason="unique",
            embedding=embedding,
        )
