"""Tests for the application-layer use cases."""

from __future__ import annotations

from app.application.use_cases import (
    GetNewsUseCase,
    GetStatsUseCase,
    ListNewsUseCase,
    RunDailyWorkflowUseCase,
    SendTestMessageUseCase,
)
from app.domain.entities import (
    DiscussionPrompt,
    EditedArticle,
    NewsItem,
    PublishableArticle,
    WorkflowReport,
)
from app.domain.value_objects import Category, RelevanceScore
from app.workflows.base import NewsWorkflow


class _StubWorkflow(NewsWorkflow):
    async def run(self) -> WorkflowReport:
        report = WorkflowReport(collected=3, classified=3, published=1)
        return report


async def _seed(repository, news_item: NewsItem) -> int:
    classified = news_item.with_classification(Category.AGENTS, RelevanceScore(90))
    article = PublishableArticle(
        news_item=classified,
        edited=EditedArticle("t", "a", "b", "c", "d", news_item.url),
        discussion=DiscussionPrompt("q"),
    ).published_as(42)
    return await repository.save_published(article, [0.1] * 64)


async def test_run_workflow_use_case() -> None:
    uc = RunDailyWorkflowUseCase(_StubWorkflow())
    report = await uc.execute()
    assert report.published == 1


async def test_list_and_get_news(repository, news_item) -> None:
    article_id = await _seed(repository, news_item)
    listed = await ListNewsUseCase(repository).execute(limit=10, offset=0, category=None)
    assert len(listed) == 1
    fetched = await GetNewsUseCase(repository).execute(article_id)
    assert fetched is not None
    assert fetched.id == article_id
    assert await GetNewsUseCase(repository).execute(9999) is None


async def test_list_news_filters_by_category(repository, news_item) -> None:
    await _seed(repository, news_item)
    agents = await ListNewsUseCase(repository).execute(limit=10, offset=0, category=Category.AGENTS)
    robotics = await ListNewsUseCase(repository).execute(
        limit=10, offset=0, category=Category.ROBOTICS
    )
    assert len(agents) == 1
    assert len(robotics) == 0


async def test_stats_use_case(repository, news_item) -> None:
    await _seed(repository, news_item)
    await repository.increment_counter("analyzed", 5)
    await repository.increment_counter("discarded", 2)
    stats = await GetStatsUseCase(repository).execute()
    assert stats.analyzed == 5
    assert stats.discarded == 2
    assert stats.published >= 1
    assert stats.by_category.get("Agents") == 1


async def test_discord_test_use_case(fake_publisher) -> None:
    uc = SendTestMessageUseCase(fake_publisher)
    message_id = await uc.execute("hola")
    assert message_id > 0
    assert fake_publisher.tests == ["hola"]
