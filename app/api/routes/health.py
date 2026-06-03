"""Health endpoint (`GET /health`)."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.api.dependencies import ContainerDep
from app.api.schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health(container: ContainerDep) -> HealthResponse:
    """Service liveness check."""
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=container.settings.app_env,
    )
