import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from stylesense.infra.database import Base
from stylesense.platform.ids import new_id

_now = func.now()


class Upload(Base):
    """A user photo in private storage: issued (pending) → confirmed (ready) → deleted.

    `user_id` is SET NULL on account purge, so the row (and the job that deletes the stored
    file at `expires_at`) outlives the account.
    """

    __tablename__ = "uploads"
    __table_args__ = (
        CheckConstraint("kind IN ('photo_search', 'selfie')", name="kind"),
        CheckConstraint("status IN ('pending', 'ready', 'rejected', 'deleted')", name="status"),
        Index("ix_uploads_user_created", "user_id", "created_at"),
        Index("ix_uploads_expiring", "expires_at", postgresql_where=text("deleted_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(Text)
    public_id: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    format: Mapped[str | None] = mapped_column(Text)
    bytes: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
