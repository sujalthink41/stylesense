import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stylesense.infra.database import Base
from stylesense.modules.catalog.ports import EMBEDDING_DIMENSIONS
from stylesense.platform.ids import new_id

_now = func.now()


class StyleProfile(Base):
    """Style DNA (what the user told us) + taste (what their swipes taught us). 1:1 with users."""

    __tablename__ = "style_profiles"
    __table_args__ = (
        CheckConstraint(
            "fit_preference IS NULL OR fit_preference IN ('men', 'women', 'unisex', 'any')",
            name="fit_preference",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    fit_preference: Mapped[str | None] = mapped_column(Text)
    styles: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    sizes: Mapped[dict[str, str]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    taste_vector: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    tag_affinity: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    swipe_count: Mapped[int] = mapped_column(server_default=text("0"))
    onboarding_done: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Profile extras the person sets themselves: a soft ranking boost and a budget default.
    favorite_brands: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    usual_budget_paise: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class Swipe(Base):
    """One swipe per (user, product, session); replays are no-ops (NULLS NOT DISTINCT)."""

    __tablename__ = "swipes"
    __table_args__ = (
        CheckConstraint("direction IN ('left', 'right', 'super')", name="direction"),
        UniqueConstraint(
            "user_id",
            "product_id",
            "session_id",
            name="uq_swipes_once",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_swipes_user_created", "user_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    # Dedupe scope, not a foreign key: swipes outlive sessions, and a SET NULL could collide.
    session_id: Mapped[uuid.UUID | None]
    direction: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
