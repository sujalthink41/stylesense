"""Users, identities, devices, consents, account deletions and refresh tokens.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUIDV7 = sa.text("uuidv7()")
NOW = sa.text("now()")


def _id() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), server_default=UUIDV7, nullable=False)


def _ts(name: str, *, nullable: bool = False, default: bool = False) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=NOW if default else None, nullable=nullable
    )


def _user_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["user_id"], ["users.id"], name=op.f(f"fk_{table}_user_id_users"), ondelete="CASCADE"
    )


def upgrade() -> None:
    op.create_table(
        "users",
        _id(),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), server_default="user", nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("locale", sa.Text(), server_default="en-IN", nullable=False),
        _ts("last_seen_at", nullable=True),
        _ts("created_at", default=True),
        _ts("updated_at", default=True),
        _ts("deleted_at", nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.CheckConstraint("role IN ('user', 'curator', 'admin')", name=op.f("ck_users_role")),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deleting')", name=op.f("ck_users_status")
        ),
    )
    op.create_table(
        "auth_identities",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        _ts("created_at", default=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_identities")),
        _user_fk("auth_identities"),
        sa.UniqueConstraint("provider", "subject", name=op.f("uq_auth_identities_provider")),
    )
    op.create_table(
        "user_devices",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("app_version", sa.Text(), nullable=False),
        sa.Column("push_token", sa.Text(), nullable=True),
        sa.Column("push_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        _ts("last_active_at"),
        _ts("created_at", default=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_devices")),
        _user_fk("user_devices"),
        sa.UniqueConstraint("user_id", "installation_id", name=op.f("uq_user_devices_user_id")),
        sa.CheckConstraint(
            "platform IN ('android', 'ios', 'web')", name=op.f("ck_user_devices_platform")
        ),
    )
    op.create_index(
        "uq_user_devices_push_token",
        "user_devices",
        ["push_token"],
        unique=True,
        postgresql_where=sa.text("push_token IS NOT NULL"),
    )
    op.create_table(
        "consents",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        _ts("created_at", default=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
        _user_fk("consents"),
        sa.CheckConstraint(
            "kind IN ('terms', 'privacy', 'photo_processing', 'marketing_push')",
            name=op.f("ck_consents_kind"),
        ),
    )
    op.create_index("ix_consents_user_kind_created", "consents", ["user_id", "kind", "created_at"])
    op.create_table(
        "account_deletions",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("requested_via", sa.Text(), nullable=False),
        _ts("requested_at"),
        _ts("purge_after"),
        _ts("purged_at", nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_deletions")),
        sa.UniqueConstraint("user_id", name=op.f("uq_account_deletions_user_id")),
        sa.CheckConstraint(
            "requested_via IN ('app', 'web', 'admin')",
            name=op.f("ck_account_deletions_requested_via"),
        ),
    )
    op.create_table(
        "refresh_tokens",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=True),
        _ts("expires_at"),
        _ts("used_at", nullable=True),
        _ts("revoked_at", nullable=True),
        _ts("created_at", default=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        _user_fk("refresh_tokens"),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index(
        "ix_refresh_tokens_active_user",
        "refresh_tokens",
        ["user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("account_deletions")
    op.drop_table("consents")
    op.drop_table("user_devices")
    op.drop_table("auth_identities")
    op.drop_table("users")
