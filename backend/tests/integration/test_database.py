import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from stylesense.infra.database import (
    UnitOfWork,
    create_engine,
    create_session_factory,
    pool_stats,
)
from stylesense.infra.health import PostgresHealthCheck
from stylesense.platform.config import Settings
from tests.factories import UNREACHABLE_DB, make_settings


@pytest.fixture
async def table(engine: AsyncEngine) -> str:
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS uow_probe"))
        await conn.execute(text("CREATE TABLE uow_probe (id int PRIMARY KEY)"))
    return "uow_probe"


async def _count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one())  # noqa: S608


async def test_unit_of_work_commits_on_success(engine: AsyncEngine, table: str) -> None:
    async with UnitOfWork(create_session_factory(engine)) as uow:
        await uow.session.execute(text(f"INSERT INTO {table} VALUES (1)"))  # noqa: S608

    assert await _count(engine, table) == 1


async def test_unit_of_work_rolls_back_on_error(engine: AsyncEngine, table: str) -> None:
    async def insert_then_fail() -> None:
        async with UnitOfWork(create_session_factory(engine)) as uow:
            await uow.session.execute(text(f"INSERT INTO {table} VALUES (1)"))  # noqa: S608
            raise RuntimeError

    with pytest.raises(RuntimeError):
        await insert_then_fail()

    assert await _count(engine, table) == 0


async def test_unit_of_work_session_unavailable_outside_context(engine: AsyncEngine) -> None:
    uow = UnitOfWork(create_session_factory(engine))

    with pytest.raises(RuntimeError, match="not active"):
        _ = uow.session


async def test_statement_timeout_is_enforced(settings: Settings) -> None:
    eng = create_engine(settings.model_copy(update={"db_statement_timeout_ms": 100}))
    try:
        async with eng.connect() as conn:
            with pytest.raises(DBAPIError, match="statement timeout"):
                await conn.execute(text("SELECT pg_sleep(1)"))
    finally:
        await eng.dispose()


async def test_session_uses_utc(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        assert (await conn.execute(text("SHOW timezone"))).scalar_one() == "UTC"


async def test_postgres_health_check_passes_when_up(engine: AsyncEngine) -> None:
    await PostgresHealthCheck(engine).check()


async def test_postgres_health_check_raises_when_down() -> None:
    eng = create_engine(make_settings(database_url=UNREACHABLE_DB, db_pool_timeout_s=0.5))
    try:
        with pytest.raises(OSError):  # noqa: PT011  # any connection failure is acceptable
            await PostgresHealthCheck(eng).check()
    finally:
        await eng.dispose()


async def test_pool_stats_reflect_checked_out_connections(engine: AsyncEngine) -> None:
    async with engine.connect():
        stats = pool_stats(engine)

    assert stats.size == 10
    assert stats.checked_out == 1
