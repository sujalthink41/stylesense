import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from redis.asyncio import Redis
from sqlalchemy import text

from stylesense.bootstrap.container import Container, build_container
from stylesense.guards.locks import LockManager
from stylesense.infra.database import UnitOfWork
from stylesense.platform.config import Settings
from stylesense.workers.app import build_worker, default_handlers
from stylesense.workers.runtime import PeriodicTask, Worker


@pytest.fixture
async def container(settings: Settings, migrated: None, tmp_path: Path) -> AsyncIterator[Container]:
    c = build_container(
        settings.model_copy(
            update={"worker_heartbeat_file": str(tmp_path / "hb"), "outbox_poll_interval_s": 0.02}
        )
    )
    await c.redis.flushdb()
    async with c.engine.begin() as conn:
        await conn.execute(text("TRUNCATE outbox_messages"))
    yield c
    await c.aclose()


async def test_exclusive_task_never_overlaps_across_workers(redis: Redis) -> None:
    await redis.flushdb()
    running = 0
    peak = 0
    runs = 0

    async def job() -> bool:
        nonlocal running, peak, runs
        running += 1
        runs += 1
        peak = max(peak, running)
        await asyncio.sleep(0.03)
        running -= 1
        return False

    workers = [
        Worker([PeriodicTask("cron:feed", 0.01, job, exclusive=True)], locks=LockManager(redis))
        for _ in range(3)
    ]
    stop = asyncio.Event()
    runners = [asyncio.create_task(w.run(stop)) for w in workers]
    await asyncio.sleep(0.2)
    stop.set()
    await asyncio.gather(*runners)

    assert runs >= 2
    assert peak == 1


async def test_worker_drains_outbox_through_registered_handlers(container: Container) -> None:
    delivered: list[dict[str, object]] = []

    async def handler(envelope: object) -> None:
        delivered.append(envelope.payload)  # type: ignore[attr-defined]

    async with UnitOfWork(container.session_factory) as uow:
        for i in range(3):
            await container.outbox.add(uow.session, "test.topic", {"n": i})

    worker = build_worker(container, handlers={"test.topic": handler})
    stop = asyncio.Event()
    runner = asyncio.create_task(worker.run(stop))
    for _ in range(50):
        if len(delivered) == 3:
            break
        await asyncio.sleep(0.02)
    stop.set()
    await runner

    assert sorted(d["n"] for d in delivered) == [0, 1, 2]  # type: ignore[type-var]
    assert await asyncio.to_thread(Path(container.settings.worker_heartbeat_file).exists)


async def test_worker_registers_the_account_purge_handler(container: Container) -> None:
    handlers = default_handlers(container)

    assert "users.purge" in handlers
