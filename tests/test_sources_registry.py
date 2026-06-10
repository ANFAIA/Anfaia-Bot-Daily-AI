"""Tests for the source registry and its configuration overrides."""

from __future__ import annotations

import httpx
import pytest

from app.infrastructure.sources.hackernews_source import HackerNewsSource
from app.infrastructure.sources.reddit_source import RedditSource
from app.infrastructure.sources.registry import (
    DEFAULT_RSS_FEEDS,
    DEFAULT_SUBREDDITS,
    build_default_sources,
)
from app.infrastructure.sources.rss_source import RSSSource


@pytest.fixture
async def client() -> httpx.AsyncClient:
    async with httpx.AsyncClient() as c:
        yield c


async def test_default_catalog(client: httpx.AsyncClient) -> None:
    sources = build_default_sources(client)
    rss = [s for s in sources if isinstance(s, RSSSource)]
    assert len(rss) == len(DEFAULT_RSS_FEEDS)
    assert sum(isinstance(s, HackerNewsSource) for s in sources) == 1
    assert sum(isinstance(s, RedditSource) for s in sources) == len(DEFAULT_SUBREDDITS)


async def test_rss_override_replaces_catalog(client: httpx.AsyncClient) -> None:
    sources = build_default_sources(
        client, rss_feeds=[("Mi Blog", "https://mi.blog/feed")], subreddits=[]
    )
    rss = [s for s in sources if isinstance(s, RSSSource)]
    assert [s.name for s in rss] == ["Mi Blog"]
    assert not any(isinstance(s, RedditSource) for s in sources)


async def test_hackernews_can_be_disabled(client: httpx.AsyncClient) -> None:
    sources = build_default_sources(client, hackernews_enabled=False)
    assert not any(isinstance(s, HackerNewsSource) for s in sources)
