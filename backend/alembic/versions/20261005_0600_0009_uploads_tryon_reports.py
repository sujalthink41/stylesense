"""Uploads (Cloudinary), try-on jobs and content reports.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUIDV7 = sa.text("uuidv7()")
NOW = sa.text("now()")


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=op.f(f"fk_{table}_{column}_{target}"), ondelete=ondelete
    )


def upgrade() -> None:
    op.create_table(
        "uploads",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("format", sa.Text(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploads")),
        # SET NULL, not CASCADE: rows must outlive an account purge so the stored files get deleted.
        _fk("uploads", "user_id", "users", "SET NULL"),
        sa.UniqueConstraint("public_id", name=op.f("uq_uploads_public_id")),
        sa.CheckConstraint("kind IN ('photo_search', 'selfie')", name=op.f("ck_uploads_kind")),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'rejected', 'deleted')", name=op.f("ck_uploads_status")
        ),
    )
    op.create_index("ix_uploads_user_created", "uploads", ["user_id", "created_at"])
    op.create_index(
        "ix_uploads_expiring",
        "uploads",
        ["expires_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "tryon_jobs",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("selfie_upload_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("result_public_id", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("cost_micro_usd", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tryon_jobs")),
        _fk("tryon_jobs", "user_id", "users", "SET NULL"),
        _fk("tryon_jobs", "selfie_upload_id", "uploads", "CASCADE"),
        _fk("tryon_jobs", "product_id", "products", "CASCADE"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name=op.f("ck_tryon_jobs_status")
        ),
    )
    op.create_index("ix_tryon_jobs_user_created", "tryon_jobs", ["user_id", "created_at"])
    op.create_index(
        "uq_tryon_jobs_active",
        "tryon_jobs",
        ["user_id", "selfie_upload_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running', 'done')"),
    )
    op.create_index(
        "ix_tryon_jobs_expiring",
        "tryon_jobs",
        ["expires_at"],
        postgresql_where=sa.text("result_public_id IS NOT NULL AND result_deleted_at IS NULL"),
    )
    op.create_table(
        "content_reports",
        sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False),
        sa.Column("reporter_user_id", sa.Uuid(), nullable=True),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_reports")),
        _fk("content_reports", "reporter_user_id", "users", "SET NULL"),
        sa.UniqueConstraint(
            "reporter_user_id", "target_kind", "target_id", name="uq_content_reports_once"
        ),
        sa.CheckConstraint(
            "target_kind IN ('tryon', 'product', 'share', 'poll')",
            name=op.f("ck_content_reports_target_kind"),
        ),
        sa.CheckConstraint(
            "reason IN ('inappropriate', 'offensive', 'wrong_item', 'spam', 'other')",
            name=op.f("ck_content_reports_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'actioned', 'dismissed')", name=op.f("ck_content_reports_status")
        ),
    )
    op.create_index("ix_content_reports_queue", "content_reports", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("content_reports")
    op.drop_table("tryon_jobs")
    op.drop_table("uploads")
