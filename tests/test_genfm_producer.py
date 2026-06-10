"""Tests for the GenFM (ElevenLabs Studio) podcast producer."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from app.domain.entities import DiscussionPrompt, EditedArticle, NewsItem
from app.domain.newsletter import Newsletter, NewsletterEntry
from app.domain.value_objects import Category, RelevanceScore
from app.infrastructure.podcast.genfm_producer import GenFMPodcastProducer
from app.interfaces.podcast_producer import PodcastProductionError

_CREATE_URL = "https://api.elevenlabs.io/v1/studio/podcasts"
_PROJECT_URL = "https://api.elevenlabs.io/v1/studio/projects/p1"
_SNAPSHOTS_URL = "https://api.elevenlabs.io/v1/studio/projects/p1/snapshots"
_STREAM_URL = "https://api.elevenlabs.io/v1/studio/projects/p1/snapshots/s1/stream"


def _newsletter() -> Newsletter:
    item = NewsItem(
        title="Noticia", url="https://example.com/x", source="OpenAI", summary="r"
    ).with_classification(Category.AGENTS, RelevanceScore(88))
    edited = EditedArticle(
        title="Noticia",
        what_happened="Pasó algo.",
        why_it_matters="Importa.",
        how_we_could_use_it="Úsalo.",
        limitations="Beta.",
        source_url="https://example.com/x",
    )
    entry = NewsletterEntry(news_item=item, edited=edited, discussion=DiscussionPrompt("¿Y?"))
    return Newsletter(
        week_label="Semana del 1 al 7 de junio de 2026",
        iso_year=2026,
        iso_week=23,
        generated_at=datetime(2026, 6, 6, 9, 0, tzinfo=ZoneInfo("Europe/Madrid")),
        entries=(entry,),
        overview="Semana de agentes.",
    )


def _producer(client: httpx.AsyncClient, **kwargs) -> GenFMPodcastProducer:
    defaults = {
        "api_key": "k",
        "host_voice_id": "va",
        "guest_voice_id": "vb",
        "target_minutes": 8,
        "poll_seconds": 0.01,
        "timeout_seconds": 1.0,
    }
    return GenFMPodcastProducer(client, **{**defaults, **kwargs})


@respx.mock
async def test_genfm_produces_episode() -> None:
    create = respx.post(_CREATE_URL).mock(
        return_value=httpx.Response(200, json={"project": {"project_id": "p1"}})
    )
    respx.get(_PROJECT_URL).mock(
        side_effect=[
            httpx.Response(200, json={"state": "converting"}),
            httpx.Response(200, json={"state": "default", "can_be_downloaded": True}),
        ]
    )
    respx.get(_SNAPSHOTS_URL).mock(
        return_value=httpx.Response(200, json={"snapshots": [{"project_snapshot_id": "s1"}]})
    )
    respx.post(_STREAM_URL).mock(return_value=httpx.Response(200, content=b"GENFM_MP3" * 4000))

    async with httpx.AsyncClient() as client:
        produced = await _producer(client).produce(_newsletter())

    assert produced.audio.data.startswith(b"GENFM_MP3")
    assert produced.audio.extension == "mp3"
    assert produced.audio.duration_seconds >= 1
    assert produced.script is None  # GenFM does not expose a local script
    assert "Semana del 1 al 7" in produced.title

    body = json.loads(create.calls.last.request.content)
    assert body["mode"] == {
        "type": "conversation",
        "conversation": {"host_voice_id": "va", "guest_voice_id": "vb"},
    }
    assert body["language"] == "es"
    assert body["duration_scale"] == "long"  # 8 target minutes -> long
    assert "Pasó algo." in body["source"]["text"]
    assert create.calls.last.request.headers["xi-api-key"] == "k"


@respx.mock
async def test_genfm_create_error_raises() -> None:
    respx.post(_CREATE_URL).mock(return_value=httpx.Response(422, text="bad request"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(PodcastProductionError):
            await _producer(client).produce(_newsletter())


@respx.mock
async def test_genfm_conversion_timeout_raises() -> None:
    respx.post(_CREATE_URL).mock(
        return_value=httpx.Response(200, json={"project": {"project_id": "p1"}})
    )
    respx.get(_PROJECT_URL).mock(return_value=httpx.Response(200, json={"state": "converting"}))
    async with httpx.AsyncClient() as client:
        with pytest.raises(PodcastProductionError, match="no terminó"):
            await _producer(client, timeout_seconds=0.03).produce(_newsletter())


@respx.mock
async def test_genfm_missing_snapshots_raises() -> None:
    respx.post(_CREATE_URL).mock(
        return_value=httpx.Response(200, json={"project": {"project_id": "p1"}})
    )
    respx.get(_PROJECT_URL).mock(
        return_value=httpx.Response(200, json={"state": "default", "can_be_downloaded": True})
    )
    respx.get(_SNAPSHOTS_URL).mock(return_value=httpx.Response(200, json={"snapshots": []}))
    async with httpx.AsyncClient() as client:
        with pytest.raises(PodcastProductionError, match="snapshots"):
            await _producer(client).produce(_newsletter())


def test_duration_scale_buckets() -> None:
    client = httpx.AsyncClient()
    assert _producer(client, target_minutes=2)._duration_scale() == "short"
    assert _producer(client, target_minutes=5)._duration_scale() == "default"
    assert _producer(client, target_minutes=8)._duration_scale() == "long"
