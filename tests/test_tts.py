"""Tests for the ElevenLabs TTS adapter (mocked with respx) and the null one."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx

from app.domain.podcast import SPEAKER_A, SPEAKER_B, PodcastLine
from app.infrastructure.tts.elevenlabs_tts import ElevenLabsTTS
from app.infrastructure.tts.gemini_tts import GeminiTTS
from app.infrastructure.tts.null_tts import NullTTS
from app.interfaces.tts import TTSError

_VOICE_A = "voiceA"
_VOICE_B = "voiceB"
_URL_A = f"https://api.elevenlabs.io/v1/text-to-speech/{_VOICE_A}"
_URL_B = f"https://api.elevenlabs.io/v1/text-to-speech/{_VOICE_B}"
_VOICE_MAP = {SPEAKER_A: _VOICE_A, SPEAKER_B: _VOICE_B}


def _tts(client: httpx.AsyncClient) -> ElevenLabsTTS:
    return ElevenLabsTTS(client, api_key="k", model_id="eleven_multilingual_v2")


@respx.mock
async def test_synthesizes_and_concatenates_per_voice() -> None:
    route_a = respx.post(_URL_A).mock(return_value=httpx.Response(200, content=b"AAA"))
    route_b = respx.post(_URL_B).mock(return_value=httpx.Response(200, content=b"BB"))
    lines = [
        PodcastLine(SPEAKER_A, "hola que tal"),
        PodcastLine(SPEAKER_B, "muy bien"),
    ]
    async with httpx.AsyncClient() as client:
        audio = await _tts(client).synthesize_dialogue(lines, _VOICE_MAP)
    # MP3 chunks are concatenated in order, one request per line with its voice.
    assert audio.data == b"AAABB"
    assert audio.content_type == "audio/mpeg"
    assert audio.extension == "mp3"
    assert audio.duration_seconds >= 1
    assert route_a.called and route_b.called
    assert route_a.calls.last.request.headers["xi-api-key"] == "k"


@respx.mock
async def test_http_error_raises_tts_error() -> None:
    respx.post(_URL_A).mock(return_value=httpx.Response(401, text="unauthorized"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(TTSError):
            await _tts(client).synthesize_dialogue([PodcastLine(SPEAKER_A, "hola")], _VOICE_MAP)


async def test_missing_voice_raises() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(TTSError):
            await _tts(client).synthesize_dialogue(
                [PodcastLine(SPEAKER_B, "hola")], {SPEAKER_A: _VOICE_A}
            )


async def test_empty_lines_raises() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(TTSError):
            await _tts(client).synthesize_dialogue([], _VOICE_MAP)


async def test_null_tts_raises() -> None:
    with pytest.raises(TTSError):
        await NullTTS().synthesize_dialogue([PodcastLine(SPEAKER_A, "x")], _VOICE_MAP)


# --- Gemini multi-speaker TTS --------------------------------------------------

_GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
_GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent"
)
_GEMINI_VOICES = {SPEAKER_A: "Kore", SPEAKER_B: "Puck"}


def _gemini(client: httpx.AsyncClient) -> GeminiTTS:
    return GeminiTTS(client, api_key="k", model=_GEMINI_MODEL)


def _audio_response(pcm: bytes) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": "audio/L16;rate=24000",
                                    "data": base64.b64encode(pcm).decode("ascii"),
                                }
                            }
                        ]
                    }
                }
            ]
        },
    )


@respx.mock
async def test_gemini_returns_wav_and_uses_multispeaker() -> None:
    pcm = b"\x01\x02" * 24000  # 1 second of 16-bit mono @ 24kHz
    route = respx.post(_GEMINI_URL).mock(return_value=_audio_response(pcm))
    lines = [PodcastLine(SPEAKER_A, "hola"), PodcastLine(SPEAKER_B, "que tal")]
    async with httpx.AsyncClient() as client:
        audio = await _gemini(client).synthesize_dialogue(lines, _GEMINI_VOICES)

    # Output is a WAV container (single multi-speaker call for the whole script).
    assert audio.data.startswith(b"RIFF")
    assert audio.content_type == "audio/wav"
    assert audio.extension == "wav"
    assert audio.duration_seconds == 1
    assert route.call_count == 1
    body = json.loads(route.calls.last.request.content)
    speech = body["generationConfig"]["speechConfig"]["multiSpeakerVoiceConfig"]
    voices = {
        c["speaker"]: c["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"]
        for c in speech["speakerVoiceConfigs"]
    }
    assert voices == {"A": "Kore", "B": "Puck"}
    assert route.calls.last.request.headers["x-goog-api-key"] == "k"


@respx.mock
async def test_gemini_chunks_long_scripts_and_concatenates() -> None:
    pcm = b"\x00\x00" * 1000
    route = respx.post(_GEMINI_URL).mock(return_value=_audio_response(pcm))
    # Lines long enough to exceed the per-request char budget => several calls.
    lines = [PodcastLine(SPEAKER_A if i % 2 == 0 else SPEAKER_B, "x" * 1500) for i in range(6)]
    async with httpx.AsyncClient() as client:
        audio = await _gemini(client).synthesize_dialogue(lines, _GEMINI_VOICES)
    assert route.call_count >= 2
    assert audio.data.startswith(b"RIFF")


@respx.mock
async def test_gemini_http_error_raises() -> None:
    respx.post(_GEMINI_URL).mock(return_value=httpx.Response(403, text="forbidden"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(TTSError):
            await _gemini(client).synthesize_dialogue(
                [PodcastLine(SPEAKER_A, "hola")], _GEMINI_VOICES
            )


@respx.mock
async def test_gemini_empty_audio_raises() -> None:
    respx.post(_GEMINI_URL).mock(return_value=httpx.Response(200, json={"candidates": []}))
    async with httpx.AsyncClient() as client:
        with pytest.raises(TTSError):
            await _gemini(client).synthesize_dialogue(
                [PodcastLine(SPEAKER_A, "hola")], _GEMINI_VOICES
            )
