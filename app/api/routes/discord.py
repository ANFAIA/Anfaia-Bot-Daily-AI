"""Discord publish test endpoint (`POST /discord/test`)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.dependencies import ContainerDep
from app.api.schemas import DiscordTestRequest, DiscordTestResponse
from app.interfaces.publisher import PublisherError

router = APIRouter(prefix="/discord", tags=["discord"])


@router.post("/test", response_model=DiscordTestResponse)
async def test_discord(payload: DiscordTestRequest, container: ContainerDep) -> DiscordTestResponse:
    """Publish a test message to the configured Discord channel."""
    try:
        message_id = await container.test_discord_uc.execute(payload.message)
    except PublisherError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return DiscordTestResponse(discord_message_id=message_id)
