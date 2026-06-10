"""Generate a podcast episode locally WITHOUT publishing anything.

A dry run of the podcast pipeline: it builds a sample weekly newsletter and
produces the episode with the engine selected by PODCAST_ENGINE — `classic`
(scriptwriter agent + per-line TTS) or `genfm` (ElevenLabs Studio generates
script and audio) — then saves the audio (and the script, when the engine
exposes one) to disk. It NEVER touches GitHub Pages, Discord or the database.

Useful to preview the voices/script and compare engines before going live.

Usage:
    # full episode with the configured engine (spends TTS/GenFM credits)
    python scripts/test_podcast.py

    # only the classic script, no audio (no credits spent; ignores genfm)
    python scripts/test_podcast.py --script-only

    # custom output folder
    python scripts/test_podcast.py --out /tmp/podcast-test

Outputs (in ./out by default):
    podcast-test.txt   the dialogue script (classic engine only)
    podcast-test.mp3   the produced audio (unless --script-only)
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.container import Container
from app.domain.entities import DiscussionPrompt, EditedArticle, NewsItem
from app.domain.newsletter import Newsletter, NewsletterEntry
from app.domain.podcast import SPEAKER_A, SPEAKER_B, PodcastScript
from app.domain.value_objects import Category, RelevanceScore

# A small, representative newsletter so the script exercises several categories
# without needing the collection pipeline, sources or any API key to build it.
_SAMPLE = [
    (
        Category.AGENTS,
        92,
        "Un nuevo framework open source para orquestar agentes con tool-use",
        "Se ha publicado un framework que coordina varios agentes y llamadas a herramientas.",
        "Reduce el código repetitivo para construir sistemas multiagente fiables.",
        "Podríamos prototipar flujos de soporte o investigación automatizada.",
        "Aún es experimental y la documentación es escasa.",
    ),
    (
        Category.AI,
        85,
        "Un modelo de lenguaje compacto iguala a otros mucho mayores en razonamiento",
        "Un equipo presenta un modelo pequeño con resultados de razonamiento sobresalientes.",
        "Abarata el despliegue de IA capaz en hardware modesto.",
        "Sirve para asistentes locales sin depender de la nube.",
        "Los benchmarks no siempre reflejan el uso real.",
    ),
    (
        Category.ROBOTICS,
        78,
        "Robots humanoides aprenden tareas del hogar por imitación",
        "Una demo muestra humanoides que copian tareas domésticas observando vídeos.",
        "Acerca la robótica de propósito general a entornos cotidianos.",
        "Útil para explorar asistencia en logística o cuidados.",
        "El salto del laboratorio al mundo real sigue siendo enorme.",
    ),
]


def _sample_newsletter() -> Newsletter:
    now = datetime.now(ZoneInfo(get_settings().timezone))
    iso = now.isocalendar()
    entries = []
    for category, score, title, what, why, how, limits in _SAMPLE:
        item = NewsItem(
            title=title,
            url="https://example.com/noticia",
            source="Fuente de ejemplo",
            summary=what,
        ).with_classification(category, RelevanceScore(score))
        edited = EditedArticle(
            title=title,
            what_happened=what,
            why_it_matters=why,
            how_we_could_use_it=how,
            limitations=limits,
            source_url="https://example.com/noticia",
        )
        entries.append(
            NewsletterEntry(
                news_item=item,
                edited=edited,
                discussion=DiscussionPrompt("¿Cómo lo aplicarías en tu equipo?"),
            )
        )
    return Newsletter(
        week_label="Semana de prueba (dry run)",
        iso_year=iso.year,
        iso_week=iso.week,
        generated_at=now,
        entries=tuple(entries),
        overview=(
            "Semana de prueba: agentes que coordinan herramientas, modelos pequeños "
            "muy capaces y robótica que aprende por imitación."
        ),
    )


def _format_script(script: PodcastScript, host_a: str, host_b: str) -> str:
    names = {SPEAKER_A: host_a, SPEAKER_B: host_b}
    parts = [f"# {script.title}", ""]
    for line in script.spoken_lines:
        parts.append(f"{names.get(line.speaker, line.speaker)}: {line.text}")
    return "\n".join(parts) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba del podcast sin publicar nada")
    parser.add_argument(
        "--script-only", action="store_true", help="No sintetiza audio (no gasta créditos de TTS)"
    )
    parser.add_argument("--out", default="out", help="Carpeta de salida (por defecto: ./out)")
    args = parser.parse_args()

    settings = get_settings()
    out_dir = Path(args.out)
    await asyncio.to_thread(out_dir.mkdir, parents=True, exist_ok=True)

    container = Container(settings)
    try:
        newsletter = _sample_newsletter()

        if args.script_only:
            # Script preview without audio (always the classic scriptwriter:
            # GenFM does not separate script from audio).
            script = await container.scriptwriter_agent.run(newsletter)
            script_path = out_dir / "podcast-test.txt"
            await asyncio.to_thread(
                script_path.write_text,
                _format_script(
                    script, settings.podcast_voice_a_name, settings.podcast_voice_b_name
                ),
                encoding="utf-8",
            )
            print(f"📝 Guion: {len(script.spoken_lines)} turnos, {script.word_count} palabras")
            print(f"   → {script_path}")
            print("⏭️  --script-only: no se sintetiza audio.")
            return 0

        # Produce the full episode with the configured engine; nothing is published.
        producer = container.build_podcast_producer()
        print(f"🎙️  Motor: {settings.podcast_engine.value} ({type(producer).__name__})")
        if settings.podcast_engine.value == "genfm":
            print("   GenFM convierte en segundo plano; esto puede tardar unos minutos…")
        produced = await producer.produce(newsletter)

        if produced.script is not None:
            script_path = out_dir / "podcast-test.txt"
            await asyncio.to_thread(
                script_path.write_text,
                _format_script(
                    produced.script,
                    settings.podcast_voice_a_name,
                    settings.podcast_voice_b_name,
                ),
                encoding="utf-8",
            )
            print(f"📝 Guion: {produced.script_lines} turnos → {script_path}")

        audio = produced.audio
        audio_path = out_dir / f"podcast-test.{audio.extension}"
        await asyncio.to_thread(audio_path.write_bytes, audio.data)
        minutes, seconds = divmod(audio.duration_seconds, 60)
        print(f"🏷️  Título: {produced.title}")
        print(
            f"🎧 Audio: {len(audio.data) / 1024:.0f} KB, "
            f"~{minutes}:{seconds:02d} ({audio.content_type})"
        )
        print(f"   → {audio_path}")
        print("✅ Listo. Nada se ha publicado (ni GitHub Pages, ni Discord, ni BD).")
        return 0
    finally:
        await container.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
