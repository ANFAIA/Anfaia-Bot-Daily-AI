"""Article fetcher port."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ArticleFetcher(ABC):
    """Retrieves the readable text of an article from its URL."""

    @abstractmethod
    async def fetch(self, url: str) -> str | None:
        """Return the cleaned article text, or None when it cannot be fetched.

        Implementations must NOT raise on network or parsing failures: this is
        a best-effort enrichment and the caller falls back to the feed summary.
        """
