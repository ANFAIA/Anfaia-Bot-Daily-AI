"""Endpoint for triggering the weekly newsletter manually (`POST /newsletter/run`)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import ContainerDep
from app.api.schemas import NewsletterRunResponse

router = APIRouter(prefix="/newsletter", tags=["newsletter"])


@router.post("/run", response_model=NewsletterRunResponse)
async def run_newsletter(container: ContainerDep) -> NewsletterRunResponse:
    """Build and publish the weekly newsletter on demand."""
    report = await container.run_newsletter_uc.execute()
    return NewsletterRunResponse.from_report(report)
