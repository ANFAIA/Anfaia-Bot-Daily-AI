"""Integration glue tests for the real ``deepagents`` adapter.

These exercise the wiring that only exists when the optional extra is installed
(structured-response decoding, the ``fetch_url`` tool, agent graph construction)
*without* hitting the network or an LLM. They are skipped when the extra is
missing, so the default test run is unaffected.
"""

from __future__ import annotations

import httpx
import pytest
import respx

pytest.importorskip("deepagents")

from app.core.config import EmbeddingProviderName, Settings
from app.domain.entities import NewsItem
from app.infrastructure.editorial.deep_agent_brain import (
    DeepAgentsEditorialBrain,
    _ArticleOut,
    _DecisionOut,
    _DiscussionOut,
)
from app.infrastructure.llm.langchain_factory import build_chat_model


class _UnusedFallback:
    name = "unused"

    async def decide(self, candidates, *, recent_titles):  # pragma: no cover
        raise AssertionError("the fallback must not be reached in these tests")


def _brain(client: httpx.AsyncClient) -> DeepAgentsEditorialBrain:
    settings = Settings(
        openai_api_key="sk-test",
        embedding_provider=EmbeddingProviderName.HASH,
        embedding_dim=64,
        _env_file=None,
    )
    return DeepAgentsEditorialBrain(
        model=build_chat_model(settings), http_client=client, fallback=_UnusedFallback()
    )


def test_langchain_factory_builds_provider_model() -> None:
    settings = Settings(openai_api_key="sk-test", _env_file=None)
    model = build_chat_model(settings)
    assert getattr(model, "model_name", getattr(model, "model", None)) == "gpt-4o-mini"


def test_extract_payload_from_structured_response() -> None:
    decision = _DecisionOut(
        chosen_index=1,
        rationale="por novedad",
        article=_ArticleOut(title="T", what_happened="ocurrió"),
        discussion=_DiscussionOut(question="¿Y bien?"),
    )
    payload = DeepAgentsEditorialBrain._extract_payload({"structured_response": decision})
    assert payload["chosen_index"] == 1
    assert payload["article"]["title"] == "T"
    assert payload["discussion"]["question"] == "¿Y bien?"


def test_extract_payload_falls_back_to_message_json() -> None:
    class _Msg:
        content = '{"chosen_index": 0, "rationale": "x"}'

    payload = DeepAgentsEditorialBrain._extract_payload({"messages": [_Msg()]})
    assert payload["chosen_index"] == 0


async def test_agent_graph_builds_with_subagents_and_tools() -> None:
    from deepagents import create_deep_agent

    from app.agents.prompts import EDITORIAL_ORCHESTRATOR_SYSTEM

    client = httpx.AsyncClient()
    try:
        brain = _brain(client)
        tool = brain._build_fetch_tool()
        assert tool.name == "fetch_url"
        subagents = brain._build_subagents(tool)
        assert [s["name"] for s in subagents] == [
            "research-editor",
            "fact-checker",
            "community-moderator",
        ]
        # research-editor and fact-checker get the fetch tool; moderator does not.
        assert "tools" in subagents[0] and "tools" not in subagents[2]
        # The whole graph must compile (no network needed to build it).
        graph = create_deep_agent(
            brain._model,
            [tool],
            system_prompt=EDITORIAL_ORCHESTRATOR_SYSTEM,
            subagents=subagents,
            response_format=_DecisionOut,
        )
        assert graph is not None
    finally:
        await client.aclose()


@respx.mock
async def test_fetch_url_tool_cleans_and_truncates() -> None:
    respx.get("https://example.com/post").mock(
        return_value=httpx.Response(200, text="<h1>Hola</h1>  <p>mundo  IA</p>")
    )
    client = httpx.AsyncClient()
    try:
        tool = _brain(client)._build_fetch_tool()
        result = await tool.ainvoke({"url": "https://example.com/post"})
        assert result == "Hola mundo IA"
    finally:
        await client.aclose()


@respx.mock
async def test_fetch_url_tool_reports_http_errors() -> None:
    respx.get("https://example.com/down").mock(return_value=httpx.Response(500))
    client = httpx.AsyncClient()
    try:
        tool = _brain(client)._build_fetch_tool()
        result = await tool.ainvoke({"url": "https://example.com/down"})
        assert result.startswith("ERROR al descargar")
    finally:
        await client.aclose()


async def test_decide_degrades_to_fallback_on_agent_error(monkeypatch) -> None:
    """If the deep agent blows up, `decide` must use the injected fallback."""
    from app.interfaces.editorial import EditorialDecision

    item = NewsItem(title="A", url="https://e.com/a", source="s", summary="r")

    class _Fallback:
        name = "fallback"
        called = False

        async def decide(self, candidates, *, recent_titles):
            self.called = True
            from app.domain.entities import DiscussionPrompt, EditedArticle

            return EditorialDecision(
                chosen=candidates[0],
                edited=EditedArticle("A", "a", "b", "c", "d", candidates[0].url),
                discussion=DiscussionPrompt("q"),
            )

    client = httpx.AsyncClient()
    fallback = _Fallback()
    try:
        brain = DeepAgentsEditorialBrain(
            model=build_chat_model(Settings(openai_api_key="sk-test", _env_file=None)),
            http_client=client,
            fallback=fallback,
        )

        async def _boom(*a, **k):
            raise RuntimeError("agente caído")

        monkeypatch.setattr(brain, "_deliberate", _boom)
        decision = await brain.decide([item], recent_titles=[])
        assert fallback.called
        assert decision.chosen.url == "https://e.com/a"
    finally:
        await client.aclose()
