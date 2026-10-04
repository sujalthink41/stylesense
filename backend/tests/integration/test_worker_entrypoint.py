import asyncio
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from stylesense.platform.config import Settings, get_settings
from stylesense.workers import healthcheck
from stylesense.workers.__main__ import main


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def worker_env(
    settings: Settings, migrated: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    heartbeat = tmp_path / "hb"
    for key, value in {
        "APP_ENV": "test",
        "APP_DATABASE_URL": str(settings.database_url),
        "APP_REDIS_URL": str(settings.redis_url),
        "APP_WORKER_HEARTBEAT_FILE": str(heartbeat),
        "APP_WORKER_METRICS_PORT": str(_free_port()),
        "APP_OUTBOX_POLL_INTERVAL_S": "0.05",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield heartbeat
    get_settings.cache_clear()


async def test_worker_process_starts_beats_and_stops_cleanly(worker_env: Path) -> None:
    stop = asyncio.Event()
    process = asyncio.create_task(main(stop))

    async with asyncio.timeout(10):
        while not await asyncio.to_thread(worker_env.exists):  # noqa: ASYNC110
            await asyncio.sleep(0.05)
    assert healthcheck.main() == 0

    stop.set()
    await asyncio.wait_for(process, timeout=10)


def test_healthcheck_fails_without_heartbeat(worker_env: Path) -> None:
    assert healthcheck.main() == 1
