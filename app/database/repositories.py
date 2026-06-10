"""SQLAlchemy implementation of the news repository.

Uses pgvector for similarity search (cosine distance). Similarity is derived as
`1 - cosine_distance`.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.models import (
    NewsArticle,
    NewsEmbedding,
    Newsletter,
    Podcast,
    WorkflowCounter,
)
from app.database.session import Database
from app.domain.entities import PublishableArticle
from app.domain.newsletter import Newsletter as NewsletterEntity
from app.domain.podcast import PodcastEpisode
from app.domain.value_objects import Category
from app.interfaces.repositories import (
    NewsRepository,
    SimilarArticle,
    StatsSnapshot,
    StoredArticle,
    StoredNewsletter,
    StoredPodcast,
)

COUNTER_ANALYZED = "analyzed"
COUNTER_PUBLISHED = "published"
COUNTER_DISCARDED = "discarded"


class SqlAlchemyNewsRepository(NewsRepository):
    """News repository backed by PostgreSQL + pgvector."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def url_exists(self, url_fingerprint: str) -> bool:
        async with self._db.session() as session:
            stmt = select(NewsArticle.id).where(NewsArticle.url_fingerprint == url_fingerprint)
            return (await session.execute(stmt)).first() is not None

    async def find_similar(
        self, embedding: list[float], threshold: float, limit: int = 5
    ) -> list[SimilarArticle]:
        max_distance = 1.0 - threshold
        distance = NewsEmbedding.embedding.cosine_distance(embedding)
        async with self._db.session() as session:
            stmt = (
                select(
                    NewsEmbedding.article_id,
                    NewsArticle.url,
                    distance.label("distance"),
                )
                .join(NewsArticle, NewsArticle.id == NewsEmbedding.article_id)
                .where(distance <= max_distance)
                .order_by(distance)
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()
        return [
            SimilarArticle(article_id=r.article_id, url=r.url, similarity=1.0 - r.distance)
            for r in rows
        ]

    async def save_published(
        self, article: PublishableArticle, embedding: list[float] | None
    ) -> int:
        item = article.news_item
        async with self._db.session() as session:
            orm_article = NewsArticle(
                title=item.title,
                url=item.url,
                url_fingerprint=item.url_fingerprint,
                source=item.source,
                category=article.category.value,
                published_at=item.published_at,
                relevance_score=article.relevance_score.value,
                summary=item.summary,
                discord_message_id=article.discord_message_id,
            )
            session.add(orm_article)
            await session.flush()
            if embedding is not None:
                session.add(NewsEmbedding(article_id=orm_article.id, embedding=embedding))
            await session.flush()
            return orm_article.id

    async def increment_counter(self, name: str, amount: int = 1) -> None:
        async with self._db.session() as session:
            stmt = (
                pg_insert(WorkflowCounter)
                .values(name=name, value=amount)
                .on_conflict_do_update(
                    index_elements=[WorkflowCounter.name],
                    set_={"value": WorkflowCounter.value + amount},
                )
            )
            await session.execute(stmt)

    async def list_articles(
        self, *, limit: int, offset: int, category: Category | None = None
    ) -> list[StoredArticle]:
        async with self._db.session() as session:
            stmt = select(NewsArticle).order_by(NewsArticle.created_at.desc())
            if category is not None:
                stmt = stmt.where(NewsArticle.category == category.value)
            stmt = stmt.limit(limit).offset(offset)
            rows = (await session.execute(stmt)).scalars().all()
        return [self._to_stored(row) for row in rows]

    async def get_article(self, article_id: int) -> StoredArticle | None:
        async with self._db.session() as session:
            row = await session.get(NewsArticle, article_id)
            return self._to_stored(row) if row else None

    async def stats(self) -> StatsSnapshot:
        async with self._db.session() as session:
            counters = dict(
                (await session.execute(select(WorkflowCounter.name, WorkflowCounter.value))).all()
            )
            by_category = dict(
                (
                    await session.execute(
                        select(NewsArticle.category, func.count()).group_by(NewsArticle.category)
                    )
                ).all()
            )
            published = (
                await session.execute(select(func.count()).select_from(NewsArticle))
            ).scalar_one()

        return StatsSnapshot(
            analyzed=counters.get(COUNTER_ANALYZED, 0),
            published=max(counters.get(COUNTER_PUBLISHED, 0), published),
            discarded=counters.get(COUNTER_DISCARDED, 0),
            by_category=by_category,
            last_run_at=None,
            last_run_status=None,
        )

    async def newsletter_exists(self, iso_year: int, iso_week: int) -> bool:
        async with self._db.session() as session:
            stmt = select(Newsletter.id).where(
                Newsletter.iso_year == iso_year, Newsletter.iso_week == iso_week
            )
            return (await session.execute(stmt)).first() is not None

    async def save_newsletter(
        self, newsletter: NewsletterEntity, *, public_url: str, discord_message_id: int | None
    ) -> int:
        async with self._db.session() as session:
            stmt = (
                pg_insert(Newsletter)
                .values(
                    iso_year=newsletter.iso_year,
                    iso_week=newsletter.iso_week,
                    week_label=newsletter.week_label,
                    public_url=public_url,
                    item_count=newsletter.count,
                    generated_at=newsletter.generated_at,
                    discord_message_id=discord_message_id,
                )
                .on_conflict_do_update(
                    constraint="uq_newsletter_year_week",
                    set_={
                        "week_label": newsletter.week_label,
                        "public_url": public_url,
                        "item_count": newsletter.count,
                        "generated_at": newsletter.generated_at,
                        "discord_message_id": discord_message_id,
                    },
                )
                .returning(Newsletter.id)
            )
            return (await session.execute(stmt)).scalar_one()

    async def list_newsletters(self, *, limit: int = 200) -> list[StoredNewsletter]:
        async with self._db.session() as session:
            stmt = (
                select(Newsletter)
                .order_by(Newsletter.iso_year.desc(), Newsletter.iso_week.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [
            StoredNewsletter(
                id=row.id,
                iso_year=row.iso_year,
                iso_week=row.iso_week,
                week_label=row.week_label,
                public_url=row.public_url,
                item_count=row.item_count,
                generated_at=row.generated_at,
                discord_message_id=row.discord_message_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def podcast_exists(self, iso_year: int, iso_week: int) -> bool:
        async with self._db.session() as session:
            stmt = select(Podcast.id).where(
                Podcast.iso_year == iso_year, Podcast.iso_week == iso_week
            )
            return (await session.execute(stmt)).first() is not None

    async def save_podcast(self, episode: PodcastEpisode, *, discord_message_id: int | None) -> int:
        values = {
            "iso_year": episode.iso_year,
            "iso_week": episode.iso_week,
            "week_label": episode.week_label,
            "title": episode.title,
            "audio_url": episode.audio_url,
            "page_url": episode.page_url,
            "duration_seconds": episode.duration_seconds,
            "byte_size": episode.byte_size,
            "summary": episode.summary,
            "generated_at": episode.generated_at,
            "discord_message_id": discord_message_id,
        }
        async with self._db.session() as session:
            stmt = (
                pg_insert(Podcast)
                .values(**values)
                .on_conflict_do_update(
                    constraint="uq_podcast_year_week",
                    set_={k: v for k, v in values.items() if k not in ("iso_year", "iso_week")},
                )
                .returning(Podcast.id)
            )
            return (await session.execute(stmt)).scalar_one()

    async def list_podcasts(self, *, limit: int = 200) -> list[StoredPodcast]:
        async with self._db.session() as session:
            stmt = (
                select(Podcast)
                .order_by(Podcast.iso_year.desc(), Podcast.iso_week.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
        return [
            StoredPodcast(
                id=row.id,
                iso_year=row.iso_year,
                iso_week=row.iso_week,
                week_label=row.week_label,
                title=row.title,
                audio_url=row.audio_url,
                page_url=row.page_url,
                duration_seconds=row.duration_seconds,
                byte_size=row.byte_size,
                summary=row.summary,
                generated_at=row.generated_at,
                discord_message_id=row.discord_message_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

    @staticmethod
    def _to_stored(row: NewsArticle) -> StoredArticle:
        return StoredArticle(
            id=row.id,
            title=row.title,
            url=row.url,
            source=row.source,
            category=Category.from_str(row.category),
            relevance_score=row.relevance_score,
            summary=row.summary,
            published_at=row.published_at,
            discord_message_id=row.discord_message_id,
            created_at=row.created_at,
        )
