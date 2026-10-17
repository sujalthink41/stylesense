"""Profile extras: favourite brands and usual budget.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "style_profiles",
        sa.Column(
            "favorite_brands",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column("style_profiles", sa.Column("usual_budget_paise", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("style_profiles", "usual_budget_paise")
    op.drop_column("style_profiles", "favorite_brands")
