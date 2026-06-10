"""Tests for the podcast RSS feed renderer."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from app.infrastructure.podcast.rss_renderer import PodcastFeedMeta, render_podcast_rss
from app.interfaces.repositories import StoredPodcast

_ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def _meta() -> PodcastFeedMeta:
    return PodcastFeedMeta(
        title="Anfaia Weekly AI",
        description="Resumen semanal",
        author="Anfaia",
        language="es-ES",
        site_url="https://anfaia.github.io/newsletter",
        feed_url="https://anfaia.github.io/newsletter/podcast/feed.xml",
        image_url="https://anfaia.org/logo.png",
        email="podcast@anfaia.org",
    )


def _episode(week: int = 23) -> StoredPodcast:
    return StoredPodcast(
        id=week,
        iso_year=2026,
        iso_week=week,
        week_label=f"Semana {week}",
        title=f"Episodio {week}",
        audio_url=f"https://anfaia.github.io/newsletter/podcast/2026-W{week}.mp3",
        page_url=f"https://anfaia.github.io/newsletter/newsletters/2026-W{week}.html",
        duration_seconds=3725,  # 1:02:05
        byte_size=987654,
        summary="Resumen del episodio",
        generated_at=datetime(2026, 6, 6, 9, 0, tzinfo=ZoneInfo("Europe/Madrid")),
        discord_message_id=None,
        created_at=datetime(2026, 6, 6, 9, 0, tzinfo=ZoneInfo("Europe/Madrid")),
    )


def test_renders_valid_rss_with_enclosure_and_duration() -> None:
    xml = render_podcast_rss([_episode(23), _episode(22)], meta=_meta())
    root = ElementTree.fromstring(xml)  # parses => well-formed XML

    channel = root.find("channel")
    assert channel is not None
    assert channel.findtext("title") == "Anfaia Weekly AI"
    assert channel.findtext("language") == "es-ES"

    items = channel.findall("item")
    assert len(items) == 2

    first = items[0]
    enclosure = first.find("enclosure")
    assert enclosure is not None
    assert enclosure.attrib["url"].endswith("2026-W23.mp3")
    assert enclosure.attrib["type"] == "audio/mpeg"
    assert enclosure.attrib["length"] == "987654"
    # HH:MM:SS for an over-an-hour episode.
    assert first.findtext(f"{_ITUNES}duration") == "1:02:05"


def test_enclosure_type_follows_audio_extension() -> None:
    wav = replace(
        _episode(),
        audio_url="https://anfaia.github.io/newsletter/podcast/2026-W23.wav",
    )
    xml = render_podcast_rss([wav], meta=_meta())
    enclosure = ElementTree.fromstring(xml).find("channel/item/enclosure")
    assert enclosure is not None
    assert enclosure.attrib["type"] == "audio/wav"


def test_escapes_special_characters() -> None:
    bad = replace(_episode(), title="A & B <x>")
    xml = render_podcast_rss([bad], meta=_meta())
    assert "A & B <x>" not in xml
    assert "A &amp; B &lt;x&gt;" in xml
    ElementTree.fromstring(xml)  # still well-formed
