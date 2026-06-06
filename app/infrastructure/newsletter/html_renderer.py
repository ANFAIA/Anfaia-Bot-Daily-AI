"""Renders the newsletter pages to self-contained HTML (Anfaia branding).

Two pages share the same look (anfaia.org: Inter typeface, blue/indigo palette,
white soft-shadowed cards):

- A weekly newsletter page: the selected stories, each explained with the exact
  same editorial format as the daily Discord post (five sections + community
  question), plus a "back to index" button.
- An index page: links to every published weekly newsletter.

Both are pure functions (no I/O), trivially testable. Every dynamic value is
escaped with `html.escape`, and links are only rendered as anchors when their
scheme is http(s) — preventing stored/LLM content from injecting markup or
`javascript:` URLs (XSS).
"""

from __future__ import annotations

from collections.abc import Iterable
from html import escape

from app.domain.category_colors import category_css_hex
from app.domain.newsletter import Newsletter, NewsletterEntry
from app.interfaces.repositories import StoredNewsletter

DEFAULT_LOGO_URL = "https://anfaia.org/ANFAIA_logo_web.png"
DEFAULT_INDEX_HREF = "../index.html"
_ORG_NAME = "Asociación Nacional Faro, para la Aceleración de la Inteligencia Artificial"
_TAGLINE = "Driving Progress with Artificial Intelligence"
_SITE_URL = "https://anfaia.org"

# (emoji, heading, attribute) for each editorial section, mirroring the Discord embed.
_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("🔍", "Qué ha pasado", "what_happened"),
    ("💡", "Por qué importa", "why_it_matters"),
    ("🛠️", "Cómo podríamos usarlo", "how_we_could_use_it"),
    ("⚠️", "Limitaciones o dudas", "limitations"),
)

_STYLES = """<style>
    :root {
      --blue-50:#eff6ff; --blue-100:#dbeafe; --blue-500:#3b82f6; --blue-600:#2563eb;
      --blue-700:#1d4ed8; --blue-900:#1e3a8a; --indigo-600:#4f46e5;
      --slate-900:#0f172a; --gray-700:#374151; --gray-500:#6b7280; --gray-200:#e5e7eb;
    }
    * { box-sizing: border-box; }
    body {
      margin:0; background:var(--blue-50); color:var(--slate-900);
      font-family:'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif;
      line-height:1.6; -webkit-font-smoothing:antialiased;
    }
    a { color:var(--blue-700); }
    .wrap { position:relative; z-index:1; max-width:820px; margin:0 auto; padding:0 20px 64px; }
    header.hero {
      position:relative;
      background:linear-gradient(135deg, var(--blue-700) 0%, var(--indigo-600) 100%);
      color:#fff; padding:40px 20px 48px; text-align:center;
    }
    .hero .backlink {
      position:absolute; left:16px; top:16px; background:rgba(255,255,255,.15); color:#fff;
      text-decoration:none; font-size:.85rem; font-weight:600; padding:6px 12px;
      border-radius:999px;
    }
    .hero .backlink:hover { background:rgba(255,255,255,.28); }
    .hero .brand { display:flex; justify-content:center; margin-bottom:12px; }
    .hero .logo { height:72px; background:#fff; border-radius:14px; padding:10px 16px; }
    .hero .tagline { opacity:.85; font-size:.9rem; font-weight:500; margin-bottom:6px; }
    .hero h1 { font-size:2rem; font-weight:800; margin:8px 0 6px; letter-spacing:-.02em; }
    .hero .sub { opacity:.9; font-weight:500; }
    .intro {
      background:#fff; border:1px solid var(--gray-200); border-radius:16px;
      padding:18px 22px; margin:-28px auto 28px; box-shadow:0 10px 30px rgba(30,58,138,.10);
      color:var(--gray-700); font-weight:500;
    }
    .card {
      background:#fff; border:1px solid var(--gray-200); border-left:5px solid var(--accent);
      border-radius:16px; padding:24px 26px; margin:0 0 22px;
      box-shadow:0 6px 20px rgba(15,23,42,.06);
    }
    .card-head { display:flex; align-items:center; gap:10px; margin-bottom:6px; }
    .badge {
      background:var(--accent); color:#fff; font-size:.72rem; font-weight:700;
      text-transform:uppercase; letter-spacing:.04em; padding:3px 10px; border-radius:999px;
    }
    .rank { color:var(--gray-500); font-size:.78rem; font-weight:600; }
    .card-title {
      font-size:1.3rem; font-weight:700; line-height:1.3; margin:6px 0 16px; letter-spacing:-.01em;
    }
    .card-title a { color:var(--slate-900); text-decoration:none; }
    .card-title a:hover { color:var(--blue-700); }
    .card-title .num { color:var(--accent); }
    .section { margin:14px 0; }
    .section h3 { font-size:.95rem; font-weight:700; margin:0 0 4px; color:var(--blue-900); }
    .section p { margin:0; color:var(--gray-700); }
    .section.question {
      background:var(--blue-50); border-radius:12px; padding:14px 16px; margin-top:18px;
    }
    .section.question h3 { color:var(--blue-700); }
    .card-foot {
      margin-top:16px; padding-top:14px; border-top:1px solid var(--gray-200); font-size:.85rem;
    }
    .source { color:var(--blue-700); font-weight:600; text-decoration:none; }
    .editions { display:flex; flex-direction:column; gap:12px; margin-top:24px; }
    .edition {
      display:flex; align-items:center; gap:12px; background:#fff; border:1px solid var(--gray-200);
      border-left:5px solid var(--blue-600); border-radius:14px; padding:16px 20px;
      text-decoration:none; color:var(--slate-900); box-shadow:0 6px 20px rgba(15,23,42,.06);
    }
    .edition:hover { border-left-color:var(--indigo-600); }
    .edition-week { font-weight:700; flex:1; }
    .edition-meta { color:var(--gray-500); font-size:.85rem; }
    .edition-go { color:var(--blue-700); font-weight:700; }
    .empty { text-align:center; color:var(--gray-500); margin-top:32px; }
    footer { text-align:center; color:var(--gray-500); font-size:.82rem; padding:8px 20px; }
    footer .org { font-weight:600; color:var(--gray-700); }
    footer a { color:var(--blue-700); text-decoration:none; }
    @media (max-width:520px) { .hero h1 { font-size:1.6rem; } .card { padding:20px; } }
  </style>"""


def _safe_link(url: str) -> str | None:
    """Return the URL if it is a safe http(s) link, else None."""
    cleaned = url.strip()
    if cleaned.lower().startswith(("http://", "https://")):
        return cleaned
    return None


def _document(*, title: str, hero_sub: str, logo_url: str, body: str, top_link: str = "") -> str:
    """Assemble a full HTML document with the shared Anfaia header and body."""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="index, follow">
  <title>{escape(title)}</title>
  <link rel="icon" href="{escape(_SITE_URL)}/favicon.ico">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap">
  {_STYLES}
</head>
<body>
  <header class="hero">
    {top_link}
    <div class="brand">
      <img class="logo" src="{escape(logo_url)}" alt="Anfaia">
    </div>
    <div class="tagline">{escape(_TAGLINE)}</div>
    <h1>Boletín de Anfaia sobre noticias de IA</h1>
    <div class="sub">{escape(hero_sub)}</div>
  </header>
  <div class="wrap">
{body}
  </div>
</body>
</html>"""


def _footer(last_line: str) -> str:
    return f"""    <footer>
      <p class="org">{escape(_ORG_NAME)}</p>
      <p>{last_line}</p>
    </footer>"""


def _render_entry(entry: NewsletterEntry, index: int) -> str:
    edited = entry.edited
    accent = category_css_hex(entry.category.value)
    title = escape(edited.title)

    link = _safe_link(edited.source_url)
    if link:
        title_html = f'<a href="{escape(link)}" target="_blank" rel="noopener">{title}</a>'
        source_html = (
            f'<a class="source" href="{escape(link)}" target="_blank" rel="noopener">'
            f"🔗 {escape(entry.news_item.source)}</a>"
        )
    else:
        title_html = title
        source_html = f'<span class="source">🔗 {escape(entry.news_item.source)}</span>'

    sections = "".join(
        f'<div class="section"><h3>{emoji} {escape(heading)}</h3>'
        f"<p>{escape(getattr(edited, attr) or '—')}</p></div>"
        for emoji, heading, attr in _SECTIONS
    )

    return f"""
    <article class="card" style="--accent: {accent}">
      <div class="card-head">
        <span class="badge">{escape(entry.category.value)}</span>
        <span class="rank">relevancia {entry.relevance_score.value}/100</span>
      </div>
      <h2 class="card-title"><span class="num">{index}.</span> {title_html}</h2>
      {sections}
      <div class="section question">
        <h3>💬 Pregunta para la comunidad</h3>
        <p>{escape(entry.discussion.question or '—')}</p>
      </div>
      <div class="card-foot">{source_html}</div>
    </article>"""


def render_newsletter_html(
    newsletter: Newsletter,
    *,
    logo_url: str = DEFAULT_LOGO_URL,
    index_href: str = DEFAULT_INDEX_HREF,
) -> str:
    """Render a weekly newsletter as a complete, self-contained HTML document."""
    cards = "".join(_render_entry(e, i) for i, e in enumerate(newsletter.entries, start=1))
    generated = escape(newsletter.generated_at.strftime("%d/%m/%Y %H:%M"))
    top_link = f'<a class="backlink" href="{escape(index_href)}">← Índice</a>'
    if newsletter.overview.strip():
        intro_text = escape(newsletter.overview.strip())
    else:
        intro_text = (
            f"Resumen de las {newsletter.count} noticias de inteligencia artificial más "
            "relevantes de la semana, explicadas con el mismo criterio que la noticia "
            "diaria de Anfaia."
        )
    intro = f'    <div class="intro">{intro_text}</div>'
    footer = _footer(
        f'Generado el {generated} · '
        f'<a href="{escape(_SITE_URL)}" target="_blank" rel="noopener">anfaia.org</a> · '
        f"Anfaia Weekly AI"
    )
    body = f"{intro}\n    {cards}\n{footer}"
    return _document(
        title=f"{newsletter.week_label} · Anfaia Weekly AI",
        hero_sub=newsletter.week_label,
        logo_url=logo_url,
        body=body,
        top_link=top_link,
    )


def _render_edition(item: StoredNewsletter) -> str:
    link = _safe_link(item.public_url)
    href = escape(link) if link else "#"
    date = escape(item.generated_at.strftime("%d/%m/%Y"))
    return (
        f'      <a class="edition" href="{href}">\n'
        f'        <span class="edition-week">{escape(item.week_label)}</span>\n'
        f'        <span class="edition-meta">{item.item_count} noticias · {date}</span>\n'
        f'        <span class="edition-go">Leer →</span>\n'
        f"      </a>"
    )


def render_index_html(
    newsletters: Iterable[StoredNewsletter], *, logo_url: str = DEFAULT_LOGO_URL
) -> str:
    """Render the index page linking to every published weekly newsletter."""
    items = list(newsletters)
    if items:
        editions = "\n".join(_render_edition(n) for n in items)
        body_inner = f'    <div class="editions">\n{editions}\n    </div>'
    else:
        body_inner = '    <p class="empty">Aún no hay boletines publicados.</p>'
    footer = _footer(
        f'<a href="{escape(_SITE_URL)}" target="_blank" rel="noopener">anfaia.org</a> · '
        f"Anfaia Weekly AI"
    )
    body = f"{body_inner}\n{footer}"
    return _document(
        title="Boletines de Anfaia sobre IA",
        hero_sub="Todas las ediciones",
        logo_url=logo_url,
        body=body,
    )
