"""Endpoint for triggering the workflow manually (`POST /workflow/run`)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import ContainerDep
from app.api.schemas import WorkflowRunResponse

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/run", response_model=WorkflowRunResponse)
async def run_workflow(container: ContainerDep) -> WorkflowRunResponse:
    """Run the full news pipeline on demand."""
    report = await container.run_workflow_uc.execute()
    return WorkflowRunResponse.from_report(report)
