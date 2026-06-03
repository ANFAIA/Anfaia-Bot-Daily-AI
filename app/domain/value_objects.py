"""Domain value objects.

They are immutable and have no identity of their own: they represent business
concepts (a news item's category, a relevance score, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Category(StrEnum):
    """Categories into which a news item is classified."""

    AI = "AI"
    AGENTS = "Agents"
    ROBOTICS = "Robotics"
    OPEN_SOURCE = "Open Source"
    AUTOMATION = "Automation"
    RESEARCH = "Research"

    @classmethod
    def from_str(cls, raw: str) -> Category:
        """Normalize an arbitrary string (e.g. from an LLM) to a valid category."""
        normalized = raw.strip().lower().replace("_", " ")
        for member in cls:
            if member.value.lower() == normalized:
                return member
        # Common synonyms returned by the models.
        aliases = {
            "artificial intelligence": cls.AI,
            "ml": cls.RESEARCH,
            "machine learning": cls.RESEARCH,
            "agent": cls.AGENTS,
            "agentic": cls.AGENTS,
            "robots": cls.ROBOTICS,
            "robot": cls.ROBOTICS,
            "oss": cls.OPEN_SOURCE,
            "opensource": cls.OPEN_SOURCE,
        }
        return aliases.get(normalized, cls.AI)


@dataclass(frozen=True, slots=True)
class RelevanceScore:
    """Relevance score bounded to the range [0, 100]."""

    value: int

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 100:
            raise ValueError(f"RelevanceScore debe estar en [0, 100], recibido {self.value}")

    def is_at_least(self, threshold: int) -> bool:
        return self.value >= threshold

    @classmethod
    def clamped(cls, value: float) -> RelevanceScore:
        """Create a score by clamping the value to the valid range."""
        return cls(int(max(0, min(100, round(value)))))
