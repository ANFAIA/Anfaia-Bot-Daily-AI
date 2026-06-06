"""GitHub Pages publishing adapter via the GitHub Contents API.

Publishes an HTML file by committing it to a repository through the REST
Contents API (no local git working tree needed). The file lands on the
configured branch; GitHub Pages then serves it at the public base URL.

Create vs. update is handled transparently: the API requires the current blob
`sha` to overwrite an existing file, so we read it first (404 means "create").
"""

from __future__ import annotations

import base64

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging import get_logger
from app.interfaces.site_publisher import PublishedSite, SitePublisher, SitePublisherError

logger = get_logger(__name__)

_API_ROOT = "https://api.github.com"
_API_VERSION = "2022-11-28"


class GitHubPagesPublisher(SitePublisher):
    """Publishes HTML pages to a GitHub repository served by GitHub Pages."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        token: str,
        owner: str,
        repo: str,
        branch: str,
        base_url: str,
    ) -> None:
        if not (token and owner and repo and base_url):
            raise ValueError("GitHubPagesPublisher requiere token, owner, repo y base_url")
        self._client = client
        self._owner = owner
        self._repo = repo
        self._branch = branch
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
        }

    def _contents_url(self, path: str) -> str:
        return f"{_API_ROOT}/repos/{self._owner}/{self._repo}/contents/{path.lstrip('/')}"

    async def _current_sha(self, path: str) -> str | None:
        """Return the blob sha of an existing file, or None if it does not exist."""
        response = await self._client.get(
            self._contents_url(path),
            headers=self._headers,
            params={"ref": self._branch},
        )
        if response.status_code == 404:
            return None
        if response.status_code == 200:
            data = response.json()
            sha = data.get("sha") if isinstance(data, dict) else None
            return str(sha) if sha else None
        raise SitePublisherError(
            f"GitHub respondió {response.status_code} al leer {path}: {response.text[:200]}"
        )

    @retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        reraise=True,
    )
    async def publish_html(self, *, path: str, html: str, commit_message: str) -> PublishedSite:
        path = path.lstrip("/")
        sha = await self._current_sha(path)
        commit_sha = await self._put(path=path, html=html, message=commit_message, sha=sha)
        public_url = f"{self._base_url}/{path}"
        logger.info(
            "site_publisher.published",
            path=path,
            url=public_url,
            created=sha is None,
        )
        return PublishedSite(public_url=public_url, path=path, commit_sha=commit_sha)

    async def _put(self, *, path: str, html: str, message: str, sha: str | None) -> str:
        body: dict[str, str] = {
            "message": message,
            "content": base64.b64encode(html.encode("utf-8")).decode("ascii"),
            "branch": self._branch,
        }
        if sha is not None:
            body["sha"] = sha

        response = await self._client.put(
            self._contents_url(path), headers=self._headers, json=body
        )
        # A 409 means the sha we sent is stale (concurrent write); re-read and retry once.
        if response.status_code == 409:
            fresh_sha = await self._current_sha(path)
            if fresh_sha is not None:
                body["sha"] = fresh_sha
            response = await self._client.put(
                self._contents_url(path), headers=self._headers, json=body
            )

        if response.status_code not in (200, 201):
            raise SitePublisherError(
                f"GitHub respondió {response.status_code} al publicar {path} "
                f"(revisa el PAT y el permiso 'contents:write'): {response.text[:200]}"
            )
        data = response.json()
        commit = data.get("commit", {}) if isinstance(data, dict) else {}
        return str(commit.get("sha", ""))
