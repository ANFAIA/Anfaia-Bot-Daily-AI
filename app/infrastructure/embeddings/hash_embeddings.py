"""Deterministic embeddings based on hashing (API-free fallback).

It does not capture deep semantics, but it is 100% offline and deterministic:
useful for local development, tests, and as a safety net when no API key is
available. It implements a "hashing trick" over normalized tokens, with L2
normalization of the vector.
"""

from __future__ import annotations

import hashlib
import math
import re

from app.interfaces.embeddings import EmbeddingProvider

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding via the hashing trick."""

    def __init__(self, dimension: int = 256) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        tokens = _TOKEN_RE.findall(text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0:
            return vector
        return [component / norm for component in vector]
