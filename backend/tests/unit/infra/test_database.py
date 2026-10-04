from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from stylesense.infra.database import pool_stats


def test_pool_stats_are_zero_for_non_queue_pools() -> None:
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/x", poolclass=NullPool)

    stats = pool_stats(engine)

    assert (stats.size, stats.checked_out, stats.overflow) == (0, 0, 0)
