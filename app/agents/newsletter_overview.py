"""Agent — Newsletter Overview.

Produces a short editorial reflection over the whole set of stories chosen for
the week's newsletter (what the issue is about, common threads). Uses the LLM and,
if it fails, falls back to a generic sentence so it never blocks publication.
"""

from __future__ import annotations

from app.agents.json_utils import extract_json_object
from app.agents.prompts import NEWSLETTER_OVERVIEW_SYSTEM
from app.core.logging import get_logger
from app.domain.newsletter import NewsletterEntry
from app.interfaces.agent import Agent
from app.interfaces.llm import ChatMessage, LLMProvider

logger = get_logger(__name__)


class NewsletterOverviewAgent(Agent[list[NewsletterEntry], str]):
    """Writes a cohesive reflection summarizing the week's selected stories."""

    name = "newsletter_overview"

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def run(self, input_data: list[NewsletterEntry]) -> str:
        try:
            return await self._generate_with_llm(input_data)
        except Exception as exc:
            logger.warning("newsletter_overview.llm_failed", error=str(exc))
            return self._fallback(input_data)

    async def _generate_with_llm(self, entries: list[NewsletterEntry]) -> str:
        listing = "\n".join(
            f"{i}. [{entry.category.value}] {entry.edited.title} — {entry.edited.what_happened}"
            for i, entry in enumerate(entries, start=1)
        )
        user = f"Noticias elegidas para el boletín de esta semana:\n{listing}"
        raw = await self._llm.complete_json(
            [
                ChatMessage(role="system", content=NEWSLETTER_OVERVIEW_SYSTEM),
                ChatMessage(role="user", content=user),
            ],
            temperature=0.5,
            max_tokens=300,
        )
        data = extract_json_object(raw)
        overview = str(data.get("overview", "")).strip()
        if not overview:
            raise ValueError("El LLM no devolvió una reflexión")
        logger.info("newsletter_overview.generated", length=len(overview))
        return overview

    @staticmethod
    def _fallback(entries: list[NewsletterEntry]) -> str:
        return (
            f"Esta semana reunimos {len(entries)} noticias de IA seleccionadas por su "
            "relevancia para la comunidad, explicadas con el mismo criterio que la "
            "noticia diaria de Anfaia."
        )
