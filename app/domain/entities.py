"""Domain entities.

`NewsItem` is the central aggregate that flows through the entire agent
pipeline. Each agent progressively enriches it (classification, editing,
discussion) until it becomes a `PublishableArticle` ready for Discord.

The domain does not depend on SQLAlchemy, FastAPI or any concrete provider:
it only models business concepts.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import datetime

from app.domain.value_objects import Category, RelevanceScore


@dataclass(frozen=True, slots=True)
class NewsItem:
    """Normalized news item coming from any source.

    It is immutable: agents produce enriched copies via `with_*`.
    """

    title: str
    url: str
    source: str
    summary: str
    published_at: datetime | None = None
    raw_content: str = ""
    category: Category | None = None
    relevance_score: RelevanceScore | None = None

    @property
    def url_fingerprint(self) -> str:
        """Stable URL fingerprint for exact duplicate detection."""
        normalized = self.url.strip().lower().split("?")[0].rstrip("/")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @property
    def embedding_text(self) -> str:
        """Canonical text used to compute the semantic embedding."""
        return f"{self.title}\n\n{self.summary}".strip()

    def with_classification(self, category: Category, score: RelevanceScore) -> NewsItem:
        return replace(self, category=category, relevance_score=score)


@dataclass(frozen=True, slots=True)
class DiscussionPrompt:
    """Open-ended question to encourage discussion in the community."""

    question: str
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class EditedArticle:
    """Edited content of a news item, structured by sections."""

    title: str
    what_happened: str
    why_it_matters: str
    how_we_could_use_it: str
    limitations: str
    source_url: str


@dataclass(frozen=True, slots=True)
class PublishableArticle:
    """Final article ready to publish, aggregating all the agents' work."""

    news_item: NewsItem
    edited: EditedArticle
    discussion: DiscussionPrompt
    discord_message_id: int | None = None

    @property
    def category(self) -> Category:
        assert self.news_item.category is not None
        return self.news_item.category

    @property
    def relevance_score(self) -> RelevanceScore:
        assert self.news_item.relevance_score is not None
        return self.news_item.relevance_score

    def published_as(self, message_id: int) -> PublishableArticle:
        return replace(self, discord_message_id=message_id)


@dataclass
class WorkflowReport:
    """Summary of the outcome of a daily workflow run."""

    collected: int = 0
    classified: int = 0
    discarded_duplicates: int = 0
    discarded_low_relevance: int = 0
    published: int = 0
    published_article: PublishableArticle | None = None
    errors: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def succeeded(self) -> bool:
        return self.published > 0 and not self.errors
