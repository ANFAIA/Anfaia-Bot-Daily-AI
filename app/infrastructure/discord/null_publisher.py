"""Null publisher used when Discord is not configured.

Allows the system to start without Discord credentials (e.g. in CI or during
development). Any real attempt to publish fails explicitly and in a controlled
way, instead of breaking application startup.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.domain.entities import PublishableArticle
from app.interfaces.publisher import Publisher, PublisherError

logger = get_logger(__name__)


class NullPublisher(Publisher):
    """Inert implementation of the `Publisher` port."""

    async def publish(self, article: PublishableArticle) -> int:
        logger.error("publisher.not_configured", title=article.edited.title)
        raise PublisherError(
            "Discord no está configurado (define DISCORD_TOKEN y DISCORD_CHANNEL_ID)"
        )

    async def publish_test_message(self, text: str) -> int:
        raise PublisherError(
            "Discord no está configurado (define DISCORD_TOKEN y DISCORD_CHANNEL_ID)"
        )
