"""Unit tests for the agents."""

from __future__ import annotations

from app.agents.discussion_generator import DiscussionGeneratorAgent, DiscussionInput
from app.agents.duplicate_detector import DuplicateDetectorAgent
from app.agents.news_classifier import NewsClassifierAgent
from app.agents.news_collector import NewsCollectorAgent
from app.agents.news_editor import NewsEditorAgent
from app.agents.newsletter_overview import NewsletterOverviewAgent
from app.domain.entities import DiscussionPrompt, EditedArticle, NewsItem
from app.domain.newsletter import NewsletterEntry
from app.domain.value_objects import Category, RelevanceScore
from app.interfaces.llm import ChatMessage, LLMProvider
from tests.conftest import BrokenLLM, FakeLLM, FakeSource


def _overview_entry(title: str = "Titular") -> NewsletterEntry:
    item = NewsItem(title=title, url="https://e.com/x", source="s", summary="r")
    classified = item.with_classification(Category.AGENTS, RelevanceScore(88))
    edited = EditedArticle(title, "qué", "por qué", "uso", "límites", "https://e.com/x")
    return NewsletterEntry(news_item=classified, edited=edited, discussion=DiscussionPrompt("q"))


class _EmptyOverviewLLM(LLMProvider):
    async def complete(self, messages, *, temperature=0.4, max_tokens=1024) -> str:
        return "{}"

    async def complete_json(
        self, messages: list[ChatMessage], *, temperature=0.2, max_tokens=1024
    ) -> str:
        return '{"overview": ""}'


async def test_overview_agent_uses_llm() -> None:
    text = await NewsletterOverviewAgent(FakeLLM()).run([_overview_entry()])
    assert "agentes" in text.lower()


async def test_overview_agent_fallback_on_empty() -> None:
    text = await NewsletterOverviewAgent(_EmptyOverviewLLM()).run(
        [_overview_entry("A"), _overview_entry("B")]
    )
    assert "2 noticias" in text  # fallback mentions the count


async def test_overview_agent_fallback_on_error() -> None:
    text = await NewsletterOverviewAgent(BrokenLLM()).run([_overview_entry()])
    assert text  # non-empty fallback


async def test_collector_aggregates_and_dedupes(news_item: NewsItem) -> None:
    dup = NewsItem(title="otra", url=news_item.url, source="s2", summary="y")
    other = NewsItem(title="b", url="https://e.com/b", source="s2", summary="z")
    sources = [FakeSource("A", [news_item, dup]), FakeSource("B", [other])]
    collector = NewsCollectorAgent(sources, max_items_per_source=10)

    result = await collector.run(None)

    assert len(result) == 2  # the URL duplicate is removed
    urls = {i.url for i in result}
    assert news_item.url in urls and other.url in urls


async def test_collector_survives_failing_source(news_item: NewsItem) -> None:
    sources = [FakeSource("ok", [news_item]), FakeSource("bad", [], fail=True)]
    collector = NewsCollectorAgent(sources, max_items_per_source=5)
    result = await collector.run(None)
    assert len(result) == 1


async def test_classifier_with_llm(fake_llm, news_item: NewsItem) -> None:
    agent = NewsClassifierAgent(fake_llm)
    classified = await agent.run(news_item)
    assert classified.category == Category.AGENTS
    assert classified.relevance_score == RelevanceScore(88)


async def test_classifier_falls_back_to_heuristic(news_item: NewsItem) -> None:
    agent = NewsClassifierAgent(BrokenLLM())
    classified = await agent.run(news_item)
    assert classified.category is not None
    assert classified.relevance_score is not None


async def test_editor_with_llm(fake_llm, news_item: NewsItem) -> None:
    classified = news_item.with_classification(Category.AGENTS, RelevanceScore(80))
    agent = NewsEditorAgent(fake_llm)
    edited = await agent.run(classified)
    assert edited.title.startswith("Nuevo framework")
    assert edited.source_url == news_item.url


async def test_editor_fallback(news_item: NewsItem) -> None:
    agent = NewsEditorAgent(BrokenLLM())
    edited = await agent.run(news_item)
    assert edited.title == news_item.title
    assert edited.what_happened


async def test_discussion_with_llm(fake_llm, news_item: NewsItem) -> None:
    edited = EditedArticle(
        title="t",
        what_happened="a",
        why_it_matters="b",
        how_we_could_use_it="c",
        limitations="d",
        source_url=news_item.url,
    )
    agent = DiscussionGeneratorAgent(fake_llm)
    prompt = await agent.run(DiscussionInput(item=news_item, edited=edited))
    assert "workflows" in prompt.question.lower()


async def test_discussion_fallback(news_item: NewsItem) -> None:
    edited = EditedArticle("t", "a", "b", "c", "d", news_item.url)
    agent = DiscussionGeneratorAgent(BrokenLLM())
    prompt = await agent.run(DiscussionInput(item=news_item, edited=edited))
    assert prompt.rationale == "fallback"
    assert prompt.question


async def test_duplicate_detector_url_match(repository, embeddings, news_item) -> None:
    # Persist the same URL first.
    from app.domain.entities import DiscussionPrompt, EditedArticle, PublishableArticle

    classified = news_item.with_classification(Category.AI, RelevanceScore(70))
    article = PublishableArticle(
        news_item=classified,
        edited=EditedArticle("t", "a", "b", "c", "d", news_item.url),
        discussion=DiscussionPrompt("q"),
    )
    await repository.save_published(article, await embeddings.embed(news_item.embedding_text))

    agent = DuplicateDetectorAgent(repository, embeddings, similarity_threshold=0.86)
    decision = await agent.run(news_item)
    assert decision.is_duplicate
    assert decision.reason == "url_already_published"


async def test_duplicate_detector_unique(repository, embeddings, news_item) -> None:
    agent = DuplicateDetectorAgent(repository, embeddings, similarity_threshold=0.86)
    decision = await agent.run(news_item)
    assert not decision.is_duplicate
    assert decision.reason == "unique"
    assert len(decision.embedding) == 64


async def test_duplicate_detector_semantic_match(repository, embeddings, news_item) -> None:
    from app.domain.entities import DiscussionPrompt, EditedArticle, PublishableArticle

    classified = news_item.with_classification(Category.AI, RelevanceScore(70))
    article = PublishableArticle(
        news_item=classified,
        edited=EditedArticle("t", "a", "b", "c", "d", news_item.url),
        discussion=DiscussionPrompt("q"),
    )
    await repository.save_published(article, await embeddings.embed(news_item.embedding_text))

    # Different URL but identical text -> high semantic similarity.
    similar = NewsItem(
        title=news_item.title,
        url="https://example.com/distinta-url",
        source="otra",
        summary=news_item.summary,
    )
    agent = DuplicateDetectorAgent(repository, embeddings, similarity_threshold=0.86)
    decision = await agent.run(similar)
    assert decision.is_duplicate
    assert decision.reason == "semantically_similar"
