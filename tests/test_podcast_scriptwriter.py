"""Tests for the podcast scriptwriter agent (LLM parsing + fallback)."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.agents.podcast_scriptwriter import PodcastScriptwriterAgent
from app.domain.entities import DiscussionPrompt, EditedArticle, NewsItem
from app.domain.newsletter import Newsletter, NewsletterEntry
from app.domain.podcast import SPEAKER_A, SPEAKER_B
from app.domain.value_objects import Category, RelevanceScore
from app.interfaces.llm import ChatMessage, LLMProvider
from tests.conftest import BrokenLLM


def _newsletter() -> Newsletter:
    item = NewsItem(
        title="Nuevo framework de agentes",
        url="https://example.com/x",
        source="OpenAI",
        summary="r",
    ).with_classification(Category.AGENTS, RelevanceScore(88))
    edited = EditedArticle(
        title="Nuevo framework de agentes",
        what_happened="Salió un framework.",
        why_it_matters="Importa.",
        how_we_could_use_it="Úsalo.",
        limitations="Beta.",
        source_url="https://example.com/x",
    )
    entry = NewsletterEntry(news_item=item, edited=edited, discussion=DiscussionPrompt("¿Y bien?"))
    return Newsletter(
        week_label="Semana del 1 al 7 de junio de 2026",
        iso_year=2026,
        iso_week=23,
        generated_at=datetime(2026, 6, 6, 9, 0, tzinfo=ZoneInfo("Europe/Madrid")),
        entries=(entry,),
        overview="Semana de agentes.",
    )


class _ScriptLLM(LLMProvider):
    async def complete(self, messages, *, temperature=0.4, max_tokens=1024) -> str:
        return await self.complete_json(messages, temperature=temperature, max_tokens=max_tokens)

    async def complete_json(
        self, messages: list[ChatMessage], *, temperature=0.2, max_tokens=1024
    ) -> str:
        return json.dumps(
            {
                "title": "Episodio de prueba",
                "intro": "Bienvenidos.",
                "lines": [
                    {"speaker": "A", "text": "Hola, ¿qué tal la semana?"},
                    {"speaker": "B", "text": "Llena de agentes."},
                    {"speaker": "x", "text": "Turno con hablante inválido."},
                    {"speaker": "B", "text": ""},
                ],
                "outro": "Hasta la próxima.",
            }
        )


async def test_writes_script_from_llm() -> None:
    script = await PodcastScriptwriterAgent(_ScriptLLM()).run(_newsletter())
    assert script.title == "Episodio de prueba"
    assert script.intro == "Bienvenidos."
    # Empty line is dropped; the invalid speaker falls back to A.
    assert [(line.speaker, line.text) for line in script.lines] == [
        (SPEAKER_A, "Hola, ¿qué tal la semana?"),
        (SPEAKER_B, "Llena de agentes."),
        (SPEAKER_A, "Turno con hablante inválido."),
    ]
    # spoken_lines wraps the dialogue with intro/outro spoken by host A.
    spoken = script.spoken_lines
    assert spoken[0].speaker == SPEAKER_A and spoken[0].text == "Bienvenidos."
    assert spoken[-1].text == "Hasta la próxima."


async def test_falls_back_when_llm_fails() -> None:
    script = await PodcastScriptwriterAgent(BrokenLLM(), host_a="Lucía").run(_newsletter())
    # The fallback never raises and yields a usable, non-empty script.
    assert script.lines
    assert "Lucía" in script.intro
    assert script.word_count > 0
