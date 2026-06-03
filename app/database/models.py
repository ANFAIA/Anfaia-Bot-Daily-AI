"""SQLAlchemy 2.x ORM models.

Tables:
  - news_articles:   history of published news items.
  - news_embeddings: vector fingerprints for duplicate detection.
  - workflow_counters: aggregate counters (analyzed, discarded, ...).

The vector dimension is taken from the configuration to stay consistent with
the active embedding provider.
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.database.base import Base

_EMBEDDING_DIM = get_settings().embedding_dim


class NewsArticle(Base):
    """A news item that has been published to Discord."""

    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    url_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    relevance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    discord_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    embedding: Mapped[NewsEmbedding] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (UniqueConstraint("url_fingerprint", name="uq_news_url_fingerprint"),)


class NewsEmbedding(Base):
    """Semantic embedding associated with a news item."""

    __tablename__ = "news_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    article: Mapped[NewsArticle] = relationship(back_populates="embedding")


class WorkflowCounter(Base):
    """Persistent aggregate counter for the administration statistics."""

    __tablename__ = "workflow_counters"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
