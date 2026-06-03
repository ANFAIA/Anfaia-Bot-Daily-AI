"""Tests for the provider factories (LLM and embeddings)."""

from __future__ import annotations

import httpx
import pytest

from app.core.config import EmbeddingProviderName, LLMProviderName, Settings
from app.infrastructure.embeddings.factory import build_embedding_provider
from app.infrastructure.embeddings.hash_embeddings import HashEmbeddingProvider
from app.infrastructure.embeddings.openai_embeddings import OpenAIEmbeddingProvider
from app.infrastructure.llm.anthropic_provider import AnthropicLLMProvider
from app.infrastructure.llm.factory import build_llm_provider
from app.infrastructure.llm.openai_provider import OpenAILLMProvider, OpenRouterLLMProvider


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


async def test_build_llm_openai() -> None:
    async with httpx.AsyncClient() as client:
        provider = build_llm_provider(
            _settings(llm_provider=LLMProviderName.OPENAI, openai_api_key="k"), client
        )
        assert isinstance(provider, OpenAILLMProvider)


async def test_build_llm_anthropic() -> None:
    async with httpx.AsyncClient() as client:
        provider = build_llm_provider(
            _settings(llm_provider=LLMProviderName.ANTHROPIC, anthropic_api_key="k"), client
        )
        assert isinstance(provider, AnthropicLLMProvider)


async def test_build_llm_openrouter() -> None:
    async with httpx.AsyncClient() as client:
        provider = build_llm_provider(
            _settings(llm_provider=LLMProviderName.OPENROUTER, openrouter_api_key="k"), client
        )
        assert isinstance(provider, OpenRouterLLMProvider)


async def test_build_llm_missing_key_raises() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            build_llm_provider(_settings(llm_provider=LLMProviderName.OPENAI), client)


async def test_build_embeddings_hash() -> None:
    async with httpx.AsyncClient() as client:
        provider = build_embedding_provider(
            _settings(embedding_provider=EmbeddingProviderName.HASH, embedding_dim=128), client
        )
        assert isinstance(provider, HashEmbeddingProvider)
        assert provider.dimension == 128


async def test_build_embeddings_openai_with_key() -> None:
    async with httpx.AsyncClient() as client:
        provider = build_embedding_provider(
            _settings(embedding_provider=EmbeddingProviderName.OPENAI, openai_api_key="k"),
            client,
        )
        assert isinstance(provider, OpenAIEmbeddingProvider)


async def test_build_embeddings_openai_without_key_falls_back() -> None:
    async with httpx.AsyncClient() as client:
        provider = build_embedding_provider(
            _settings(embedding_provider=EmbeddingProviderName.OPENAI), client
        )
        assert isinstance(provider, HashEmbeddingProvider)
