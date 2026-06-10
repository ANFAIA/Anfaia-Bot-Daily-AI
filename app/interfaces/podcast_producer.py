"""Podcast episode producer port.

Abstracts "turn the weekly newsletter into a titled audio episode". The classic
implementation scripts the dialogue locally and synthesizes it line by line;
the GenFM implementation delegates both steps to ElevenLabs Studio. The podcast
workflow only sees this contract, so engines can be swapped from configuration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.newsletter import Newsletter
from app.domain.podcast import PodcastScript
from app.interfaces.tts import SynthesizedAudio


class PodcastProductionError(RuntimeError):
    """Unrecoverable error while producing the episode."""


@dataclass(frozen=True, slots=True)
class ProducedEpisode:
    """The produced episode: its title, audio and (when available) the script."""

    title: str
    audio: SynthesizedAudio
    # Engines that script locally expose the dialogue (useful for previews);
    # engines that generate audio directly (GenFM) leave it as None.
    script: PodcastScript | None = None

    @property
    def script_lines(self) -> int:
        return len(self.script.spoken_lines) if self.script else 0


class PodcastProducer(ABC):
    """Produces the weekly episode from the newsletter."""

    @abstractmethod
    async def produce(self, newsletter: Newsletter) -> ProducedEpisode:
        """Raises PodcastProductionError (or TTSError) on permanent failure."""
