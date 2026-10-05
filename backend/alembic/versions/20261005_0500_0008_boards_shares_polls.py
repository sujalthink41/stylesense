"""Boards (wishlist + outfits), share links and polls.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUIDV7 = sa.text("uuidv7()")
NOW = sa.text("now()")


def _fk(table: str, column: str, target: str, ondelete: str = "CASCADE") -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        [f"{target}.id"],
        name=op.f(f"fk_{table}_{column}_{target}"),
        ondelete=ondelete,
    )


def upgrade() -> None:
    op.create_table(
        "boards",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("cover_product_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_boards")),
        _fk("boards", "user_id", "users"),
        _fk("boards", "cover_product_id", "products", "SET NULL"),
        sa.CheckConstraint("kind IN ('wishlist', 'outfit')", name=op.f("ck_boards_kind")),
    )
    op.create_index("ix_boards_user", "boards", ["user_id", "created_at"])
    op.create_index(
        "uq_boards_one_wishlist",
        "boards",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'wishlist' AND deleted_at IS NULL"),
    )
    op.create_table(
        "board_items",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("board_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_board_items")),
        _fk("board_items", "board_id", "boards"),
        _fk("board_items", "product_id", "products"),
        sa.UniqueConstraint("board_id", "product_id", name="uq_board_items_once"),
    )
    op.create_table(
        "shares",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("views", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shares")),
        _fk("shares", "user_id", "users"),
        sa.UniqueConstraint("slug", name=op.f("uq_shares_slug")),
        sa.UniqueConstraint("user_id", "content_hash", name="uq_shares_same_content"),
        sa.CheckConstraint("kind IN ('look', 'product', 'board')", name=op.f("ck_shares_kind")),
    )
    op.create_table(
        "polls",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_polls")),
        _fk("polls", "user_id", "users"),
        sa.UniqueConstraint("slug", name=op.f("uq_polls_slug")),
    )
    op.create_index("ix_polls_user", "polls", ["user_id", "created_at"])
    op.create_table(
        "poll_options",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("poll_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_poll_options")),
        _fk("poll_options", "poll_id", "polls"),
        _fk("poll_options", "product_id", "products"),
        sa.UniqueConstraint("poll_id", "product_id", name="uq_poll_options_once"),
    )
    op.create_table(
        "poll_votes",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("poll_id", sa.Uuid(), nullable=False),
        sa.Column("option_id", sa.Uuid(), nullable=False),
        sa.Column("voter_hash", sa.Text(), nullable=False),
        sa.Column("ip_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_poll_votes")),
        _fk("poll_votes", "poll_id", "polls"),
        _fk("poll_votes", "option_id", "poll_options"),
        sa.UniqueConstraint("poll_id", "voter_hash", name="uq_poll_votes_once"),
    )
    op.create_index("ix_poll_votes_option", "poll_votes", ["option_id"])


def downgrade() -> None:
    op.drop_table("poll_votes")
    op.drop_table("poll_options")
    op.drop_table("polls")
    op.drop_table("shares")
    op.drop_table("board_items")
    op.drop_table("boards")
