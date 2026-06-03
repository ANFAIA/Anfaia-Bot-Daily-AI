"""Factory that selects the LLM adapter based on the configuration."""

from __future__ import annotations

import httpx

from app.core.config import LLMProviderName, Settings
from app.infrastructure.llm.anthropic_provider import AnthropicLLMProvider
from app.infrastructure.llm.openai_provider import OpenAILLMProvider, OpenRouterLLMProvider
from app.interfaces.llm import LLMProvider


def build_llm_provider(settings: Settings, client: httpx.AsyncClient) -> LLMProvider:
    """Build the active `LLMProvider` based on `settings.llm_provider`."""
    api_key = settings.active_llm_api_key
    if not api_key:
        raise ValueError(
            f"Falta la API key para el proveedor LLM '{settings.llm_provider}'. "
            "Configúrala en las variables de entorno."
        )

    match settings.llm_provider:
        case LLMProviderName.OPENAI:
            return OpenAILLMProvider(api_key, settings.llm_model, client=client)
        case LLMProviderName.ANTHROPIC:
            return AnthropicLLMProvider(api_key, settings.llm_model, client=client)
        case LLMProviderName.OPENROUTER:
            return OpenRouterLLMProvider(api_key, settings.llm_model, client=client)
        case _:  # pragma: no cover - exhaustive due to the enum
            raise ValueError(f"Proveedor LLM no soportado: {settings.llm_provider}")
