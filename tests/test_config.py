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


def test_newsletter_post_time_parsing_and_validation() -> None:
    s = _settings(newsletter_post_time="10:15")
    assert s.newsletter_post_hour == 10
    assert s.newsletter_post_minute == 15
    with pytest.raises(ValidationError):
        _settings(newsletter_post_time="99:99")


def test_github_settings_empty_to_none() -> None:
    s = _settings(github_token="", github_owner="", github_repo="", newsletter_base_url="")
    assert s.github_token is None
    assert s.github_owner is None
    assert s.github_repo is None
    assert s.newsletter_base_url is None


def test_rss_feeds_default_is_none() -> None:
    s = _settings(rss_feeds="")
    assert s.rss_feeds is None
    assert s.rss_feed_list is None  # None -> use the built-in catalog


def test_rss_feeds_parsing_commas_and_newlines() -> None:
    s = _settings(rss_feeds="Blog A|https://a.com/feed\nBlog B|https://b.com/rss, Blog C|https://c.com/atom")
    assert s.rss_feed_list == [
        ("Blog A", "https://a.com/feed"),
        ("Blog B", "https://b.com/rss"),
        ("Blog C", "https://c.com/atom"),
    ]


def test_rss_feeds_invalid_entry_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(rss_feeds="sin separador")
    with pytest.raises(ValidationError):
        _settings(rss_feeds="Nombre|ftp://no-http.com/feed")


def test_reddit_subreddits_parsing() -> None:
    s = _settings(reddit_subreddits="artificial, LocalLLaMA ,")
    assert s.reddit_subreddit_list == ["artificial", "LocalLLaMA"]
    assert _settings(reddit_subreddits="").reddit_subreddit_list == []


def test_podcast_jingle_settings_empty_to_none() -> None:
    s = _settings(
        podcast_intro_path="",
        podcast_outro_path="",
        podcast_intro_elevenlabs_id="",
        podcast_outro_elevenlabs_id="",
    )
    assert s.podcast_intro_path is None
    assert s.podcast_outro_path is None
    assert s.podcast_intro_elevenlabs_id is None
    assert s.podcast_outro_elevenlabs_id is None


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
