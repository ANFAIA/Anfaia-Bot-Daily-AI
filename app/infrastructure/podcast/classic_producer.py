"""Classic podcast producer: local script + line-by-line TTS.

This is the original pipeline — the scriptwriter agent writes the two-host
dialogue from the newsletter and the configured TTS provider renders it line by
line. Kept behind the `PodcastProducer` port so it can be swapped for GenFM.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.agents.podcast_scriptwriter import PodcastScriptwriterAgent
from app.core.logging import get_logger
from app.domain.newsletter import Newsletter
from app.interfaces.podcast_producer import PodcastProducer, ProducedEpisode
from app.interfaces.tts import TextToSpeechProvider

logger = get_logger(__name__)


class ClassicPodcastProducer(PodcastProducer):
    """Scriptwriter agent + per-line TTS synthesis."""

    def __init__(
        self,
        *,
        scriptwriter: PodcastScriptwriterAgent,
        tts: TextToSpeechProvider,
        voice_map: Mapping[str, str],
    ) -> None:
        self._scriptwriter = scriptwriter
        self._tts = tts
        self._voice_map = dict(voice_map)

    async def produce(self, newsletter: Newsletter) -> ProducedEpisode:
        script = await self._scriptwriter.run(newsletter)
        audio = await self._tts.synthesize_dialogue(script.spoken_lines, self._voice_map)
        return ProducedEpisode(title=script.title, audio=audio, script=script)
