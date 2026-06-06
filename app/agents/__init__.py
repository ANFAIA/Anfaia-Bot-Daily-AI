"""Agents of the Anfaia Daily AI multi-agent system."""

from app.agents.discord_publisher_agent import DiscordPublisherAgent
from app.agents.discussion_generator import DiscussionGeneratorAgent
from app.agents.duplicate_detector import DuplicateDecision, DuplicateDetectorAgent
from app.agents.news_classifier import NewsClassifierAgent
from app.agents.news_collector import NewsCollectorAgent
from app.agents.news_editor import NewsEditorAgent
from app.agents.newsletter_overview import NewsletterOverviewAgent

__all__ = [
    "DiscordPublisherAgent",
    "DiscussionGeneratorAgent",
    "DuplicateDecision",
    "DuplicateDetectorAgent",
    "NewsClassifierAgent",
    "NewsCollectorAgent",
    "NewsEditorAgent",
    "NewsletterOverviewAgent",
]
