"""Tests for infrastructure adapters testable without external services."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.core.metrics import Metrics
from app.domain.entities import (
    DiscussionPrompt,
    EditedArticle,
    NewsItem,
    PublishableArticle,
)
from app.domain.newsletter import Newsletter, NewsletterEntry
from app.domain.value_objects import Category, RelevanceScore
from app.infrastructure.discord.embed_builder import (
    build_article_embed,
    build_newsletter_announcement_embed,
)
from app.infrastructure.discord.null_publisher import NullPublisher
from app.infrastructure.embeddings.hash_embeddings import HashEmbeddingProvider
from app.infrastructure.persistence.in_memory import InMemoryNewsRepository, cosine_similarity
from app.infrastructure.sources.registry import build_default_sources
from app.infrastructure.sources.text import clean_html, truncate
from app.interfaces.publisher import PublisherError


def _article(url: str = "https://e.com/a") -> PublishableArticle:
    item = NewsItem(title="t", url=url, source="OpenAI Blog", summary="r")
    classified = item.with_classification(Category.AGENTS, RelevanceScore(88))
    return PublishableArticle(
        news_item=classified,
        edited=EditedArticle(
            title="Titular",
            what_happened="qué",
            why_it_matters="por qué",
            how_we_could_use_it="uso",
            limitations="límites",
            source_url=url,
        ),
        discussion=DiscussionPrompt("¿pregunta?"),
    )


# --- text utils ---
def test_clean_html() -> None:
    assert clean_html("<p>Hola&nbsp;<b>mundo</b></p>") == "Hola mundo"


def test_truncate() -> None:
    assert truncate("hola", 10) == "hola"
    assert truncate("abcdef", 4).endswith("…")
    assert len(truncate("abcdef", 4)) == 4


# --- embeddings hash ---
async def test_hash_embeddings_deterministic() -> None:
    provider = HashEmbeddingProvider(dimension=32)
    a = await provider.embed("agentes de inteligencia artificial")
    b = await provider.embed("agentes de inteligencia artificial")
    assert a == b
    assert len(a) == 32


async def test_hash_embeddings_empty_text() -> None:
    provider = HashEmbeddingProvider(dimension=16)
    vector = await provider.embed("")
    assert vector == [0.0] * 16


async def test_embed_batch_default() -> None:
    provider = HashEmbeddingProvider(dimension=8)
    vectors = await provider.embed_batch(["a", "b"])
    assert len(vectors) == 2


# --- cosine similarity ---
def test_cosine_similarity() -> None:
    assert cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine_similarity([], [1]) == 0.0
    assert cosine_similarity([0, 0], [1, 1]) == 0.0


# --- in-memory repo ---
async def test_in_memory_repository_flow() -> None:
    repo = InMemoryNewsRepository()
    article = _article()
    embedding = [1.0, 0.0, 0.0]
    article_id = await repo.save_published(article, embedding)

    assert await repo.url_exists(article.news_item.url_fingerprint)
    assert not await repo.url_exists("inexistente")

    similar = await repo.find_similar([1.0, 0.0, 0.0], threshold=0.9)
    assert similar and similar[0].article_id == article_id

    none = await repo.find_similar([0.0, 1.0, 0.0], threshold=0.9)
    assert none == []

    await repo.increment_counter("analyzed", 3)
    stats = await repo.stats()
    assert stats.analyzed == 3
    assert stats.published == 1
    assert stats.by_category["Agents"] == 1


# --- discord embed ---
def test_build_article_embed() -> None:
    embed = build_article_embed(_article())
    titles = [field.name for field in embed.fields]
    assert "🔍 Qué ha pasado" in titles
    assert "💬 Pregunta para la comunidad" in titles
    assert embed.url == "https://e.com/a"


def test_build_article_embed_truncates_long_fields() -> None:
    item = NewsItem(title="t", url="https://e.com/a", source="s", summary="r")
    classified = item.with_classification(Category.AI, RelevanceScore(50))
    article = PublishableArticle(
        news_item=classified,
        edited=EditedArticle("t", "x" * 5000, "b", "c", "d", "https://e.com/a"),
        discussion=DiscussionPrompt("q"),
    )
    embed = build_article_embed(article)
    what = next(f for f in embed.fields if f.name == "🔍 Qué ha pasado")
    assert len(what.value) <= 1024


def _newsletter(n: int = 2) -> Newsletter:
    entry = NewsletterEntry(
        news_item=_article().news_item,
        edited=_article().edited,
        discussion=DiscussionPrompt("¿pregunta?"),
    )
    return Newsletter(
        week_label="Semana del 1 al 7 de junio de 2026",
        iso_year=2026,
        iso_week=23,
        generated_at=datetime(2026, 6, 6, 9, 0, tzinfo=UTC),
        entries=tuple(entry for _ in range(n)),
    )


def test_build_newsletter_announcement_embed() -> None:
    url = "https://o.github.io/r/newsletters/2026-W23.html"
    embed = build_newsletter_announcement_embed(_newsletter(2), url)
    assert embed.url == url
    assert "Semana del 1 al 7 de junio de 2026" in embed.title
    # All headlines collapsed into a single field.
    field = next(f for f in embed.fields if f.name == "En esta edición")
    assert "1." in field.value and "2." in field.value


def test_build_newsletter_announcement_truncates_headlines() -> None:
    embed = build_newsletter_announcement_embed(_newsletter(40), "https://e.com/x")
    field = next(f for f in embed.fields if f.name == "En esta edición")
    assert len(field.value) <= 1024


# --- null publisher ---
async def test_null_publisher_raises() -> None:
    publisher = NullPublisher()
    with pytest.raises(PublisherError):
        await publisher.publish(_article())
    with pytest.raises(PublisherError):
        await publisher.publish_test_message("x")


# --- sources registry ---
async def test_registry_builds_all_sources() -> None:
    async with httpx.AsyncClient() as client:
        sources = build_default_sources(client)
    names = {s.name for s in sources}
    assert "OpenAI Blog" in names
    assert "Hacker News" in names
    assert "Reddit r/MachineLearning" in names
    assert len(sources) == 9


# --- metrics ---
def test_metrics() -> None:
    m = Metrics()
    m.increment("x")
    m.increment("x", 2)
    now = datetime.now(UTC)
    m.record_run("success", now)
    snap = m.snapshot()
    assert snap["counters"]["x"] == 3
    assert snap["last_run_status"] == "success"
    assert snap["last_run_at"] == now.isoformat()
