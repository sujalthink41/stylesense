"""Catalog: stores, products (with embeddings), images, offers, price snapshots, clicks.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUIDV7 = sa.text("uuidv7()")
NOW = sa.text("now()")
TEXT_ARRAY = postgresql.ARRAY(sa.Text())
EMPTY_ARRAY = sa.text("'{}'")

STORES = [
    {"code": "amazon", "name": "Amazon", "allowed_hosts": ["amazon.in", "amzn.to"]},
    {"code": "flipkart", "name": "Flipkart", "allowed_hosts": ["flipkart.com"]},
    {"code": "myntra", "name": "Myntra", "allowed_hosts": ["myntra.com"]},
]


def _id() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False)


def _ts(name: str, *, nullable: bool = False, default: bool = False) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=NOW if default else None, nullable=nullable
    )


def upgrade() -> None:
    stores = op.create_table(
        "stores",
        _id(),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("allowed_hosts", TEXT_ARRAY, nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _ts("created_at", default=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stores")),
        sa.UniqueConstraint("code", name=op.f("uq_stores_code")),
    )
    op.bulk_insert(stores, STORES)  # reference data: sources refer to stores by code

    op.create_table(
        "products",
        _id(),
        sa.Column("canonical_key", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("subcategory", sa.Text(), nullable=True),
        sa.Column("gender", sa.Text(), nullable=False),
        sa.Column(
            "attributes", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("colors", TEXT_ARRAY, server_default=EMPTY_ARRAY, nullable=False),
        sa.Column("tags", TEXT_ARRAY, server_default=EMPTY_ARRAY, nullable=False),
        sa.Column("sizes_available", TEXT_ARRAY, server_default=EMPTY_ARRAY, nullable=False),
        sa.Column("rating", sa.Numeric(2, 1), nullable=True),
        sa.Column("rating_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("primary_image_url", sa.Text(), nullable=True),
        sa.Column("min_price_paise", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("embedding_hash", sa.Text(), nullable=True),
        _ts("created_at", default=True),
        _ts("updated_at", default=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("canonical_key", name=op.f("uq_products_canonical_key")),
        sa.CheckConstraint("gender IN ('men', 'women', 'unisex')", name=op.f("ck_products_gender")),
    )
    op.create_index(
        "ix_products_browse",
        "products",
        ["category", "gender", "min_price_paise"],
        postgresql_where=sa.text("active"),
    )
    op.create_index("ix_products_tags", "products", ["tags"], postgresql_using="gin")
    # HNSW: approximate nearest neighbours in ~log time; cosine matches our normalised vectors.
    op.create_index(
        "ix_products_embedding_hnsw",
        "products",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "product_images",
        _id(),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_images")),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_images_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("product_id", "position", name=op.f("uq_product_images_product_id")),
    )

    op.create_table(
        "offers",
        _id(),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        sa.Column("mrp_paise", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Numeric(2, 1), nullable=True),
        sa.Column("in_stock", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sizes_in_stock", TEXT_ARRAY, server_default=EMPTY_ARRAY, nullable=False),
        _ts("last_refreshed_at"),
        _ts("created_at", default=True),
        _ts("updated_at", default=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offers")),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_offers_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], name=op.f("fk_offers_store_id_stores")
        ),
        sa.UniqueConstraint("store_id", "external_id", name=op.f("uq_offers_store_id")),
        sa.CheckConstraint("price_paise > 0", name=op.f("ck_offers_price_positive")),
        sa.CheckConstraint(
            "mrp_paise IS NULL OR mrp_paise >= price_paise",
            name=op.f("ck_offers_mrp_not_below_price"),
        ),
    )
    op.create_index("ix_offers_product_id", "offers", ["product_id"])

    op.create_table(
        "price_snapshots",
        _id(),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        _ts("captured_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_snapshots")),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["offers.id"],
            name=op.f("fk_price_snapshots_offer_id_offers"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_price_snapshots_offer_captured", "price_snapshots", ["offer_id", "captured_at"]
    )

    op.create_table(
        "outbound_clicks",
        _id(),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        _ts("created_at", default=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_clicks")),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["offers.id"],
            name=op.f("fk_outbound_clicks_offer_id_offers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_outbound_clicks_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "source IN ('stylist', 'feed', 'board', 'poll', 'share', 'product', 'other')",
            name=op.f("ck_outbound_clicks_source"),
        ),
    )
    op.create_index("ix_outbound_clicks_created_at", "outbound_clicks", ["created_at"])


def downgrade() -> None:
    op.drop_table("outbound_clicks")
    op.drop_table("price_snapshots")
    op.drop_table("offers")
    op.drop_table("product_images")
    op.drop_table("products")
    op.drop_table("stores")
