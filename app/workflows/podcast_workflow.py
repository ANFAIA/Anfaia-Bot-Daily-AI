"""Weekly podcast workflow.

Pipeline (runs after the newsletter is built, from the same selected stories):

    Produce episode (script + audio, via the configured engine) → Publish MP3
    → Record → Rebuild RSS feed → Announce on Discord

Every step after the audio is published is best-effort: a failure there is logged
but does not discard the episode. The whole workflow is itself best-effort from
the newsletter's point of view — if anything fails it returns ``None`` and the
newsletter is still published without an embedded player.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime

from app.core.logging import get_logger
from app.domain.newsletter import Newsletter
from app.domain.podcast import PodcastEpisode, PodcastReport
from app.interfaces.podcast_producer import PodcastProducer, PodcastProductionError
from app.interfaces.publisher import Publisher, PublisherError
from app.interfaces.repositories import NewsRepository, StoredPodcast
from app.interfaces.site_publisher import SitePublisher, SitePublisherError
from app.interfaces.tts import SynthesizedAudio, TTSError

logger = get_logger(__name__)

# Bitrate of the TTS output (and required for the jingles): CBR 128 kbps.
_MP3_BYTES_PER_SECOND = 128_000 / 8

# A jingle is either the audio bytes themselves (e.g. read from a local file)
# or an async source that retrieves them (e.g. an ElevenLabs download).
JingleSource = bytes | Callable[[], Awaitable[bytes | None]]


class PodcastWorkflow:
    """Builds and publishes the weekly podcast episode from a newsletter."""

    def __init__(
        self,
        *,
        producer: PodcastProducer,
        site_publisher: SitePublisher,
        publisher: Publisher,
        feed_renderer: Callable[[list[StoredPodcast]], str],
        repository: NewsRepository,
        path_prefix: str,
        intro_audio: JingleSource | None = None,
        outro_audio: JingleSource | None = None,
    ) -> None:
        self._producer = producer
        self._site_publisher = site_publisher
        self._publisher = publisher
        self._render_feed = feed_renderer
        self._repo = repository
        self._path_prefix = path_prefix.strip("/")
        self._intro_audio = intro_audio
        self._outro_audio = outro_audio

    async def run(self, newsletter: Newsletter) -> PodcastEpisode | None:
        """Generate, publish and announce the episode. Returns it, or None on failure."""
        report = PodcastReport(started_at=datetime.now(UTC))
        episode: PodcastEpisode | None = None
        try:
            episode = await self._run_pipeline(newsletter, report)
        except (TTSError, PodcastProductionError, SitePublisherError) as exc:
            logger.error("podcast.failed", error=str(exc))
            report.errors.append(str(exc))
        except Exception as exc:
            logger.exception("podcast.failed")
            report.errors.append(str(exc))
        finally:
            report.finished_at = datetime.now(UTC)
            logger.info(
                "podcast.finished",
                status="success" if report.succeeded else "failed",
                lines=report.script_lines,
                bytes=report.audio_bytes,
                url=report.audio_url,
            )
        return episode

    async def _run_pipeline(self, newsletter: Newsletter, report: PodcastReport) -> PodcastEpisode:
        # 1-2. Produce the episode (script + audio) with the configured engine
        # and add the intro/outro jingles when configured.
        produced = await self._producer.produce(newsletter)
        report.script_lines = produced.script_lines
        intro = await self._resolve_jingle(self._intro_audio, "intro")
        outro = await self._resolve_jingle(self._outro_audio, "outro")
        audio = self._with_branding(produced.audio, intro, outro)
        report.audio_bytes = len(audio.data)
        report.duration_seconds = audio.duration_seconds

        # 3. Publish the audio to the static host. This is the critical output.
        slug = f"{newsletter.iso_year}-W{newsletter.iso_week:02d}"
        audio_path = f"{self._path_prefix}/{slug}.{audio.extension}"
        published = await self._site_publisher.publish_bytes(
            path=audio_path,
            content=audio.data,
            content_type=audio.content_type,
            commit_message=f"Podcast IA · {newsletter.week_label}",
        )
        report.audio_url = published.public_url

        episode = PodcastEpisode(
            iso_year=newsletter.iso_year,
            iso_week=newsletter.iso_week,
            week_label=newsletter.week_label,
            title=produced.title,
            audio_url=published.public_url,
            page_url=published.public_url,
            duration_seconds=audio.duration_seconds,
            byte_size=len(audio.data),
            generated_at=newsletter.generated_at,
            summary=newsletter.overview,
        )

        # The audio is already live; persistence/feed/announcement are best-effort.
        # 4. Skip the announcement if this episode was already announced.
        already = False
        try:
            already = await self._repo.podcast_exists(newsletter.iso_year, newsletter.iso_week)
        except Exception as exc:
            logger.warning("podcast.exists_check_failed", error=str(exc))
            report.errors.append(f"No se pudo comprobar el registro previo: {exc}")

        # 5. Announce on Discord (non-fatal on failure).
        message_id: int | None = None
        if already:
            logger.info("podcast.already_announced", week=newsletter.week_label)
        else:
            try:
                message_id = await self._publisher.publish_podcast_announcement(
                    episode, episode.page_url
                )
                report.discord_message_id = message_id
            except PublisherError as exc:
                logger.error("podcast.announce_failed", error=str(exc))
                report.errors.append(f"No se pudo anunciar en Discord: {exc}")

        # 6. Persist the record (idempotent per ISO week; non-fatal on failure).
        try:
            await self._repo.save_podcast(episode, discord_message_id=message_id)
        except Exception as exc:
            logger.warning("podcast.record_failed", error=str(exc))
            report.errors.append(f"No se pudo registrar el podcast: {exc}")

        # 7. Rebuild and publish the RSS feed (non-fatal).
        await self._publish_feed(report)
        return episode

    @staticmethod
    async def _resolve_jingle(source: JingleSource | None, label: str) -> bytes | None:
        """Materialize a jingle source to bytes (best-effort, never fatal)."""
        if source is None or isinstance(source, bytes):
            return source
        try:
            return await source()
        except Exception as exc:
            logger.warning("podcast.jingle_failed", jingle=label, error=str(exc))
            return None

    @staticmethod
    def _with_branding(
        audio: SynthesizedAudio, intro: bytes | None, outro: bytes | None
    ) -> SynthesizedAudio:
        """Concatenate the intro/outro jingles around the episode (MP3 only).

        The jingles are byte-concatenated, which only yields a valid stream
        when everything shares the MP3 encoding of the TTS output; for other
        formats (e.g. Gemini's WAV) the episode is published as-is.
        """
        if intro is None and outro is None:
            return audio
        if audio.extension != "mp3":
            logger.warning("podcast.branding_skipped", extension=audio.extension)
            return audio
        data = b"".join(part for part in (intro, audio.data, outro) if part)
        extra_seconds = round((len(data) - len(audio.data)) / _MP3_BYTES_PER_SECOND)
        logger.info("podcast.branding_applied", extra_bytes=len(data) - len(audio.data))
        return replace(
            audio, data=data, duration_seconds=audio.duration_seconds + extra_seconds
        )

    async def _publish_feed(self, report: PodcastReport) -> None:
        """Regenerate feed.xml from the recorded episodes (best effort)."""
        try:
            episodes = await self._repo.list_podcasts()
            if not episodes:
                return  # nothing recorded (e.g. DB down): keep the existing feed
            feed_xml = self._render_feed(episodes)
            published = await self._site_publisher.publish_bytes(
                path=f"{self._path_prefix}/feed.xml",
                content=feed_xml.encode("utf-8"),
                content_type="application/rss+xml; charset=utf-8",
                commit_message="Feed RSS del podcast IA",
            )
            report.feed_url = published.public_url
        except Exception as exc:
            logger.warning("podcast.feed_failed", error=str(exc))
            report.errors.append(f"No se pudo actualizar el feed RSS: {exc}")
