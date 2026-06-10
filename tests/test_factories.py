"""Tests for the provider factories (LLM and embeddings)."""

from __future__ import annotations

import httpx
import pytest

from app.core.config import (
    EmbeddingProviderName,
    LLMProviderName,
    Settings,
    TTSProviderName,
)
from app.infrastructure.embeddings.factory import build_embedding_provider
from app.infrastructure.embeddings.hash_embeddings import HashEmbeddingProvider
from app.infrastructure.embeddings.openai_embeddings import OpenAIEmbeddingProvider
from app.infrastructure.llm.anthropic_provider import AnthropicLLMProvider
from app.infrastructure.llm.factory import build_llm_provider
from app.infrastructure.llm.openai_provider import OpenAILLMProvider, OpenRouterLLMProvider
from app.infrastructure.tts.elevenlabs_tts import ElevenLabsTTS
from app.infrastructure.tts.factory import build_tts_provider
from app.infrastructure.tts.gemini_tts import GeminiTTS
from app.infrastructure.tts.null_tts import NullTTS


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


async def test_build_tts_elevenlabs_with_key() -> None:
    async with httpx.AsyncClient() as client:
        provider = build_tts_provider(
            _settings(tts_provider=TTSProviderName.ELEVENLABS, elevenlabs_api_key="k"), client
        )
        assert isinstance(provider, ElevenLabsTTS)


async def test_build_tts_gemini_with_key() -> None:
    async with httpx.AsyncClient() as client:
        provider = build_tts_provider(
            _settings(tts_provider=TTSProviderName.GEMINI, gemini_api_key="k"), client
        )
        assert isinstance(provider, GeminiTTS)


async def test_build_tts_without_key_falls_back_to_null() -> None:
    async with httpx.AsyncClient() as client:
        assert isinstance(
            build_tts_provider(_settings(tts_provider=TTSProviderName.GEMINI), client), NullTTS
        )
        assert isinstance(
            build_tts_provider(_settings(tts_provider=TTSProviderName.ELEVENLABS), client), NullTTS
        )
