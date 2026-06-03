"""Embedding adapter based on the OpenAI API."""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.interfaces.embeddings import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Generates embeddings with OpenAI's `text-embedding-*` models."""

    base_url = "https://api.openai.com/v1"

    def __init__(
        self, api_key: str, model: str, dimension: int, *, client: httpx.AsyncClient
    ) -> None:
        if not api_key:
            raise ValueError("Se requiere API key para embeddings de OpenAI")
        self._api_key = api_key
        self._model = model
        self._dimension = dimension
        self._client = client

    @property
    def dimension(self) -> int:
        return self._dimension

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _request(self, inputs: list[str]) -> list[list[float]]:
        response = await self._client.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self._model, "input": inputs, "dimensions": self._dimension},
        )
        response.raise_for_status()
        data = response.json()
        ordered = sorted(data["data"], key=lambda d: d["index"])
        return [item["embedding"] for item in ordered]

    async def embed(self, text: str) -> list[float]:
        return (await self._request([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._request(texts)
