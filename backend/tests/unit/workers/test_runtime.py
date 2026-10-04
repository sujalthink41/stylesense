import asyncio
from collections.abc import Awaitable, Callable

import pytest
from prometheus_client import CollectorRegistry

from stylesense.workers.runtime import PeriodicTask, Worker


class Probe:
    """Scripted task body: records runs, can fail, block, or report more work."""

    def __init__(
        self,
        *,
        more: list[bool] | None = None,
        fail: bool = False,
        delay: float = 0,
    ) -> None:
        self.runs = 0
        self._more = list(more or [])
        self._fail = fail
        self._delay = delay

    async def __call__(self) -> bool:
        self.runs += 1
        await asyncio.sleep(self._delay)
        if self._fail:
            raise RuntimeError("task broke")
        return self._more.pop(0) if self._more else False


async def _run_for(worker: Worker, seconds: float) -> None:
    stop = asyncio.Event()
    runner = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(seconds)
    stop.set()
    await runner


def _worker(*tasks: PeriodicTask, **kwargs: object) -> Worker:
    return Worker(list(tasks), locks=None, **kwargs)  # type: ignore[arg-type]


async def test_runs_task_periodically_until_stopped() -> None:
    probe = Probe()

    await _run_for(_worker(PeriodicTask("tick", 0.02, probe)), 0.11)

    assert 3 <= probe.runs <= 7


async def test_runs_again_immediately_while_there_is_more_work() -> None:
    probe = Probe(more=[True, True, True])

    await _run_for(_worker(PeriodicTask("drain", 60, probe)), 0.05)

    assert probe.runs == 4  # three "more" + one final; then waits the full interval


async def test_failing_task_does_not_kill_the_loop() -> None:
    probe = Probe(fail=True)
    stop = asyncio.Event()
    runner = asyncio.create_task(_worker(PeriodicTask("flaky", 0.01, probe)).run(stop))

    async with asyncio.timeout(5):
        while probe.runs < 2:  # noqa: ASYNC110  # polling a counter owned by the code under test
            await asyncio.sleep(0.01)
    stop.set()
    await runner


async def test_stop_lets_the_current_iteration_finish() -> None:
    probe = Probe(delay=0.05)
    stop = asyncio.Event()
    runner = asyncio.create_task(_worker(PeriodicTask("slow", 60, probe)).run(stop))
    await asyncio.sleep(0.01)

    stop.set()
    await runner

    assert probe.runs == 1


async def test_iteration_exceeding_grace_period_is_cancelled() -> None:
    probe = Probe(delay=10)
    stop = asyncio.Event()
    worker = _worker(PeriodicTask("stuck", 60, probe), shutdown_grace_s=0.05)
    runner = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(0.01)

    stop.set()
    await asyncio.wait_for(runner, timeout=1)


async def test_heartbeat_follows_successful_iterations() -> None:
    beats: list[int] = []
    probe = Probe()

    await _run_for(
        _worker(PeriodicTask("tick", 0.01, probe), heartbeat=lambda: beats.append(1)), 0.05
    )

    assert len(beats) == probe.runs


async def test_records_metrics_per_task_outcome() -> None:
    registry = CollectorRegistry()

    await _run_for(
        _worker(
            PeriodicTask("ok", 0.01, Probe()),
            PeriodicTask("bad", 0.01, Probe(fail=True)),
            registry=registry,
        ),
        0.05,
    )

    ok = registry.get_sample_value("worker_task_runs_total", {"task": "ok", "outcome": "ok"})
    bad = registry.get_sample_value("worker_task_runs_total", {"task": "bad", "outcome": "error"})
    assert ok is not None
    assert ok >= 1
    assert bad is not None
    assert bad >= 1


def test_exclusive_task_requires_locks() -> None:
    with pytest.raises(ValueError, match="locks"):
        Worker([PeriodicTask("cron", 1, Probe(), exclusive=True)], locks=None)


@pytest.mark.parametrize("interval", [0, -1])
def test_rejects_non_positive_interval(interval: float) -> None:
    run: Callable[[], Awaitable[bool]] = Probe()
    with pytest.raises(ValueError, match="interval"):
        PeriodicTask("x", interval, run)
