"""Generic news source based on RSS/Atom feeds.

Downloads the feed with httpx (async) and parses it with feedparser. Any network
or parsing failure is caught and an empty list is returned, so a single broken
source never breaks the whole pipeline.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import feedparser
import httpx

from app.core.logging import get_logger
from app.domain.entities import NewsItem
from app.infrastructure.sources.text import clean_html, truncate
from app.interfaces.news_source import NewsSource

logger = get_logger(__name__)


class RSSSource(NewsSource):
    """Source that reads from a single RSS/Atom feed."""

    def __init__(self, name: str, feed_url: str, *, client: httpx.AsyncClient) -> None:
        self._name = name
        self._feed_url = feed_url
        self._client = client

    @property
    def name(self) -> str:
        return self._name

    @staticmethod
    def _parse_date(entry: feedparser.FeedParserDict) -> datetime | None:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if not parsed:
            return None
        return datetime.fromtimestamp(time.mktime(parsed), tz=UTC)

    async def fetch(self, limit: int) -> list[NewsItem]:
        try:
            response = await self._client.get(self._feed_url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("source.fetch_failed", source=self._name, error=str(exc))
            return []

        feed = feedparser.parse(response.content)
        items: list[NewsItem] = []
        for entry in feed.entries[:limit]:
            link = entry.get("link")
            title = entry.get("title")
            if not link or not title:
                continue
            summary = clean_html(entry.get("summary") or entry.get("description") or "")
            items.append(
                NewsItem(
                    title=title.strip(),
                    url=link.strip(),
                    source=self._name,
                    summary=truncate(summary, 800),
                    published_at=self._parse_date(entry),
                    raw_content=truncate(summary, 4000),
                )
            )
        logger.info("source.fetched", source=self._name, count=len(items))
        return items
