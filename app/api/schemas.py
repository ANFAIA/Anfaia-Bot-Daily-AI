"""Pydantic v2 input/output schemas for the REST API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.entities import WorkflowReport
from app.interfaces.repositories import StatsSnapshot, StoredArticle


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    environment: str


class NewsItemResponse(BaseModel):
    id: int
    title: str
    url: str
    source: str
    category: str
    relevance_score: int
    summary: str
    published_at: datetime | None
    discord_message_id: int | None
    created_at: datetime

    @classmethod
    def from_domain(cls, article: StoredArticle) -> NewsItemResponse:
        return cls(
            id=article.id,
            title=article.title,
            url=article.url,
            source=article.source,
            category=article.category.value,
            relevance_score=article.relevance_score,
            summary=article.summary,
            published_at=article.published_at,
            discord_message_id=article.discord_message_id,
            created_at=article.created_at,
        )


class WorkflowRunResponse(BaseModel):
    status: str
    collected: int
    classified: int
    published: int
    discarded_duplicates: int
    discarded_low_relevance: int
    errors: list[str]
    published_title: str | None = None
    discord_message_id: int | None = None

    @classmethod
    def from_report(cls, report: WorkflowReport) -> WorkflowRunResponse:
        article = report.published_article
        return cls(
            status="success" if report.succeeded else "failed",
            collected=report.collected,
            classified=report.classified,
            published=report.published,
            discarded_duplicates=report.discarded_duplicates,
            discarded_low_relevance=report.discarded_low_relevance,
            errors=report.errors,
            published_title=article.edited.title if article else None,
            discord_message_id=article.discord_message_id if article else None,
        )


class DiscordTestRequest(BaseModel):
    message: str = Field(
        default="Mensaje de prueba de Anfaia Daily AI 🤖",
        max_length=1500,
    )


class DiscordTestResponse(BaseModel):
    status: str = "sent"
    discord_message_id: int


class StatsResponse(BaseModel):
    analyzed: int
    published: int
    discarded: int
    by_category: dict[str, int]
    last_run_at: str | None
    last_run_status: str | None

    @classmethod
    def from_snapshot(cls, snapshot: StatsSnapshot) -> StatsResponse:
        return cls(
            analyzed=snapshot.analyzed,
            published=snapshot.published,
            discarded=snapshot.discarded,
            by_category=snapshot.by_category,
            last_run_at=snapshot.last_run_at,
            last_run_status=snapshot.last_run_status,
        )
