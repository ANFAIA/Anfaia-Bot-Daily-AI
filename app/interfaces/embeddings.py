"""Embedding provider port."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Generates vector representations of text for semantic similarity."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimension of the generated vectors."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return the embedding of a single text."""

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return the embeddings of several texts.

        Default sequential implementation; adapters can optimize by making a
        single batch call to the API.
        """
        return [await self.embed(text) for text in texts]
