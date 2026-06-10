"""Null text-to-speech provider used when ElevenLabs is not configured.

Lets the system start without TTS credentials. Any real attempt to synthesize
fails explicitly instead of silently doing nothing (mirrors `NullSitePublisher`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.core.logging import get_logger
from app.domain.podcast import PodcastLine
from app.interfaces.tts import SynthesizedAudio, TextToSpeechProvider, TTSError

logger = get_logger(__name__)


class NullTTS(TextToSpeechProvider):
    """Inert implementation of the `TextToSpeechProvider` port."""

    async def synthesize_dialogue(
        self, lines: Sequence[PodcastLine], voice_map: Mapping[str, str]
    ) -> SynthesizedAudio:
        logger.error("tts.not_configured", lines=len(lines))
        raise TTSError(
            "El TTS no está configurado (define ELEVENLABS_API_KEY, "
            "PODCAST_VOICE_A y PODCAST_VOICE_B)"
        )
