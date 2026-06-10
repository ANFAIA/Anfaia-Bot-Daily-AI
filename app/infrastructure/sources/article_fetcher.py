"""Best-effort article body fetcher.

Downloads the article page with httpx and extracts its readable text with the
same lightweight HTML cleanup used by the sources (no extra dependencies). It
prefers the <article>/<main> block when present to skip navigation chrome. Any
failure returns None so the editor falls back to the feed summary.
"""

from __future__ import annotations

import re

import httpx

from app.core.logging import get_logger
from app.infrastructure.sources.text import clean_html, truncate
from app.interfaces.article_fetcher import ArticleFetcher

logger = get_logger(__name__)

# Non-content blocks stripped before text extraction.
_NOISE_RE = re.compile(
    r"<(script|style|noscript|svg|nav|header|footer|aside|form)\b.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_MAIN_RE = re.compile(r"<(article|main)\b[^>]*>(.*?)</\1\s*>", re.IGNORECASE | re.DOTALL)

# Below this many characters the extraction likely failed (paywall, JS-only
# page, error page) and the feed summary is a better input for the editor.
_MIN_USEFUL_CHARS = 400


class HttpArticleFetcher(ArticleFetcher):
    """Fetches the article HTML and reduces it to plain readable text."""

    def __init__(self, client: httpx.AsyncClient, *, max_chars: int = 8000) -> None:
        self._client = client
        self._max_chars = max_chars

    async def fetch(self, url: str) -> str | None:
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("article_fetcher.fetch_failed", url=url, error=str(exc))
            return None

        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and not content_type.startswith("text/"):
            logger.info("article_fetcher.not_html", url=url, content_type=content_type)
            return None

        try:
            text = self._extract_text(response.text)
        except Exception as exc:
            logger.warning("article_fetcher.parse_failed", url=url, error=str(exc))
            return None

        if len(text) < _MIN_USEFUL_CHARS:
            logger.info("article_fetcher.too_short", url=url, chars=len(text))
            return None
        logger.info("article_fetcher.fetched", url=url, chars=len(text))
        return text

    def _extract_text(self, html: str) -> str:
        html = _NOISE_RE.sub(" ", html)
        # Prefer the largest <article>/<main> block; fall back to the full page.
        blocks = [match.group(2) for match in _MAIN_RE.finditer(html)]
        body = max(blocks, key=len) if blocks else html
        return truncate(clean_html(body), self._max_chars)
