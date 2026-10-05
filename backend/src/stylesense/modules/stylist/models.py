import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stylesense.infra.database import Base
from stylesense.platform.ids import new_id

_now = func.now()


class StylistSession(Base):
    """Server-authoritative session. `envelope` is the last rendered turn (the resume snapshot)."""

    __tablename__ = "stylist_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'busy', 'ended')", name="status"),
        Index("ix_stylist_sessions_user_activity", "user_id", "last_activity_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    flow: Mapped[str] = mapped_column(Text)
    entry: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="active")
    turn_id: Mapped[int] = mapped_column(Integer)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    envelope: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionEvent(Base):
    """Append-only log of actions and renders (analytics, debugging); pruned after 90 days."""

    __tablename__ = "session_events"
    __table_args__ = (
        CheckConstraint("kind IN ('action', 'render', 'error')", name="kind"),
        Index("ix_session_events_session_turn", "session_id", "turn_id"),
        Index("ix_session_events_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stylist_sessions.id", ondelete="CASCADE")
    )
    turn_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
