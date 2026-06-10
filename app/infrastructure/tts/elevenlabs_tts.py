"""ElevenLabs text-to-speech adapter.

Synthesizes a two-host dialogue by calling the ElevenLabs Text-to-Speech API
once per line (with the speaker's voice) and concatenating the resulting MP3
streams into a single episode. ElevenLabs returns constant-bitrate MP3
(``mp3_44100_128``), so the concatenated bytes play back as one continuous file
in every common player — no ffmpeg needed.

The episode duration is estimated from the word count (~2.5 words/second in
Spanish), which is accurate enough for the RSS ``<itunes:duration>`` tag.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging import get_logger
from app.domain.podcast import PodcastLine
from app.interfaces.tts import SynthesizedAudio, TextToSpeechProvider, TTSError

logger = get_logger(__name__)

_API_ROOT = "https://api.elevenlabs.io/v1"
_OUTPUT_FORMAT = "mp3_44100_128"
_CONTENT_TYPE = "audio/mpeg"
# Average Spanish narration pace, used to estimate the episode duration.
_WORDS_PER_SECOND = 2.5


class ElevenLabsTTS(TextToSpeechProvider):
    """Renders a dialogue to a single MP3 using the ElevenLabs API."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        model_id: str = "eleven_multilingual_v2",
    ) -> None:
        if not api_key:
            raise ValueError("ElevenLabsTTS requiere ELEVENLABS_API_KEY")
        self._client = client
        self._model_id = model_id
        self._headers = {
            "xi-api-key": api_key,
            "Accept": _CONTENT_TYPE,
            "Content-Type": "application/json",
        }

    async def synthesize_dialogue(
        self, lines: Sequence[PodcastLine], voice_map: Mapping[str, str]
    ) -> SynthesizedAudio:
        if not lines:
            raise TTSError("El guion no contiene líneas que sintetizar")
        missing = {line.speaker for line in lines} - set(voice_map)
        if missing:
            raise TTSError(f"Faltan voces para los hablantes: {', '.join(sorted(missing))}")

        chunks: list[bytes] = []
        words = 0
        for index, line in enumerate(lines):
            audio = await self._synthesize_line(voice_map[line.speaker], line.text)
            chunks.append(audio)
            words += len(line.text.split())
            logger.info("tts.line_synthesized", index=index, speaker=line.speaker, bytes=len(audio))

        data = b"".join(chunks)
        duration = max(1, round(words / _WORDS_PER_SECOND))
        logger.info("tts.synthesized", lines=len(lines), bytes=len(data), duration=duration)
        return SynthesizedAudio(
            data=data, content_type=_CONTENT_TYPE, duration_seconds=duration, extension="mp3"
        )

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        reraise=True,
    )
    async def _synthesize_line(self, voice_id: str, text: str) -> bytes:
        response = await self._client.post(
            f"{_API_ROOT}/text-to-speech/{voice_id}",
            headers=self._headers,
            params={"output_format": _OUTPUT_FORMAT},
            json={"text": text, "model_id": self._model_id},
        )
        if response.status_code != 200:
            raise TTSError(
                f"ElevenLabs respondió {response.status_code} al sintetizar "
                f"(revisa ELEVENLABS_API_KEY y el voice id): {response.text[:200]}"
            )
        return response.content
