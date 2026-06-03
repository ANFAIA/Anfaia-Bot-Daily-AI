"""Agent 5 — Discussion Generator.

Generates an open-ended question to foster community debate based on the
edited news item.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.json_utils import extract_json_object
from app.agents.prompts import DISCUSSION_SYSTEM
from app.core.logging import get_logger
from app.domain.entities import DiscussionPrompt, EditedArticle, NewsItem
from app.interfaces.agent import Agent
from app.interfaces.llm import ChatMessage, LLMProvider

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DiscussionInput:
    """Input for the discussion generator."""

    item: NewsItem
    edited: EditedArticle


class DiscussionGeneratorAgent(Agent[DiscussionInput, DiscussionPrompt]):
    """Produces an open-ended question that invites technical debate."""

    name = "discussion_generator"

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def run(self, input_data: DiscussionInput) -> DiscussionPrompt:
        try:
            return await self._generate_with_llm(input_data)
        except Exception as exc:
            logger.warning("discussion.llm_failed", error=str(exc))
            return DiscussionPrompt(
                question=(
                    "¿Cómo creéis que este avance cambiará vuestra forma de "
                    "construir sistemas de IA en el día a día?"
                ),
                rationale="fallback",
            )

    async def _generate_with_llm(self, data: DiscussionInput) -> DiscussionPrompt:
        edited = data.edited
        user = (
            f"Título: {edited.title}\n"
            f"Qué ha pasado: {edited.what_happened}\n"
            f"Por qué importa: {edited.why_it_matters}\n"
            f"Limitaciones: {edited.limitations}"
        )
        raw = await self._llm.complete_json(
            [
                ChatMessage(role="system", content=DISCUSSION_SYSTEM),
                ChatMessage(role="user", content=user),
            ],
            temperature=0.7,
            max_tokens=200,
        )
        parsed = extract_json_object(raw)
        question = str(parsed.get("question", "")).strip()
        if not question:
            raise ValueError("El LLM no devolvió una pregunta")
        logger.info("discussion.generated", question=question)
        return DiscussionPrompt(question=question, rationale=str(parsed.get("rationale", "")))
