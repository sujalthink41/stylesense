import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from stylesense.infra.database import Base
from stylesense.platform.ids import new_id

_now = func.now()
OUTCOMES = ("ok", "cache_hit", "error", "invalid_output")


class LlmModel(Base):
    """A usable model and its price. No price, no calls: budgets must be enforceable."""

    __tablename__ = "llm_models"
    __table_args__ = (
        UniqueConstraint("provider", "model"),
        CheckConstraint("kind IN ('chat', 'embedding')", name="kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, server_default="chat")
    input_usd_per_mtok: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    cached_input_usd_per_mtok: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    output_usd_per_mtok: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now, onupdate=_now
    )
    updated_by: Mapped[uuid.UUID | None]


class LlmTaskConfig(Base):
    """Which models serve a task (first = primary, rest = fallbacks) and its limits."""

    __tablename__ = "llm_task_configs"

    task: Mapped[str] = mapped_column(Text, primary_key=True)
    targets: Mapped[list[str]] = mapped_column(ARRAY(Text))  # "provider:model", in order
    temperature: Mapped[float | None] = mapped_column(Float)
    max_input_tokens: Mapped[int] = mapped_column(Integer)
    max_output_tokens: Mapped[int] = mapped_column(Integer)
    timeout_s: Mapped[float] = mapped_column(Float)
    cache_ttl_s: Mapped[int] = mapped_column(Integer, server_default="0")
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now, onupdate=_now
    )
    updated_by: Mapped[uuid.UUID | None]


class LlmUsage(Base):
    """One row per attempt (a gateway call may try several models). Cost in integer micro-USD."""

    __tablename__ = "llm_usage"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('ok', 'cache_hit', 'error', 'invalid_output')", name="outcome"
        ),
        Index("ix_llm_usage_created_at", "created_at"),
        Index("ix_llm_usage_task_created_at", "task", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=new_id, server_default=text("uuidv7()")
    )
    call_id: Mapped[uuid.UUID]
    task: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    prompt_version: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cached_input_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cost_micro_usd: Mapped[int] = mapped_column(BigInteger, server_default="0")
    latency_ms: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
