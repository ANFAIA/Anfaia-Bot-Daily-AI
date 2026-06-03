"""REST API tests via TestClient with fake dependencies."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.application.use_cases import RunDailyWorkflowUseCase, SendTestMessageUseCase
from app.core.config import EmbeddingProviderName, Settings
from app.core.container import Container
from app.domain.entities import (
    DiscussionPrompt,
    EditedArticle,
    NewsItem,
    PublishableArticle,
    WorkflowReport,
)
from app.domain.value_objects import Category, RelevanceScore
from app.infrastructure.persistence.in_memory import InMemoryNewsRepository
from app.main import create_app
from app.workflows.base import NewsWorkflow
from tests.conftest import FakePublisher


class _StubWorkflow(NewsWorkflow):
    async def run(self) -> WorkflowReport:
        item = NewsItem(title="t", url="https://e.com/x", source="s", summary="r")
        classified = item.with_classification(Category.AI, RelevanceScore(80))
        article = PublishableArticle(
            news_item=classified,
            edited=EditedArticle("Titular", "a", "b", "c", "d", item.url),
            discussion=DiscussionPrompt("q"),
        ).published_as(123)
        return WorkflowReport(collected=2, classified=2, published=1, published_article=article)


def _test_settings() -> Settings:
    return Settings(
        openai_api_key="test-key",
        embedding_provider=EmbeddingProviderName.HASH,
        embedding_dim=64,
        scheduler_enabled=False,
        discord_token=None,
        discord_channel_id=None,
        _env_file=None,
    )


@pytest.fixture
def container():
    settings = _test_settings()
    instance = Container(settings, repository=InMemoryNewsRepository())
    yield instance
    asyncio.run(instance.aclose())


@pytest.fixture
def client(container: Container):
    app = create_app(container.settings, container=container)
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_stats_empty(client: TestClient) -> None:
    response = client.get("/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["analyzed"] == 0
    assert body["published"] == 0


def test_workflow_run(client: TestClient, container: Container) -> None:
    container.run_workflow_uc = RunDailyWorkflowUseCase(_StubWorkflow())
    response = client.post("/workflow/run")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["published"] == 1
    assert body["published_title"] == "Titular"
    assert body["discord_message_id"] == 123


def test_news_list_and_detail(client: TestClient, container: Container) -> None:
    # Persist directly via the container's repository (in-memory).
    item = NewsItem(title="Noticia", url="https://e.com/n", source="s", summary="r")
    classified = item.with_classification(Category.RESEARCH, RelevanceScore(77))
    article = PublishableArticle(
        news_item=classified,
        edited=EditedArticle("t", "a", "b", "c", "d", item.url),
        discussion=DiscussionPrompt("q"),
    ).published_as(99)

    article_id = asyncio.run(container.repository.save_published(article, None))

    listed = client.get("/news").json()
    assert len(listed) == 1
    detail = client.get(f"/news/{article_id}")
    assert detail.status_code == 200
    assert detail.json()["category"] == "Research"

    missing = client.get("/news/123456")
    assert missing.status_code == 404


def test_discord_test_not_configured(client: TestClient) -> None:
    # No token configured -> NullPublisher -> 503.
    response = client.post("/discord/test", json={"message": "hola"})
    assert response.status_code == 503


def test_discord_test_success(client: TestClient, container: Container) -> None:
    publisher = FakePublisher()
    container.test_discord_uc = SendTestMessageUseCase(publisher)
    response = client.post("/discord/test", json={"message": "hola"})
    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert publisher.tests == ["hola"]
