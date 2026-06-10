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


class TTSProviderName(StrEnum):
    """Text-to-speech backend for the weekly podcast."""

    ELEVENLABS = "elevenlabs"
    GEMINI = "gemini"  # Google Gemini multi-speaker TTS (NotebookLM-style voices)


class WorkflowEngine(StrEnum):
    """Orchestration engine for the daily pipeline."""

    SEQUENTIAL = "sequential"  # custom in-code pipeline (single-shot agents)
    DEEPAGENTS = "deepagents"  # deliberative editorial brain (deepagents)


class PodcastEngineName(StrEnum):
    """Engine that produces the weekly episode (script + audio)."""

    CLASSIC = "classic"  # local scriptwriter agent + per-line TTS
    GENFM = "genfm"  # ElevenLabs Studio podcast generator (script + audio)


def _parse_rss_feeds(raw: str) -> list[tuple[str, str]]:
    """Parse "Name|URL" entries separated by commas or newlines."""
    feeds: list[tuple[str, str]] = []
    for entry in (e.strip() for chunk in raw.split("\n") for e in chunk.split(",")):
        if not entry:
            continue
        name, sep, url = entry.partition("|")
        name, url = name.strip(), url.strip()
        if not sep or not name or not url.startswith(("http://", "https://")):
            raise ValueError(
                f"Entrada RSS inválida: {entry!r}. Formato esperado: 'Nombre|https://...'"
            )
        feeds.append((name, url))
    return feeds


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

    # --- Weekly podcast (generated from the newsletter) ---
    podcast_enabled: bool = False
    # Which TTS backend voices the episode.
    tts_provider: TTSProviderName = TTSProviderName.ELEVENLABS
    # ElevenLabs.
    elevenlabs_api_key: str | None = None
    elevenlabs_model: str = "eleven_multilingual_v2"
    # Google Gemini multi-speaker TTS (NotebookLM-style). The voices below are
    # interpreted as Gemini prebuilt voice names (e.g. "Kore", "Puck").
    gemini_api_key: str | None = None
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"
    # Per-host "voice": an ElevenLabs voice id OR a Gemini prebuilt voice name,
    # depending on `tts_provider`. Plus the display names used in the script.
    podcast_voice_a: str | None = None
    podcast_voice_b: str | None = None
    podcast_voice_a_name: str = "Lucía"
    podcast_voice_b_name: str = "Mateo"
    # Target episode length (minutes) guiding the scriptwriter.
    podcast_target_minutes: int = 8
    # Engine producing the episode: 'classic' (own scriptwriter + TTS) or
    # 'genfm' (ElevenLabs Studio generates script and audio; needs the
    # ElevenLabs API key and the two voice ids).
    podcast_engine: PodcastEngineName = PodcastEngineName.CLASSIC
    # GenFM tuning: episode language, optional extra style instructions, and
    # how long to wait for Studio's background conversion.
    genfm_language: str = "es"
    genfm_instructions: str | None = None
    genfm_poll_seconds: float = 10.0
    genfm_timeout_seconds: float = 900.0
    # On-disk cache for synthesized audio lines, so re-running a week does not
    # pay the TTS API again for unchanged lines. Empty disables the cache.
    tts_cache_dir: str = "var/tts_cache"
    # Optional intro/outro jingles prepended/appended to the episode. Must be
    # MP3 files matching the TTS output (CBR 128 kbps, 44.1 kHz); they are
    # byte-concatenated, so a different encoding would corrupt playback.
    podcast_intro_path: str | None = None
    podcast_outro_path: str | None = None
    # Alternatively, the id of a track generated with ElevenLabs (e.g. Eleven
    # Music): it is downloaded from the account history and cached on disk.
    # Takes precedence over the local path when both are set.
    podcast_intro_elevenlabs_id: str | None = None
    podcast_outro_elevenlabs_id: str | None = None
    # Folder under the static host for the MP3s and feed.xml.
    podcast_path_prefix: str = "podcast"
    # RSS channel metadata.
    podcast_title: str = "Anfaia Weekly AI"
    podcast_author: str = "Anfaia"
    podcast_description: str = (
        "El repaso semanal en español de las noticias de IA más relevantes, "
        "en formato conversación."
    )
    podcast_language: str = "es-ES"
    podcast_email: str | None = None
    # Optional separate Discord channel for the podcast announcement.
    podcast_discord_channel_id: int | None = None

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
    # RSS catalog override: "Name|URL" entries separated by commas or newlines.
    # Unset/empty keeps the built-in default catalog (see sources/registry.py).
    rss_feeds: str | None = None
    # Subreddits to monitor (comma-separated). Empty disables the Reddit source.
    reddit_subreddits: str = "artificial,MachineLearning"
    hackernews_enabled: bool = True
    # Fetch the full article body before editing (best-effort; the editor falls
    # back to the feed summary when the page cannot be retrieved).
    article_fetch_enabled: bool = True
    article_fetch_max_chars: int = 8000

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
        "elevenlabs_api_key",
        "gemini_api_key",
        "podcast_voice_a",
        "podcast_voice_b",
        "podcast_email",
        "podcast_discord_channel_id",
        "podcast_intro_path",
        "podcast_outro_path",
        "podcast_intro_elevenlabs_id",
        "podcast_outro_elevenlabs_id",
        "genfm_instructions",
        "rss_feeds",
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

    @field_validator("rss_feeds")
    @classmethod
    def _validate_rss_feeds(cls, value: str | None) -> str | None:
        # Fail fast on malformed entries instead of silently dropping feeds.
        if value is not None:
            _parse_rss_feeds(value)
        return value

    @property
    def rss_feed_list(self) -> list[tuple[str, str]] | None:
        """Parsed RSS catalog override, or None to use the built-in defaults."""
        if self.rss_feeds is None:
            return None
        return _parse_rss_feeds(self.rss_feeds)

    @property
    def reddit_subreddit_list(self) -> list[str]:
        return [sub.strip() for sub in self.reddit_subreddits.split(",") if sub.strip()]

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
