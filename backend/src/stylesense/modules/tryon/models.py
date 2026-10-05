import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import Mapped, mapped_column

from stylesense.infra.database import Base
from stylesense.platform.ids import new_id

_now = func.now()


class TryOnJob(Base):
    """queued → running → done | failed. One active job per (user, selfie, product): a double
    tap finds the existing job instead of paying the provider twice."""

    __tablename__ = "tryon_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="status"),
        Index("ix_tryon_jobs_user_created", "user_id", "created_at"),
        Index(
            "uq_tryon_jobs_active",
            "user_id",
            "selfie_upload_id",
            "product_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running', 'done')"),
        ),
        Index(
            "ix_tryon_jobs_expiring",
            "expires_at",
            postgresql_where=text("result_public_id IS NOT NULL AND result_deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    selfie_upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("uploads.id", ondelete="CASCADE")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    result_public_id: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    cost_micro_usd: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentReport(Base):
    """A user flags something (a try-on result, product, share or poll) for review."""

    __tablename__ = "content_reports"
    __table_args__ = (
        UniqueConstraint(
            "reporter_user_id", "target_kind", "target_id", name="uq_content_reports_once"
        ),
        CheckConstraint("target_kind IN ('tryon', 'product', 'share', 'poll')", name="target_kind"),
        CheckConstraint(
            "reason IN ('inappropriate', 'offensive', 'wrong_item', 'spam', 'other')", name="reason"
        ),
        CheckConstraint("status IN ('open', 'actioned', 'dismissed')", name="status"),
        Index("ix_content_reports_queue", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    reporter_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    target_kind: Mapped[str] = mapped_column(Text)
    target_id: Mapped[uuid.UUID]
    reason: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
