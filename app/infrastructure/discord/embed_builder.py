"""Builds the Discord embed from a publishable article.

Isolating rendering from sending allows testing the format without touching the
network and reusing it if other channels are published to in the future.
"""

from __future__ import annotations

import discord

from app.domain.entities import PublishableArticle

# Per-category colors (improve readability of the feed in Discord).
_CATEGORY_COLORS = {
    "AI": 0x5865F2,
    "Agents": 0x57F287,
    "Robotics": 0xEB459E,
    "Open Source": 0xFEE75C,
    "Automation": 0xED4245,
    "Research": 0x3498DB,
}

_MAX_FIELD = 1024  # Discord limit per embed field


def _field(value: str) -> str:
    value = value.strip() or "—"
    return value[: _MAX_FIELD - 1] + "…" if len(value) > _MAX_FIELD else value


def build_article_embed(article: PublishableArticle) -> discord.Embed:
    """Create the embed using the Anfaia Daily AI editorial format."""
    edited = article.edited
    color = _CATEGORY_COLORS.get(article.category.value, 0x5865F2)

    embed = discord.Embed(
        title=f"📰 {edited.title}",
        url=edited.source_url,
        color=color,
    )
    embed.set_author(name="Noticia IA del día · Anfaia Daily AI")
    embed.add_field(name="🔍 Qué ha pasado", value=_field(edited.what_happened), inline=False)
    embed.add_field(name="💡 Por qué importa", value=_field(edited.why_it_matters), inline=False)
    embed.add_field(
        name="🛠️ Cómo podríamos usarlo",
        value=_field(edited.how_we_could_use_it),
        inline=False,
    )
    embed.add_field(name="⚠️ Limitaciones o dudas", value=_field(edited.limitations), inline=False)
    embed.add_field(
        name="💬 Pregunta para la comunidad",
        value=_field(article.discussion.question),
        inline=False,
    )
    embed.add_field(name="🔗 Fuente", value=edited.source_url, inline=False)
    embed.set_footer(
        text=f"{article.category.value} · relevancia {article.relevance_score.value}/100 · "
        f"{article.news_item.source}"
    )
    return embed
