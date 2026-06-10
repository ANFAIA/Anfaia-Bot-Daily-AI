"""Null static-site publisher used when GitHub Pages is not configured.

Lets the system start without GitHub credentials. Any real attempt to publish
fails explicitly instead of silently doing nothing (mirrors `NullPublisher`).
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.interfaces.site_publisher import PublishedSite, SitePublisher, SitePublisherError

logger = get_logger(__name__)


class NullSitePublisher(SitePublisher):
    """Inert implementation of the `SitePublisher` port."""

    _NOT_CONFIGURED = (
        "GitHub Pages no está configurado (define GITHUB_TOKEN, GITHUB_OWNER, "
        "GITHUB_REPO y NEWSLETTER_BASE_URL)"
    )

    async def publish_html(self, *, path: str, html: str, commit_message: str) -> PublishedSite:
        logger.error("site_publisher.not_configured", path=path)
        raise SitePublisherError(self._NOT_CONFIGURED)

    async def publish_bytes(
        self, *, path: str, content: bytes, content_type: str, commit_message: str
    ) -> PublishedSite:
        logger.error("site_publisher.not_configured", path=path)
        raise SitePublisherError(self._NOT_CONFIGURED)
