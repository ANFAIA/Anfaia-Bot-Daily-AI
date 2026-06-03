"""Tests for the configuration (pydantic-settings)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import LLMProviderName, Settings


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_post_time_parsing() -> None:
    s = _settings(post_time="07:30")
    assert s.post_hour == 7
    assert s.post_minute == 30


def test_invalid_post_time() -> None:
    with pytest.raises(ValidationError):
        _settings(post_time="25:00")
    with pytest.raises(ValidationError):
        _settings(post_time="bad")


def test_database_url_assembled_from_parts() -> None:
    s = _settings(
        postgres_user="u",
        postgres_password="p",
        postgres_db="d",
        postgres_host="db.example.com",
        postgres_port=6543,
    )
    assert s.database_url == "postgresql+asyncpg://u:p@db.example.com:6543/d"


def test_database_url_explicit_takes_precedence() -> None:
    explicit = "postgresql+asyncpg://x:y@host:1234/z"
    s = _settings(database_url=explicit, postgres_user="ignored")
    assert s.database_url == explicit


def test_empty_strings_become_none() -> None:
    s = _settings(discord_channel_id="", discord_token="", openai_api_key="")
    assert s.discord_channel_id is None
    assert s.discord_token is None
    assert s.openai_api_key is None


def test_active_llm_api_key_selection() -> None:
    s = _settings(
        llm_provider=LLMProviderName.ANTHROPIC,
        anthropic_api_key="ak",
        openai_api_key="ok",
    )
    assert s.active_llm_api_key == "ak"

    s2 = _settings(llm_provider=LLMProviderName.OPENROUTER, openrouter_api_key="ork")
    assert s2.active_llm_api_key == "ork"

    s3 = _settings(llm_provider=LLMProviderName.OPENAI, openai_api_key="ok")
    assert s3.active_llm_api_key == "ok"
