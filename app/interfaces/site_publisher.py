"""Static-site publishing port (outbound channel for the HTML newsletter).

Abstracts "publish this HTML at this path and give me a public URL". The default
adapter targets GitHub Pages, but the port keeps the workflow agnostic so it can
be swapped for S3, Netlify, etc. without touching the domain.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class SitePublisherError(RuntimeError):
    """Unrecoverable error while publishing the static page."""


@dataclass(frozen=True, slots=True)
class PublishedSite:
    """Result of publishing a page: its public URL and the commit it produced."""

    public_url: str
    path: str
    commit_sha: str


class SitePublisher(ABC):
    """Publishes an HTML page to a static host and returns its public URL."""

    @abstractmethod
    async def publish_html(self, *, path: str, html: str, commit_message: str) -> PublishedSite:
        """Publish ``html`` at ``path`` and return the resulting `PublishedSite`.

        Raises:
            SitePublisherError: if publishing fails permanently.
        """

    @abstractmethod
    async def publish_bytes(
        self, *, path: str, content: bytes, content_type: str, commit_message: str
    ) -> PublishedSite:
        """Publish raw ``content`` (e.g. an MP3 or an RSS feed) at ``path``.

        ``content_type`` is the MIME type of the asset (used by callers for
        announcements/feeds; the static host serves it by file extension).

        Raises:
            SitePublisherError: if publishing fails permanently.
        """
