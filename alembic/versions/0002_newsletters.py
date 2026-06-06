"""Weekly newsletters table.

Revision ID: 0002_newsletters
Revises: 0001_initial
Create Date: 2026-06-06

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_newsletters"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "newsletters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("iso_year", sa.Integer(), nullable=False),
        sa.Column("iso_week", sa.Integer(), nullable=False),
        sa.Column("week_label", sa.String(length=128), nullable=False),
        sa.Column("public_url", sa.String(length=2048), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("discord_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("iso_year", "iso_week", name="uq_newsletter_year_week"),
    )


def downgrade() -> None:
    op.drop_table("newsletters")
