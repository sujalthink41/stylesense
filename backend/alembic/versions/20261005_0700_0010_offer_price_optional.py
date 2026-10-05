"""Offers may have no known price yet (web-search sources). Never estimated.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("offers", "price_paise", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM offers WHERE price_paise IS NULL")
    op.alter_column("offers", "price_paise", existing_type=sa.Integer(), nullable=False)
