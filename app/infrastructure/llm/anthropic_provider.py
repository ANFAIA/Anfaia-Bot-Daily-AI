"""LLM adapter for the Anthropic API (Messages)."""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging import get_logger
from app.interfaces.llm import ChatMessage, LLMProvider

logger = get_logger(__name__)

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicLLMProvider(LLMProvider):
    """LLM provider based on the Anthropic Messages API."""

    base_url = "https://api.anthropic.com/v1"

    def __init__(self, api_key: str, model: str, *, client: httpx.AsyncClient) -> None:
        if not api_key:
            raise ValueError("Se requiere API key para Anthropic")
        self._api_key = api_key
        self._model = model
        self._client = client

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _split_system(messages: list[ChatMessage]) -> tuple[str | None, list[dict]]:
        """Anthropic receives the system prompt in a separate field."""
        system_parts = [m.content for m in messages if m.role == "system"]
        convo = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        system = "\n\n".join(system_parts) if system_parts else None
        return system, convo

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> str:
        system, convo = self._split_system(messages)
        payload: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": convo,
        }
        if system:
            payload["system"] = system

        response = await self._client.post(
            f"{self.base_url}/messages",
            headers=self._headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return "".join(
            block["text"] for block in data["content"] if block.get("type") == "text"
        ).strip()
