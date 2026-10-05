"""Stylist sessions and their event log.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUIDV7 = sa.text("uuidv7()")
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "stylist_sessions",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("flow", sa.Text(), nullable=False),
        sa.Column("entry", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("turn_id", sa.Integer(), nullable=False),
        sa.Column(
            "state", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("envelope", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stylist_sessions")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_stylist_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'busy', 'ended')", name=op.f("ck_stylist_sessions_status")
        ),
    )
    op.create_index(
        "ix_stylist_sessions_user_activity", "stylist_sessions", ["user_id", "last_activity_at"]
    )
    op.create_table(
        "session_events",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("turn_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_events")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["stylist_sessions.id"],
            name=op.f("fk_session_events_session_id_stylist_sessions"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('action', 'render', 'error')", name=op.f("ck_session_events_kind")
        ),
    )
    op.create_index("ix_session_events_session_turn", "session_events", ["session_id", "turn_id"])
    op.create_index("ix_session_events_created_at", "session_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("session_events")
    op.drop_table("stylist_sessions")
