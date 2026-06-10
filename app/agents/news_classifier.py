"""Agent 2 — News Classifier.

Classifies a news item into a category and assigns it a relevance score
(0-100) using an LLM. If the LLM fails, it falls back to a keyword-based
heuristic so the pipeline does not stall.
"""

from __future__ import annotations

from app.agents.json_utils import extract_json_object
from app.agents.prompts import CLASSIFIER_SYSTEM
from app.core.logging import get_logger
from app.domain.entities import NewsItem
from app.domain.value_objects import Category, RelevanceScore
from app.interfaces.agent import Agent
from app.interfaces.llm import ChatMessage, LLMProvider

logger = get_logger(__name__)

# Markers of sensationalist headlines penalized by the fallback heuristic.
_CLICKBAIT_MARKERS: tuple[str, ...] = (
    "you won't believe",
    "no creerás",
    "no te imaginas",
    "shocking",
    "impactante",
    "changes everything",
    "cambia todo",
    "cambiará tu vida",
    "el fin de",
    "the end of",
    "nadie se lo esperaba",
    "secret",
    "el secreto",
    "mind-blowing",
    "alucinante",
)

_KEYWORDS: dict[Category, tuple[str, ...]] = {
    Category.AGENTS: ("agent", "agentic", "multi-agent", "tool use", "autonomous"),
    Category.ROBOTICS: ("robot", "robotics", "humanoid", "embodied", "drone"),
    Category.OPEN_SOURCE: ("open source", "open-source", "weights", "apache", "mit license"),
    Category.AUTOMATION: ("automation", "workflow", "rpa", "pipeline", "orchestrat"),
    Category.RESEARCH: ("paper", "arxiv", "benchmark", "research", "dataset"),
    Category.AI: ("ai", "llm", "model", "gpt", "neural", "machine learning"),
}


class NewsClassifierAgent(Agent[NewsItem, NewsItem]):
    """Assigns a category and relevance to a news item."""

    name = "news_classifier"

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def run(self, input_data: NewsItem) -> NewsItem:
        try:
            return await self._classify_with_llm(input_data)
        except Exception as exc:
            logger.warning("classifier.llm_failed", error=str(exc), title=input_data.title)
            return self._classify_with_heuristic(input_data)

    async def _classify_with_llm(self, item: NewsItem) -> NewsItem:
        user = f"Título: {item.title}\nFuente: {item.source}\nResumen: {item.summary}"
        raw = await self._llm.complete_json(
            [
                ChatMessage(role="system", content=CLASSIFIER_SYSTEM),
                ChatMessage(role="user", content=user),
            ],
            temperature=0.0,
            max_tokens=300,
        )
        data = extract_json_object(raw)
        category = Category.from_str(str(data.get("category", "AI")))
        score = RelevanceScore.clamped(float(data.get("relevance_score", 50)))
        logger.info(
            "classifier.classified",
            title=item.title,
            category=category.value,
            score=score.value,
        )
        return item.with_classification(category, score)

    def _classify_with_heuristic(self, item: NewsItem) -> NewsItem:
        text = f"{item.title} {item.summary}".lower()
        best_category = Category.AI
        best_hits = 0
        for category, keywords in _KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in text)
            if hits > best_hits:
                best_hits, best_category = hits, category
        # Base score from the number of matches, with a clickbait penalty.
        title = item.title.lower()
        clickbait_hits = sum(1 for marker in _CLICKBAIT_MARKERS if marker in title)
        score = RelevanceScore.clamped(45 + best_hits * 10 - clickbait_hits * 25)
        return item.with_classification(best_category, score)
