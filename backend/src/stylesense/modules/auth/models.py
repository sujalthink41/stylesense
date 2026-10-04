import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, func, text
from sqlalchemy.orm import Mapped, mapped_column

from stylesense.infra.database import Base


class RefreshToken(Base):
    """One row per issued refresh token. A *family* is one sign-in session on one device.

    Rotation: each use marks the row `used_at` and issues a child in the same family.
    Reusing a used token (outside the grace window) revokes the whole family.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_family_id", "family_id"),
        Index(
            "ix_refresh_tokens_active_user", "user_id", postgresql_where=text("revoked_at IS NULL")
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    family_id: Mapped[uuid.UUID]
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    installation_id: Mapped[uuid.UUID | None]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
