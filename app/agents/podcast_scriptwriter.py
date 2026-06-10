"""Agent — Podcast Scriptwriter.

Turns the week's `Newsletter` into a two-host dialogue (`PodcastScript`) that a
text-to-speech provider can render to audio. Uses the LLM and, if it fails,
falls back to a simple alternating script built from the entries so it never
blocks the episode.
"""

from __future__ import annotations

from app.agents.json_utils import extract_json_object
from app.agents.prompts import PODCAST_SCRIPT_SYSTEM
from app.core.logging import get_logger
from app.domain.newsletter import Newsletter
from app.domain.podcast import SPEAKER_A, SPEAKER_B, PodcastLine, PodcastScript
from app.interfaces.agent import Agent
from app.interfaces.llm import ChatMessage, LLMProvider

logger = get_logger(__name__)


class PodcastScriptwriterAgent(Agent[Newsletter, PodcastScript]):
    """Writes a two-host conversational script from the weekly newsletter."""

    name = "podcast_scriptwriter"

    def __init__(
        self,
        llm: LLMProvider,
        *,
        host_a: str = "Lucía",
        host_b: str = "Mateo",
        target_minutes: int = 8,
    ) -> None:
        self._llm = llm
        self._host_a = host_a
        self._host_b = host_b
        self._target_minutes = max(2, target_minutes)

    async def run(self, input_data: Newsletter) -> PodcastScript:
        try:
            return await self._write_with_llm(input_data)
        except Exception as exc:
            logger.warning("podcast_scriptwriter.llm_failed", error=str(exc))
            return self._fallback(input_data)

    async def _write_with_llm(self, newsletter: Newsletter) -> PodcastScript:
        system = PODCAST_SCRIPT_SYSTEM.format(
            host_a=self._host_a, host_b=self._host_b, target_minutes=self._target_minutes
        )
        listing = "\n\n".join(
            f"{i}. [{entry.category.value}] {entry.edited.title}\n"
            f"   Qué ha pasado: {entry.edited.what_happened}\n"
            f"   Por qué importa: {entry.edited.why_it_matters}\n"
            f"   Cómo usarlo: {entry.edited.how_we_could_use_it}\n"
            f"   Limitaciones: {entry.edited.limitations}"
            for i, entry in enumerate(newsletter.entries, start=1)
        )
        user = (
            f"Boletín: {newsletter.week_label}\n"
            f"Reflexión de conjunto: {newsletter.overview or '(sin reflexión)'}\n\n"
            f"Noticias de la semana:\n{listing}"
        )
        raw = await self._llm.complete_json(
            [
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=user),
            ],
            temperature=0.7,
            max_tokens=4000,
        )
        data = extract_json_object(raw)
        lines = self._parse_lines(data.get("lines"))
        if not lines:
            raise ValueError("El LLM no devolvió líneas de diálogo")
        script = PodcastScript(
            title=str(data.get("title") or f"Anfaia Weekly AI · {newsletter.week_label}").strip(),
            intro=str(data.get("intro", "")).strip(),
            lines=lines,
            outro=str(data.get("outro", "")).strip(),
        )
        logger.info("podcast_scriptwriter.written", lines=len(lines), words=script.word_count)
        return script

    @staticmethod
    def _parse_lines(raw_lines: object) -> tuple[PodcastLine, ...]:
        if not isinstance(raw_lines, list):
            return ()
        parsed: list[PodcastLine] = []
        for item in raw_lines:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            speaker = str(item.get("speaker", "")).strip().upper()
            speaker = SPEAKER_B if speaker == SPEAKER_B else SPEAKER_A
            parsed.append(PodcastLine(speaker=speaker, text=text))
        return tuple(parsed)

    def _fallback(self, newsletter: Newsletter) -> PodcastScript:
        intro = (
            f"Bienvenidos a Anfaia Weekly AI. Soy {self._host_a} y hoy repasamos con "
            f"{self._host_b} las noticias de IA de la semana."
        )
        lines: list[PodcastLine] = []
        if newsletter.overview.strip():
            lines.append(PodcastLine(speaker=SPEAKER_B, text=newsletter.overview.strip()))
        for i, entry in enumerate(newsletter.entries, start=1):
            speaker = SPEAKER_A if i % 2 else SPEAKER_B
            lines.append(
                PodcastLine(
                    speaker=speaker,
                    text=f"{entry.edited.title}. {entry.edited.what_happened} "
                    f"{entry.edited.why_it_matters}",
                )
            )
        outro = f"Y hasta aquí el episodio de esta semana. Soy {self._host_a}, ¡hasta la próxima!"
        return PodcastScript(
            title=f"Anfaia Weekly AI · {newsletter.week_label}",
            intro=intro,
            lines=tuple(lines),
            outro=outro,
        )
