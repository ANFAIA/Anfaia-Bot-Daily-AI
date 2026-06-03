"""Framework-agnostic helpers shared by the editorial brains.

These functions hold no orchestration-framework dependency (no ``deepagents``,
no LangChain): they only build the prompts handed to the brain and decode its
structured answer back into domain objects. Keeping them here lets us unit-test
the fragile parsing in isolation, and lets any future brain reuse them.
"""

from __future__ import annotations

from typing import Any

from app.domain.entities import DiscussionPrompt, EditedArticle, NewsItem
from app.interfaces.editorial import EditorialDecision

_DEFAULT_QUESTION = (
    "¿Cómo creéis que este avance cambiará vuestra forma de construir "
    "sistemas de IA en el día a día?"
)


def build_candidate_brief(candidates: list[NewsItem]) -> str:
    """Render the shortlist as a numbered brief for the editorial agent."""
    lines: list[str] = []
    for index, item in enumerate(candidates):
        category = item.category.value if item.category else "AI"
        score = item.relevance_score.value if item.relevance_score else 0
        summary = (item.summary or "").strip()
        lines.append(
            f"[{index}] ({category}, relevancia {score}) {item.title}\n"
            f"    Fuente: {item.source} — {item.url}\n"
            f"    Resumen: {summary}"
        )
    return "\n".join(lines)


def build_recent_context(recent_titles: list[str]) -> str:
    """Render recently published titles so the brain can avoid repetition."""
    if not recent_titles:
        return "No hay publicaciones recientes."
    return "\n".join(f"- {title}" for title in recent_titles)


def decode_decision(payload: dict[str, Any], candidates: list[NewsItem]) -> EditorialDecision:
    """Turn the brain's JSON answer into a validated `EditorialDecision`.

    The parsing is defensive: a missing/garbage index falls back to the
    top-ranked candidate, and missing editorial fields fall back to the chosen
    item's own data, so the workflow never stalls on a malformed answer.

    Raises:
        ValueError: only if ``candidates`` is empty (nothing to decide).
    """
    if not candidates:
        raise ValueError("No hay candidatos para la decisión editorial")

    index = _coerce_index(payload.get("chosen_index"), len(candidates))
    chosen = candidates[index]
    return EditorialDecision(
        chosen=chosen,
        edited=_decode_edited(payload, chosen),
        discussion=_decode_discussion(payload),
        rationale=str(payload.get("rationale", "")).strip(),
        fact_check_notes=str(payload.get("fact_check_notes", "")).strip(),
    )


def _coerce_index(raw: Any, count: int) -> int:
    """Best-effort parse of the chosen index, clamped to ``[0, count - 1]``."""
    try:
        index = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, min(index, count - 1))


def _decode_edited(payload: dict[str, Any], chosen: NewsItem) -> EditedArticle:
    # The agent may nest the article under "article" or return it flat.
    article = payload.get("article")
    if not isinstance(article, dict):
        article = payload
    fallback_body = chosen.summary or "Sin resumen disponible."
    return EditedArticle(
        title=(str(article.get("title") or chosen.title).strip() or chosen.title)[:256],
        what_happened=str(article.get("what_happened") or fallback_body).strip(),
        why_it_matters=str(
            article.get("why_it_matters") or "Relevante para la comunidad de IA por su temática."
        ).strip(),
        how_we_could_use_it=str(
            article.get("how_we_could_use_it")
            or "Revisa la fuente para evaluar aplicaciones concretas."
        ).strip(),
        limitations=str(
            article.get("limitations") or "Resumen automático: contrasta con la fuente original."
        ).strip(),
        source_url=chosen.url,
    )


def _decode_discussion(payload: dict[str, Any]) -> DiscussionPrompt:
    discussion = payload.get("discussion")
    if isinstance(discussion, dict):
        question = str(discussion.get("question", "")).strip()
        rationale = str(discussion.get("rationale", "")).strip()
    elif isinstance(discussion, str):
        question, rationale = discussion.strip(), ""
    else:
        question = str(payload.get("question", "")).strip()
        rationale = str(payload.get("discussion_rationale", "")).strip()
    return DiscussionPrompt(question=question or _DEFAULT_QUESTION, rationale=rationale)
