"""Download audio assets (e.g. podcast jingles) from the ElevenLabs history.

Any track generated with ElevenLabs (including Eleven Music) is stored in the
account history and can be downloaded by its history item id via
``GET /v1/history/{history_item_id}/audio``. The download is cached on disk so
the weekly run does not re-fetch the same jingle, and it is best-effort: on any
failure it returns None and the episode is published without the jingle.
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger
from app.infrastructure.tts.cache import FileAudioCache

logger = get_logger(__name__)

_API_ROOT = "https://api.elevenlabs.io/v1"


async def fetch_history_audio(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    history_item_id: str,
    cache: FileAudioCache | None = None,
) -> bytes | None:
    """Return the audio bytes of an ElevenLabs history item, or None on failure."""
    key = FileAudioCache.key("elevenlabs-history", history_item_id)
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return cached

    try:
        response = await client.get(
            f"{_API_ROOT}/history/{history_item_id}/audio",
            headers={"xi-api-key": api_key},
        )
    except httpx.HTTPError as exc:
        logger.warning("elevenlabs_asset.fetch_failed", item=history_item_id, error=str(exc))
        return None
    if response.status_code != 200:
        logger.warning(
            "elevenlabs_asset.fetch_failed",
            item=history_item_id,
            status=response.status_code,
            body=response.text[:200],
        )
        return None

    logger.info("elevenlabs_asset.fetched", item=history_item_id, bytes=len(response.content))
    if cache is not None:
        cache.put(key, response.content)
    return response.content
