import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from stylesense.infra.database import Base
from stylesense.platform.ids import new_id

LEGAL_KINDS = ("privacy", "terms", "delete_account")


class LegalDocument(Base):
    """One published version of a legal page. Publishing adds a version; old ones are kept, so
    we can always show what a person agreed to and when."""

    __tablename__ = "legal_documents"
    __table_args__ = (
        UniqueConstraint("kind", "version"),
        CheckConstraint("kind IN ('privacy', 'terms', 'delete_account')", name="kind"),
        CheckConstraint("version > 0", name="version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    kind: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    # Trusted HTML written by us (never user input); {{support_email}} is filled in when shown.
    body_html: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
