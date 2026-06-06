"""Per-category accent colors, shared across output channels.

Centralized so the Discord embed and the HTML newsletter use the exact same
color for a given category, keeping the brand consistent across surfaces.
"""

from __future__ import annotations

# Per-category colors as integers (the form `discord.Embed(color=...)` expects).
CATEGORY_COLORS: dict[str, int] = {
    "AI": 0x2563EB,  # blue-600 (Anfaia primary)
    "Agents": 0x6366F1,  # indigo-500
    "Robotics": 0xEB459E,  # pink
    "Open Source": 0x16A34A,  # green-600
    "Automation": 0xF59E0B,  # amber-500
    "Research": 0x4338CA,  # indigo-700
}

# Fallback when a category has no explicit color (Anfaia primary blue).
DEFAULT_COLOR = 0x2563EB


def category_color(category_value: str) -> int:
    """Return the integer color for a category value, or the default."""
    return CATEGORY_COLORS.get(category_value, DEFAULT_COLOR)


def category_css_hex(category_value: str) -> str:
    """Return the category color as a CSS hex string (e.g. ``#2563eb``)."""
    return f"#{category_color(category_value):06x}"
