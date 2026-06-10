"""Null publisher used when Discord is not configured.

Allows the system to start without Discord credentials (e.g. in CI or during
development). Any real attempt to publish fails explicitly and in a controlled
way, instead of breaking application startup.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.domain.entities import PublishableArticle
from app.domain.newsletter import Newsletter
from app.domain.podcast import PodcastEpisode
from app.interfaces.publisher import Publisher, PublisherError

_NOT_CONFIGURED = "Discord no está configurado (define DISCORD_TOKEN y DISCORD_CHANNEL_ID)"

logger = get_logger(__name__)


class NullPublisher(Publisher):
    """Inert implementation of the `Publisher` port."""

    async def publish(self, article: PublishableArticle) -> int:
        logger.error("publisher.not_configured", title=article.edited.title)
        raise PublisherError(_NOT_CONFIGURED)

    async def publish_test_message(self, text: str) -> int:
        raise PublisherError(_NOT_CONFIGURED)

    async def publish_newsletter_announcement(self, newsletter: Newsletter, url: str) -> int:
        logger.error("publisher.not_configured", newsletter=newsletter.week_label)
        raise PublisherError(_NOT_CONFIGURED)

    async def publish_podcast_announcement(self, episode: PodcastEpisode, url: str) -> int:
        logger.error("publisher.not_configured", podcast=episode.week_label)
        raise PublisherError(_NOT_CONFIGURED)
