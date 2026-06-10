"""File-based cache for synthesized audio fragments.

Synthesis is the most expensive step of the podcast (one API call per line),
so re-running a week (e.g. after a failure halfway) should not pay for the
same lines again. Fragments are stored as files keyed by a content hash of
(model, format, voice, text); any change in those produces a different key.

The cache is strictly best-effort: a read or write failure degrades to a miss
and never breaks synthesis.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


class FileAudioCache:
    """Stores small audio blobs on disk, keyed by a SHA-256 content hash."""

    def __init__(self, directory: Path | str, *, extension: str = "mp3") -> None:
        self._dir = Path(directory)
        self._extension = extension

    @staticmethod
    def key(*parts: str) -> str:
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        try:
            if path.is_file():
                return path.read_bytes()
        except OSError as exc:
            logger.warning("tts_cache.read_failed", key=key, error=str(exc))
        return None

    def put(self, key: str, data: bytes) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._path(key).write_bytes(data)
        except OSError as exc:
            logger.warning("tts_cache.write_failed", key=key, error=str(exc))

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.{self._extension}"
