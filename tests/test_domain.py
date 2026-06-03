"""Domain tests: value objects and entities."""

from __future__ import annotations

import pytest

from app.domain.entities import NewsItem
from app.domain.value_objects import Category, RelevanceScore


def test_category_from_str_known_values() -> None:
    assert Category.from_str("Agents") == Category.AGENTS
    assert Category.from_str("open source") == Category.OPEN_SOURCE
    assert Category.from_str("ROBOTICS") == Category.ROBOTICS


def test_category_from_str_aliases_and_fallback() -> None:
    assert Category.from_str("agentic") == Category.AGENTS
    assert Category.from_str("machine learning") == Category.RESEARCH
    assert Category.from_str("desconocido") == Category.AI


def test_relevance_score_bounds() -> None:
    assert RelevanceScore(0).value == 0
    assert RelevanceScore(100).value == 100
    with pytest.raises(ValueError):
        RelevanceScore(101)
    with pytest.raises(ValueError):
        RelevanceScore(-1)


def test_relevance_score_clamped() -> None:
    assert RelevanceScore.clamped(150).value == 100
    assert RelevanceScore.clamped(-10).value == 0
    assert RelevanceScore.clamped(72.6).value == 73


def test_relevance_is_at_least() -> None:
    assert RelevanceScore(80).is_at_least(55)
    assert not RelevanceScore(40).is_at_least(55)


def test_news_item_url_fingerprint_is_normalized() -> None:
    a = NewsItem(title="t", url="https://Example.com/Path/?utm=1", source="s", summary="x")
    b = NewsItem(title="t", url="https://example.com/Path", source="s", summary="x")
    assert a.url_fingerprint == b.url_fingerprint


def test_news_item_with_classification_is_immutable() -> None:
    item = NewsItem(title="t", url="https://e.com/a", source="s", summary="x")
    classified = item.with_classification(Category.AI, RelevanceScore(70))
    assert item.category is None  # original untouched
    assert classified.category == Category.AI
    assert classified.relevance_score == RelevanceScore(70)


def test_embedding_text_combines_title_and_summary() -> None:
    item = NewsItem(title="Título", url="https://e.com/a", source="s", summary="Resumen")
    assert "Título" in item.embedding_text
    assert "Resumen" in item.embedding_text
