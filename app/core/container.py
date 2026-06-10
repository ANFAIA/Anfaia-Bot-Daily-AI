"""Dependency injection container (composition root).

This is the only place where concrete adapters are wired up with the business
logic. It builds the object graph from the configuration and exposes it to the
inbound adapters (API and scheduler). Keeping it here lets us swap any
implementation (LLM, source, repository, publisher) without touching the rest.
"""

from __future__ import annotations

from functools import partial

import httpx

from app.agents import (
    DiscordPublisherAgent,
    DiscussionGeneratorAgent,
    DuplicateDetectorAgent,
    NewsClassifierAgent,
    NewsCollectorAgent,
    NewsEditorAgent,
    NewsletterOverviewAgent,
    PodcastScriptwriterAgent,
)
from app.agents.classic_editorial_brain import ClassicEditorialBrain
from app.application.use_cases import (
    GetNewsUseCase,
    GetStatsUseCase,
    ListNewsUseCase,
    RunDailyWorkflowUseCase,
    RunWeeklyNewsletterUseCase,
    SendTestMessageUseCase,
)
from app.core.config import Settings, WorkflowEngine
from app.core.logging import get_logger
from app.database.repositories import SqlAlchemyNewsRepository
from app.database.session import Database
from app.domain.podcast import SPEAKER_A, SPEAKER_B
from app.infrastructure.discord.discord_publisher import DiscordPublisher
from app.infrastructure.discord.null_publisher import NullPublisher
from app.infrastructure.embeddings.factory import build_embedding_provider
from app.infrastructure.hosting.github_pages_publisher import GitHubPagesPublisher
from app.infrastructure.hosting.null_site_publisher import NullSitePublisher
from app.infrastructure.llm.factory import build_llm_provider
from app.infrastructure.newsletter.html_renderer import (
    render_index_html,
    render_newsletter_html,
)
from app.infrastructure.podcast.rss_renderer import PodcastFeedMeta, render_podcast_rss
from app.infrastructure.sources.registry import build_default_sources
from app.infrastructure.tts.factory import build_tts_provider
from app.interfaces.editorial import EditorialBrain
from app.interfaces.publisher import Publisher
from app.interfaces.repositories import NewsRepository
from app.interfaces.site_publisher import SitePublisher
from app.interfaces.tts import TextToSpeechProvider
from app.workflows.base import NewsWorkflow
from app.workflows.daily_news_workflow import DailyNewsWorkflow
from app.workflows.deepagents_news_workflow import DeepAgentsNewsWorkflow
from app.workflows.podcast_workflow import PodcastWorkflow
from app.workflows.weekly_newsletter_workflow import WeeklyNewsletterWorkflow

logger = get_logger(__name__)


class Container:
    """Process dependency graph, built only once at startup."""

    def __init__(self, settings: Settings, *, repository: NewsRepository | None = None) -> None:
        self.settings = settings

        # --- Shared HTTP client ---
        self.http_client = httpx.AsyncClient(
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": settings.http_user_agent},
            follow_redirects=True,
        )

        # --- Persistence ---
        self.database: Database | None = None
        if repository is not None:
            self.repository = repository
        else:
            self.database = Database(settings.database_url, echo=False)
            self.repository = SqlAlchemyNewsRepository(self.database)

        # --- Outbound adapters ---
        self.llm = build_llm_provider(settings, self.http_client)
        self.embeddings = build_embedding_provider(settings, self.http_client)
        self.publisher: Publisher = self._build_publisher(settings)
        self.site_publisher: SitePublisher = self._build_site_publisher(settings)
        self.tts: TextToSpeechProvider = build_tts_provider(settings, self.http_client)
        self.sources = build_default_sources(self.http_client)

        # --- Agents ---
        self.collector_agent = NewsCollectorAgent(
            self.sources, max_items_per_source=settings.max_items_per_source
        )
        self.classifier_agent = NewsClassifierAgent(self.llm)
        self.duplicate_agent = DuplicateDetectorAgent(
            self.repository,
            self.embeddings,
            similarity_threshold=settings.duplicate_similarity_threshold,
        )
        self.editor_agent = NewsEditorAgent(self.llm)
        self.discussion_agent = DiscussionGeneratorAgent(self.llm)
        self.overview_agent = NewsletterOverviewAgent(self.llm)
        self.scriptwriter_agent = PodcastScriptwriterAgent(
            self.llm,
            host_a=settings.podcast_voice_a_name,
            host_b=settings.podcast_voice_b_name,
            target_minutes=settings.podcast_target_minutes,
        )
        self.publisher_agent = DiscordPublisherAgent(self.publisher)

        # --- Workflows ---
        self.workflow: NewsWorkflow = self._build_workflow(settings)
        self.podcast_workflow = self._build_podcast_workflow(settings)
        self.newsletter_workflow = WeeklyNewsletterWorkflow(
            collector=self.collector_agent,
            classifier=self.classifier_agent,
            editor=self.editor_agent,
            discussion_generator=self.discussion_agent,
            overview_generator=self.overview_agent,
            embeddings=self.embeddings,
            publisher=self.publisher,
            site_publisher=self.site_publisher,
            renderer=partial(render_newsletter_html, logo_url=settings.newsletter_logo_url),
            index_renderer=partial(render_index_html, logo_url=settings.newsletter_logo_url),
            repository=self.repository,
            min_relevance_score=settings.newsletter_min_relevance,
            top_n=settings.newsletter_top_n,
            extra_relevance=settings.newsletter_extra_relevance,
            dedup_threshold=settings.newsletter_dedup_threshold,
            timezone=settings.timezone,
            path_prefix=settings.newsletter_path_prefix,
            podcast_workflow=self.podcast_workflow,
        )

        # --- Use cases ---
        self.run_workflow_uc = RunDailyWorkflowUseCase(self.workflow)
        self.run_newsletter_uc = RunWeeklyNewsletterUseCase(self.newsletter_workflow)
        self.list_news_uc = ListNewsUseCase(self.repository)
        self.get_news_uc = GetNewsUseCase(self.repository)
        self.stats_uc = GetStatsUseCase(self.repository)
        self.test_discord_uc = SendTestMessageUseCase(self.publisher)

    def _build_workflow(self, settings: Settings) -> NewsWorkflow:
        """Select the orchestration engine based on `settings.workflow_engine`.

        The default sequential pipeline is fully self-contained. The deepagents
        engine swaps only the editorial decision for a deliberative brain,
        reusing the same collector/classifier/dedup/publisher agents and falling
        back to the classic brain on any error.
        """
        if settings.workflow_engine is WorkflowEngine.DEEPAGENTS:
            from app.infrastructure.editorial.factory import build_editorial_brain

            classic_brain: EditorialBrain = ClassicEditorialBrain(
                self.editor_agent, self.discussion_agent
            )
            brain = build_editorial_brain(settings, self.http_client, fallback=classic_brain)
            logger.info("container.workflow_engine", engine="deepagents")
            return DeepAgentsNewsWorkflow(
                collector=self.collector_agent,
                classifier=self.classifier_agent,
                duplicate_detector=self.duplicate_agent,
                brain=brain,
                publisher=self.publisher_agent,
                repository=self.repository,
                min_relevance_score=settings.min_relevance_score,
                shortlist_size=settings.editorial_shortlist_size,
            )

        return DailyNewsWorkflow(
            collector=self.collector_agent,
            classifier=self.classifier_agent,
            duplicate_detector=self.duplicate_agent,
            editor=self.editor_agent,
            discussion_generator=self.discussion_agent,
            publisher=self.publisher_agent,
            repository=self.repository,
            min_relevance_score=settings.min_relevance_score,
        )

    def _build_podcast_workflow(self, settings: Settings) -> PodcastWorkflow | None:
        """Build the podcast workflow when enabled, else None (boletín unaffected)."""
        if not settings.podcast_enabled:
            return None
        voice_map = {
            speaker: voice
            for speaker, voice in (
                (SPEAKER_A, settings.podcast_voice_a),
                (SPEAKER_B, settings.podcast_voice_b),
            )
            if voice
        }
        base_url = (settings.newsletter_base_url or "https://anfaia.org").rstrip("/")
        prefix = settings.podcast_path_prefix.strip("/")
        feed_meta = PodcastFeedMeta(
            title=settings.podcast_title,
            description=settings.podcast_description,
            author=settings.podcast_author,
            language=settings.podcast_language,
            site_url=base_url,
            feed_url=f"{base_url}/{prefix}/feed.xml",
            image_url=settings.newsletter_logo_url,
            email=settings.podcast_email or "",
        )
        return PodcastWorkflow(
            scriptwriter=self.scriptwriter_agent,
            tts=self.tts,
            site_publisher=self.site_publisher,
            publisher=self.publisher,
            feed_renderer=partial(render_podcast_rss, meta=feed_meta),
            repository=self.repository,
            voice_map=voice_map,
            path_prefix=settings.podcast_path_prefix,
        )

    @staticmethod
    def _build_publisher(settings: Settings) -> Publisher:
        if settings.discord_token and settings.discord_channel_id:
            return DiscordPublisher(
                settings.discord_token,
                settings.discord_channel_id,
                newsletter_channel_id=settings.newsletter_discord_channel_id,
                podcast_channel_id=settings.podcast_discord_channel_id,
            )
        logger.warning("container.discord_not_configured")
        return NullPublisher()

    def _build_site_publisher(self, settings: Settings) -> SitePublisher:
        if (
            settings.github_token
            and settings.github_owner
            and settings.github_repo
            and settings.newsletter_base_url
        ):
            return GitHubPagesPublisher(
                self.http_client,
                token=settings.github_token,
                owner=settings.github_owner,
                repo=settings.github_repo,
                branch=settings.github_branch,
                base_url=settings.newsletter_base_url,
            )
        logger.warning("container.github_pages_not_configured")
        return NullSitePublisher()

    async def aclose(self) -> None:
        """Release resources (HTTP client and database connections)."""
        await self.http_client.aclose()
        if self.database is not None:
            await self.database.dispose()
