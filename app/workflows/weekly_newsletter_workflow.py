"""Weekly newsletter workflow.

Pipeline:

    Collect → Classify → Rank → Dedup (intra-batch, semantic) → Edit each
    → Render HTML → Publish to GitHub Pages → Announce on Discord → Save record

Unlike the daily pipeline it picks the **top N distinct** stories of the week
(not a single one) and explains every one of them with the very same editorial
format (the five sections + a community question). Deduplication is done only
among this run's candidates — a weekly recap may legitimately include stories
that were already shared in the dailies, so the published-history check is not
used here.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.agents.discussion_generator import DiscussionGeneratorAgent, DiscussionInput
from app.agents.news_classifier import NewsClassifierAgent
from app.agents.news_collector import NewsCollectorAgent
from app.agents.news_editor import NewsEditorAgent
from app.agents.newsletter_overview import NewsletterOverviewAgent
from app.core.logging import get_logger
from app.domain.entities import NewsItem
from app.domain.newsletter import Newsletter, NewsletterEntry, NewsletterReport
from app.interfaces.embeddings import EmbeddingProvider
from app.interfaces.publisher import Publisher, PublisherError
from app.interfaces.repositories import NewsRepository, StoredNewsletter
from app.interfaces.site_publisher import SitePublisher, SitePublisherError

logger = get_logger(__name__)

_MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors; 0 if either is null/mismatched."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _week_label(monday: date, sunday: date) -> str:
    """Human-friendly Spanish label, e.g. 'Semana del 1 al 7 de junio de 2026'."""
    if monday.month == sunday.month:
        return (
            f"Semana del {monday.day} al {sunday.day} de "
            f"{_MONTHS_ES[sunday.month - 1]} de {sunday.year}"
        )
    return (
        f"Semana del {monday.day} de {_MONTHS_ES[monday.month - 1]} "
        f"al {sunday.day} de {_MONTHS_ES[sunday.month - 1]} de {sunday.year}"
    )


class WeeklyNewsletterWorkflow:
    """Builds and publishes the weekly HTML newsletter."""

    def __init__(
        self,
        *,
        collector: NewsCollectorAgent,
        classifier: NewsClassifierAgent,
        editor: NewsEditorAgent,
        discussion_generator: DiscussionGeneratorAgent,
        overview_generator: NewsletterOverviewAgent,
        embeddings: EmbeddingProvider,
        publisher: Publisher,
        site_publisher: SitePublisher,
        renderer: Callable[..., str],
        index_renderer: Callable[[list[StoredNewsletter]], str],
        repository: NewsRepository,
        min_relevance_score: int,
        top_n: int,
        extra_relevance: int,
        dedup_threshold: float,
        timezone: str,
        path_prefix: str,
    ) -> None:
        self._collector = collector
        self._classifier = classifier
        self._editor = editor
        self._discussion_generator = discussion_generator
        self._overview_generator = overview_generator
        self._embeddings = embeddings
        self._publisher = publisher
        self._site_publisher = site_publisher
        self._render = renderer
        self._render_index = index_renderer
        self._repo = repository
        self._min_relevance = min_relevance_score
        self._top_n = max(1, top_n)
        self._extra_relevance = extra_relevance
        self._dedup_threshold = dedup_threshold
        self._tz = ZoneInfo(timezone)
        self._path_prefix = path_prefix.strip("/")
        # Relative link from a permalink (under path_prefix) back to the root index.
        depth = len([p for p in self._path_prefix.split("/") if p])
        self._index_href = "../" * depth + "index.html"

    async def run(self) -> NewsletterReport:
        report = NewsletterReport(started_at=datetime.now(UTC))
        try:
            await self._run_pipeline(report)
        except Exception as exc:
            logger.exception("newsletter.failed")
            report.errors.append(str(exc))
        finally:
            report.finished_at = datetime.now(UTC)
            logger.info(
                "newsletter.finished",
                status="success" if report.succeeded else "failed",
                collected=report.collected,
                selected=report.selected,
                published=report.published_count,
                url=report.public_url,
            )
        return report

    async def _run_pipeline(self, report: NewsletterReport) -> None:
        # 1. Collect.
        collected = await self._collector.run(None)
        cutoff = datetime.now(self._tz) - timedelta(days=7)
        collected = [it for it in collected if self._within_week(it, cutoff)]
        report.collected = len(collected)
        if not collected:
            report.errors.append("No se recolectó ninguna noticia para el boletín")
            return

        # 2. Classify (in parallel).
        classified = await asyncio.gather(*(self._classifier.run(it) for it in collected))
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
        if not candidates:
            report.errors.append("Ninguna noticia superó el umbral de relevancia")
            return

        # 4. Dedup intra-batch (semantic), then pick ensuring category coverage.
        distinct = await self._distinct_candidates(candidates)
        selected = self._pick_with_category_coverage(distinct)
        report.selected = len(selected)

        # 5. Generate editorial content for each selected story (in parallel).
        entries = await asyncio.gather(*(self._make_entry(it) for it in selected))
        if not entries:
            report.errors.append("No se pudo generar contenido para ninguna noticia")
            return

        # 6. Editorial reflection over the whole set, then build the aggregate.
        overview = await self._overview_generator.run(list(entries))
        newsletter = self._build_newsletter(tuple(entries), overview)

        # 7. Render the weekly page (with a "back to index" link).
        html = self._render(newsletter, index_href=self._index_href)

        # 8. Publish the weekly permalink to GitHub Pages. Abort on failure.
        slug = f"{newsletter.iso_year}-W{newsletter.iso_week:02d}.html"
        permalink_path = f"{self._path_prefix}/{slug}"
        commit_msg = f"Boletín IA · {newsletter.week_label}"
        try:
            published = await self._site_publisher.publish_html(
                path=permalink_path, html=html, commit_message=commit_msg
            )
        except SitePublisherError as exc:
            logger.error("newsletter.publish_failed", error=str(exc))
            report.errors.append(f"No se pudo publicar el HTML: {exc}")
            return

        report.public_url = published.public_url
        report.published_count = newsletter.count

        # The HTML is already live; the DB is only used for idempotency/record, so
        # any DB problem here must NOT prevent the Discord announcement.
        # 9. Skip the announcement if this issue was already announced (best effort).
        already = False
        try:
            already = await self._repo.newsletter_exists(newsletter.iso_year, newsletter.iso_week)
        except Exception as exc:
            logger.warning("newsletter.exists_check_failed", error=str(exc))
            report.errors.append(f"No se pudo comprobar el registro previo: {exc}")

        # 10. Announce on Discord (non-fatal on failure).
        message_id: int | None = None
        if already:
            logger.info("newsletter.already_announced", week=newsletter.week_label)
        else:
            try:
                message_id = await self._publisher.publish_newsletter_announcement(
                    newsletter, published.public_url
                )
                report.discord_message_id = message_id
            except PublisherError as exc:
                logger.error("newsletter.announce_failed", error=str(exc))
                report.errors.append(f"No se pudo anunciar en Discord: {exc}")

        # 11. Persist the record (idempotent per ISO week; non-fatal on failure).
        try:
            await self._repo.save_newsletter(
                newsletter, public_url=published.public_url, discord_message_id=message_id
            )
        except Exception as exc:
            logger.warning("newsletter.record_failed", error=str(exc))
            report.errors.append(f"No se pudo registrar el boletín: {exc}")

        # 12. Rebuild the index page from the recorded newsletters (non-fatal).
        await self._publish_index(report)

    async def _publish_index(self, report: NewsletterReport) -> None:
        """Regenerate index.html linking to every recorded newsletter (best effort)."""
        try:
            editions = await self._repo.list_newsletters()
            if not editions:
                return  # nothing recorded (e.g. DB down): keep the existing index
            index_html = self._render_index(editions)
            await self._site_publisher.publish_html(
                path="index.html", html=index_html, commit_message="Índice de boletines IA"
            )
        except Exception as exc:
            logger.warning("newsletter.index_failed", error=str(exc))
            report.errors.append(f"No se pudo actualizar el índice: {exc}")

    def _within_week(self, item: NewsItem, cutoff: datetime) -> bool:
        """Keep items without a date (treat as recent) or published within 7 days."""
        if item.published_at is None:
            return True
        published = item.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        return published >= cutoff

    async def _distinct_candidates(self, candidates: list[NewsItem]) -> list[NewsItem]:
        """Drop semantically duplicated candidates, keeping relevance order."""
        vectors = await self._embeddings.embed_batch([c.embedding_text for c in candidates])
        distinct: list[NewsItem] = []
        kept_vectors: list[list[float]] = []
        for item, vector in zip(candidates, vectors, strict=True):
            if any(_cosine(vector, kept) >= self._dedup_threshold for kept in kept_vectors):
                continue
            distinct.append(item)
            kept_vectors.append(vector)
        return distinct

    def _pick_with_category_coverage(self, distinct: list[NewsItem]) -> list[NewsItem]:
        """Pick at least one story per category, then add very relevant extras.

        `distinct` is ordered by relevance (desc), so the first item seen for a
        category is its most relevant one. After guaranteeing coverage, the most
        relevant remaining stories are added (those above `extra_relevance`),
        bounded by `top_n` (which can only grow to fit the per-category floor).
        """
        selected: list[NewsItem] = []
        covered: set[str] = set()
        for item in distinct:
            if item.category.value not in covered:
                covered.add(item.category.value)
                selected.append(item)

        cap = max(self._top_n, len(selected))
        for item in distinct:
            if len(selected) >= cap:
                break
            if item in selected:
                continue
            if item.relevance_score and item.relevance_score.value >= self._extra_relevance:
                selected.append(item)

        selected.sort(
            key=lambda it: it.relevance_score.value if it.relevance_score else 0, reverse=True
        )
        return selected

    async def _make_entry(self, item: NewsItem) -> NewsletterEntry:
        edited = await self._editor.run(item)
        discussion = await self._discussion_generator.run(DiscussionInput(item=item, edited=edited))
        return NewsletterEntry(news_item=item, edited=edited, discussion=discussion)

    def _build_newsletter(
        self, entries: tuple[NewsletterEntry, ...], overview: str
    ) -> Newsletter:
        now = datetime.now(self._tz)
        iso = now.isocalendar()
        monday = date.fromisocalendar(iso.year, iso.week, 1)
        sunday = date.fromisocalendar(iso.year, iso.week, 7)
        return Newsletter(
            week_label=_week_label(monday, sunday),
            iso_year=iso.year,
            iso_week=iso.week,
            generated_at=now,
            entries=entries,
            overview=overview,
        )
