"""Tests for the weekly podcast workflow (orchestration + degradation)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from functools import partial
from zoneinfo import ZoneInfo

import pytest

from app.agents.podcast_scriptwriter import PodcastScriptwriterAgent
from app.domain.entities import DiscussionPrompt, EditedArticle, NewsItem
from app.domain.newsletter import Newsletter, NewsletterEntry
from app.domain.podcast import PodcastLine
from app.domain.value_objects import Category, RelevanceScore
from app.infrastructure.podcast.rss_renderer import PodcastFeedMeta, render_podcast_rss
from app.infrastructure.tts.null_tts import NullTTS
from app.interfaces.tts import SynthesizedAudio, TextToSpeechProvider
from app.workflows.podcast_workflow import PodcastWorkflow
from tests.conftest import BrokenLLM, FakePublisher, FakeSitePublisher

_VOICE_MAP = {"A": "va", "B": "vb"}


class FakeTTS(TextToSpeechProvider):
    """Returns deterministic audio and records the lines it was asked to speak."""

    def __init__(self) -> None:
        self.lines: list[PodcastLine] = []

    async def synthesize_dialogue(
        self, lines: Sequence[PodcastLine], voice_map: Mapping[str, str]
    ) -> SynthesizedAudio:
        self.lines = list(lines)
        return SynthesizedAudio(data=b"MP3DATA", content_type="audio/mpeg", duration_seconds=42)


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
    entry = NewsletterEntry(news_item=item, edited=edited, discussion=DiscussionPrompt("¿Y bien?"))
    return Newsletter(
        week_label="Semana del 1 al 7 de junio de 2026",
        iso_year=2026,
        iso_week=23,
        generated_at=datetime(2026, 6, 6, 9, 0, tzinfo=ZoneInfo("Europe/Madrid")),
        entries=(entry,),
        overview="Semana de agentes.",
    )


def _feed_renderer():
    meta = PodcastFeedMeta(
        title="Anfaia Weekly AI",
        description="d",
        author="Anfaia",
        language="es-ES",
        site_url="https://fake.github.io/newsbot",
        feed_url="https://fake.github.io/newsbot/podcast/feed.xml",
        image_url="https://anfaia.org/logo.png",
    )
    return partial(render_podcast_rss, meta=meta)


def _workflow(
    *, tts: TextToSpeechProvider, site: FakeSitePublisher, pub: FakePublisher, repo
) -> PodcastWorkflow:
    return PodcastWorkflow(
        scriptwriter=PodcastScriptwriterAgent(BrokenLLM()),  # uses the deterministic fallback
        tts=tts,
        site_publisher=site,
        publisher=pub,
        feed_renderer=_feed_renderer(),
        repository=repo,
        voice_map=_VOICE_MAP,
        path_prefix="podcast",
    )


async def test_happy_path_publishes_records_feed_and_announces(repository) -> None:
    tts, site, pub = FakeTTS(), FakeSitePublisher(), FakePublisher()
    episode = await _workflow(tts=tts, site=site, pub=pub, repo=repository).run(_newsletter())

    assert episode is not None
    assert episode.audio_url == "https://fake.github.io/newsbot/podcast/2026-W23.mp3"
    assert episode.byte_size == len(b"MP3DATA")
    assert episode.duration_seconds == 42

    # The MP3 and the RSS feed were both published as binary assets.
    paths = [path for path, _, _ in site.assets]
    assert "podcast/2026-W23.mp3" in paths
    assert "podcast/feed.xml" in paths
    mp3 = next(c for path, c, _ in site.assets if path.endswith(".mp3"))
    assert mp3 == b"MP3DATA"

    # Announced on Discord and recorded in the repository.
    assert len(pub.podcast_announcements) == 1
    assert await repository.podcast_exists(2026, 23)
    # intro + dialogue + outro were all sent to the TTS.
    assert tts.lines[0].speaker == "A"


async def test_returns_none_when_audio_publish_fails(repository) -> None:
    from tests.conftest import BrokenSitePublisher

    pub = FakePublisher()
    episode = await _workflow(
        tts=FakeTTS(), site=BrokenSitePublisher(), pub=pub, repo=repository
    ).run(_newsletter())

    assert episode is None
    assert pub.podcast_announcements == []
    assert not await repository.podcast_exists(2026, 23)


async def test_returns_none_when_tts_unconfigured(repository) -> None:
    episode = await _workflow(
        tts=NullTTS(), site=FakeSitePublisher(), pub=FakePublisher(), repo=repository
    ).run(_newsletter())
    assert episode is None


async def test_does_not_reannounce_when_already_recorded(repository) -> None:
    tts, site, pub = FakeTTS(), FakeSitePublisher(), FakePublisher()
    wf = _workflow(tts=tts, site=site, pub=pub, repo=repository)
    await wf.run(_newsletter())
    await wf.run(_newsletter())
    # Second run republishes the audio but skips the duplicate announcement.
    assert len(pub.podcast_announcements) == 1


@pytest.mark.parametrize("week", [1, 23])
async def test_audio_path_uses_iso_week(repository, week: int) -> None:
    nl = _newsletter()
    nl = Newsletter(
        week_label=nl.week_label,
        iso_year=nl.iso_year,
        iso_week=week,
        generated_at=nl.generated_at,
        entries=nl.entries,
        overview=nl.overview,
    )
    site = FakeSitePublisher()
    await _workflow(tts=FakeTTS(), site=site, pub=FakePublisher(), repo=repository).run(nl)
    assert any(path == f"podcast/{2026}-W{week:02d}.mp3" for path, _, _ in site.assets)
