"""Transactional outbox: side effects recorded in the same transaction as the business change.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_messages")),
        sa.CheckConstraint(
            "status IN ('pending', 'done', 'dead')", name=op.f("ck_outbox_messages_status")
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_outbox_messages_attempts")),
    )
    # The relay's hot query: due pending messages, oldest first. Partial index stays tiny.
    op.create_index(
        "ix_outbox_messages_due",
        "outbox_messages",
        ["available_at", "id"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_outbox_messages_dedupe_key",
        "outbox_messages",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_outbox_messages_dedupe_key", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_due", table_name="outbox_messages")
    op.drop_table("outbox_messages")
