"""Sequential implementation of the daily news workflow.

Pipeline:

    Collect News → Classify → Remove Duplicates → Rank → Generate Article
    → Generate Discussion → Publish to Discord → Save History

It is a custom implementation (without an orchestration framework) that honors
the `NewsWorkflow` contract. Each step delegates to a specialized agent.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.agents.discord_publisher_agent import DiscordPublisherAgent
from app.agents.discussion_generator import DiscussionGeneratorAgent, DiscussionInput
from app.agents.duplicate_detector import DuplicateDecision, DuplicateDetectorAgent
from app.agents.news_classifier import NewsClassifierAgent
from app.agents.news_collector import NewsCollectorAgent
from app.agents.news_editor import NewsEditorAgent
from app.core.logging import get_logger
from app.core.metrics import metrics
from app.domain.entities import NewsItem, PublishableArticle, WorkflowReport
from app.interfaces.repositories import NewsRepository
from app.workflows.base import NewsWorkflow

logger = get_logger(__name__)


class DailyNewsWorkflow(NewsWorkflow):
    """Sequential orchestrator of the six agents."""

    def __init__(
        self,
        *,
        collector: NewsCollectorAgent,
        classifier: NewsClassifierAgent,
        duplicate_detector: DuplicateDetectorAgent,
        editor: NewsEditorAgent,
        discussion_generator: DiscussionGeneratorAgent,
        publisher: DiscordPublisherAgent,
        repository: NewsRepository,
        min_relevance_score: int,
    ) -> None:
        self._collector = collector
        self._classifier = classifier
        self._duplicate_detector = duplicate_detector
        self._editor = editor
        self._discussion_generator = discussion_generator
        self._publisher = publisher
        self._repo = repository
        self._min_relevance = min_relevance_score

    async def run(self) -> WorkflowReport:
        report = WorkflowReport(started_at=datetime.now(UTC))
        try:
            await self._run_pipeline(report)
        except Exception as exc:
            logger.exception("workflow.failed")
            report.errors.append(str(exc))
        finally:
            report.finished_at = datetime.now(UTC)
            status = "success" if report.succeeded else "failed"
            metrics.record_run(status, report.finished_at)
            metrics.increment(f"workflow_runs_{status}")
            logger.info(
                "workflow.finished",
                status=status,
                collected=report.collected,
                published=report.published,
                discarded_duplicates=report.discarded_duplicates,
                discarded_low_relevance=report.discarded_low_relevance,
            )
        return report

    async def _run_pipeline(self, report: WorkflowReport) -> None:
        # 1. Collect.
        collected = await self._collector.run(None)
        report.collected = len(collected)
        metrics.increment("news_collected", len(collected))
        await self._repo.increment_counter("analyzed", len(collected))
        if not collected:
            report.errors.append("No se recolectó ninguna noticia")
            return

        # 2. Classify (in parallel).
        classified = await asyncio.gather(*(self._classifier.run(item) for item in collected))
        report.classified = len(classified)

        # 3. Rank + filter by minimum relevance.
        ranked = sorted(
            classified,
            key=lambda it: it.relevance_score.value if it.relevance_score else 0,
            reverse=True,
        )
        candidates = [
            it
            for it in ranked
            if it.relevance_score and it.relevance_score.is_at_least(self._min_relevance)
        ]
        report.discarded_low_relevance = len(ranked) - len(candidates)
        if not candidates:
            report.errors.append("Ninguna noticia superó el umbral de relevancia")
            return

        # 4. Remove duplicates: iterate candidates until a unique one is found.
        chosen: NewsItem | None = None
        decision: DuplicateDecision | None = None
        for candidate in candidates:
            decision = await self._duplicate_detector.run(candidate)
            if not decision.is_duplicate:
                chosen = decision.item
                break
            report.discarded_duplicates += 1

        if chosen is None or decision is None:
            await self._repo.increment_counter("discarded", report.discarded_duplicates)
            report.errors.append("Todas las noticias candidatas eran duplicadas")
            return

        await self._repo.increment_counter(
            "discarded", report.discarded_duplicates + report.discarded_low_relevance
        )

        # 5. Generate Article (Editor).
        edited = await self._editor.run(chosen)

        # 6. Generate Discussion.
        discussion = await self._discussion_generator.run(
            DiscussionInput(item=chosen, edited=edited)
        )

        article = PublishableArticle(news_item=chosen, edited=edited, discussion=discussion)

        # 7. Publish to Discord.
        published = await self._publisher.run(article)

        # 8. Save History.
        article_id = await self._repo.save_published(published, decision.embedding)
        await self._repo.increment_counter("published", 1)
        metrics.increment("news_published")

        report.published = 1
        report.published_article = published
        logger.info("workflow.published", article_id=article_id, title=edited.title)
