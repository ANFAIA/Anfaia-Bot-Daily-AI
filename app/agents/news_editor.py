"""Agent 4 — News Editor.

Transforms a news item into edited content for Discord, structured into the
newsletter's sections. It uses the LLM and, if it fails, generates a minimal
version from the summary itself so as not to block publication. When an
article fetcher is provided, it enriches the LLM input with the full article
body instead of the (often thin) feed summary.
"""

from __future__ import annotations

from app.agents.json_utils import extract_json_object
from app.agents.prompts import EDITOR_SYSTEM
from app.core.logging import get_logger
from app.domain.entities import EditedArticle, NewsItem
from app.interfaces.agent import Agent
from app.interfaces.article_fetcher import ArticleFetcher
from app.interfaces.llm import ChatMessage, LLMProvider

logger = get_logger(__name__)


class NewsEditorAgent(Agent[NewsItem, EditedArticle]):
    """Edits and contextualizes a news item for the community."""

    name = "news_editor"

    def __init__(self, llm: LLMProvider, *, article_fetcher: ArticleFetcher | None = None) -> None:
        self._llm = llm
        self._article_fetcher = article_fetcher

    async def run(self, input_data: NewsItem) -> EditedArticle:
        try:
            return await self._edit_with_llm(input_data)
        except Exception as exc:
            logger.warning("editor.llm_failed", error=str(exc), title=input_data.title)
            return self._fallback(input_data)

    async def _edit_with_llm(self, item: NewsItem) -> EditedArticle:
        content = await self._fetch_full_article(item) or item.raw_content or item.summary
        user = (
            f"Categoría: {item.category.value if item.category else 'AI'}\n"
            f"Título original: {item.title}\n"
            f"Fuente: {item.source}\n"
            f"URL: {item.url}\n"
            f"Contenido: {content}"
        )
        raw = await self._llm.complete_json(
            [
                ChatMessage(role="system", content=EDITOR_SYSTEM),
                ChatMessage(role="user", content=user),
            ],
            temperature=0.5,
            max_tokens=900,
        )
        data = extract_json_object(raw)
        edited = EditedArticle(
            title=str(data.get("title") or item.title).strip()[:256],
            what_happened=str(data.get("what_happened", "")).strip(),
            why_it_matters=str(data.get("why_it_matters", "")).strip(),
            how_we_could_use_it=str(data.get("how_we_could_use_it", "")).strip(),
            limitations=str(data.get("limitations", "")).strip(),
            source_url=item.url,
        )
        logger.info("editor.edited", title=edited.title)
        return edited

    async def _fetch_full_article(self, item: NewsItem) -> str | None:
        if self._article_fetcher is None:
            return None
        return await self._article_fetcher.fetch(item.url)

    @staticmethod
    def _fallback(item: NewsItem) -> EditedArticle:
        return EditedArticle(
            title=item.title[:256],
            what_happened=item.summary or "Sin resumen disponible.",
            why_it_matters="Relevante para la comunidad de IA por su temática.",
            how_we_could_use_it="Revisa la fuente para evaluar aplicaciones concretas.",
            limitations="Resumen automático: contrasta con la fuente original.",
            source_url=item.url,
        )
