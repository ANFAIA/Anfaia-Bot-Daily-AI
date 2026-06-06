"""Centralized application configuration (pydantic-settings).

All configuration is loaded from environment variables / the `.env` file.
This is the only point in the system that knows about the environment; the rest
of the code receives its configuration via dependency injection.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderName(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"


class EmbeddingProviderName(StrEnum):
    OPENAI = "openai"
    HASH = "hash"


class WorkflowEngine(StrEnum):
    """Orchestration engine for the daily pipeline."""

    SEQUENTIAL = "sequential"  # custom in-code pipeline (single-shot agents)
    DEEPAGENTS = "deepagents"  # deliberative editorial brain (deepagents)


def _validate_hhmm(value: str) -> str:
    """Validate a 24h HH:MM time string."""
    hh, _, mm = value.partition(":")
    if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
        raise ValueError("La hora debe tener formato HH:MM (24h)")
    return value


class Settings(BaseSettings):
    """Typed and validated system configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_env: str = "development"
    log_level: str = "INFO"
    log_json: bool = False

    # --- Database ---
    # PostgreSQL connection parts, all read from the environment. They are used
    # to assemble `database_url` when it is not provided explicitly, so there is
    # a single source of truth and no hardcoded credentials.
    postgres_user: str = "anfaia"
    postgres_password: str = "anfaia"
    postgres_db: str = "anfaia"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    # Full async DSN. If set in the environment it takes precedence; otherwise it
    # is built from the POSTGRES_* parts above.
    database_url: str | None = None

    # --- LLM ---
    llm_provider: LLMProviderName = LLMProviderName.OPENAI
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None

    # --- Embeddings ---
    embedding_provider: EmbeddingProviderName = EmbeddingProviderName.OPENAI
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    duplicate_similarity_threshold: float = 0.86

    # --- Discord ---
    discord_token: str | None = None
    discord_channel_id: int | None = None
    # Optional separate channel for the weekly newsletter announcement.
    # Falls back to discord_channel_id when unset.
    newsletter_discord_channel_id: int | None = None

    # --- Scheduler ---
    scheduler_enabled: bool = True
    post_time: str = "09:00"
    timezone: str = "Europe/Madrid"

    # --- Weekly newsletter ---
    newsletter_enabled: bool = False
    # Soft cap on stories; it only grows to fit the "one per category" floor.
    newsletter_top_n: int = 6
    newsletter_min_relevance: int = 50
    # Extra stories beyond the per-category floor must score at least this.
    newsletter_extra_relevance: int = 80
    newsletter_dedup_threshold: float = 0.86
    newsletter_post_time: str = "09:00"
    newsletter_day_of_week: str = "mon"
    newsletter_base_url: str | None = None
    newsletter_path_prefix: str = "newsletters"
    newsletter_logo_url: str = "https://anfaia.org/ANFAIA_logo_web.png"

    # --- GitHub Pages (newsletter hosting) ---
    github_token: str | None = None
    github_owner: str | None = None
    github_repo: str | None = None
    github_branch: str = "gh-pages"

    # --- Orchestration ---
    # `sequential` (default) keeps the deterministic single-shot pipeline.
    # `deepagents` delegates the editorial decision to a deliberative agent.
    workflow_engine: WorkflowEngine = WorkflowEngine.SEQUENTIAL
    # How many unique candidates the editorial brain gets to choose from.
    editorial_shortlist_size: int = 5
    # Safety cap on the deep agent's reasoning loop.
    deepagents_recursion_limit: int = 50

    # --- Collection ---
    max_items_per_source: int = 15
    min_relevance_score: int = 55
    http_user_agent: str = "AnfaiaDailyAI/0.1 (+https://anfaia.org)"
    http_timeout_seconds: float = 20.0

    @field_validator(
        "openai_api_key",
        "anthropic_api_key",
        "openrouter_api_key",
        "discord_token",
        "discord_channel_id",
        "newsletter_discord_channel_id",
        "github_token",
        "github_owner",
        "github_repo",
        "newsletter_base_url",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, value: object) -> object:
        # An empty value in the .env (e.g. DISCORD_CHANNEL_ID=) means "unset".
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @model_validator(mode="after")
    def _assemble_database_url(self) -> Settings:
        # Build the DSN from the POSTGRES_* parts unless DATABASE_URL was given.
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        return self

    @field_validator("post_time", "newsletter_post_time")
    @classmethod
    def _validate_times(cls, value: str) -> str:
        return _validate_hhmm(value)

    @property
    def post_hour(self) -> int:
        return int(self.post_time.split(":")[0])

    @property
    def post_minute(self) -> int:
        return int(self.post_time.split(":")[1])

    @property
    def newsletter_post_hour(self) -> int:
        return int(self.newsletter_post_time.split(":")[0])

    @property
    def newsletter_post_minute(self) -> int:
        return int(self.newsletter_post_time.split(":")[1])

    @property
    def active_llm_api_key(self) -> str | None:
        return {
            LLMProviderName.OPENAI: self.openai_api_key,
            LLMProviderName.ANTHROPIC: self.anthropic_api_key,
            LLMProviderName.OPENROUTER: self.openrouter_api_key,
        }[self.llm_provider]


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of the configuration."""
    return Settings()
