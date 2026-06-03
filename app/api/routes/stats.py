"""Administration statistics endpoint (`GET /stats`)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import ContainerDep
from app.api.schemas import StatsResponse

router = APIRouter(tags=["admin"])


@router.get("/stats", response_model=StatsResponse)
async def stats(container: ContainerDep) -> StatsResponse:
    """Return aggregates: analyzed, published, discarded, by category, etc."""
    snapshot = await container.stats_uc.execute()
    return StatsResponse.from_snapshot(snapshot)
