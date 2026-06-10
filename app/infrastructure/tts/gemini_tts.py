"""Google Gemini multi-speaker text-to-speech adapter (NotebookLM-style).

Renders the two-host dialogue with Gemini's native multi-speaker TTS: the whole
transcript is sent (labelled ``A:`` / ``B:``) and Gemini voices both speakers in
a single pass, giving the natural, conversational feel of NotebookLM's audio.

Gemini returns raw 16-bit PCM (not MP3), so we concatenate the PCM across
requests — gaplessly, since PCM has no container framing — and wrap the result
in a WAV header with the stdlib ``wave`` module (no system dependencies). The
transcript is split into chunks that stay within the model's per-request audio
limit; PCM duration is exact (bytes / (rate · 2)).
"""

from __future__ import annotations

import base64
import contextlib
import io
import wave
from collections.abc import Mapping, Sequence

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging import get_logger
from app.domain.podcast import PodcastLine
from app.interfaces.tts import SynthesizedAudio, TextToSpeechProvider, TTSError

logger = get_logger(__name__)

_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
_CONTENT_TYPE = "audio/wav"
_DEFAULT_RATE = 24000  # Gemini TTS sample rate (Hz), 16-bit mono PCM
# Keep each request's transcript well within the model's audio output limit.
_CHUNK_CHAR_BUDGET = 2500


class GeminiTTS(TextToSpeechProvider):
    """Renders a dialogue to a single WAV using Gemini multi-speaker TTS."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        model: str = "gemini-2.5-flash-preview-tts",
    ) -> None:
        if not api_key:
            raise ValueError("GeminiTTS requiere GEMINI_API_KEY")
        self._client = client
        self._model = model
        self._headers = {
            "x-goog-api-key": api_key,
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

        speaker_configs = [
            {"speaker": speaker, "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}
            for speaker, voice in voice_map.items()
        ]

        pcm = b""
        rate = _DEFAULT_RATE
        for index, chunk in enumerate(self._chunk(lines)):
            transcript = "\n".join(f"{line.speaker}: {line.text}" for line in chunk)
            audio_bytes, rate = await self._synthesize_chunk(transcript, speaker_configs)
            pcm += audio_bytes
            logger.info("tts.chunk_synthesized", index=index, bytes=len(audio_bytes))

        data = _pcm_to_wav(pcm, rate)
        duration = max(1, round(len(pcm) / (rate * 2)))  # 16-bit mono => 2 bytes/sample
        logger.info("tts.synthesized", lines=len(lines), bytes=len(data), duration=duration)
        return SynthesizedAudio(
            data=data, content_type=_CONTENT_TYPE, duration_seconds=duration, extension="wav"
        )

    @staticmethod
    def _chunk(lines: Sequence[PodcastLine]) -> list[list[PodcastLine]]:
        """Group consecutive lines so each request stays within the char budget."""
        chunks: list[list[PodcastLine]] = []
        current: list[PodcastLine] = []
        size = 0
        for line in lines:
            length = len(line.text) + len(line.speaker) + 2
            if current and size + length > _CHUNK_CHAR_BUDGET:
                chunks.append(current)
                current, size = [], 0
            current.append(line)
            size += length
        if current:
            chunks.append(current)
        return chunks

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        reraise=True,
    )
    async def _synthesize_chunk(
        self, transcript: str, speaker_configs: list[dict]
    ) -> tuple[bytes, int]:
        body = {
            "contents": [{"parts": [{"text": transcript}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "multiSpeakerVoiceConfig": {"speakerVoiceConfigs": speaker_configs}
                },
            },
        }
        response = await self._client.post(
            f"{_API_ROOT}/models/{self._model}:generateContent",
            headers=self._headers,
            json=body,
        )
        if response.status_code != 200:
            raise TTSError(
                f"Gemini respondió {response.status_code} al sintetizar "
                f"(revisa GEMINI_API_KEY y el modelo/voces): {response.text[:200]}"
            )
        return _extract_pcm(response.json())


def _extract_pcm(payload: dict) -> tuple[bytes, int]:
    """Pull the base64 PCM and its sample rate out of a generateContent response."""
    try:
        part = payload["candidates"][0]["content"]["parts"][0]
        inline = part["inlineData"]
        data = base64.b64decode(inline["data"])
    except (KeyError, IndexError, TypeError) as exc:
        raise TTSError(f"Respuesta de Gemini sin audio válido: {exc}") from exc
    if not data:
        raise TTSError("Gemini devolvió audio vacío")
    return data, _rate_from_mime(inline.get("mimeType", ""))


def _rate_from_mime(mime: str) -> int:
    """Parse the sample rate from a mime type like 'audio/L16;rate=24000'."""
    for token in mime.split(";"):
        stripped = token.strip()
        if stripped.startswith("rate="):
            with contextlib.suppress(ValueError):
                return int(stripped.removeprefix("rate="))
    return _DEFAULT_RATE


def _pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    """Wrap raw 16-bit mono PCM in a WAV container (pure stdlib)."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()
