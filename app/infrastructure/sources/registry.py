"""Registry of the system's default news sources.

Centralizes the initial catalog of sources. Adding a new source is just a matter
of extending `build_default_sources` without touching agents or the workflow.
"""

from __future__ import annotations

import httpx

from app.infrastructure.sources.hackernews_source import HackerNewsSource
from app.infrastructure.sources.reddit_source import RedditSource
from app.infrastructure.sources.rss_source import RSSSource
from app.interfaces.news_source import NewsSource

# (human-readable name, RSS/Atom feed URL)
_RSS_FEEDS: list[tuple[str, str]] = [
    ("OpenAI Blog", "https://openai.com/news/rss.xml"),
    ("Anthropic Blog", "https://www.anthropic.com/rss.xml"),
    ("Google DeepMind Blog", "https://deepmind.google/blog/rss.xml"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("Ars Technica AI", "https://arstechnica.com/ai/feed/"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
]

_SUBREDDITS: list[str] = ["artificial", "MachineLearning"]


def build_default_sources(client: httpx.AsyncClient) -> list[NewsSource]:
    """Build the system's initial list of sources."""
    sources: list[NewsSource] = [RSSSource(name, url, client=client) for name, url in _RSS_FEEDS]
    sources.append(HackerNewsSource(client=client))
    sources.extend(RedditSource(sub, client=client) for sub in _SUBREDDITS)
    return sources
