"""Endpoints for querying the news history."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import ContainerDep
from app.api.schemas import NewsItemResponse
from app.domain.value_objects import Category

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=list[NewsItemResponse])
async def list_news(
    container: ContainerDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category: Category | None = Query(default=None),
) -> list[NewsItemResponse]:
    """List published news items, optionally filtered by category."""
    articles = await container.list_news_uc.execute(limit=limit, offset=offset, category=category)
    return [NewsItemResponse.from_domain(a) for a in articles]


@router.get("/{article_id}", response_model=NewsItemResponse)
async def get_news(article_id: int, container: ContainerDep) -> NewsItemResponse:
    """Retrieve a specific news item by id."""
    article = await container.get_news_uc.execute(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")
    return NewsItemResponse.from_domain(article)
