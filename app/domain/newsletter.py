"""Domain entities for the weekly newsletter.

A `Newsletter` aggregates several `NewsletterEntry` items (each one explained
with the very same editorial format as the daily news: the five sections plus a
community question). It is a pure domain object: the HTML renderer, the Discord
announcer and the persistence layer all consume it without leaking infrastructure
concerns back into the domain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.entities import DiscussionPrompt, EditedArticle, NewsItem
from app.domain.value_objects import Category, RelevanceScore


@dataclass(frozen=True, slots=True)
class NewsletterEntry:
    """A single news item explained in the newsletter's editorial format."""

    news_item: NewsItem
    edited: EditedArticle
    discussion: DiscussionPrompt

    @property
    def category(self) -> Category:
        assert self.news_item.category is not None
        return self.news_item.category

    @property
    def relevance_score(self) -> RelevanceScore:
        assert self.news_item.relevance_score is not None
        return self.news_item.relevance_score


@dataclass(frozen=True, slots=True)
class Newsletter:
    """A weekly digest: several entries plus its calendar metadata."""

    week_label: str
    iso_year: int
    iso_week: int
    generated_at: datetime
    entries: tuple[NewsletterEntry, ...]
    overview: str = ""

    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def headlines(self) -> list[str]:
        return [entry.edited.title for entry in self.entries]


@dataclass
class NewsletterReport:
    """Summary of the outcome of a weekly newsletter run."""

    collected: int = 0
    classified: int = 0
    selected: int = 0
    published_count: int = 0
    public_url: str | None = None
    discord_message_id: int | None = None
    errors: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def succeeded(self) -> bool:
        return self.public_url is not None and self.published_count > 0
