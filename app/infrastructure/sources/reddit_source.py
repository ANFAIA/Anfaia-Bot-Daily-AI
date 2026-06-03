"""News source based on Reddit's public JSON endpoints.

Reads `https://www.reddit.com/r/<subreddit>/top.json`. No OAuth is required for
basic reading, but Reddit requires a descriptive User-Agent (provided by the
shared httpx client).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.core.logging import get_logger
from app.domain.entities import NewsItem
from app.infrastructure.sources.text import truncate
from app.interfaces.news_source import NewsSource

logger = get_logger(__name__)


class RedditSource(NewsSource):
    """Top posts from a subreddit within the given time window."""

    def __init__(self, subreddit: str, *, client: httpx.AsyncClient, period: str = "day") -> None:
        self._subreddit = subreddit
        self._client = client
        self._period = period

    @property
    def name(self) -> str:
        return f"Reddit r/{self._subreddit}"

    async def fetch(self, limit: int) -> list[NewsItem]:
        url = f"https://www.reddit.com/r/{self._subreddit}/top.json"
        try:
            response = await self._client.get(url, params={"t": self._period, "limit": limit})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("source.fetch_failed", source=self.name, error=str(exc))
            return []

        items: list[NewsItem] = []
        for child in response.json().get("data", {}).get("children", []):
            post = child.get("data", {})
            title = post.get("title")
            if not title or post.get("stickied"):
                continue
            permalink = post.get("permalink", "")
            external = post.get("url_overridden_by_dest")
            url_final = external or f"https://www.reddit.com{permalink}"
            created = post.get("created_utc")
            published = datetime.fromtimestamp(created, tz=UTC) if created else None
            selftext = post.get("selftext") or ""
            items.append(
                NewsItem(
                    title=title.strip(),
                    url=url_final,
                    source=self.name,
                    summary=truncate(selftext or title, 600),
                    published_at=published,
                    raw_content=truncate(selftext, 2000),
                )
            )
        logger.info("source.fetched", source=self.name, count=len(items))
        return items
