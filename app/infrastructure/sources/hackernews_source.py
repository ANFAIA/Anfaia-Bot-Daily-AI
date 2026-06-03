"""News source based on the Hacker News search API (Algolia).

Filters AI-relevant stories via a keyword query, sorted by date. The API is
public and requires no authentication.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.core.logging import get_logger
from app.domain.entities import NewsItem
from app.infrastructure.sources.text import truncate
from app.interfaces.news_source import NewsSource

logger = get_logger(__name__)

_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
_QUERY = "AI OR LLM OR agents OR robotics OR open source AI"


class HackerNewsSource(NewsSource):
    """Recent AI-related stories from Hacker News."""

    def __init__(self, *, client: httpx.AsyncClient) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "Hacker News"

    async def fetch(self, limit: int) -> list[NewsItem]:
        try:
            response = await self._client.get(
                _SEARCH_URL,
                params={
                    "query": _QUERY,
                    "tags": "story",
                    "hitsPerPage": limit,
                    "numericFilters": "points>30",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("source.fetch_failed", source=self.name, error=str(exc))
            return []

        items: list[NewsItem] = []
        for hit in response.json().get("hits", []):
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            title = hit.get("title")
            if not title:
                continue
            created = hit.get("created_at_i")
            published = datetime.fromtimestamp(created, tz=UTC) if created else None
            comment = hit.get("story_text") or ""
            items.append(
                NewsItem(
                    title=title.strip(),
                    url=url,
                    source=self.name,
                    summary=truncate(comment or title, 600),
                    published_at=published,
                    raw_content=truncate(comment, 2000),
                )
            )
        logger.info("source.fetched", source=self.name, count=len(items))
        return items
