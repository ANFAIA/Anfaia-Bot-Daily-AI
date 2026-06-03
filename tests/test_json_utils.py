"""Tests for robust JSON extraction from LLM responses."""

from __future__ import annotations

import pytest

from app.agents.json_utils import extract_json_object


def test_plain_json() -> None:
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_json_wrapped_in_code_fence() -> None:
    text = 'Aquí tienes:\n```json\n{"category": "AI", "relevance_score": 70}\n```'
    result = extract_json_object(text)
    assert result["category"] == "AI"


def test_json_with_surrounding_text() -> None:
    text = 'Respuesta: {"question": "¿Y bien?"} ¡Gracias!'
    assert extract_json_object(text)["question"] == "¿Y bien?"


def test_nested_braces() -> None:
    text = '{"a": {"b": 2}, "c": 3}'
    assert extract_json_object(text) == {"a": {"b": 2}, "c": 3}


def test_raises_without_json() -> None:
    with pytest.raises(ValueError):
        extract_json_object("sin json aquí")


def test_raises_on_unbalanced() -> None:
    with pytest.raises(ValueError):
        extract_json_object("{roto")
