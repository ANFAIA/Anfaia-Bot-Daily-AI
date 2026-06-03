"""Classic editorial brain.

Implements `EditorialBrain` by reusing the existing single-shot LLM agents
(`NewsEditorAgent` + `DiscussionGeneratorAgent`). It does not deliberate: it
publishes the top-ranked candidate. This is both the default editorial engine
and the graceful fallback used when the deep-agents brain is unavailable.
"""

from __future__ import annotations

from app.agents.discussion_generator import DiscussionGeneratorAgent, DiscussionInput
from app.agents.news_editor import NewsEditorAgent
from app.core.logging import get_logger
from app.domain.entities import NewsItem
from app.interfaces.editorial import EditorialBrain, EditorialDecision

logger = get_logger(__name__)


class ClassicEditorialBrain(EditorialBrain):
    """Edits and discusses the highest-ranked candidate, without deliberation."""

    name = "classic_editorial_brain"

    def __init__(
        self, editor: NewsEditorAgent, discussion_generator: DiscussionGeneratorAgent
    ) -> None:
        self._editor = editor
        self._discussion = discussion_generator

    async def decide(
        self, candidates: list[NewsItem], *, recent_titles: list[str]
    ) -> EditorialDecision:
        if not candidates:
            raise ValueError("No hay candidatos para la decisión editorial")
        chosen = candidates[0]  # candidates arrive ranked by relevance (highest first)
        edited = await self._editor.run(chosen)
        discussion = await self._discussion.run(DiscussionInput(item=chosen, edited=edited))
        logger.info("editorial.classic_decided", title=edited.title)
        return EditorialDecision(
            chosen=chosen,
            edited=edited,
            discussion=discussion,
            rationale="Selección por ranking de relevancia (modo clásico).",
        )
