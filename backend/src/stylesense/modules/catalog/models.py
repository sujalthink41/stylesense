import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stylesense.infra.database import Base
from stylesense.modules.catalog.ports import EMBEDDING_DIMENSIONS
from stylesense.platform.ids import new_id

_now = func.now()
CLICK_SOURCES = ("stylist", "feed", "board", "poll", "share", "product", "other")


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    allowed_hosts: Mapped[list[str]] = mapped_column(ARRAY(Text))  # outbound redirect allow-list
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)


class Product(Base):
    """What an item *is*, independent of who sells it (see Offer)."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("gender IN ('men', 'women', 'unisex')", name="gender"),
        Index(
            "ix_products_browse",
            "category",
            "gender",
            "min_price_paise",
            postgresql_where=text("active"),
        ),
        Index("ix_products_tags", "tags", postgresql_using="gin"),
        Index(
            "ix_products_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    canonical_key: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    brand: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    subcategory: Mapped[str | None] = mapped_column(Text)
    gender: Mapped[str] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    colors: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    sizes_available: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    rating: Mapped[float | None] = mapped_column(Numeric(2, 1, asdecimal=False))
    rating_count: Mapped[int] = mapped_column(Integer, server_default="0")
    primary_image_url: Mapped[str | None] = mapped_column(Text)
    min_price_paise: Mapped[int | None] = mapped_column(
        Integer
    )  # best in-stock offer, denormalised
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    content_hash: Mapped[str] = mapped_column(Text)  # what the embedding should reflect
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    embedding_hash: Mapped[str | None] = mapped_column(Text)  # what it currently reflects
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now, onupdate=_now
    )

    images: Mapped[list["ProductImage"]] = relationship(
        order_by="ProductImage.position", cascade="all, delete-orphan", lazy="raise"
    )
    offers: Mapped[list["Offer"]] = relationship(cascade="all, delete-orphan", lazy="raise")


class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (UniqueConstraint("product_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)


class Offer(Base):
    """A product sold at one store at one price."""

    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("store_id", "external_id"),
        CheckConstraint("price_paise > 0", name="price_positive"),
        CheckConstraint(
            "mrp_paise IS NULL OR mrp_paise >= price_paise", name="mrp_not_below_price"
        ),
        Index("ix_offers_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"))
    external_id: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    # None = the store has it but its price isn't known yet (web search found no real price).
    # Never estimated: such offers are left out of best price, budgets and price history.
    price_paise: Mapped[int | None] = mapped_column(Integer)
    mrp_paise: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[float | None] = mapped_column(Numeric(2, 1, asdecimal=False))
    in_stock: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sizes_in_stock: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now, onupdate=_now
    )

    store: Mapped[Store] = relationship(lazy="raise")


class PriceSnapshot(Base):
    """Written only when an offer's price changes: the basis for drops and price history."""

    __tablename__ = "price_snapshots"
    __table_args__ = (Index("ix_price_snapshots_offer_captured", "offer_id", "captured_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"))
    price_paise: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    offer: Mapped["Offer"] = relationship(
        lazy="raise"
    )  # lets inserts batch without flushing for ids


class OutboundClick(Base):
    __tablename__ = "outbound_clicks"
    __table_args__ = (
        CheckConstraint(
            "source IN ('stylist', 'feed', 'board', 'poll', 'share', 'product', 'other')",
            name="source",
        ),
        Index("ix_outbound_clicks_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offers.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
