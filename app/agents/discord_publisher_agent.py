"""Agent 6 — Discord Publisher.

Thin wrapper over the `Publisher` port that exposes publishing as one more
agent in the pipeline, preserving the symmetry of the multi-agent system.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.domain.entities import PublishableArticle
from app.interfaces.agent import Agent
from app.interfaces.publisher import Publisher

logger = get_logger(__name__)


class DiscordPublisherAgent(Agent[PublishableArticle, PublishableArticle]):
    """Publishes the final article and returns it with the message id."""

    name = "discord_publisher"

    def __init__(self, publisher: Publisher) -> None:
        self._publisher = publisher

    async def run(self, input_data: PublishableArticle) -> PublishableArticle:
        message_id = await self._publisher.publish(input_data)
        logger.info("publisher.done", message_id=message_id, title=input_data.edited.title)
        return input_data.published_as(message_id)
