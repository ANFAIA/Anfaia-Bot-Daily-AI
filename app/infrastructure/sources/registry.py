"""Registry of the system's default news sources.

Centralizes the initial catalog of sources. The catalog can be overridden from
configuration (RSS_FEEDS, REDDIT_SUBREDDITS, HACKERNEWS_ENABLED) without
touching agents or the workflow; the lists below are only the defaults.
"""

from __future__ import annotations

import httpx

from app.infrastructure.sources.hackernews_source import HackerNewsSource
from app.infrastructure.sources.reddit_source import RedditSource
from app.infrastructure.sources.rss_source import RSSSource
from app.interfaces.news_source import NewsSource

# (human-readable name, RSS/Atom feed URL)
DEFAULT_RSS_FEEDS: list[tuple[str, str]] = [
    ("OpenAI Blog", "https://openai.com/news/rss.xml"),
    ("Anthropic Blog", "https://www.anthropic.com/rss.xml"),
    ("Google DeepMind Blog", "https://deepmind.google/blog/rss.xml"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("Ars Technica AI", "https://arstechnica.com/ai/feed/"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("Simon Willison", "https://simonwillison.net/atom/everything/"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
]

DEFAULT_SUBREDDITS: list[str] = ["artificial", "MachineLearning"]


def build_default_sources(
    client: httpx.AsyncClient,
    *,
    rss_feeds: list[tuple[str, str]] | None = None,
    subreddits: list[str] | None = None,
    hackernews_enabled: bool = True,
) -> list[NewsSource]:
    """Build the list of sources, honoring configuration overrides."""
    feeds = DEFAULT_RSS_FEEDS if rss_feeds is None else rss_feeds
    subs = DEFAULT_SUBREDDITS if subreddits is None else subreddits
    sources: list[NewsSource] = [RSSSource(name, url, client=client) for name, url in feeds]
    if hackernews_enabled:
        sources.append(HackerNewsSource(client=client))
    sources.extend(RedditSource(sub, client=client) for sub in subs)
    return sources
