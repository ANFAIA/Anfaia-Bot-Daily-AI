"""LLM provider port.

Abstracts any language model backend (OpenAI, Anthropic, OpenRouter).
Agents depend on this interface, not on a concrete SDK, which allows switching
providers without touching the business logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A message in a conversation with the model."""

    role: str  # "system" | "user" | "assistant"
    content: str


class LLMProvider(ABC):
    """Contract for generating text from a conversation."""

    @abstractmethod
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> str:
        """Return the model's response as plain text."""

    async def complete_json(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """Return the model's response, forcing JSON output when possible.

        Default implementation: delegates to `complete`. Adapters that support
        native "JSON mode" may override it.
        """
        return await self.complete(messages, temperature=temperature, max_tokens=max_tokens)
