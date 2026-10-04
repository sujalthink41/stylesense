from types import TracebackType
from typing import Self

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import QueuePool

from stylesense.platform.config import Settings
from stylesense.platform.observability.metrics import PoolStats

# Deterministic constraint names keep Alembic autogenerate diffs stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Don't RETURNING server defaults after INSERT: it forces row-by-row inserts. Code that
    # needs a server default right after insert must `refresh()` explicitly.
    __mapper_args__ = {"eager_defaults": False}  # noqa: RUF012  # read by SQLAlchemy, never mutated


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        str(settings.database_url),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_s,
        pool_pre_ping=True,
        pool_recycle=1_800,
        connect_args={
            "timeout": settings.db_pool_timeout_s,
            "server_settings": {
                "application_name": settings.name,
                "statement_timeout": str(settings.db_statement_timeout_ms),
                "timezone": "UTC",
            },
        },
    )


def pool_stats(engine: AsyncEngine) -> PoolStats:
    pool = engine.pool
    if not isinstance(pool, QueuePool):  # e.g. NullPool in tools: nothing to report
        return PoolStats(size=0, checked_out=0, overflow=0)
    return PoolStats(
        size=pool.size(), checked_out=pool.checkedout(), overflow=max(pool.overflow(), 0)
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


class UnitOfWork:
    """One transaction per use case: commit on clean exit, roll back on any error."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active; use it as an async context manager")
        return self._session

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self.session
        try:
            if exc_type is None:
                await session.commit()
            else:
                await session.rollback()
        finally:
            await session.close()
            self._session = None
