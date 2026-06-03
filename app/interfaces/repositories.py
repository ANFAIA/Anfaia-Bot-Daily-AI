"""Persistence ports (repositories).

The domain and the application depend on these abstractions; the concrete
implementation lives in `app/database` and uses SQLAlchemy + PostgreSQL.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.domain.entities import PublishableArticle
from app.domain.value_objects import Category


@dataclass(frozen=True, slots=True)
class StoredArticle:
    """Read projection of an already persisted news item."""

    id: int
    title: str
    url: str
    source: str
    category: Category
    relevance_score: int
    summary: str
    published_at: datetime | None
    discord_message_id: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SimilarArticle:
    """Result of a semantic similarity search."""

    article_id: int
    url: str
    similarity: float


@dataclass(frozen=True, slots=True)
class StatsSnapshot:
    """Aggregates for the `/stats` admin endpoint."""

    analyzed: int
    published: int
    discarded: int
    by_category: dict[str, int]
    last_run_at: str | None
    last_run_status: str | None


class NewsRepository(ABC):
    """Persistence of the news history and their embeddings."""

    @abstractmethod
    async def url_exists(self, url_fingerprint: str) -> bool:
        """True if a news item with that URL fingerprint has already been published."""

    @abstractmethod
    async def find_similar(
        self, embedding: list[float], threshold: float, limit: int = 5
    ) -> list[SimilarArticle]:
        """Return articles whose cosine similarity exceeds `threshold`."""

    @abstractmethod
    async def save_published(
        self, article: PublishableArticle, embedding: list[float] | None
    ) -> int:
        """Persist a published article and its embedding. Return the id."""

    @abstractmethod
    async def increment_counter(self, name: str, amount: int = 1) -> None:
        """Accumulate an aggregate counter (analyzed, discarded, ...)."""

    @abstractmethod
    async def list_articles(
        self, *, limit: int, offset: int, category: Category | None = None
    ) -> list[StoredArticle]:
        """List published articles, optionally filtered by category."""

    @abstractmethod
    async def get_article(self, article_id: int) -> StoredArticle | None:
        """Retrieve an article by id, or None if it does not exist."""

    @abstractmethod
    async def stats(self) -> StatsSnapshot:
        """Return the admin aggregates."""
