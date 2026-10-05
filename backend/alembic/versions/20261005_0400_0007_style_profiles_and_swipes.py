"""Style DNA profiles (with taste vector) and swipes.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUIDV7 = sa.text("uuidv7()")
NOW = sa.text("now()")
EMPTY_JSON = sa.text("'{}'::jsonb")


def upgrade() -> None:
    op.create_table(
        "style_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("fit_preference", sa.Text(), nullable=True),
        sa.Column(
            "styles", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("sizes", postgresql.JSONB(), server_default=EMPTY_JSON, nullable=False),
        sa.Column("taste_vector", Vector(1536), nullable=True),
        sa.Column("tag_affinity", postgresql.JSONB(), server_default=EMPTY_JSON, nullable=False),
        sa.Column("swipe_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("onboarding_done", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_style_profiles")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_style_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "fit_preference IS NULL OR fit_preference IN ('men', 'women', 'unisex', 'any')",
            name=op.f("ck_style_profiles_fit_preference"),
        ),
    )
    op.create_table(
        "swipes",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_swipes")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_swipes_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_swipes_product_id_products"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "direction IN ('left', 'right', 'super')", name=op.f("ck_swipes_direction")
        ),
        sa.UniqueConstraint(
            "user_id",
            "product_id",
            "session_id",
            name="uq_swipes_once",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_swipes_user_created", "swipes", ["user_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_table("swipes")
    op.drop_table("style_profiles")
