"""Factory that builds the deepagents editorial brain on demand.

Imports the optional ``deepagents`` stack lazily so the rest of the system runs
without it installed. If the extras are missing it raises an actionable error.
"""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.interfaces.editorial import EditorialBrain


def build_editorial_brain(
    settings: Settings, http_client: httpx.AsyncClient, *, fallback: EditorialBrain
) -> EditorialBrain:
    """Build the `DeepAgentsEditorialBrain`, degrading to ``fallback`` on errors."""
    try:
        from app.infrastructure.editorial.deep_agent_brain import DeepAgentsEditorialBrain
        from app.infrastructure.llm.langchain_factory import build_chat_model
    except ImportError as exc:  # pragma: no cover - depends on optional extras
        raise RuntimeError(
            "WORKFLOW_ENGINE=deepagents requiere dependencias adicionales. "
            "Instálalas con: pip install '.[deepagents]'"
        ) from exc

    model = build_chat_model(settings, temperature=0.3)
    return DeepAgentsEditorialBrain(
        model=model,
        http_client=http_client,
        fallback=fallback,
        recursion_limit=settings.deepagents_recursion_limit,
    )
