"""Editorial-brain implementation of the daily news workflow.

Same `NewsWorkflow` contract as the sequential pipeline, but with a different
division of labour:

    Collect → Classify → Rank → De-duplicate  (deterministic code)
        → Editorial deliberation              (EditorialBrain port)
        → Publish → Save History              (deterministic code)

The mechanical steps (which are not judgement calls) stay in code so they remain
deterministic and testable. The judgement-heavy step — *which* news to publish,
*how* to edit it and *what* question to ask — is delegated to an
`EditorialBrain`, which in production is a deliberative agent built on
``deepagents`` (planning, sub-agents, source verification). The brain is
injected, so this workflow is fully testable with a fake brain and never
imports the orchestration framework directly.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.agents.discord_publisher_agent import DiscordPublisherAgent
from app.agents.duplicate_detector import DuplicateDetectorAgent
from app.agents.news_classifier import NewsClassifierAgent
from app.agents.news_collector import NewsCollectorAgent
from app.core.logging import get_logger
from app.core.metrics import metrics
from app.domain.entities import NewsItem, PublishableArticle, WorkflowReport
from app.interfaces.editorial import EditorialBrain
from app.interfaces.repositories import NewsRepository
from app.workflows.base import NewsWorkflow

logger = get_logger(__name__)


class DeepAgentsNewsWorkflow(NewsWorkflow):
    """Daily workflow whose editorial decision is delegated to an `EditorialBrain`."""

    def __init__(
        self,
        *,
        collector: NewsCollectorAgent,
        classifier: NewsClassifierAgent,
        duplicate_detector: DuplicateDetectorAgent,
        brain: EditorialBrain,
        publisher: DiscordPublisherAgent,
        repository: NewsRepository,
        min_relevance_score: int,
        shortlist_size: int = 5,
        recent_titles_limit: int = 15,
    ) -> None:
        self._collector = collector
        self._classifier = classifier
        self._duplicate_detector = duplicate_detector
        self._brain = brain
        self._publisher = publisher
        self._repo = repository
        self._min_relevance = min_relevance_score
        self._shortlist_size = max(1, shortlist_size)
        self._recent_titles_limit = recent_titles_limit

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
                engine="deepagents",
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

        # 4. Build a shortlist of unique candidates (drop duplicates against history),
        #    keeping each one's embedding for later persistence.
        shortlist, embeddings_by_fp = await self._build_shortlist(candidates, report)
        await self._repo.increment_counter(
            "discarded", report.discarded_duplicates + report.discarded_low_relevance
        )
        if not shortlist:
            report.errors.append("Todas las noticias candidatas eran duplicadas")
            return

        # 5. Editorial deliberation: pick one, edit it and craft the discussion.
        recent_titles = await self._recent_titles()
        decision = await self._brain.decide(shortlist, recent_titles=recent_titles)
        chosen = decision.chosen

        article = PublishableArticle(
            news_item=chosen, edited=decision.edited, discussion=decision.discussion
        )

        # 6. Publish to Discord.
        published = await self._publisher.run(article)

        # 7. Save History (with the embedding computed during de-duplication).
        embedding = embeddings_by_fp.get(chosen.url_fingerprint)
        article_id = await self._repo.save_published(published, embedding)
        await self._repo.increment_counter("published", 1)
        metrics.increment("news_published")

        report.published = 1
        report.published_article = published
        logger.info(
            "workflow.published",
            article_id=article_id,
            title=decision.edited.title,
            brain=self._brain.name,
            rationale=decision.rationale,
        )

    async def _build_shortlist(
        self, candidates: list[NewsItem], report: WorkflowReport
    ) -> tuple[list[NewsItem], dict[str, list[float]]]:
        """Collect up to ``shortlist_size`` unique candidates and their embeddings."""
        shortlist: list[NewsItem] = []
        embeddings_by_fp: dict[str, list[float]] = {}
        for candidate in candidates:
            if len(shortlist) >= self._shortlist_size:
                break
            decision = await self._duplicate_detector.run(candidate)
            if decision.is_duplicate:
                report.discarded_duplicates += 1
                continue
            shortlist.append(decision.item)
            embeddings_by_fp[decision.item.url_fingerprint] = decision.embedding
        return shortlist, embeddings_by_fp

    async def _recent_titles(self) -> list[str]:
        stored = await self._repo.list_articles(
            limit=self._recent_titles_limit, offset=0, category=None
        )
        return [article.title for article in stored]
