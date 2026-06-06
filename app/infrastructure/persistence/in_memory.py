"""In-memory news repository.

Implements the same port as the SQLAlchemy repository. It is useful for:
  - unit and integration tests of the workflow without PostgreSQL,
  - fast local development without spinning up the database.

Similarity is computed with pure-Python cosine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.entities import PublishableArticle
from app.domain.newsletter import Newsletter
from app.domain.value_objects import Category
from app.interfaces.repositories import (
    NewsRepository,
    SimilarArticle,
    StatsSnapshot,
    StoredArticle,
    StoredNewsletter,
)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors; 0 if either is null."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class _Record:
    stored: StoredArticle
    embedding: list[float] | None
    fingerprint: str


class InMemoryNewsRepository(NewsRepository):
    """Volatile repository for tests and development."""

    def __init__(self) -> None:
        self._records: list[_Record] = []
        self._counters: dict[str, int] = {}
        self._next_id = 1
        self._newsletters: dict[tuple[int, int], StoredNewsletter] = {}
        self._next_newsletter_id = 1

    async def url_exists(self, url_fingerprint: str) -> bool:
        return any(r.fingerprint == url_fingerprint for r in self._records)

    async def find_similar(
        self, embedding: list[float], threshold: float, limit: int = 5
    ) -> list[SimilarArticle]:
        scored = [
            SimilarArticle(
                article_id=r.stored.id,
                url=r.stored.url,
                similarity=cosine_similarity(embedding, r.embedding or []),
            )
            for r in self._records
            if r.embedding is not None
        ]
        hits = [s for s in scored if s.similarity >= threshold]
        hits.sort(key=lambda s: s.similarity, reverse=True)
        return hits[:limit]

    async def save_published(
        self, article: PublishableArticle, embedding: list[float] | None
    ) -> int:
        article_id = self._next_id
        self._next_id += 1
        item = article.news_item
        stored = StoredArticle(
            id=article_id,
            title=item.title,
            url=item.url,
            source=item.source,
            category=article.category,
            relevance_score=article.relevance_score.value,
            summary=item.summary,
            published_at=item.published_at,
            discord_message_id=article.discord_message_id,
            created_at=datetime.now(UTC),
        )
        self._records.append(
            _Record(stored=stored, embedding=embedding, fingerprint=item.url_fingerprint)
        )
        return article_id

    async def increment_counter(self, name: str, amount: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + amount

    async def list_articles(
        self, *, limit: int, offset: int, category: Category | None = None
    ) -> list[StoredArticle]:
        items = [r.stored for r in self._records]
        if category is not None:
            items = [s for s in items if s.category == category]
        items.sort(key=lambda s: s.created_at, reverse=True)
        return items[offset : offset + limit]

    async def get_article(self, article_id: int) -> StoredArticle | None:
        return next((r.stored for r in self._records if r.stored.id == article_id), None)

    async def newsletter_exists(self, iso_year: int, iso_week: int) -> bool:
        return (iso_year, iso_week) in self._newsletters

    async def save_newsletter(
        self, newsletter: Newsletter, *, public_url: str, discord_message_id: int | None
    ) -> int:
        key = (newsletter.iso_year, newsletter.iso_week)
        existing = self._newsletters.get(key)
        newsletter_id = existing.id if existing else self._next_newsletter_id
        if existing is None:
            self._next_newsletter_id += 1
        self._newsletters[key] = StoredNewsletter(
            id=newsletter_id,
            iso_year=newsletter.iso_year,
            iso_week=newsletter.iso_week,
            week_label=newsletter.week_label,
            public_url=public_url,
            item_count=newsletter.count,
            generated_at=newsletter.generated_at,
            discord_message_id=discord_message_id,
            created_at=datetime.now(UTC),
        )
        return newsletter_id

    async def list_newsletters(self, *, limit: int = 200) -> list[StoredNewsletter]:
        items = sorted(
            self._newsletters.values(),
            key=lambda n: (n.iso_year, n.iso_week),
            reverse=True,
        )
        return items[:limit]

    async def stats(self) -> StatsSnapshot:
        by_category: dict[str, int] = {}
        for r in self._records:
            key = r.stored.category.value
            by_category[key] = by_category.get(key, 0) + 1
        return StatsSnapshot(
            analyzed=self._counters.get("analyzed", 0),
            published=max(self._counters.get("published", 0), len(self._records)),
            discarded=self._counters.get("discarded", 0),
            by_category=by_category,
            last_run_at=None,
            last_run_status=None,
        )
