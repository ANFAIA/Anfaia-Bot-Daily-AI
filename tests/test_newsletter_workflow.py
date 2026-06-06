"""Integration tests for the weekly newsletter workflow."""

from __future__ import annotations

import json
import re

from app.agents.discussion_generator import DiscussionGeneratorAgent
from app.agents.news_classifier import NewsClassifierAgent
from app.agents.news_collector import NewsCollectorAgent
from app.agents.news_editor import NewsEditorAgent
from app.agents.newsletter_overview import NewsletterOverviewAgent
from app.domain.entities import NewsItem
from app.infrastructure.discord.null_publisher import NullPublisher
from app.infrastructure.newsletter.html_renderer import (
    render_index_html,
    render_newsletter_html,
)
from app.workflows.weekly_newsletter_workflow import WeeklyNewsletterWorkflow
from tests.conftest import (
    BrokenLLM,
    BrokenSitePublisher,
    FakeLLM,
    FakeSitePublisher,
    FakeSource,
)


class MultiCategoryLLM(FakeLLM):
    """Classifies each item using a ``[Category#score]`` marker in its title."""

    async def complete_json(self, messages, *, temperature=0.2, max_tokens=1024) -> str:
        system = next((m.content for m in messages if m.role == "system"), "")
        if "Clasificas noticias" in system:
            user = next((m.content for m in messages if m.role == "user"), "")
            match = re.search(r"\[([A-Za-z ]+)#(\d+)\]", user)
            cat, score = match.group(1), int(match.group(2))
            return json.dumps({"category": cat, "relevance_score": score, "reason": "t"})
        return await super().complete_json(messages, temperature=temperature, max_tokens=max_tokens)


def _items(n: int) -> list[NewsItem]:
    return [
        NewsItem(
            title=f"Noticia distinta numero {i}",
            url=f"https://example.com/n{i}",
            source="OpenAI Blog",
            summary=f"Resumen unico sobre el tema {i} con palabras propias {i}.",
        )
        for i in range(n)
    ]


def _build(
    *,
    llm,
    repository,
    embeddings,
    publisher,
    site_publisher,
    sources,
    editor_llm=None,
    min_relevance=50,
    top_n=5,
    extra_relevance=80,
    dedup_threshold=0.86,
) -> WeeklyNewsletterWorkflow:
    editor_llm = editor_llm or llm
    return WeeklyNewsletterWorkflow(
        collector=NewsCollectorAgent(sources, max_items_per_source=20),
        classifier=NewsClassifierAgent(llm),
        editor=NewsEditorAgent(editor_llm),
        discussion_generator=DiscussionGeneratorAgent(editor_llm),
        overview_generator=NewsletterOverviewAgent(editor_llm),
        embeddings=embeddings,
        publisher=publisher,
        site_publisher=site_publisher,
        renderer=render_newsletter_html,
        index_renderer=render_index_html,
        repository=repository,
        min_relevance_score=min_relevance,
        top_n=top_n,
        extra_relevance=extra_relevance,
        dedup_threshold=dedup_threshold,
        timezone="Europe/Madrid",
        path_prefix="newsletters",
    )


async def test_newsletter_happy_path(fake_llm, repository, embeddings, fake_publisher) -> None:
    site = FakeSitePublisher()
    workflow = _build(
        llm=fake_llm,
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        site_publisher=site,
        sources=[FakeSource("OpenAI Blog", _items(3))],
        top_n=2,
    )

    report = await workflow.run()

    assert report.succeeded
    assert report.selected == 2
    assert report.published_count == 2
    assert report.public_url is not None
    # Permalink + index were published.
    assert len(site.pages) == 2
    pages = dict(site.pages)
    permalink_path = next(p for p in pages if p.startswith("newsletters/") and p.endswith(".html"))
    assert "index.html" in pages
    # The weekly page has a "back to index" button.
    assert 'class="backlink"' in pages[permalink_path]
    assert 'href="../index.html"' in pages[permalink_path]
    # The editorial reflection over the week is shown in the intro.
    assert "Esta semana destacan los agentes" in pages[permalink_path]
    # The index links to the just-published weekly edition.
    assert 'class="edition"' in pages["index.html"]
    assert permalink_path.rsplit("/", 1)[-1] in pages["index.html"]
    # Announced once and recorded for the current ISO week.
    assert len(fake_publisher.announcements) == 1
    from datetime import datetime
    from zoneinfo import ZoneInfo

    iso = datetime.now(ZoneInfo("Europe/Madrid")).isocalendar()
    assert await repository.newsletter_exists(iso.year, iso.week)


async def test_newsletter_dedupes_similar_stories(
    fake_llm, repository, embeddings, fake_publisher
) -> None:
    duplicate = NewsItem(
        title="Mismo titular repetido",
        url="https://example.com/a",
        source="OpenAI Blog",
        summary="Mismo contenido exacto repetido.",
    )
    near_copy = NewsItem(
        title="Mismo titular repetido",
        url="https://example.com/b",  # different URL -> survives URL dedup
        source="VentureBeat",
        summary="Mismo contenido exacto repetido.",
    )
    site = FakeSitePublisher()
    workflow = _build(
        llm=fake_llm,
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        site_publisher=site,
        sources=[FakeSource("s", [duplicate, near_copy])],
        top_n=5,
    )

    report = await workflow.run()

    assert report.collected == 2
    assert report.selected == 1  # semantic dedup collapsed the near-copy


async def test_newsletter_respects_top_n(fake_llm, repository, embeddings, fake_publisher) -> None:
    workflow = _build(
        llm=fake_llm,
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        site_publisher=FakeSitePublisher(),
        sources=[FakeSource("s", _items(5))],
        top_n=3,
    )
    report = await workflow.run()
    assert report.collected == 5
    assert report.selected == 3
    assert report.published_count == 3


async def test_newsletter_covers_each_category_plus_extras(
    repository, embeddings, fake_publisher
) -> None:
    items = [
        NewsItem(title="[AI#95] Modelo nuevo", url="https://e.com/1", source="s", summary="uno"),
        NewsItem(title="[Agents#92] Agente", url="https://e.com/2", source="s", summary="dos"),
        NewsItem(title="[Robotics#70] Robot", url="https://e.com/3", source="s", summary="tres"),
        NewsItem(title="[AI#91] Otro modelo", url="https://e.com/4", source="s", summary="cuatro"),
    ]
    site = FakeSitePublisher()
    workflow = _build(
        llm=MultiCategoryLLM(),
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        site_publisher=site,
        sources=[FakeSource("s", items)],
        top_n=4,
        extra_relevance=90,
    )

    report = await workflow.run()

    assert report.succeeded
    # One per present category (AI, Agents, Robotics) + the very relevant extra AI.
    assert report.selected == 4
    html = site.pages[0][1]
    for category in ("AI", "Agents", "Robotics"):
        assert f'class="badge">{category}<' in html


async def test_newsletter_db_failure_still_announces(
    fake_llm, embeddings, fake_publisher
) -> None:
    # The DB is down: the record/idempotency check fails, but the HTML is live
    # and the Discord announcement must still happen.
    from app.infrastructure.persistence.in_memory import InMemoryNewsRepository

    class BrokenRepo(InMemoryNewsRepository):
        async def newsletter_exists(self, iso_year: int, iso_week: int) -> bool:
            raise RuntimeError("db down")

        async def save_newsletter(self, newsletter, *, public_url, discord_message_id) -> int:
            raise RuntimeError("db down")

    workflow = _build(
        llm=fake_llm,
        repository=BrokenRepo(),
        embeddings=embeddings,
        publisher=fake_publisher,
        site_publisher=FakeSitePublisher(),
        sources=[FakeSource("s", _items(2))],
    )
    report = await workflow.run()
    assert report.public_url is not None
    assert report.published_count == 2
    assert len(fake_publisher.announcements) == 1  # announced despite DB failure
    assert report.discord_message_id is not None
    assert any("registrar" in e for e in report.errors)


async def test_newsletter_no_news(fake_llm, repository, embeddings, fake_publisher) -> None:
    site = FakeSitePublisher()
    workflow = _build(
        llm=fake_llm,
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        site_publisher=site,
        sources=[FakeSource("vacía", [])],
    )
    report = await workflow.run()
    assert not report.succeeded
    assert report.errors
    assert site.pages == []


async def test_newsletter_filters_low_relevance(
    fake_llm, repository, embeddings, fake_publisher
) -> None:
    workflow = _build(
        llm=fake_llm,
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        site_publisher=FakeSitePublisher(),
        sources=[FakeSource("s", _items(3))],
        min_relevance=95,  # fake classifies at 88
    )
    report = await workflow.run()
    assert not report.succeeded
    assert report.published_count == 0


async def test_newsletter_editor_failure_degrades(
    fake_llm, repository, embeddings, fake_publisher
) -> None:
    # Classification works (fake_llm) but the editor/discussion LLM is down.
    site = FakeSitePublisher()
    workflow = _build(
        llm=fake_llm,
        editor_llm=BrokenLLM(),
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        site_publisher=site,
        sources=[FakeSource("s", _items(2))],
    )
    report = await workflow.run()
    # The newsletter is still published with fallback editorial content.
    assert report.succeeded
    assert report.published_count == 2
    assert len(fake_publisher.announcements) == 1


async def test_newsletter_site_failure_skips_announcement(
    fake_llm, repository, embeddings, fake_publisher
) -> None:
    workflow = _build(
        llm=fake_llm,
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        site_publisher=BrokenSitePublisher(),
        sources=[FakeSource("s", _items(2))],
    )
    report = await workflow.run()
    assert not report.succeeded
    assert report.public_url is None
    assert report.errors
    assert fake_publisher.announcements == []


async def test_newsletter_discord_failure_is_non_fatal(
    fake_llm, repository, embeddings
) -> None:
    # NullPublisher raises PublisherError on announce; the HTML is already live.
    workflow = _build(
        llm=fake_llm,
        repository=repository,
        embeddings=embeddings,
        publisher=NullPublisher(),
        site_publisher=FakeSitePublisher(),
        sources=[FakeSource("s", _items(2))],
    )
    report = await workflow.run()
    assert report.public_url is not None
    assert report.published_count == 2
    assert any("Discord" in e for e in report.errors)
