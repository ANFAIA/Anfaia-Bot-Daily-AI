"""Editorial brain port.

The *editorial brain* is the judgment-heavy stage of the pipeline: given a
shortlist of unique, already-ranked candidates, it decides which single news
item to publish, edits it and crafts a discussion prompt.

This is deliberately a port. The deterministic mechanics (collecting,
classifying, de-duplicating, persisting) stay in code; only the editorial
judgement is delegated behind this contract. Today it has two implementations:

  * `ClassicEditorialBrain`  — reuses the existing single-shot LLM agents.
  * `DeepAgentsEditorialBrain` — a deliberative agent (planning, sub-agents,
    source verification) built on the ``deepagents`` framework.

Swapping one for the other does not touch the workflow, the domain or the API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.entities import DiscussionPrompt, EditedArticle, NewsItem


@dataclass(frozen=True, slots=True)
class EditorialDecision:
    """Outcome of the editorial deliberation over a shortlist of candidates."""

    chosen: NewsItem
    edited: EditedArticle
    discussion: DiscussionPrompt
    #: Why this candidate was chosen over the others (for logs/observability).
    rationale: str = ""
    #: Notes from the fact-checking pass, if any.
    fact_check_notes: str = ""


class EditorialBrain(ABC):
    """Decides which candidate to publish and produces the editorial content."""

    #: Stable name used in logs and metrics.
    name: str = "editorial_brain"

    @abstractmethod
    async def decide(
        self, candidates: list[NewsItem], *, recent_titles: list[str]
    ) -> EditorialDecision:
        """Pick one item from ``candidates``, edit it and craft a discussion.

        Args:
            candidates: unique candidates, ranked by relevance (highest first).
            recent_titles: titles already published recently, so the brain can
                favour topical diversity. Implementations may ignore it.
        """
