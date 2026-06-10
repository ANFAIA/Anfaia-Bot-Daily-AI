"""Discord publishing adapter using discord.py.

Lifecycle strategy: for an occasional publishing task (one message a day) it is
not worth keeping a bot permanently connected. Each publication opens a client
session, waits for `on_ready`, sends the message, and closes. Sending is wrapped
in retries with exponential backoff.
"""

from __future__ import annotations

import asyncio

import discord
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.logging import get_logger
from app.domain.entities import PublishableArticle
from app.domain.newsletter import Newsletter
from app.domain.podcast import PodcastEpisode
from app.infrastructure.discord.embed_builder import (
    build_article_embed,
    build_newsletter_announcement_embed,
    build_podcast_announcement_embed,
)
from app.interfaces.publisher import Publisher, PublisherError

logger = get_logger(__name__)

# Hard ceiling for the whole login + send cycle. If the gateway is unreachable
# (no outbound WebSocket, blocked network) we fail fast with a clear message
# instead of hanging on discord.py's internal reconnection loop.
_CONNECT_TIMEOUT_SECONDS = 30.0


class DiscordPublisher(Publisher):
    """Publishes articles as embeds in a Discord channel."""

    def __init__(
        self,
        token: str,
        channel_id: int,
        *,
        newsletter_channel_id: int | None = None,
        podcast_channel_id: int | None = None,
    ) -> None:
        if not token or not channel_id:
            raise ValueError("DISCORD_TOKEN y DISCORD_CHANNEL_ID son obligatorios")
        self._token = token
        self._channel_id = channel_id
        # The newsletter goes to its own channel when configured; otherwise the main one.
        self._newsletter_channel_id = newsletter_channel_id or channel_id
        # The podcast falls back to the newsletter channel when not set explicitly.
        self._podcast_channel_id = podcast_channel_id or self._newsletter_channel_id

    async def _send(
        self,
        *,
        content: str | None = None,
        embed: discord.Embed | None = None,
        channel_id: int | None = None,
    ) -> int:
        """Open an ephemeral client session and send a message to the channel."""
        target_channel = channel_id or self._channel_id
        intents = discord.Intents.none()
        client = discord.Client(intents=intents)
        result: dict[str, int | Exception] = {}

        @client.event
        async def on_ready() -> None:
            try:
                channel = client.get_channel(target_channel) or await client.fetch_channel(
                    target_channel
                )
                if not isinstance(channel, discord.abc.Messageable):
                    raise PublisherError(f"El canal {target_channel} no admite mensajes")
                message = await channel.send(content=content, embed=embed)
                result["message_id"] = message.id
            except discord.Forbidden as exc:
                result["error"] = PublisherError(
                    f"El bot no tiene permisos en el canal {target_channel} "
                    f"(necesita Ver canal + Enviar mensajes + Insertar enlaces): {exc}"
                )
            except discord.NotFound as exc:
                result["error"] = PublisherError(
                    f"Canal {target_channel} no encontrado; revisa la configuración "
                    f"y que el bot esté en ese servidor: {exc}"
                )
            except Exception as exc:
                result["error"] = exc
            finally:
                await client.close()

        try:
            async with asyncio.timeout(_CONNECT_TIMEOUT_SECONDS):
                await client.start(self._token)
        except discord.LoginFailure as exc:
            raise PublisherError(
                f"Token de Discord inválido (revisa DISCORD_TOKEN): {exc}"
            ) from exc
        except TimeoutError as exc:
            await client.close()
            raise PublisherError(
                "Timeout conectando al gateway de Discord; revisa la conectividad "
                "de red saliente (wss://gateway.discord.gg) desde el contenedor"
            ) from exc
        except (discord.HTTPException, OSError) as exc:
            raise PublisherError(f"No se pudo conectar con Discord: {exc}") from exc

        if "error" in result:
            raise PublisherError(str(result["error"]))
        if "message_id" not in result:
            raise PublisherError("Discord cerró la sesión sin confirmar el envío")
        return int(result["message_id"])

    @retry(
        retry=retry_if_exception_type((discord.HTTPException, ConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        reraise=True,
    )
    async def publish(self, article: PublishableArticle) -> int:
        embed = build_article_embed(article)
        message_id = await self._send(embed=embed)
        logger.info("discord.published", message_id=message_id, title=article.edited.title)
        return message_id

    @retry(
        retry=retry_if_exception_type((discord.HTTPException, ConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        reraise=True,
    )
    async def publish_newsletter_announcement(self, newsletter: Newsletter, url: str) -> int:
        embed = build_newsletter_announcement_embed(newsletter, url)
        message_id = await self._send(embed=embed, channel_id=self._newsletter_channel_id)
        logger.info(
            "discord.newsletter_announced",
            message_id=message_id,
            url=url,
            channel_id=self._newsletter_channel_id,
        )
        return message_id

    @retry(
        retry=retry_if_exception_type((discord.HTTPException, ConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        reraise=True,
    )
    async def publish_podcast_announcement(self, episode: PodcastEpisode, url: str) -> int:
        embed = build_podcast_announcement_embed(episode, url)
        message_id = await self._send(embed=embed, channel_id=self._podcast_channel_id)
        logger.info(
            "discord.podcast_announced",
            message_id=message_id,
            url=url,
            channel_id=self._podcast_channel_id,
        )
        return message_id

    async def publish_test_message(self, text: str) -> int:
        message_id = await self._send(content=f"✅ Anfaia Daily AI · test\n{text}")
        logger.info("discord.test_published", message_id=message_id)
        return message_id
