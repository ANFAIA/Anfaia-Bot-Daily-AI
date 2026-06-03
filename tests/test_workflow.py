"""Integration tests for the complete daily workflow."""

from __future__ import annotations

from app.agents.discord_publisher_agent import DiscordPublisherAgent
from app.agents.discussion_generator import DiscussionGeneratorAgent
from app.agents.duplicate_detector import DuplicateDetectorAgent
from app.agents.news_classifier import NewsClassifierAgent
from app.agents.news_collector import NewsCollectorAgent
from app.agents.news_editor import NewsEditorAgent
from app.domain.entities import NewsItem
from app.workflows.daily_news_workflow import DailyNewsWorkflow
from tests.conftest import FakeSource


def _build_workflow(
    *, llm, repository, embeddings, publisher, sources, min_relevance=55
) -> DailyNewsWorkflow:
    return DailyNewsWorkflow(
        collector=NewsCollectorAgent(sources, max_items_per_source=10),
        classifier=NewsClassifierAgent(llm),
        duplicate_detector=DuplicateDetectorAgent(
            repository, embeddings, similarity_threshold=0.86
        ),
        editor=NewsEditorAgent(llm),
        discussion_generator=DiscussionGeneratorAgent(llm),
        publisher=DiscordPublisherAgent(publisher),
        repository=repository,
        min_relevance_score=min_relevance,
    )


async def test_workflow_happy_path(
    fake_llm, repository, embeddings, fake_publisher, news_item
) -> None:
    workflow = _build_workflow(
        llm=fake_llm,
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        sources=[FakeSource("OpenAI Blog", [news_item])],
    )

    report = await workflow.run()

    assert report.succeeded
    assert report.collected == 1
    assert report.published == 1
    assert len(fake_publisher.published) == 1
    # Persisted in the history.
    stored = await repository.list_articles(limit=10, offset=0)
    assert len(stored) == 1
    assert stored[0].discord_message_id is not None


async def test_workflow_no_news(fake_llm, repository, embeddings, fake_publisher) -> None:
    workflow = _build_workflow(
        llm=fake_llm,
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        sources=[FakeSource("vacía", [])],
    )
    report = await workflow.run()
    assert not report.succeeded
    assert report.published == 0
    assert report.errors


async def test_workflow_skips_duplicates(
    fake_llm, repository, embeddings, fake_publisher, news_item
) -> None:
    sources = [FakeSource("OpenAI Blog", [news_item])]
    workflow = _build_workflow(
        llm=fake_llm,
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        sources=sources,
    )
    # First run publishes.
    first = await workflow.run()
    assert first.published == 1

    # Second run with the same news item: it must be discarded as a duplicate.
    second = await workflow.run()
    assert second.published == 0
    assert second.discarded_duplicates >= 1
    assert len(fake_publisher.published) == 1


async def test_workflow_filters_low_relevance(
    fake_llm, repository, embeddings, fake_publisher, news_item
) -> None:
    workflow = _build_workflow(
        llm=fake_llm,
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        sources=[FakeSource("OpenAI Blog", [news_item])],
        min_relevance=95,  # the fake classifies at 88 -> below the threshold
    )
    report = await workflow.run()
    assert report.published == 0
    assert report.discarded_low_relevance == 1


async def test_workflow_picks_highest_ranked(
    fake_llm, repository, embeddings, fake_publisher
) -> None:
    items = [
        NewsItem(title=f"Noticia {i}", url=f"https://e.com/{i}", source="s", summary=f"r{i}")
        for i in range(3)
    ]
    workflow = _build_workflow(
        llm=fake_llm,
        repository=repository,
        embeddings=embeddings,
        publisher=fake_publisher,
        sources=[FakeSource("s", items)],
    )
    report = await workflow.run()
    assert report.collected == 3
    assert report.classified == 3
    assert report.published == 1
