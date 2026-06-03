"""Tests for the editorial brain port, its helpers and the deepagents workflow.

The ``deepagents`` framework itself is an optional, network-bound dependency and
is exercised only in integration; here we test everything around it: the pure
decode/brief helpers, the classic fallback brain, the new workflow (with a fake
brain) and the container wiring that selects the engine.
"""

from __future__ import annotations

import asyncio

import pytest

from app.agents.classic_editorial_brain import ClassicEditorialBrain
from app.agents.discord_publisher_agent import DiscordPublisherAgent
from app.agents.discussion_generator import DiscussionGeneratorAgent
from app.agents.duplicate_detector import DuplicateDetectorAgent
from app.agents.news_classifier import NewsClassifierAgent
from app.agents.news_collector import NewsCollectorAgent
from app.agents.news_editor import NewsEditorAgent
from app.core.config import EmbeddingProviderName, Settings, WorkflowEngine
from app.core.container import Container
from app.domain.entities import NewsItem
from app.domain.value_objects import Category, RelevanceScore
from app.infrastructure.persistence.in_memory import InMemoryNewsRepository
from app.interfaces.editorial import EditorialBrain, EditorialDecision
from app.workflows.deepagents_news_workflow import DeepAgentsNewsWorkflow
from app.workflows.editorial import (
    build_candidate_brief,
    build_recent_context,
    decode_decision,
)
from tests.conftest import FakeSource


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
class FakeEditorialBrain(EditorialBrain):
    """Brain that records its inputs and picks a configured index."""

    name = "fake_editorial_brain"

    def __init__(self, *, pick: int = 0) -> None:
        self._pick = pick
        self.seen_candidates: list[NewsItem] | None = None
        self.seen_recent: list[str] | None = None

    async def decide(
        self, candidates: list[NewsItem], *, recent_titles: list[str]
    ) -> EditorialDecision:
        self.seen_candidates = candidates
        self.seen_recent = recent_titles
        payload = {
            "chosen_index": self._pick,
            "rationale": "elegida por el test",
            "article": {"title": f"Editado: {candidates[self._pick].title}"},
            "discussion": {"question": "¿Y vosotros qué opináis?"},
        }
        return decode_decision(payload, candidates)


def _classified(title: str, url: str, *, score: int = 88) -> NewsItem:
    item = NewsItem(title=title, url=url, source="s", summary=f"resumen de {title}")
    return item.with_classification(Category.AGENTS, RelevanceScore(score))


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def test_build_candidate_brief_numbers_and_details() -> None:
    brief = build_candidate_brief([_classified("Noticia A", "https://e.com/a")])
    assert "[0]" in brief
    assert "Noticia A" in brief
    assert "https://e.com/a" in brief
    assert "relevancia 88" in brief


def test_build_recent_context_empty_and_filled() -> None:
    assert "No hay" in build_recent_context([])
    filled = build_recent_context(["Primera", "Segunda"])
    assert "- Primera" in filled
    assert "- Segunda" in filled


def test_decode_decision_flat_and_nested() -> None:
    candidates = [_classified("A", "https://e.com/a"), _classified("B", "https://e.com/b")]
    nested = decode_decision(
        {"chosen_index": 1, "article": {"title": "T", "what_happened": "ocurrió"}}, candidates
    )
    assert nested.chosen.url == "https://e.com/b"
    assert nested.edited.title == "T"
    assert nested.edited.what_happened == "ocurrió"
    # source_url is always taken from the chosen item, never trusted from the LLM.
    assert nested.edited.source_url == "https://e.com/b"

    flat = decode_decision({"chosen_index": 0, "title": "Plano"}, candidates)
    assert flat.edited.title == "Plano"


def test_decode_decision_clamps_bad_index_and_fills_defaults() -> None:
    candidates = [_classified("A", "https://e.com/a")]
    decision = decode_decision({"chosen_index": "99", "article": {}}, candidates)
    assert decision.chosen.url == "https://e.com/a"
    # Missing fields fall back to the chosen item / safe defaults.
    assert decision.edited.title == "A"
    assert decision.edited.what_happened  # non-empty
    assert decision.discussion.question  # default question


def test_decode_decision_garbage_index_defaults_to_top() -> None:
    candidates = [_classified("A", "https://e.com/a"), _classified("B", "https://e.com/b")]
    decision = decode_decision({"chosen_index": None}, candidates)
    assert decision.chosen.url == "https://e.com/a"


def test_decode_decision_discussion_as_plain_string() -> None:
    candidates = [_classified("A", "https://e.com/a")]
    decision = decode_decision({"chosen_index": 0, "discussion": "¿Pregunta suelta?"}, candidates)
    assert decision.discussion.question == "¿Pregunta suelta?"


def test_decode_decision_empty_candidates_raises() -> None:
    with pytest.raises(ValueError):
        decode_decision({"chosen_index": 0}, [])


# --------------------------------------------------------------------------- #
# Classic editorial brain (fallback)
# --------------------------------------------------------------------------- #
async def test_classic_brain_picks_top_and_edits(fake_llm) -> None:
    brain = ClassicEditorialBrain(NewsEditorAgent(fake_llm), DiscussionGeneratorAgent(fake_llm))
    candidates = [_classified("A", "https://e.com/a"), _classified("B", "https://e.com/b")]
    decision = await brain.decide(candidates, recent_titles=[])
    assert decision.chosen.url == "https://e.com/a"  # top-ranked
    assert decision.edited.title == "Nuevo framework de agentes autónomos"  # from FakeLLM
    assert decision.discussion.question


# --------------------------------------------------------------------------- #
# DeepAgentsNewsWorkflow (with a fake brain)
# --------------------------------------------------------------------------- #
def _build_workflow(*, brain, repository, embeddings, fake_publisher, sources, fake_llm):
    return DeepAgentsNewsWorkflow(
        collector=NewsCollectorAgent(sources, max_items_per_source=10),
        classifier=NewsClassifierAgent(fake_llm),
        duplicate_detector=DuplicateDetectorAgent(
            repository, embeddings, similarity_threshold=0.86
        ),
        brain=brain,
        publisher=DiscordPublisherAgent(fake_publisher),
        repository=repository,
        min_relevance_score=55,
        shortlist_size=5,
    )


async def test_deepagents_workflow_happy_path(
    fake_llm, repository, embeddings, fake_publisher, news_item
) -> None:
    brain = FakeEditorialBrain(pick=0)
    workflow = _build_workflow(
        brain=brain,
        repository=repository,
        embeddings=embeddings,
        fake_publisher=fake_publisher,
        sources=[FakeSource("OpenAI Blog", [news_item])],
        fake_llm=fake_llm,
    )
    report = await workflow.run()
    assert report.succeeded
    assert report.published == 1
    assert len(fake_publisher.published) == 1
    stored = await repository.list_articles(limit=10, offset=0)
    assert len(stored) == 1
    assert stored[0].discord_message_id is not None


async def test_deepagents_workflow_brain_chooses_among_shortlist(
    fake_llm, repository, embeddings, fake_publisher
) -> None:
    items = [
        NewsItem(title=f"Noticia {i}", url=f"https://e.com/{i}", source="s", summary=f"r{i}")
        for i in range(3)
    ]
    brain = FakeEditorialBrain(pick=1)
    workflow = _build_workflow(
        brain=brain,
        repository=repository,
        embeddings=embeddings,
        fake_publisher=fake_publisher,
        sources=[FakeSource("s", items)],
        fake_llm=fake_llm,
    )
    report = await workflow.run()
    assert report.published == 1
    # The brain received the full unique shortlist...
    assert brain.seen_candidates is not None
    assert len(brain.seen_candidates) == 3
    # ...and its pick (index 1) is what got published.
    assert fake_publisher.published[0].news_item.url == "https://e.com/1"


async def test_deepagents_workflow_caps_shortlist_size(
    fake_llm, repository, embeddings, fake_publisher
) -> None:
    items = [
        NewsItem(title=f"Noticia {i}", url=f"https://e.com/{i}", source="s", summary=f"r{i}")
        for i in range(3)
    ]
    brain = FakeEditorialBrain(pick=0)
    workflow = DeepAgentsNewsWorkflow(
        collector=NewsCollectorAgent([FakeSource("s", items)], max_items_per_source=10),
        classifier=NewsClassifierAgent(fake_llm),
        duplicate_detector=DuplicateDetectorAgent(
            repository, embeddings, similarity_threshold=0.86
        ),
        brain=brain,
        publisher=DiscordPublisherAgent(fake_publisher),
        repository=repository,
        min_relevance_score=55,
        shortlist_size=1,  # the brain must see exactly one candidate
    )
    report = await workflow.run()
    assert report.published == 1
    assert brain.seen_candidates is not None
    assert len(brain.seen_candidates) == 1


async def test_deepagents_workflow_no_news(
    fake_llm, repository, embeddings, fake_publisher
) -> None:
    workflow = _build_workflow(
        brain=FakeEditorialBrain(),
        repository=repository,
        embeddings=embeddings,
        fake_publisher=fake_publisher,
        sources=[FakeSource("vacía", [])],
        fake_llm=fake_llm,
    )
    report = await workflow.run()
    assert not report.succeeded
    assert report.published == 0
    assert report.errors


async def test_deepagents_workflow_skips_duplicates(
    fake_llm, repository, embeddings, fake_publisher, news_item
) -> None:
    sources = [FakeSource("OpenAI Blog", [news_item])]
    workflow = _build_workflow(
        brain=FakeEditorialBrain(),
        repository=repository,
        embeddings=embeddings,
        fake_publisher=fake_publisher,
        sources=sources,
        fake_llm=fake_llm,
    )
    first = await workflow.run()
    assert first.published == 1
    second = await workflow.run()
    assert second.published == 0
    assert second.discarded_duplicates >= 1
    assert len(fake_publisher.published) == 1


async def test_deepagents_workflow_filters_low_relevance(
    repository, embeddings, fake_publisher, news_item
) -> None:
    # An LLM-less classifier path is not needed: raise the threshold above the
    # fake score of 88 so the only candidate is filtered out.
    from tests.conftest import FakeLLM

    workflow = DeepAgentsNewsWorkflow(
        collector=NewsCollectorAgent(
            [FakeSource("OpenAI Blog", [news_item])], max_items_per_source=10
        ),
        classifier=NewsClassifierAgent(FakeLLM()),
        duplicate_detector=DuplicateDetectorAgent(
            repository, embeddings, similarity_threshold=0.86
        ),
        brain=FakeEditorialBrain(),
        publisher=DiscordPublisherAgent(fake_publisher),
        repository=repository,
        min_relevance_score=95,
        shortlist_size=5,
    )
    report = await workflow.run()
    assert report.published == 0
    assert report.discarded_low_relevance == 1


# --------------------------------------------------------------------------- #
# Container wiring
# --------------------------------------------------------------------------- #
def test_container_selects_deepagents_engine(monkeypatch) -> None:
    import app.infrastructure.editorial.factory as factory

    monkeypatch.setattr(factory, "build_editorial_brain", lambda *a, **k: FakeEditorialBrain())
    settings = Settings(
        openai_api_key="test-key",
        embedding_provider=EmbeddingProviderName.HASH,
        embedding_dim=64,
        scheduler_enabled=False,
        workflow_engine=WorkflowEngine.DEEPAGENTS,
        _env_file=None,
    )
    container = Container(settings, repository=InMemoryNewsRepository())
    try:
        assert isinstance(container.workflow, DeepAgentsNewsWorkflow)
    finally:
        asyncio.run(container.aclose())


def test_container_defaults_to_sequential_engine() -> None:
    from app.workflows.daily_news_workflow import DailyNewsWorkflow

    settings = Settings(
        openai_api_key="test-key",
        embedding_provider=EmbeddingProviderName.HASH,
        embedding_dim=64,
        scheduler_enabled=False,
        _env_file=None,
    )
    container = Container(settings, repository=InMemoryNewsRepository())
    try:
        assert isinstance(container.workflow, DailyNewsWorkflow)
    finally:
        asyncio.run(container.aclose())
