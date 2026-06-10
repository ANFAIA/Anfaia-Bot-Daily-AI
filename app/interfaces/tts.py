"""Text-to-speech port (outbound channel that renders a script to audio).

Abstracts "turn this two-host dialogue into a single audio file". The default
adapter targets ElevenLabs, but the port keeps the workflow agnostic so it can
be swapped for OpenAI TTS, Azure, etc. without touching the domain.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.podcast import PodcastLine


class TTSError(RuntimeError):
    """Unrecoverable error while synthesizing speech."""


@dataclass(frozen=True, slots=True)
class SynthesizedAudio:
    """Result of synthesizing a script: the audio bytes and its metadata."""

    data: bytes
    content_type: str
    duration_seconds: int
    extension: str = "mp3"  # file extension for the published asset (e.g. mp3, wav)


class TextToSpeechProvider(ABC):
    """Renders a multi-speaker dialogue to a single audio file."""

    @abstractmethod
    async def synthesize_dialogue(
        self, lines: Sequence[PodcastLine], voice_map: Mapping[str, str]
    ) -> SynthesizedAudio:
        """Synthesize ``lines`` using ``voice_map`` (speaker id -> voice id).

        Raises:
            TTSError: if synthesis fails permanently.
        """
