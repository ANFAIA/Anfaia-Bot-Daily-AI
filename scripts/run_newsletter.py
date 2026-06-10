"""Run the weekly newsletter once and exit.

Builds the application container and runs the newsletter workflow a single time
(collect → classify → select → edit → publish to GitHub Pages → announce on
Discord → record), then prints the resulting report as JSON. Useful for manual
testing or a cron job, without starting the API server.

Exit code is 0 on success, 1 otherwise.

Usage:
    # locally (with the venv active)
    python scripts/run_newsletter.py

    # inside the running container
    docker compose exec app python scripts/run_newsletter.py
"""

from __future__ import annotations

import asyncio
import json

from app.core.config import get_settings
from app.core.container import Container


async def main() -> int:
    settings = get_settings()
    container = Container(settings)
    try:
        report = await container.run_newsletter_uc.execute()
    finally:
        await container.aclose()

    payload = {
        "status": "success" if report.succeeded else "failed",
        "collected": report.collected,
        "classified": report.classified,
        "selected": report.selected,
        "published": report.published_count,
        "public_url": report.public_url,
        "discord_message_id": report.discord_message_id,
        "podcast_url": report.podcast_url,
        "errors": report.errors,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if report.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
