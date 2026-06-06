"""Tests for the GitHub Pages publisher (Contents API), mocked with respx."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.infrastructure.hosting.github_pages_publisher import GitHubPagesPublisher
from app.infrastructure.hosting.null_site_publisher import NullSitePublisher
from app.interfaces.site_publisher import SitePublisherError

_CONTENTS = "https://api.github.com/repos/o/r/contents/newsletters/2026-W23.html"


def _publisher(client: httpx.AsyncClient) -> GitHubPagesPublisher:
    return GitHubPagesPublisher(
        client,
        token="tok",
        owner="o",
        repo="r",
        branch="gh-pages",
        base_url="https://o.github.io/r",
    )


@respx.mock
async def test_create_when_file_absent() -> None:
    respx.get(_CONTENTS).mock(return_value=httpx.Response(404))
    put = respx.put(_CONTENTS).mock(
        return_value=httpx.Response(201, json={"commit": {"sha": "abc123"}})
    )
    async with httpx.AsyncClient() as client:
        result = await _publisher(client).publish_html(
            path="newsletters/2026-W23.html", html="<h1>hola</h1>", commit_message="msg"
        )
    assert result.public_url == "https://o.github.io/r/newsletters/2026-W23.html"
    assert result.commit_sha == "abc123"
    # No sha sent on create.
    body = json.loads(put.calls.last.request.content)
    assert "sha" not in body
    assert body["branch"] == "gh-pages"


@respx.mock
async def test_update_when_file_exists() -> None:
    respx.get(_CONTENTS).mock(return_value=httpx.Response(200, json={"sha": "oldsha"}))
    put = respx.put(_CONTENTS).mock(
        return_value=httpx.Response(200, json={"commit": {"sha": "newsha"}})
    )
    async with httpx.AsyncClient() as client:
        result = await _publisher(client).publish_html(
            path="newsletters/2026-W23.html", html="<h1>hola</h1>", commit_message="msg"
        )
    assert result.commit_sha == "newsha"
    body = json.loads(put.calls.last.request.content)
    assert body["sha"] == "oldsha"  # sha required to overwrite


@respx.mock
async def test_get_error_raises() -> None:
    respx.get(_CONTENTS).mock(return_value=httpx.Response(403, text="forbidden"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(SitePublisherError):
            await _publisher(client).publish_html(
                path="newsletters/2026-W23.html", html="x", commit_message="m"
            )


@respx.mock
async def test_put_error_raises() -> None:
    respx.get(_CONTENTS).mock(return_value=httpx.Response(404))
    respx.put(_CONTENTS).mock(return_value=httpx.Response(422, text="unprocessable"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(SitePublisherError):
            await _publisher(client).publish_html(
                path="newsletters/2026-W23.html", html="x", commit_message="m"
            )


async def test_null_site_publisher_raises() -> None:
    with pytest.raises(SitePublisherError):
        await NullSitePublisher().publish_html(path="x.html", html="x", commit_message="m")
