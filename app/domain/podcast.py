"""Domain entities for the weekly podcast.

The podcast is built from a published `Newsletter`: a scriptwriter turns the
selected stories into a two-host dialogue (`PodcastScript`), a text-to-speech
provider renders it to audio, and the result is published as a `PodcastEpisode`
(an MP3 plus an RSS item). These are pure domain objects — the TTS adapter, the
RSS renderer and the persistence layer all consume them without leaking
infrastructure concerns back into the domain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Speaker identifiers used across the script and the voice mapping.
SPEAKER_A = "A"
SPEAKER_B = "B"


@dataclass(frozen=True, slots=True)
class PodcastLine:
    """A single spoken line, attributed to one of the two hosts ("A"/"B")."""

    speaker: str
    text: str


@dataclass(frozen=True, slots=True)
class PodcastScript:
    """A two-host dialogue script for a weekly episode."""

    title: str
    intro: str
    lines: tuple[PodcastLine, ...]
    outro: str = ""

    @property
    def spoken_lines(self) -> tuple[PodcastLine, ...]:
        """All lines to synthesize: intro and outro (host A) wrapping the dialogue."""
        lines: list[PodcastLine] = []
        if self.intro.strip():
            lines.append(PodcastLine(speaker=SPEAKER_A, text=self.intro.strip()))
        lines.extend(line for line in self.lines if line.text.strip())
        if self.outro.strip():
            lines.append(PodcastLine(speaker=SPEAKER_A, text=self.outro.strip()))
        return tuple(lines)

    @property
    def full_text(self) -> str:
        """The whole script as plain text (for word counting / fallbacks)."""
        parts = [self.intro, *(line.text for line in self.lines), self.outro]
        return "\n".join(p for p in parts if p.strip())

    @property
    def word_count(self) -> int:
        return len(self.full_text.split())


@dataclass(frozen=True, slots=True)
class PodcastEpisode:
    """A published weekly episode: its audio plus calendar metadata."""

    iso_year: int
    iso_week: int
    week_label: str
    title: str
    audio_url: str
    page_url: str
    duration_seconds: int
    byte_size: int
    generated_at: datetime
    summary: str = ""


@dataclass
class PodcastReport:
    """Summary of the outcome of a weekly podcast run."""

    script_lines: int = 0
    audio_bytes: int = 0
    duration_seconds: int = 0
    audio_url: str | None = None
    feed_url: str | None = None
    discord_message_id: int | None = None
    errors: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def succeeded(self) -> bool:
        return self.audio_url is not None and self.audio_bytes > 0
