"""Agent 1 — News Collector.

Collects news from all configured sources in parallel, normalizes them to
`NewsItem` and removes exact URL duplicates within the same batch.
"""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.domain.entities import NewsItem
from app.interfaces.agent import Agent
from app.interfaces.news_source import NewsSource

logger = get_logger(__name__)


class NewsCollectorAgent(Agent[None, list[NewsItem]]):
    """Aggregates and normalizes news from multiple sources."""

    name = "news_collector"

    def __init__(self, sources: list[NewsSource], *, max_items_per_source: int) -> None:
        self._sources = sources
        self._max_items_per_source = max_items_per_source

    async def run(self, input_data: None = None) -> list[NewsItem]:
        results = await asyncio.gather(
            *(source.fetch(self._max_items_per_source) for source in self._sources),
            return_exceptions=True,
        )

        collected: list[NewsItem] = []
        for source, result in zip(self._sources, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning("collector.source_error", source=source.name, error=str(result))
                continue
            collected.extend(result)

        deduped = self._dedupe(collected)
        logger.info(
            "collector.done",
            raw=len(collected),
            unique=len(deduped),
            sources=len(self._sources),
        )
        return deduped

    @staticmethod
    def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
        seen: set[str] = set()
        unique: list[NewsItem] = []
        for item in items:
            fp = item.url_fingerprint
            if fp in seen:
                continue
            seen.add(fp)
            unique.append(item)
        return unique
