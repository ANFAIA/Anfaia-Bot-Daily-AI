"""GenFM podcast producer (ElevenLabs Studio).

Delegates both the script and the audio to ElevenLabs' podcast generator:

1. ``POST /v1/studio/podcasts`` creates a *conversation* project from the
   newsletter content and auto-converts it.
2. The project is polled until the conversion finishes (Studio converts in a
   background queue).
3. The audio is downloaded from the latest project snapshot
   (``POST .../snapshots/{id}/stream``), which with the ``standard`` quality
   preset is MP3 at 128 kbps / 44.1 kHz — the same encoding as the classic
   engine, so jingles and RSS handling work unchanged.

The episode duration is estimated from the byte size at that constant bitrate.
"""

from __future__ import annotations

import asyncio

import httpx

from app.core.logging import get_logger
from app.domain.newsletter import Newsletter
from app.interfaces.podcast_producer import (
    PodcastProducer,
    PodcastProductionError,
    ProducedEpisode,
)
from app.interfaces.tts import SynthesizedAudio

logger = get_logger(__name__)

_API_ROOT = "https://api.elevenlabs.io/v1"
_CONTENT_TYPE = "audio/mpeg"
# `standard` quality preset: CBR 128 kbps -> 16000 bytes per second.
_MP3_BYTES_PER_SECOND = 128_000 / 8

_DEFAULT_INSTRUCTIONS = (
    "Podcast semanal en español sobre inteligencia artificial para una "
    "comunidad técnica de desarrolladores. Tono cercano, ágil y con humor, "
    "pero riguroso: cubre todas las noticias del material, sin inventar datos "
    "y sin hype vacío."
)


class GenFMPodcastProducer(PodcastProducer):
    """Produces the episode with ElevenLabs Studio's podcast generator."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        model_id: str = "eleven_multilingual_v2",
        host_voice_id: str,
        guest_voice_id: str,
        language: str = "es",
        target_minutes: int = 8,
        instructions: str | None = None,
        poll_seconds: float = 10.0,
        timeout_seconds: float = 900.0,
    ) -> None:
        if not api_key:
            raise ValueError("GenFMPodcastProducer requiere ELEVENLABS_API_KEY")
        self._client = client
        self._headers = {"xi-api-key": api_key}
        self._model_id = model_id
        self._host_voice_id = host_voice_id
        self._guest_voice_id = guest_voice_id
        self._language = language
        self._target_minutes = target_minutes
        self._instructions = instructions or _DEFAULT_INSTRUCTIONS
        self._poll_seconds = poll_seconds
        self._timeout_seconds = timeout_seconds

    async def produce(self, newsletter: Newsletter) -> ProducedEpisode:
        project_id = await self._create_project(newsletter)
        await self._wait_until_converted(project_id)
        data = await self._download_latest_snapshot(project_id)
        duration = max(1, round(len(data) / _MP3_BYTES_PER_SECOND))
        logger.info("genfm.produced", project=project_id, bytes=len(data), duration=duration)
        return ProducedEpisode(
            title=f"Anfaia Weekly AI · {newsletter.week_label}",
            audio=SynthesizedAudio(
                data=data,
                content_type=_CONTENT_TYPE,
                duration_seconds=duration,
                extension="mp3",
            ),
        )

    async def _create_project(self, newsletter: Newsletter) -> str:
        payload = {
            "model_id": self._model_id,
            "mode": {
                "type": "conversation",
                "conversation": {
                    "host_voice_id": self._host_voice_id,
                    "guest_voice_id": self._guest_voice_id,
                },
            },
            "source": {"type": "text", "text": self._source_text(newsletter)},
            "language": self._language,
            "quality_preset": "standard",
            "duration_scale": self._duration_scale(),
            "instructions_prompt": self._instructions,
        }
        response = await self._client.post(
            f"{_API_ROOT}/studio/podcasts", headers=self._headers, json=payload
        )
        if response.status_code != 200:
            raise PodcastProductionError(
                f"GenFM respondió {response.status_code} al crear el podcast: "
                f"{response.text[:300]}"
            )
        project = response.json().get("project") or {}
        project_id = project.get("project_id") or project.get("id")
        if not project_id:
            raise PodcastProductionError("GenFM no devolvió el id del proyecto")
        logger.info("genfm.project_created", project=project_id)
        return str(project_id)

    async def _wait_until_converted(self, project_id: str) -> None:
        attempts = max(1, int(self._timeout_seconds / self._poll_seconds))
        for _ in range(attempts):
            response = await self._client.get(
                f"{_API_ROOT}/studio/projects/{project_id}", headers=self._headers
            )
            if response.status_code != 200:
                raise PodcastProductionError(
                    f"GenFM respondió {response.status_code} al consultar el proyecto"
                )
            data = response.json()
            state = str(data.get("state", ""))
            if state == "default" and data.get("can_be_downloaded", True):
                return
            logger.info("genfm.converting", project=project_id, state=state)
            await asyncio.sleep(self._poll_seconds)
        raise PodcastProductionError(
            f"GenFM no terminó la conversión en {self._timeout_seconds:.0f}s "
            f"(proyecto {project_id})"
        )

    async def _download_latest_snapshot(self, project_id: str) -> bytes:
        response = await self._client.get(
            f"{_API_ROOT}/studio/projects/{project_id}/snapshots", headers=self._headers
        )
        if response.status_code != 200:
            raise PodcastProductionError(
                f"GenFM respondió {response.status_code} al listar snapshots"
            )
        snapshots = response.json().get("snapshots") or []
        if not snapshots:
            raise PodcastProductionError(f"El proyecto {project_id} no tiene snapshots")
        latest = snapshots[-1]
        snapshot_id = latest.get("project_snapshot_id") or latest.get("id")
        if not snapshot_id:
            raise PodcastProductionError("GenFM no devolvió el id del snapshot")

        audio = await self._client.post(
            f"{_API_ROOT}/studio/projects/{project_id}/snapshots/{snapshot_id}/stream",
            headers=self._headers,
            json={},
        )
        if audio.status_code != 200 or not audio.content:
            raise PodcastProductionError(
                f"GenFM respondió {audio.status_code} al descargar el audio"
            )
        return audio.content

    def _duration_scale(self) -> str:
        if self._target_minutes < 3:
            return "short"
        if self._target_minutes <= 7:
            return "default"
        return "long"

    @staticmethod
    def _source_text(newsletter: Newsletter) -> str:
        listing = "\n\n".join(
            f"{i}. [{entry.category.value}] {entry.edited.title}\n"
            f"   Qué ha pasado: {entry.edited.what_happened}\n"
            f"   Por qué importa: {entry.edited.why_it_matters}\n"
            f"   Cómo usarlo: {entry.edited.how_we_could_use_it}\n"
            f"   Limitaciones: {entry.edited.limitations}"
            for i, entry in enumerate(newsletter.entries, start=1)
        )
        return (
            f"Boletín semanal de IA: {newsletter.week_label}\n"
            f"Reflexión de conjunto: {newsletter.overview or '(sin reflexión)'}\n\n"
            f"Noticias de la semana:\n{listing}"
        )
