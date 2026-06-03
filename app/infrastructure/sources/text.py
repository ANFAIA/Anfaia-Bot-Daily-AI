"""Text cleaning and normalization utilities for the sources."""

from __future__ import annotations

import re
from html import unescape

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_html(raw: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    text = _TAG_RE.sub(" ", raw)
    text = unescape(text)
    return _WS_RE.sub(" ", text).strip()


def truncate(text: str, max_chars: int) -> str:
    """Truncate the text to `max_chars`, adding an ellipsis if needed."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"
