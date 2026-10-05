"""LLM gateway: model prices, per-task routing config, usage ledger.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUIDV7 = sa.text("uuidv7()")
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "llm_models",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), server_default="chat", nullable=False),
        sa.Column("input_usd_per_mtok", sa.Numeric(12, 6), nullable=False),
        sa.Column("cached_input_usd_per_mtok", sa.Numeric(12, 6), nullable=False),
        sa.Column("output_usd_per_mtok", sa.Numeric(12, 6), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_models")),
        sa.UniqueConstraint("provider", "model", name=op.f("uq_llm_models_provider")),
        sa.CheckConstraint("kind IN ('chat', 'embedding')", name=op.f("ck_llm_models_kind")),
    )
    op.create_table(
        "llm_task_configs",
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("targets", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_input_tokens", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("timeout_s", sa.Float(), nullable=False),
        sa.Column("cache_ttl_s", sa.Integer(), server_default="0", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("task", name=op.f("pk_llm_task_configs")),
    )
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_micro_usd", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_usage")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_llm_usage_user_id_users"), ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "outcome IN ('ok', 'cache_hit', 'error', 'invalid_output')",
            name=op.f("ck_llm_usage_outcome"),
        ),
    )
    op.create_index("ix_llm_usage_created_at", "llm_usage", ["created_at"])
    op.create_index("ix_llm_usage_task_created_at", "llm_usage", ["task", "created_at"])


def downgrade() -> None:
    op.drop_table("llm_usage")
    op.drop_table("llm_task_configs")
    op.drop_table("llm_models")
