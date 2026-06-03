"""LLM adapter for the OpenAI API (Chat Completions).

Uses httpx directly to keep dependencies minimal and retain full control over
retries and timeouts. Also compatible with OpenRouter (same payload shape),
which is modeled as a subclass with a different base_url.
"""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging import get_logger
from app.interfaces.llm import ChatMessage, LLMProvider

logger = get_logger(__name__)


class OpenAILLMProvider(LLMProvider):
    """LLM provider compatible with the OpenAI Chat Completions API."""

    base_url = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: httpx.AsyncClient,
        base_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Se requiere API key para el proveedor LLM")
        self._api_key = api_key
        self._model = model
        self._client = client
        self._base_url = (base_url or self.base_url).rstrip("/")
        self._extra_headers = extra_headers or {}

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _post(self, payload: dict) -> dict:
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = await self._post(payload)
        return data["choices"][0]["message"]["content"].strip()

    async def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        data = await self._post(payload)
        return data["choices"][0]["message"]["content"].strip()


class OpenRouterLLMProvider(OpenAILLMProvider):
    """OpenRouter exposes an OpenAI-compatible API at a different base_url."""

    base_url = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, model: str, *, client: httpx.AsyncClient) -> None:
        super().__init__(
            api_key,
            model,
            client=client,
            extra_headers={
                "HTTP-Referer": "https://anfaia.dev",
                "X-Title": "Anfaia Daily AI",
            },
        )
