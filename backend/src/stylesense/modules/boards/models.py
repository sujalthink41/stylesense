import uuid
from datetime import datetime

from sqlalchemy import (
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


class Board(Base):
    """A user's wishlist (exactly one, created on demand) or a named outfit board.

    `version` is the optimistic lock: every change bumps it, and edits that name an older
    version are refused (HTTP If-Match → 412).
    """

    __tablename__ = "boards"
    __table_args__ = (
        CheckConstraint("kind IN ('wishlist', 'outfit')", name="kind"),
        Index("ix_boards_user", "user_id", "created_at"),
        Index(
            "uq_boards_one_wishlist",
            "user_id",
            unique=True,
            postgresql_where=text("kind = 'wishlist' AND deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    cover_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BoardItem(Base):
    __tablename__ = "board_items"
    __table_args__ = (UniqueConstraint("board_id", "product_id", name="uq_board_items_once"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    board_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
