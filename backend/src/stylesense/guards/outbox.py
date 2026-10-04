"""Transactional outbox: record side effects in the same DB transaction as the business change,
then deliver them asynchronously with retries. Delivery is at-least-once, so handlers must be
idempotent (use `envelope.id` as the dedupe key).
"""

import asyncio
import random
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from stylesense.infra.database import Base
from stylesense.platform.clock import Clock
from stylesense.platform.observability.redaction import scrub

logger = structlog.get_logger(__name__)

PENDING, DONE, DEAD = "pending", "done", "dead"
_MAX_ERROR_CHARS = 500


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'done', 'dead')", name="status"),
        CheckConstraint("attempts >= 0", name="attempts"),
        Index(
            "ix_outbox_messages_due",
            "available_at",
            "id",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "uq_outbox_messages_dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    topic: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=PENDING)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True, slots=True)
class OutboxEnvelope:
    id: uuid.UUID
    topic: str
    payload: dict[str, Any]
    attempt: int


Handler = Callable[[OutboxEnvelope], Awaitable[None]]


class OutboxWriter:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    async def add(
        self,
        session: AsyncSession,
        topic: str,
        payload: dict[str, Any],
        *,
        dedupe_key: str | None = None,
        delay: timedelta | None = None,
    ) -> bool:
        """Stage a message in the caller's transaction. Returns False if `dedupe_key` exists."""
        stmt = (
            insert(OutboxMessage)
            .values(
                topic=topic,
                payload=payload,
                dedupe_key=dedupe_key,
                available_at=self._clock.now() + (delay or timedelta()),
            )
            .on_conflict_do_nothing(
                index_elements=["dedupe_key"], index_where=text("dedupe_key IS NOT NULL")
            )
            .returning(OutboxMessage.id)
        )
        return (await session.execute(stmt)).scalar_one_or_none() is not None


class OutboxRelay:
    """Claims due messages one per transaction with `FOR UPDATE SKIP LOCKED`,
    so any number of relays can run in parallel without double delivery.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        handlers: Mapping[str, Handler],
        *,
        clock: Clock,
        batch_size: int = 50,
        max_attempts: int = 10,
        base_backoff_s: float = 5,
        max_backoff_s: float = 3_600,
        handler_timeout_s: float = 30,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._sessions = session_factory
        self._handlers = handlers
        self._clock = clock
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._base_backoff_s = base_backoff_s
        self._max_backoff_s = max_backoff_s
        self._handler_timeout_s = handler_timeout_s
        self._jitter = jitter

    async def run_batch(self) -> int:
        """Deliver up to `batch_size` due messages. Returns how many were attempted."""
        processed = 0
        while processed < self._batch_size and await self._process_one():
            processed += 1
        return processed

    async def pending_count(self) -> int:
        async with self._sessions() as session:
            stmt = select(func.count()).where(OutboxMessage.status == PENDING)
            return int((await session.execute(stmt)).scalar_one())

    async def _process_one(self) -> bool:
        async with self._sessions() as session, session.begin():
            msg = await session.scalar(
                select(OutboxMessage)
                .where(
                    OutboxMessage.status == PENDING,
                    OutboxMessage.available_at <= self._clock.now(),
                )
                .order_by(OutboxMessage.available_at, OutboxMessage.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if msg is None:
                return False
            await self._deliver(msg)
            return True

    async def _deliver(self, msg: OutboxMessage) -> None:
        log = logger.bind(outbox_id=str(msg.id), topic=msg.topic, attempt=msg.attempts + 1)
        handler = self._handlers.get(msg.topic)
        if handler is None:
            msg.status, msg.last_error = DEAD, f"no handler for topic '{msg.topic}'"
            log.error("outbox_dead_letter", reason="no_handler")
            return

        msg.attempts += 1
        envelope = OutboxEnvelope(msg.id, msg.topic, msg.payload, msg.attempts)
        try:
            async with asyncio.timeout(self._handler_timeout_s):
                await handler(envelope)
        except Exception as exc:  # any handler failure → retry or dead-letter
            msg.last_error = _describe(exc)
            if msg.attempts >= self._max_attempts:
                msg.status = DEAD
                log.exception("outbox_dead_letter", reason="max_attempts", error=msg.last_error)
            else:
                msg.available_at = self._clock.now() + self._backoff(msg.attempts)
                log.warning("outbox_retry_scheduled", error=msg.last_error)
            return

        msg.status, msg.processed_at, msg.last_error = DONE, self._clock.now(), None
        log.info("outbox_delivered")

    def _backoff(self, attempts: int) -> timedelta:
        base = min(self._max_backoff_s, self._base_backoff_s * 2 ** (attempts - 1))
        # Jitter spreads retries so a recovered dependency isn't hit by everything at once.
        return timedelta(seconds=base * (1 + 0.2 * self._jitter()))


def _describe(exc: Exception) -> str:
    detail = str(exc)
    text_ = f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
    return str(scrub(text_))[:_MAX_ERROR_CHARS]
