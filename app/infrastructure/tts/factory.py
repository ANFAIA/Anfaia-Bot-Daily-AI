"""Factory for text-to-speech providers."""

from __future__ import annotations

import httpx

from app.core.config import Settings, TTSProviderName
from app.core.logging import get_logger
from app.infrastructure.tts.cache import FileAudioCache
from app.infrastructure.tts.elevenlabs_tts import ElevenLabsTTS
from app.infrastructure.tts.gemini_tts import GeminiTTS
from app.infrastructure.tts.null_tts import NullTTS
from app.interfaces.tts import TextToSpeechProvider

logger = get_logger(__name__)


def build_tts_provider(settings: Settings, client: httpx.AsyncClient) -> TextToSpeechProvider:
    """Build the TTS provider based on `settings.tts_provider`.

    Returns the selected backend when its API key is configured; otherwise a null
    provider that fails explicitly on use (the podcast step is best-effort, so the
    rest of the system still starts).
    """
    if settings.tts_provider is TTSProviderName.GEMINI:
        if settings.gemini_api_key:
            return GeminiTTS(
                client, api_key=settings.gemini_api_key, model=settings.gemini_tts_model
            )
        logger.warning("tts.not_configured", reason="GEMINI_API_KEY ausente")
        return NullTTS()

    if settings.elevenlabs_api_key:
        cache_dir = settings.tts_cache_dir.strip()
        return ElevenLabsTTS(
            client,
            api_key=settings.elevenlabs_api_key,
            model_id=settings.elevenlabs_model,
            cache=FileAudioCache(cache_dir) if cache_dir else None,
        )
    logger.warning("tts.not_configured", reason="ELEVENLABS_API_KEY ausente")
    return NullTTS()
