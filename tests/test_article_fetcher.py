"""Tests for the best-effort article body fetcher."""

from __future__ import annotations

import httpx

from app.infrastructure.sources.article_fetcher import HttpArticleFetcher

_BODY = "El framework de agentes permite orquestar herramientas. " * 20

_PAGE = f"""
<html>
  <head><title>t</title><style>body {{ color: red }}</style></head>
  <body>
    <nav>Inicio | Noticias | Contacto</nav>
    <script>analytics();</script>
    <article><h1>Titular</h1><p>{_BODY}</p></article>
    <footer>Copyright</footer>
  </body>
</html>
"""


def _fetcher(handler, **kwargs) -> HttpArticleFetcher:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpArticleFetcher(client, **kwargs)


async def test_extracts_article_block() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_PAGE, headers={"content-type": "text/html"})

    text = await _fetcher(handler).fetch("https://e.com/a")
    assert text is not None
    assert "framework de agentes" in text
    assert "analytics" not in text  # scripts stripped
    assert "Contacto" not in text  # nav stripped (outside <article>)


async def test_truncates_to_max_chars() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_PAGE, headers={"content-type": "text/html"})

    text = await _fetcher(handler, max_chars=500).fetch("https://e.com/a")
    assert text is not None
    assert len(text) <= 500


async def test_returns_none_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    assert await _fetcher(handler).fetch("https://e.com/404") is None


async def test_returns_none_on_non_html() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})

    assert await _fetcher(handler).fetch("https://e.com/doc.pdf") is None


async def test_returns_none_when_too_short() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="<html><body>403</body></html>", headers={"content-type": "text/html"}
        )

    assert await _fetcher(handler).fetch("https://e.com/paywall") is None
