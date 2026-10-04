import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from stylesense.infra.database import Base

_now = func.now()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'curator', 'admin')", name="role"),
        CheckConstraint("status IN ('active', 'suspended', 'deleting')", name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, server_default="user")
    status: Mapped[str] = mapped_column(Text, server_default="active")
    locale: Mapped[str] = mapped_column(Text, server_default="en-IN")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now, onupdate=_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthIdentity(Base):
    """Links a user to an external identity (Google `sub`). Keyed by subject, not email."""

    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class UserDevice(Base):
    __tablename__ = "user_devices"
    __table_args__ = (
        UniqueConstraint("user_id", "installation_id"),
        CheckConstraint("platform IN ('android', 'ios', 'web')", name="platform"),
        # A push token belongs to one device at a time, even if the phone changes accounts.
        Index(
            "uq_user_devices_push_token",
            "push_token",
            unique=True,
            postgresql_where=text("push_token IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    installation_id: Mapped[uuid.UUID]
    platform: Mapped[str] = mapped_column(Text)
    app_version: Mapped[str] = mapped_column(Text)
    push_token: Mapped[str | None] = mapped_column(Text)
    push_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class Consent(Base):
    """Append-only consent history: the latest row per kind is the current answer."""

    __tablename__ = "consents"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('terms', 'privacy', 'photo_processing', 'marketing_push')", name="kind"
        ),
        Index("ix_consents_user_kind_created", "user_id", "kind", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    granted: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class AccountDeletion(Base):
    """Kept after the user row is purged, as proof the request was honoured (no FK on purpose)."""

    __tablename__ = "account_deletions"
    __table_args__ = (
        CheckConstraint("requested_via IN ('app', 'web', 'admin')", name="requested_via"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    user_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    requested_via: Mapped[str] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
