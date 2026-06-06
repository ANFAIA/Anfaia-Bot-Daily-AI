"""Shared test fixtures and test doubles."""

from __future__ import annotations

import json

import pytest

from app.domain.entities import NewsItem, PublishableArticle
from app.domain.newsletter import Newsletter
from app.infrastructure.embeddings.hash_embeddings import HashEmbeddingProvider
from app.infrastructure.persistence.in_memory import InMemoryNewsRepository
from app.interfaces.llm import ChatMessage, LLMProvider
from app.interfaces.news_source import NewsSource
from app.interfaces.publisher import Publisher
from app.interfaces.site_publisher import PublishedSite, SitePublisher, SitePublisherError


class FakeLLM(LLMProvider):
    """Deterministic LLM that responds based on the system prompt received."""

    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> str:
        return await self.complete_json(messages, temperature=temperature, max_tokens=max_tokens)

    async def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        self.calls.append(messages)
        system = next((m.content for m in messages if m.role == "system"), "")
        if "Clasificas noticias" in system:
            return json.dumps(
                {"category": "Agents", "relevance_score": 88, "reason": "novedad relevante"}
            )
        if "editor de" in system:
            return json.dumps(
                {
                    "title": "Nuevo framework de agentes autónomos",
                    "what_happened": "Se ha publicado un framework de agentes.",
                    "why_it_matters": "Simplifica la orquestación multiagente.",
                    "how_we_could_use_it": "Para construir pipelines de IA.",
                    "limitations": "Aún experimental.",
                }
            )
        if "dinamizador" in system:
            return json.dumps(
                {
                    "question": "¿Sustituirán los agentes a los workflows tradicionales?",
                    "rationale": "Tema con opiniones enfrentadas.",
                }
            )
        if "REFLEXIÓN DE CONJUNTO" in system:
            return json.dumps(
                {"overview": "Esta semana destacan los agentes autónomos y el open source."}
            )
        return "{}"


class BrokenLLM(LLMProvider):
    """LLM that always fails, to exercise the degradation paths."""

    async def complete(self, messages, *, temperature=0.4, max_tokens=1024) -> str:
        raise RuntimeError("LLM caído")

    async def complete_json(self, messages, *, temperature=0.2, max_tokens=1024) -> str:
        raise RuntimeError("LLM caído")


class FakeSource(NewsSource):
    """Source that returns a fixed list of news items."""

    def __init__(self, name: str, items: list[NewsItem], *, fail: bool = False) -> None:
        self._name = name
        self._items = items
        self._fail = fail

    @property
    def name(self) -> str:
        return self._name

    async def fetch(self, limit: int) -> list[NewsItem]:
        if self._fail:
            raise RuntimeError("fuente caída")
        return self._items[:limit]


class FakePublisher(Publisher):
    """In-memory publisher that records what was published."""

    def __init__(self) -> None:
        self.published: list[PublishableArticle] = []
        self.tests: list[str] = []
        self.announcements: list[tuple[Newsletter, str]] = []
        self._next_id = 1000

    async def publish(self, article: PublishableArticle) -> int:
        self.published.append(article)
        self._next_id += 1
        return self._next_id

    async def publish_test_message(self, text: str) -> int:
        self.tests.append(text)
        self._next_id += 1
        return self._next_id

    async def publish_newsletter_announcement(self, newsletter: Newsletter, url: str) -> int:
        self.announcements.append((newsletter, url))
        self._next_id += 1
        return self._next_id


class FakeSitePublisher(SitePublisher):
    """Records published pages and returns a deterministic public URL."""

    def __init__(self, base_url: str = "https://fake.github.io/newsbot") -> None:
        self.pages: list[tuple[str, str]] = []  # (path, html)
        self._base_url = base_url.rstrip("/")

    async def publish_html(self, *, path: str, html: str, commit_message: str) -> PublishedSite:
        self.pages.append((path, html))
        return PublishedSite(
            public_url=f"{self._base_url}/{path.lstrip('/')}", path=path, commit_sha="deadbeef"
        )


class BrokenSitePublisher(SitePublisher):
    """Site publisher that always fails, to exercise the failure path."""

    async def publish_html(self, *, path: str, html: str, commit_message: str) -> PublishedSite:
        raise SitePublisherError("hosting caído")


@pytest.fixture
def news_item() -> NewsItem:
    return NewsItem(
        title="Nuevo framework de agentes",
        url="https://example.com/agents-framework",
        source="OpenAI Blog",
        summary="Un framework para construir agentes autónomos con tool-use.",
        raw_content="Detalles ampliados del framework de agentes autónomos.",
    )


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def repository() -> InMemoryNewsRepository:
    return InMemoryNewsRepository()


@pytest.fixture
def embeddings() -> HashEmbeddingProvider:
    return HashEmbeddingProvider(dimension=64)


@pytest.fixture
def fake_publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def fake_site_publisher() -> FakeSitePublisher:
    return FakeSitePublisher()
