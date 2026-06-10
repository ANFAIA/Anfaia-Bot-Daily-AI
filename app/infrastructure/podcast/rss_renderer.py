"""Renders the podcast RSS feed (RSS 2.0 + iTunes namespace).

A pure function (no I/O), trivially testable: it takes the recorded episodes
plus the channel metadata and returns a feed string that Spotify and Apple
Podcasts can ingest. Every dynamic value is XML-escaped, and each episode
exposes an ``<enclosure>`` pointing at its MP3.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from email.utils import format_datetime
from xml.sax.saxutils import escape, quoteattr

from app.interfaces.repositories import StoredPodcast

_ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"


@dataclass(frozen=True, slots=True)
class PodcastFeedMeta:
    """Channel-level metadata for the podcast feed."""

    title: str
    description: str
    author: str
    language: str
    site_url: str
    feed_url: str
    image_url: str
    email: str = ""
    category: str = "Technology"


def _duration_hms(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def _enclosure_type(audio_url: str) -> str:
    """MIME type for the enclosure, derived from the audio file extension."""
    lowered = audio_url.lower()
    if lowered.endswith(".wav"):
        return "audio/wav"
    if lowered.endswith((".m4a", ".aac")):
        return "audio/aac"
    if lowered.endswith(".ogg"):
        return "audio/ogg"
    return "audio/mpeg"


def _item(episode: StoredPodcast) -> str:
    title = escape(episode.title or episode.week_label)
    summary = escape(episode.summary or episode.week_label)
    page = episode.page_url or episode.audio_url
    pub_date = format_datetime(episode.generated_at)
    enclosure = (
        f"<enclosure url={quoteattr(episode.audio_url)} "
        f'length="{episode.byte_size}" type="{_enclosure_type(episode.audio_url)}"/>'
    )
    return f"""    <item>
      <title>{title}</title>
      <link>{escape(page)}</link>
      <guid isPermaLink="false">{escape(episode.audio_url)}</guid>
      <pubDate>{escape(pub_date)}</pubDate>
      <description>{summary}</description>
      <itunes:summary>{summary}</itunes:summary>
      <itunes:duration>{_duration_hms(episode.duration_seconds)}</itunes:duration>
      {enclosure}
    </item>"""


def render_podcast_rss(episodes: Iterable[StoredPodcast], *, meta: PodcastFeedMeta) -> str:
    """Render the podcast RSS feed for all recorded episodes."""
    items = "\n".join(_item(e) for e in episodes)
    owner = ""
    if meta.email:
        owner = (
            f"\n    <itunes:owner>\n      <itunes:name>{escape(meta.author)}</itunes:name>"
            f"\n      <itunes:email>{escape(meta.email)}</itunes:email>\n    </itunes:owner>"
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="{_ITUNES_NS}">
  <channel>
    <title>{escape(meta.title)}</title>
    <link>{escape(meta.site_url)}</link>
    <language>{escape(meta.language)}</language>
    <description>{escape(meta.description)}</description>
    <itunes:author>{escape(meta.author)}</itunes:author>
    <itunes:summary>{escape(meta.description)}</itunes:summary>
    <itunes:category text={quoteattr(meta.category)}/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:image href={quoteattr(meta.image_url)}/>{owner}
    <image>
      <url>{escape(meta.image_url)}</url>
      <title>{escape(meta.title)}</title>
      <link>{escape(meta.site_url)}</link>
    </image>
{items}
  </channel>
</rss>"""
