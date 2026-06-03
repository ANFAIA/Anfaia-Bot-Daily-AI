"""Builds a LangChain chat model from the app `Settings`.

Only used by the ``deepagents`` editorial brain, which (unlike the rest of the
system) needs a LangChain ``BaseChatModel`` rather than our minimal httpx
adapter. The LangChain provider packages are optional extras; this module
imports them lazily and raises an actionable error if they are missing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import LLMProviderName, Settings

if TYPE_CHECKING:  # pragma: no cover
    from langchain_core.language_models.chat_models import BaseChatModel

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_MISSING_EXTRAS = (
    "El motor 'deepagents' requiere dependencias adicionales. "
    "Instálalas con: pip install '.[deepagents]'"
)


def build_chat_model(settings: Settings, *, temperature: float = 0.3) -> BaseChatModel:
    """Build the LangChain chat model matching ``settings.llm_provider``."""
    api_key = settings.active_llm_api_key
    if not api_key:
        raise ValueError(
            f"Falta la API key para el proveedor LLM '{settings.llm_provider}'. "
            "Configúrala en las variables de entorno."
        )

    try:
        match settings.llm_provider:
            case LLMProviderName.OPENAI:
                from langchain_openai import ChatOpenAI

                return ChatOpenAI(
                    model=settings.llm_model, api_key=api_key, temperature=temperature
                )
            case LLMProviderName.OPENROUTER:
                from langchain_openai import ChatOpenAI

                return ChatOpenAI(
                    model=settings.llm_model,
                    api_key=api_key,
                    base_url=_OPENROUTER_BASE_URL,
                    temperature=temperature,
                )
            case LLMProviderName.ANTHROPIC:
                from langchain_anthropic import ChatAnthropic

                return ChatAnthropic(
                    model=settings.llm_model, api_key=api_key, temperature=temperature
                )
            case _:  # pragma: no cover - exhaustive due to the enum
                raise ValueError(f"Proveedor LLM no soportado: {settings.llm_provider}")
    except ImportError as exc:  # pragma: no cover - depends on optional extras
        raise RuntimeError(_MISSING_EXTRAS) from exc
