"""News source port."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities import NewsItem


class NewsSource(ABC):
    """A source from which normalized news items can be collected."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the source (e.g. 'OpenAI Blog')."""

    @abstractmethod
    async def fetch(self, limit: int) -> list[NewsItem]:
        """Collect up to `limit` news items already normalized to `NewsItem`.

        Implementations must NOT raise exceptions on network failures: they
        should catch them, log them, and return whatever they managed to obtain
        (ideally an empty list) so as not to break the rest of the pipeline.
        """
