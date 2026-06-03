"""Deliberative editorial brain built on the ``deepagents`` framework.

This is the production implementation of `EditorialBrain`. Instead of a single
LLM call, it runs a deep agent that:

  * plans its work (built-in planning / todo tool),
  * delegates source reading + drafting to a *research-editor* sub-agent that
    can ``fetch_url`` the original article,
  * runs an adversarial *fact-checker* sub-agent over the draft,
  * delegates the discussion question to a *community-moderator* sub-agent,
  * returns the final decision as a typed, structured response.

It depends on optional extras (``deepagents`` + a LangChain provider). The
module therefore imports them at top level on purpose: if they are missing the
import fails and `build_editorial_brain` turns it into an actionable error.

On any failure the brain degrades gracefully to the injected ``fallback`` brain
(the classic single-shot agents), so the daily pipeline never stalls.
"""

from __future__ import annotations

import httpx
from deepagents import create_deep_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from app.agents.json_utils import extract_json_object
from app.agents.prompts import (
    COMMUNITY_MODERATOR_PROMPT,
    EDITORIAL_ORCHESTRATOR_SYSTEM,
    FACT_CHECKER_PROMPT,
    RESEARCH_EDITOR_PROMPT,
)
from app.core.logging import get_logger
from app.domain.entities import NewsItem
from app.infrastructure.sources.text import clean_html, truncate
from app.interfaces.editorial import EditorialBrain, EditorialDecision
from app.workflows.editorial import (
    build_candidate_brief,
    build_recent_context,
    decode_decision,
)

logger = get_logger(__name__)


# --- Structured-output schema for the deep agent's final answer ------------- #
class _ArticleOut(BaseModel):
    title: str = ""
    what_happened: str = ""
    why_it_matters: str = ""
    how_we_could_use_it: str = ""
    limitations: str = ""


class _DiscussionOut(BaseModel):
    question: str = ""
    rationale: str = ""


class _DecisionOut(BaseModel):
    """Schema the orchestrator must fill in as its final structured response."""

    chosen_index: int = Field(0, description="Índice (0-based) de la noticia elegida")
    rationale: str = Field("", description="Por qué esta noticia y no otra")
    article: _ArticleOut = Field(default_factory=_ArticleOut)
    discussion: _DiscussionOut = Field(default_factory=_DiscussionOut)
    fact_check_notes: str = ""


class DeepAgentsEditorialBrain(EditorialBrain):
    """Editorial brain that deliberates with a deep agent + sub-agents."""

    name = "deepagents_editorial_brain"

    def __init__(
        self,
        *,
        model: BaseChatModel,
        http_client: httpx.AsyncClient,
        fallback: EditorialBrain,
        recursion_limit: int = 50,
        fetch_char_limit: int = 6000,
    ) -> None:
        self._model = model
        self._http = http_client
        self._fallback = fallback
        self._recursion_limit = recursion_limit
        self._fetch_char_limit = fetch_char_limit

    async def decide(
        self, candidates: list[NewsItem], *, recent_titles: list[str]
    ) -> EditorialDecision:
        try:
            payload = await self._deliberate(candidates, recent_titles)
            return decode_decision(payload, candidates)
        except Exception as exc:  # pragma: no cover - depends on live agent/network
            logger.warning("editorial.deepagents_failed", error=str(exc))
            return await self._fallback.decide(candidates, recent_titles=recent_titles)

    async def _deliberate(self, candidates: list[NewsItem], recent_titles: list[str]) -> dict:
        fetch_tool = self._build_fetch_tool()
        agent = create_deep_agent(
            self._model,
            [fetch_tool],
            system_prompt=EDITORIAL_ORCHESTRATOR_SYSTEM,
            subagents=self._build_subagents(fetch_tool),
            response_format=_DecisionOut,
        )
        user = (
            "NOTICIAS CANDIDATAS:\n"
            f"{build_candidate_brief(candidates)}\n\n"
            "PUBLICADAS RECIENTEMENTE (evita repetir tema):\n"
            f"{build_recent_context(recent_titles)}\n\n"
            "Elige una y devuelve la decisión final con el esquema indicado."
        )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user}]},
            {"recursion_limit": self._recursion_limit},
        )
        return self._extract_payload(result)

    @staticmethod
    def _extract_payload(result: dict) -> dict:
        structured = result.get("structured_response")
        if isinstance(structured, _DecisionOut):
            return structured.model_dump()
        if isinstance(structured, dict):
            return structured
        # Fallback: recover JSON from the last assistant message.
        messages = result.get("messages", [])
        if messages:
            content = getattr(messages[-1], "content", "") or ""
            return extract_json_object(content if isinstance(content, str) else str(content))
        raise ValueError("El agente no produjo una decisión")

    def _build_fetch_tool(self) -> BaseTool:
        char_limit = self._fetch_char_limit
        client = self._http

        @tool
        async def fetch_url(url: str) -> str:
            """Descarga una URL y devuelve su texto limpio (sin HTML), truncado."""
            try:
                response = await client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                return f"ERROR al descargar {url}: {exc}"
            return truncate(clean_html(response.text), char_limit)

        return fetch_url

    @staticmethod
    def _build_subagents(fetch_tool: BaseTool) -> list[dict]:
        return [
            {
                "name": "research-editor",
                "description": "Lee la fuente original y redacta el contenido editorial.",
                "system_prompt": RESEARCH_EDITOR_PROMPT,
                "tools": [fetch_tool],
            },
            {
                "name": "fact-checker",
                "description": "Verifica de forma adversarial las afirmaciones del borrador.",
                "system_prompt": FACT_CHECKER_PROMPT,
                "tools": [fetch_tool],
            },
            {
                "name": "community-moderator",
                "description": "Formula la pregunta abierta para el debate.",
                "system_prompt": COMMUNITY_MODERATOR_PROMPT,
            },
        ]
