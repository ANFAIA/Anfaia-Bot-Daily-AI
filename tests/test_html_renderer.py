"""Tests for the newsletter HTML renderer (format + XSS safety)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.entities import DiscussionPrompt, EditedArticle, NewsItem
from app.domain.newsletter import Newsletter, NewsletterEntry
from app.domain.value_objects import Category, RelevanceScore
from app.infrastructure.newsletter.html_renderer import (
    render_index_html,
    render_newsletter_html,
)
from app.interfaces.repositories import StoredNewsletter


def _entry(*, title: str, source_url: str = "https://example.com/x") -> NewsletterEntry:
    item = NewsItem(
        title=title, url=source_url, source="OpenAI Blog", summary="r"
    ).with_classification(Category.AGENTS, RelevanceScore(88))
    edited = EditedArticle(
        title=title,
        what_happened="Qué pasó.",
        why_it_matters="Por qué importa.",
        how_we_could_use_it="Cómo usarlo.",
        limitations="Límites.",
        source_url=source_url,
    )
    return NewsletterEntry(news_item=item, edited=edited, discussion=DiscussionPrompt("¿Y bien?"))


def _newsletter(entries) -> Newsletter:
    return Newsletter(
        week_label="Semana del 1 al 7 de junio de 2026",
        iso_year=2026,
        iso_week=23,
        generated_at=datetime(2026, 6, 6, 9, 0, tzinfo=ZoneInfo("Europe/Madrid")),
        entries=tuple(entries),
    )


def test_embeds_podcast_player_when_url_given() -> None:
    nl = _newsletter([_entry(title="Titular A")])
    url = "https://anfaia.github.io/newsletter/podcast/2026-W23.mp3"
    html = render_newsletter_html(nl, podcast_url=url)
    assert "<audio controls" in html
    assert url in html
    assert "Escucha el podcast" in html
    # Without a URL there is no player (boletín unchanged).
    assert "<audio" not in render_newsletter_html(nl)
    # An unsafe (non http/s) URL is not embedded.
    assert "<audio" not in render_newsletter_html(nl, podcast_url="javascript:alert(1)")


def test_renders_structure_and_branding() -> None:
    html = render_newsletter_html(
        _newsletter([_entry(title="Titular A"), _entry(title="Titular B")]),
        logo_url="https://anfaia.org/ANFAIA_logo_web.png",
    )
    assert "<!DOCTYPE html>" in html
    assert "Semana del 1 al 7 de junio de 2026" in html
    assert "Titular A" in html and "Titular B" in html
    # The five editorial sections + community question.
    for heading in (
        "Qué ha pasado",
        "Por qué importa",
        "Cómo podríamos usarlo",
        "Limitaciones o dudas",
        "Pregunta para la comunidad",
    ):
        assert heading in html
    # Anfaia branding: logo image + tagline.
    assert 'src="https://anfaia.org/ANFAIA_logo_web.png"' in html
    assert "Driving Progress with Artificial Intelligence" in html


def test_escapes_html_in_dynamic_content() -> None:
    html = render_newsletter_html(_newsletter([_entry(title="<script>alert(1)</script>")]))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_non_http_source_url_is_not_linked() -> None:
    html = render_newsletter_html(
        _newsletter([_entry(title="X", source_url="javascript:alert(1)")])
    )
    assert "javascript:alert(1)" not in html
    assert 'href="javascript:' not in html


def test_newsletter_has_back_to_index_button() -> None:
    html = render_newsletter_html(_newsletter([_entry(title="X")]), index_href="../index.html")
    assert 'class="backlink"' in html
    assert 'href="../index.html"' in html


def test_newsletter_shows_overview_when_present() -> None:
    nl = Newsletter(
        week_label="Semana del 1 al 7 de junio de 2026",
        iso_year=2026,
        iso_week=23,
        generated_at=datetime(2026, 6, 6, 9, 0, tzinfo=ZoneInfo("Europe/Madrid")),
        entries=(_entry(title="X"),),
        overview="Reflexión <de> la semana sobre agentes.",
    )
    html = render_newsletter_html(nl)
    # Shown and HTML-escaped.
    assert "Reflexión &lt;de&gt; la semana sobre agentes." in html


def _stored(year: int, week: int, url: str) -> StoredNewsletter:
    return StoredNewsletter(
        id=week,
        iso_year=year,
        iso_week=week,
        week_label=f"Semana {week} de {year}",
        public_url=url,
        item_count=5,
        generated_at=datetime(year, 6, 6, 9, 0, tzinfo=ZoneInfo("Europe/Madrid")),
        discord_message_id=None,
        created_at=datetime(year, 6, 6, 9, 0, tzinfo=ZoneInfo("Europe/Madrid")),
    )


def test_index_lists_each_edition() -> None:
    items = [
        _stored(2026, 23, "https://o.github.io/r/newsletters/2026-W23.html"),
        _stored(2026, 22, "https://o.github.io/r/newsletters/2026-W22.html"),
    ]
    html = render_index_html(items)
    assert "Semana 23 de 2026" in html and "Semana 22 de 2026" in html
    assert 'href="https://o.github.io/r/newsletters/2026-W23.html"' in html
    assert 'href="https://o.github.io/r/newsletters/2026-W22.html"' in html
    assert "Todas las ediciones" in html


def test_index_empty_state() -> None:
    html = render_index_html([])
    assert "Aún no hay boletines publicados" in html
