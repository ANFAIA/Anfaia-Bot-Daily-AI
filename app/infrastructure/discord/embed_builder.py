"""Builds the Discord embed from a publishable article.

Isolating rendering from sending allows testing the format without touching the
network and reusing it if other channels are published to in the future.
"""

from __future__ import annotations

import discord

from app.domain.category_colors import DEFAULT_COLOR, category_color
from app.domain.entities import PublishableArticle
from app.domain.newsletter import Newsletter

_MAX_FIELD = 1024  # Discord limit per embed field


def _field(value: str) -> str:
    value = value.strip() or "—"
    return value[: _MAX_FIELD - 1] + "…" if len(value) > _MAX_FIELD else value


def build_article_embed(article: PublishableArticle) -> discord.Embed:
    """Create the embed using the Anfaia Daily AI editorial format."""
    edited = article.edited
    color = category_color(article.category.value)

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


def build_newsletter_announcement_embed(newsletter: Newsletter, url: str) -> discord.Embed:
    """Create the embed announcing a published weekly newsletter."""
    if newsletter.overview.strip():
        intro = newsletter.overview.strip()
    else:
        intro = (
            f"Ya está disponible el resumen de las {newsletter.count} noticias de IA más "
            "relevantes de la semana, explicadas con el formato de siempre."
        )
    embed = discord.Embed(
        title=f"🗞️ Boletín semanal de IA · {newsletter.week_label}",
        url=url,
        description=f"{intro}\n\n👉 **[Leer el boletín completo]({url})**",
        color=DEFAULT_COLOR,
    )
    embed.set_author(name="Anfaia Weekly AI")
    # All headlines go in a single multiline field to respect Discord's field limits.
    headlines = "\n".join(f"{i}. {title}" for i, title in enumerate(newsletter.headlines, start=1))
    embed.add_field(name="En esta edición", value=_field(headlines), inline=False)
    embed.set_footer(
        text=f"{newsletter.count} noticias · {newsletter.generated_at.strftime('%d/%m/%Y')}"
    )
    return embed
